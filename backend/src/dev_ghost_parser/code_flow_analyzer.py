"""
Code_Flow_Analyzer — directory traversal, architectural classification, and node generation.

Task 4.1: implements recursive directory scanning and Node production.
  - os.walk traversal of the target directory
  - Architectural classification by filename/class-name patterns
  - Stable Node.id via SHA-1 of the relative path
  - Node.label from primary class name (tree-sitter) or filename stem

Task 4.3: implements import/dependency extraction with tree-sitter.
  - For each recognized file, extract import/require/use statements from AST
  - Resolve imports to files within the codebase
  - Generate Edge objects with appropriate relation types
  - Non-parseable files are recorded in errors (non-fatal) and processing continues

Task 4.4: implements referential integrity filter for edges.
  - Builds the set of all generated node IDs
  - Removes any edge whose source or target is not in that set
  - Returns CodeFlowResult with nodes, filtered edges, and errors
  - Raises AnalysisFatalError if root_path is inaccessible

Satisfies Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6.
"""

from __future__ import annotations

import fnmatch
import hashlib
import importlib
import os
from typing import Callable, Optional

from tree_sitter import Language, Parser

from .models import AnalysisError, AnalysisFatalError, CodeFlowResult, Edge, Node, NodeType

# ---------------------------------------------------------------------------
# Supported file extensions and their tree-sitter grammar configurations
# ---------------------------------------------------------------------------

# Map: lowercase extension → (module_name, language_function_attr)
# Extensions with incompatible grammar versions gracefully fall back to
# filename-based labelling; the try/except in _build_parsers handles this.
_GRAMMAR_MAP: dict[str, tuple[str, str]] = {
    ".py":   ("tree_sitter_python",     "language"),
    ".js":   ("tree_sitter_javascript", "language"),
    ".ts":   ("tree_sitter_typescript", "language_typescript"),
    ".tsx":  ("tree_sitter_typescript", "language_tsx"),
    ".php":  ("tree_sitter_php",        "language_php"),
    ".rb":   ("tree_sitter_ruby",       "language"),
    ".go":   ("tree_sitter_go",         "language"),
    ".rs":   ("tree_sitter_rust",       "language"),
    ".java": ("tree_sitter_java",       "language"),
    ".cs":   ("tree_sitter_c_sharp",    "language"),
}

# Recognized source extensions (superset of _GRAMMAR_MAP keys, used for fast filtering)
_RECOGNIZED_EXTENSIONS: frozenset[str] = frozenset(_GRAMMAR_MAP.keys())

# ---------------------------------------------------------------------------
# Tree-sitter node-type → class/type name extraction helpers
# Each language uses a different AST node type and identifier child type.
# ---------------------------------------------------------------------------

# Mapping: language extension → list of (declaration_type, name_child_type)
# For each declaration type we look for a child of name_child_type to extract
# the primary entity name.
_CLASS_NODE_PATTERNS: dict[str, list[tuple[str, str]]] = {
    ".py":   [("class_definition",  "identifier")],
    ".js":   [("class_declaration", "identifier")],
    ".ts":   [("class_declaration", "type_identifier")],
    ".tsx":  [("class_declaration", "type_identifier")],
    ".php":  [("class_declaration", "name")],
    ".rb":   [("class",             "constant")],
    ".go":   [("type_spec",         "type_identifier")],
    ".rs":   [("struct_item",       "type_identifier"),
              ("impl_item",         "type_identifier")],
    ".java": [("class_declaration", "identifier")],
    ".cs":   [("class_declaration", "identifier")],
}


def _build_parsers() -> dict[str, Parser]:
    """Instantiate a tree-sitter Parser for each supported extension.

    Extensions whose grammar has an incompatible ABI version are silently
    skipped; those files will fall back to filename-based labelling.
    """
    parsers: dict[str, Parser] = {}
    for ext, (mod_name, fn_name) in _GRAMMAR_MAP.items():
        try:
            mod = importlib.import_module(mod_name)
            lang_fn: Callable = getattr(mod, fn_name)
            lang = Language(lang_fn())
            parsers[ext] = Parser(lang)
        except Exception:
            # Grammar unavailable or version mismatch — skip gracefully.
            pass
    return parsers


# Build parsers once at module load time (cheap; avoids repeated imports).
_PARSERS: dict[str, Parser] = _build_parsers()


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

_CLASSIFICATION_RULES: list[tuple[list[str], NodeType]] = [
    # patterns              category
    (["*Controller*", "*_controller*"],                "Controller"),
    (["*Endpoint*", "*_endpoint*", "*Resource*"],      "Controller"),
    (["*Service*",    "*_service*", "*Manager*", "*Handler*", "*Provider*"], "Service"),
    (["*Route*",      "router*", "routes*", "*_route*", "*_routes*", "*Config*", "*Configuration*"], "Route"),
    (["*Middleware*", "*_middleware*", "*Filter*", "*Interceptor*", "*Guard*"], "Middleware"),
    (["*Repository*", "*Repo*", "*_repository*", "*_repo*", "*Dao*", "*DAO*", "*Mapper*", "*Store*"], "Repository"),
]


def _classify(name: str) -> NodeType:
    """Return the architectural NodeType for *name* (filename stem or class name).

    Matching is case-sensitive fnmatch so ``UserController`` → ``Controller``
    and ``userController`` → ``Controller`` both match ``*Controller*``.
    """
    for patterns, category in _CLASSIFICATION_RULES:
        for pat in patterns:
            if fnmatch.fnmatch(name, pat):
                return category
    return "Utility"


def _classify_for_file(filename: str, class_name: Optional[str]) -> NodeType:
    """Classify using *class_name* if present, otherwise use *filename* stem."""
    stem = os.path.splitext(filename)[0]
    # Class name takes priority (it's more semantically accurate).
    if class_name:
        result = _classify(class_name)
        if result != "Utility":
            return result
        # If class name gave Utility, try the filename as a tiebreaker.
        return _classify(stem)
    return _classify(stem)


# ---------------------------------------------------------------------------
# Tree-sitter: primary class/entity name extraction
# ---------------------------------------------------------------------------

def _find_first_entity_name(node, patterns: list[tuple[str, str]]) -> Optional[str]:
    """Depth-first search for the first class/struct declaration matching *patterns*.

    Returns the text of the identifier child node, or None if not found.
    """
    for decl_type, id_type in patterns:
        if node.type == decl_type:
            for child in node.children:
                if child.type == id_type and child.text:
                    return child.text.decode("utf-8", errors="replace")
    for child in node.children:
        result = _find_first_entity_name(child, patterns)
        if result is not None:
            return result
    return None


def _extract_class_name(source_bytes: bytes, ext: str) -> Optional[str]:
    """Parse *source_bytes* with the appropriate tree-sitter grammar and return
    the name of the first class/struct/type declaration found, or None.

    Raises nothing — callers should wrap in try/except and treat failures as
    non-fatal per-file errors.
    """
    parser = _PARSERS.get(ext)
    if parser is None:
        return None

    patterns = _CLASS_NODE_PATTERNS.get(ext, [])
    if not patterns:
        return None

    tree = parser.parse(source_bytes)
    return _find_first_entity_name(tree.root_node, patterns)


# ---------------------------------------------------------------------------
# Import/dependency extraction (Task 4.3)
# ---------------------------------------------------------------------------

def _get_string_content(node) -> Optional[str]:
    """Extract the text content of a string literal node, stripping quotes."""
    if node is None or node.text is None:
        return None
    text = node.text.decode("utf-8", errors="replace")
    # Strip surrounding quotes (single, double, or backtick)
    if len(text) >= 2 and text[0] in ('"', "'", '`') and text[-1] == text[0]:
        return text[1:-1]
    return text


def _find_nodes_by_type(root, node_type: str) -> list:
    """Recursively find all AST nodes of *node_type*."""
    results: list = []
    if root.type == node_type:
        results.append(root)
    for child in root.children:
        results.extend(_find_nodes_by_type(child, node_type))
    return results


def _find_nodes_by_types(root, node_types: set[str]) -> list:
    """Recursively find all AST nodes whose type is in *node_types*."""
    results: list = []
    if root.type in node_types:
        results.append(root)
    for child in root.children:
        results.extend(_find_nodes_by_types(child, node_types))
    return results


def _extract_python_imports(root) -> list[tuple[str, str]]:
    """Extract imports from Python AST.

    Returns list of (import_path, relation) tuples.
    - import_statement: `import foo.bar` → "foo.bar"
    - import_from_statement: `from foo.bar import Baz` → "foo.bar"
    """
    results: list[tuple[str, str]] = []
    nodes = _find_nodes_by_types(root, {"import_statement", "import_from_statement"})
    for node in nodes:
        if node.type == "import_from_statement":
            # `from X import Y` — extract the module name (X)
            module_node = node.child_by_field_name("module_name")
            if module_node and module_node.text:
                mod_path = module_node.text.decode("utf-8", errors="replace")
                results.append((mod_path, "imports"))
        elif node.type == "import_statement":
            # `import X` — extract dotted name
            for child in node.children:
                if child.type == "dotted_name" and child.text:
                    mod_path = child.text.decode("utf-8", errors="replace")
                    results.append((mod_path, "imports"))
    return results


def _extract_js_ts_imports(root) -> list[tuple[str, str]]:
    """Extract imports from JavaScript/TypeScript AST.

    Returns list of (import_path, relation) tuples.
    - import_statement: `import X from 'path'` → "path", relation "imports"
    - call_expression with `require('path')` → "path", relation "calls"
    """
    results: list[tuple[str, str]] = []

    # Static imports: import_statement with a source string
    import_nodes = _find_nodes_by_type(root, "import_statement")
    for node in import_nodes:
        source_node = node.child_by_field_name("source")
        if source_node and source_node.type == "string":
            path = _get_string_content(source_node)
            if path:
                results.append((path, "imports"))

    # Dynamic requires: require('path')
    call_nodes = _find_nodes_by_type(root, "call_expression")
    for node in call_nodes:
        fn_node = node.child_by_field_name("function")
        if fn_node and fn_node.type == "identifier" and fn_node.text == b"require":
            args_node = node.child_by_field_name("arguments")
            if args_node:
                for arg in args_node.children:
                    if arg.type == "string":
                        path = _get_string_content(arg)
                        if path:
                            results.append((path, "calls"))
    return results


def _extract_php_imports(root) -> list[tuple[str, str]]:
    """Extract imports from PHP AST.

    Returns list of (import_path, relation) tuples.
    - namespace_use_declaration: `use App\\Services\\Foo` → "App/Services/Foo"
    - require_expression / include_expression: `require 'path'` → "path"
    """
    results: list[tuple[str, str]] = []

    # use declarations
    use_nodes = _find_nodes_by_type(root, "namespace_use_declaration")
    for node in use_nodes:
        # Extract the qualified name
        for child in node.children:
            if child.type == "namespace_use_clause":
                for sub in child.children:
                    if sub.type == "qualified_name" and sub.text:
                        ns_path = sub.text.decode("utf-8", errors="replace")
                        # Convert namespace separators to path separators
                        ns_path = ns_path.replace("\\", "/")
                        results.append((ns_path, "depends_on"))
            elif child.type == "qualified_name" and child.text:
                ns_path = child.text.decode("utf-8", errors="replace")
                ns_path = ns_path.replace("\\", "/")
                results.append((ns_path, "depends_on"))

    # require/include expressions
    req_nodes = _find_nodes_by_types(root, {
        "require_expression", "include_expression",
        "require_once_expression", "include_once_expression",
    })
    for node in req_nodes:
        for child in node.children:
            if child.type in ("string", "encapsed_string"):
                path = _get_string_content(child)
                if path:
                    results.append((path, "depends_on"))
    return results


def _extract_go_imports(root) -> list[tuple[str, str]]:
    """Extract imports from Go AST.

    Returns list of (import_path, relation) tuples.
    - import_declaration → extract interpreted_string_literal children
    """
    results: list[tuple[str, str]] = []
    import_nodes = _find_nodes_by_type(root, "import_declaration")
    for node in import_nodes:
        # Find all string literals within the import declaration
        strings = _find_nodes_by_types(node, {"interpreted_string_literal", "raw_string_literal"})
        for s in strings:
            path = _get_string_content(s)
            if path:
                results.append((path, "imports"))
    return results


def _extract_java_imports(root) -> list[tuple[str, str]]:
    """Extract imports from Java AST.

    Returns list of (import_path, relation) tuples.
    - import_declaration → qualified name like `com.example.service.OrderService`
    """
    results: list[tuple[str, str]] = []
    import_nodes = _find_nodes_by_type(root, "import_declaration")
    for node in import_nodes:
        # The scoped_identifier or identifier child contains the full import path
        for child in node.children:
            if child.type in ("scoped_identifier", "identifier") and child.text:
                import_path = child.text.decode("utf-8", errors="replace")
                results.append((import_path, "imports"))
                break
    return results


def _extract_ruby_imports(root) -> list[tuple[str, str]]:
    """Extract imports from Ruby AST.

    Returns list of (import_path, relation) tuples.
    - call nodes with method_name `require` or `require_relative`
    """
    results: list[tuple[str, str]] = []
    call_nodes = _find_nodes_by_type(root, "call")
    for node in call_nodes:
        method_node = node.child_by_field_name("method")
        if method_node and method_node.text in (b"require", b"require_relative"):
            args_node = node.child_by_field_name("arguments")
            if args_node:
                for arg in args_node.children:
                    if arg.type == "string" and arg.text:
                        path = _get_string_content(arg)
                        if path:
                            results.append((path, "imports"))
            # Also check for direct argument (no parentheses)
            for child in node.children:
                if child.type == "argument_list":
                    for arg in child.children:
                        if arg.type == "string" and arg.text:
                            path = _get_string_content(arg)
                            if path:
                                results.append((path, "imports"))
    return results


def _extract_rust_imports(root) -> list[tuple[str, str]]:
    """Extract imports from Rust AST.

    Returns list of (import_path, relation) tuples.
    - use_declaration → path like `crate::services::order_service`
    """
    results: list[tuple[str, str]] = []
    use_nodes = _find_nodes_by_type(root, "use_declaration")
    for node in use_nodes:
        # Extract the scoped identifier / path
        for child in node.children:
            if child.type in ("scoped_identifier", "use_wildcard", "scoped_use_list", "identifier") and child.text:
                use_path = child.text.decode("utf-8", errors="replace")
                results.append((use_path, "imports"))
                break
    return results


def _extract_csharp_imports(root) -> list[tuple[str, str]]:
    """Extract imports from C# AST.

    Returns list of (import_path, relation) tuples.
    - using_directive → namespace like `System.Collections.Generic`
    """
    results: list[tuple[str, str]] = []
    using_nodes = _find_nodes_by_type(root, "using_directive")
    for node in using_nodes:
        # Look for qualified_name or identifier child
        for child in node.children:
            if child.type in ("qualified_name", "identifier", "name") and child.text:
                ns_path = child.text.decode("utf-8", errors="replace")
                results.append((ns_path, "imports"))
                break
    return results


# Dispatcher: extension → extraction function
_IMPORT_EXTRACTORS: dict[str, Callable] = {
    ".py":   _extract_python_imports,
    ".js":   _extract_js_ts_imports,
    ".ts":   _extract_js_ts_imports,
    ".tsx":  _extract_js_ts_imports,
    ".php":  _extract_php_imports,
    ".go":   _extract_go_imports,
    ".java": _extract_java_imports,
    ".rb":   _extract_ruby_imports,
    ".rs":   _extract_rust_imports,
    ".cs":   _extract_csharp_imports,
}


def _extract_imports(source_bytes: bytes, ext: str) -> list[tuple[str, str]]:
    """Parse *source_bytes* with tree-sitter and extract import paths.

    Returns a list of (raw_import_path, relation) tuples where relation is
    one of "imports", "calls", or "depends_on".

    Falls back to regex-based extraction if tree-sitter parsing fails.
    Returns an empty list if the extension is not supported.
    """
    parser = _PARSERS.get(ext)
    extractor = _IMPORT_EXTRACTORS.get(ext)

    # Try tree-sitter first
    if parser is not None and extractor is not None:
        try:
            tree = parser.parse(source_bytes)
            results = extractor(tree.root_node)
            if results:
                return results
        except Exception:
            pass

    # Fallback: regex-based import extraction
    return _extract_imports_regex(source_bytes, ext)


# Regex patterns for import extraction (fallback when tree-sitter fails)
import re as _re

_IMPORT_PATTERNS: dict[str, list[tuple[_re.Pattern, str]]] = {
    ".java": [
        (_re.compile(rb"^\s*import\s+(?:static\s+)?([a-zA-Z0-9_.]+)\s*;", _re.MULTILINE), "imports"),
    ],
    ".py": [
        (_re.compile(rb"^\s*from\s+([a-zA-Z0-9_.]+)\s+import", _re.MULTILINE), "imports"),
        (_re.compile(rb"^\s*import\s+([a-zA-Z0-9_.]+)", _re.MULTILINE), "imports"),
    ],
    ".js": [
        (_re.compile(rb"""^\s*import\s+.*?from\s+['"](.*?)['"]""", _re.MULTILINE), "imports"),
        (_re.compile(rb"""require\(\s*['"](.*?)['"]\s*\)""", _re.MULTILINE), "calls"),
    ],
    ".ts": [
        (_re.compile(rb"""^\s*import\s+.*?from\s+['"](.*?)['"]""", _re.MULTILINE), "imports"),
    ],
    ".tsx": [
        (_re.compile(rb"""^\s*import\s+.*?from\s+['"](.*?)['"]""", _re.MULTILINE), "imports"),
    ],
    ".php": [
        (_re.compile(rb"^\s*use\s+([a-zA-Z0-9_\\]+)\s*;", _re.MULTILINE), "depends_on"),
        (_re.compile(rb"""(?:require|include)(?:_once)?\s*\(\s*['"](.*?)['"]\s*\)""", _re.MULTILINE), "depends_on"),
    ],
    ".go": [
        (_re.compile(rb'"([^"]+)"', _re.MULTILINE), "imports"),
    ],
    ".rb": [
        (_re.compile(rb"""^\s*require(?:_relative)?\s+['"](.*?)['"]""", _re.MULTILINE), "imports"),
    ],
    ".rs": [
        (_re.compile(rb"^\s*use\s+([a-zA-Z0-9_:]+)", _re.MULTILINE), "imports"),
    ],
    ".cs": [
        (_re.compile(rb"^\s*using\s+([a-zA-Z0-9_.]+)\s*;", _re.MULTILINE), "imports"),
    ],
}


def _extract_imports_regex(source_bytes: bytes, ext: str) -> list[tuple[str, str]]:
    """Regex-based fallback for import extraction when tree-sitter is unavailable."""
    patterns = _IMPORT_PATTERNS.get(ext, [])
    results: list[tuple[str, str]] = []

    for pattern, relation in patterns:
        for match in pattern.finditer(source_bytes):
            raw_path = match.group(1).decode("utf-8", errors="replace")
            if raw_path:
                results.append((raw_path, relation))

    return results


# ---------------------------------------------------------------------------
# Import resolution (Task 4.3)
# ---------------------------------------------------------------------------

def _normalize_import_path(raw_path: str) -> str:
    """Normalize an import path for resolution.

    Strips leading `./`, `../`, converts dots to slashes (for Python/Java),
    converts `::` to `/` (Rust), and strips file extensions.
    """
    path = raw_path.strip()
    # Strip leading ./
    while path.startswith("./"):
        path = path[2:]
    # Strip leading ../
    while path.startswith("../"):
        path = path[3:]
    # Convert namespace separators to path separators
    path = path.replace("::", "/")
    path = path.replace("\\", "/")
    # Strip known extensions BEFORE converting dots to slashes
    for ext in (".py", ".js", ".ts", ".tsx", ".php", ".rb", ".go", ".rs", ".java", ".cs"):
        if path.endswith(ext):
            path = path[: -len(ext)]
            break
    # Convert remaining dots to slashes (for Python module paths, Java packages)
    path = path.replace(".", "/")
    return path


def _build_resolution_maps(
    nodes: list[Node], rel_paths: list[str]
) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
    """Build lookup maps for resolving imports to node IDs.

    Returns:
      - path_no_ext_to_id: maps "services/OrderService" → node_id
      - stem_to_id: maps "OrderService" → node_id (last wins if duplicates)
      - full_rel_path_to_id: maps "services/OrderService.ts" → node_id
      - label_to_id: maps node label (class name) → node_id
    """
    path_no_ext_to_id: dict[str, str] = {}
    stem_to_id: dict[str, str] = {}
    full_rel_path_to_id: dict[str, str] = {}
    label_to_id: dict[str, str] = {}

    for node, rel_path in zip(nodes, rel_paths):
        # Normalize path separators to forward slashes for comparison
        normalized = rel_path.replace("\\", "/")
        full_rel_path_to_id[normalized] = node.id

        # Strip extension
        base, _ext = os.path.splitext(normalized)
        path_no_ext_to_id[base] = node.id

        # Stem (filename without extension)
        stem = os.path.basename(base)
        stem_to_id[stem] = node.id

        # Label (class name or filename) for direct matching
        label_to_id[node.label] = node.id

    return path_no_ext_to_id, stem_to_id, full_rel_path_to_id, label_to_id


def _resolve_import(
    raw_import: str,
    current_rel_path: str,
    path_no_ext_to_id: dict[str, str],
    stem_to_id: dict[str, str],
    full_rel_path_to_id: dict[str, str],
    label_to_id: dict[str, str],
) -> Optional[str]:
    """Try to resolve a raw import string to a node ID.

    Resolution strategy (from most to least specific):
    1. Try as a relative path from current file's directory
    2. Try normalized path against path_no_ext_to_id
    3. Try the last segment (stem) against stem_to_id
    4. Try the last segment against label_to_id (class names)

    Returns the node_id if resolved, None otherwise.
    """
    # Normalize the current file's directory
    current_dir = os.path.dirname(current_rel_path.replace("\\", "/"))

    # If it's a relative path (starts with . or ..)
    if raw_import.startswith("./") or raw_import.startswith("../"):
        # Resolve relative to current file
        resolved = os.path.normpath(os.path.join(current_dir, raw_import))
        resolved = resolved.replace("\\", "/")
        # Try with and without extension
        if resolved in full_rel_path_to_id:
            return full_rel_path_to_id[resolved]
        # Strip extension from resolved and check
        base, _ = os.path.splitext(resolved)
        if base in path_no_ext_to_id:
            return path_no_ext_to_id[base]
        # Try common extensions
        for ext in (".ts", ".js", ".tsx", ".py", ".php", ".rb", ".go", ".rs", ".java", ".cs"):
            candidate = resolved + ext
            if candidate in full_rel_path_to_id:
                return full_rel_path_to_id[candidate]

    # Normalize the import path (convert dots/colons to slashes, strip ext)
    normalized = _normalize_import_path(raw_import)

    # Try as full path without extension
    if normalized in path_no_ext_to_id:
        return path_no_ext_to_id[normalized]

    # Try the last segment as a stem (filename without extension)
    stem = normalized.rsplit("/", 1)[-1] if "/" in normalized else normalized
    if stem in stem_to_id:
        return stem_to_id[stem]

    # Try the last segment against node labels (class names)
    if stem in label_to_id:
        return label_to_id[stem]

    return None


# ---------------------------------------------------------------------------
# Node ID generation
# ---------------------------------------------------------------------------

def _make_node_id(relative_path: str) -> str:
    """Return a stable SHA-1 hex digest of *relative_path* encoded as UTF-8."""
    return hashlib.sha1(relative_path.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Code_Flow_Analyzer
# ---------------------------------------------------------------------------

class Code_Flow_Analyzer:
    """Scans a codebase directory and produces architectural graph nodes and edges.

    Task 4.1: Directory traversal and node generation.
    Task 4.4: Referential integrity filter for edges.

    - Traverses the directory with os.walk.
    - Classifies each recognized source file into a NodeType.
    - Generates a stable Node.id and a Node.label.
    - Applies referential integrity filter: removes edges whose source or
      target does not reference an existing node ID.

    Satisfies Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6.
    """

    def analyze(self, root_path: str) -> CodeFlowResult:
        """Analyze *root_path* and return a :class:`CodeFlowResult`.

        Parameters
        ----------
        root_path:
            Absolute or relative filesystem path to the codebase root.

        Returns
        -------
        CodeFlowResult
            - ``nodes``: one Node per recognized source file.
            - ``edges``: dependency edges filtered to only reference existing
              nodes (referential integrity guaranteed).
            - ``errors``: per-file non-fatal errors (e.g. unreadable files,
              parse failures).

        Raises
        ------
        AnalysisFatalError
            If *root_path* does not exist or cannot be read.
        """
        # --- Validate root_path ------------------------------------------------
        # Order matches DevGhost_Parser validation sequence:
        # (1) not found → (2) permission denied → (3) not a directory.
        if not os.path.exists(root_path):
            raise AnalysisFatalError(
                f"Path '{root_path}' was not found."
            )
        # Check permissions before checking if it's a directory so that
        # permission errors take priority over "not a directory" errors.
        try:
            # Use os.stat() to check accessibility without triggering
            # NotADirectoryError on Windows when root_path is a file.
            os.stat(root_path)
        except PermissionError:
            raise AnalysisFatalError(
                f"Permission denied accessing '{root_path}'."
            )
        if not os.path.isdir(root_path):
            raise AnalysisFatalError(
                f"Path '{root_path}' is not a directory."
            )
        # Final read-access check on the directory itself.
        try:
            os.listdir(root_path)
        except PermissionError:
            raise AnalysisFatalError(
                f"Permission denied accessing '{root_path}'."
            )

        nodes: list[Node] = []
        edges: list[Edge] = []
        errors: list[AnalysisError] = []

        # Normalize root_path so relative paths are computed consistently.
        root_path = os.path.realpath(root_path)

        # Store file data during traversal for import extraction (Task 4.3)
        # Each entry: (rel_path, ext, source_bytes or None)
        file_data: list[tuple[str, str, Optional[bytes]]] = []

        for dirpath, _dirnames, filenames in os.walk(root_path):
            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()
                if ext not in _RECOGNIZED_EXTENSIONS:
                    continue

                abs_path = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(abs_path, root_path)

                # --- Attempt to read and parse the file -----------------------
                class_name: Optional[str] = None
                source_bytes: Optional[bytes] = None
                try:
                    with open(abs_path, "rb") as fh:
                        source_bytes = fh.read()
                    class_name = _extract_class_name(source_bytes, ext)
                except PermissionError as exc:
                    errors.append(AnalysisError(
                        path=rel_path,
                        reason=f"Permission denied reading file: {exc}",
                    ))
                    # Still produce a node using filename-based label.
                except OSError as exc:
                    errors.append(AnalysisError(
                        path=rel_path,
                        reason=f"OS error reading file: {exc}",
                    ))
                    # Still produce a node using filename-based label.
                except Exception as exc:
                    errors.append(AnalysisError(
                        path=rel_path,
                        reason=f"Parse error: {exc}",
                    ))
                    # Still produce a node using filename-based label.

                # --- Generate Node --------------------------------------------
                node_id = _make_node_id(rel_path)
                stem = os.path.splitext(filename)[0]
                label = class_name if class_name else stem
                node_type = _classify_for_file(filename, class_name)

                nodes.append(Node(id=node_id, label=label, type=node_type))
                file_data.append((rel_path, ext, source_bytes))

        # --- Import extraction and edge generation (Task 4.3) -----------------
        # Build resolution maps from all generated nodes
        rel_paths_list = [fd[0] for fd in file_data]
        path_no_ext_to_id, stem_to_id, full_rel_path_to_id, label_to_id = _build_resolution_maps(
            nodes, rel_paths_list
        )

        for (rel_path, ext, source_bytes), node in zip(file_data, nodes):
            if source_bytes is None:
                # File could not be read; skip import extraction
                continue

            raw_imports = _extract_imports(source_bytes, ext)
            if not raw_imports:
                continue

            for raw_import, relation in raw_imports:
                target_id = _resolve_import(
                    raw_import,
                    rel_path,
                    path_no_ext_to_id,
                    stem_to_id,
                    full_rel_path_to_id,
                    label_to_id,
                )
                if target_id is not None and target_id != node.id:
                    edges.append(Edge(
                        source=node.id,
                        target=target_id,
                        relation=relation,
                    ))

        # --- Referential integrity filter (Task 4.4) --------------------------
        # Remove any edge whose source or target does not reference an existing
        # node id.  This guarantees Property 1 (referential integrity): every
        # edge in the result connects two nodes that are also present in the
        # nodes list.  Edges referencing external libraries or files outside the
        # analysed tree are discarded here.
        # Satisfies Requirements 1.3, 1.4, 1.5, 1.6.
        node_ids: set[str] = {n.id for n in nodes}
        edges = [e for e in edges if e.source in node_ids and e.target in node_ids]

        return CodeFlowResult(nodes=nodes, edges=edges, errors=errors)
