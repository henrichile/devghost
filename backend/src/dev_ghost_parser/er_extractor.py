"""
ER_Extractor — Entity-Relationship model extractor.

Scans a codebase directory for ORM models, migration files, and SQL scripts,
then extracts Entity and Relation objects describing the data model.

Current parsers implemented:
  - Task 5.1: Eloquent (Laravel PHP) via tree-sitter-php
  - Task 5.2: Prisma schema (regex-based parsing)
  - Task 5.3: SQLAlchemy (Python) via tree-sitter-python
  - Task 5.4: SQL migrations and raw SQL (regex-based)

Satisfies Requirements: 2.1, 2.2, 2.3
"""

from __future__ import annotations

import os
import re
from typing import Optional

import tree_sitter_php as tsphp
import tree_sitter_python as tspython
from tree_sitter import Language, Node as TSNode, Parser

from .models import AnalysisError, Attribute, Entity, ERResult, Relation


# ---------------------------------------------------------------------------
# tree-sitter language setup
# ---------------------------------------------------------------------------

_PHP_LANGUAGE = Language(tsphp.language_php())
_PYTHON_LANGUAGE = Language(tspython.language())


# ---------------------------------------------------------------------------
# Eloquent relationship method → ER relation type mapping
# ---------------------------------------------------------------------------

_ELOQUENT_RELATION_MAP: dict[str, str] = {
    "hasOne": "one-to-one",
    "hasMany": "one-to-many",
    "belongsTo": "one-to-many",
    "belongsToMany": "many-to-many",
    "hasManyThrough": "one-to-many",
    "hasOneThrough": "one-to-one",
}

# Methods that should be treated as "unknown"
_ELOQUENT_MORPH_METHODS = {
    "morphTo",
    "morphOne",
    "morphMany",
    "morphToMany",
    "morphedByMany",
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _to_snake_case(name: str) -> str:
    """Convert a PascalCase class name to snake_case for FK derivation."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _get_node_text(node: TSNode, source: bytes) -> str:
    """Extract the UTF-8 text of a tree-sitter node from source bytes."""
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _find_children_by_type(node: TSNode, type_name: str) -> list[TSNode]:
    """Recursively collect all descendant nodes of the given type."""
    results: list[TSNode] = []
    for child in node.children:
        if child.type == type_name:
            results.append(child)
        results.extend(_find_children_by_type(child, type_name))
    return results


def _find_first_child_by_type(node: TSNode, type_name: str) -> Optional[TSNode]:
    """Return the first direct child node with the given type, or None."""
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _find_direct_children_by_type(node: TSNode, type_name: str) -> list[TSNode]:
    """Return all direct children with the given type."""
    return [c for c in node.children if c.type == type_name]


# ---------------------------------------------------------------------------
# Eloquent parser
# ---------------------------------------------------------------------------

def _parse_eloquent_file(
    filepath: str,
) -> tuple[list[Entity], list[Relation], list[AnalysisError]]:
    """Parse a single PHP file and extract Eloquent Entity and Relation objects.

    Only processes files whose class hierarchy includes ``extends Model``
    (or a subclass of it by name convention).

    Parameters
    ----------
    filepath:
        Absolute path to the PHP file to parse.

    Returns
    -------
    tuple[list[Entity], list[Relation], list[AnalysisError]]
        Extracted entities, extracted relations, and any non-fatal errors
        encountered during parsing.
    """
    entities: list[Entity] = []
    relations: list[Relation] = []
    errors: list[AnalysisError] = []

    try:
        with open(filepath, "rb") as fh:
            source = fh.read()
    except OSError as exc:
        errors.append(AnalysisError(path=filepath, reason=str(exc)))
        return entities, relations, errors

    # Quick pre-check: only parse files that look like Eloquent models.
    # This avoids the overhead of full AST parsing on non-model files.
    if b"extends Model" not in source and b"extends Authenticatable" not in source:
        return entities, relations, errors

    try:
        parser = Parser(language=_PHP_LANGUAGE)
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as exc:  # noqa: BLE001
        errors.append(AnalysisError(path=filepath, reason=f"tree-sitter parse error: {exc}"))
        return entities, relations, errors

    # Locate all class declarations in the file.
    class_declarations = _find_children_by_type(root, "class_declaration")
    if not class_declarations:
        return entities, relations, errors

    for class_node in class_declarations:
        # ----------------------------------------------------------------
        # 1. Verify the class extends Model (or a known base model class)
        # ----------------------------------------------------------------
        base_clause = _find_first_child_by_type(class_node, "base_clause")
        if base_clause is None:
            continue

        base_name_node = None
        for child in base_clause.children:
            if child.type in ("name", "qualified_name", "named_type"):
                base_name_node = child
                break
            # Sometimes the name is nested inside a named_type
            if child.type == "named_type":
                inner = _find_first_child_by_type(child, "name")
                if inner:
                    base_name_node = inner
                    break

        if base_name_node is None:
            # Try any child that looks like an identifier
            for child in base_clause.children:
                if child.is_named and child.type not in ("extends",):
                    base_name_node = child
                    break

        if base_name_node is None:
            continue

        base_name = _get_node_text(base_name_node, source)

        # Accept common Eloquent base classes
        eloquent_bases = {
            "Model",
            "Authenticatable",
            "Pivot",
            "MorphPivot",
        }
        if base_name not in eloquent_bases:
            continue

        # ----------------------------------------------------------------
        # 2. Extract the class name
        # ----------------------------------------------------------------
        class_name_node = _find_first_child_by_type(class_node, "name")
        if class_name_node is None:
            continue
        class_name = _get_node_text(class_name_node, source)

        # ----------------------------------------------------------------
        # 3. Parse class body for properties and methods
        # ----------------------------------------------------------------
        declaration_list = _find_first_child_by_type(class_node, "declaration_list")
        if declaration_list is None:
            # Empty class — produce a minimal entity
            entities.append(Entity(name=class_name))
            continue

        attributes: list[Attribute] = []
        primary_key = "id"
        casts: dict[str, str] = {}

        # We'll collect raw relation method source texts for rawDeclaration
        model_relations: list[Relation] = []

        for member in declaration_list.children:
            # ---- Property declarations ($fillable, $casts, $primaryKey) ----
            if member.type == "property_declaration":
                prop_name, prop_value_node = _extract_property(member, source)

                if prop_name == "primaryKey" and prop_value_node is not None:
                    pk_value = _get_string_value(prop_value_node, source)
                    if pk_value:
                        primary_key = pk_value

                elif prop_name == "fillable" and prop_value_node is not None:
                    fillable_names = _extract_array_strings(prop_value_node, source)
                    for fname in fillable_names:
                        if fname:
                            attributes.append(Attribute(name=fname, type="string"))

                elif prop_name == "casts" and prop_value_node is not None:
                    casts = _extract_array_key_values(prop_value_node, source)

            # ---- Method declarations (relationship methods) ----
            elif member.type == "method_declaration":
                _extract_relation_from_method(
                    member, source, class_name, model_relations
                )

        # Apply $casts to update attribute types
        cast_type_map: dict[str, str] = {}
        for attr_name, cast_type in casts.items():
            # Normalize PHP cast types to simpler type names
            cast_type_map[attr_name] = _normalize_cast_type(cast_type)

        final_attributes: list[Attribute] = []
        for attr in attributes:
            resolved_type = cast_type_map.get(attr.name, attr.type)
            final_attributes.append(Attribute(name=attr.name, type=resolved_type))

        entity = Entity(
            name=class_name,
            attributes=final_attributes,
            primaryKey=primary_key,
        )
        entities.append(entity)
        relations.extend(model_relations)

    return entities, relations, errors


# ---------------------------------------------------------------------------
# Property extraction helpers
# ---------------------------------------------------------------------------

def _extract_property(
    prop_node: TSNode, source: bytes
) -> tuple[str, Optional[TSNode]]:
    """Return (property_name_without_dollar, value_node_or_None) for a property_declaration."""
    name = ""
    value_node: Optional[TSNode] = None

    for child in prop_node.children:
        if child.type == "property_element":
            # property_element contains: variable_name = default_value
            for subchild in child.children:
                if subchild.type == "variable_name":
                    raw = _get_node_text(subchild, source)
                    name = raw.lstrip("$")
                elif subchild.type in (
                    "array_creation_expression",
                    "string",
                    "encapsed_string",
                    "integer",
                ):
                    value_node = subchild
    return name, value_node


def _get_string_value(node: TSNode, source: bytes) -> str:
    """Extract the string content from a string/encapsed_string node."""
    text = _get_node_text(node, source)
    # Strip surrounding quotes
    if len(text) >= 2 and text[0] in ("'", '"') and text[-1] in ("'", '"'):
        return text[1:-1]
    return text


def _extract_array_strings(array_node: TSNode, source: bytes) -> list[str]:
    """Extract all string values from an array_creation_expression node."""
    results: list[str] = []
    # Traverse array_element_initializer children
    for child in array_node.children:
        if child.type == "array_element_initializer":
            for subchild in child.children:
                if subchild.type in ("string", "encapsed_string"):
                    val = _get_string_value(subchild, source)
                    results.append(val)
        elif child.type in ("string", "encapsed_string"):
            # Inline values without array_element_initializer wrapper
            results.append(_get_string_value(child, source))
    return results


def _extract_array_key_values(array_node: TSNode, source: bytes) -> dict[str, str]:
    """Extract key => value string pairs from an array_creation_expression node."""
    result: dict[str, str] = {}
    for child in array_node.children:
        if child.type == "array_element_initializer":
            children = [c for c in child.children if c.is_named]
            if len(children) >= 2:
                key = _get_string_value(children[0], source)
                val = _get_string_value(children[1], source)
                if key:
                    result[key] = val
    return result


def _normalize_cast_type(cast_type: str) -> str:
    """Map Laravel/PHP cast type strings to simple type names."""
    mapping = {
        "int": "integer",
        "integer": "integer",
        "real": "float",
        "float": "float",
        "double": "float",
        "decimal": "decimal",
        "string": "string",
        "bool": "boolean",
        "boolean": "boolean",
        "object": "object",
        "array": "array",
        "json": "json",
        "collection": "collection",
        "date": "date",
        "datetime": "datetime",
        "immutable_date": "date",
        "immutable_datetime": "datetime",
        "timestamp": "integer",
        "encrypted": "string",
    }
    return mapping.get(cast_type.lower(), cast_type)


# ---------------------------------------------------------------------------
# Relation extraction from method bodies
# ---------------------------------------------------------------------------

def _extract_relation_from_method(
    method_node: TSNode,
    source: bytes,
    model_name: str,
    relations: list[Relation],
) -> None:
    """Inspect a method body for Eloquent relationship calls and add to relations."""
    # Look for return statements containing method calls like $this->hasMany(...)
    return_stmts = _find_children_by_type(method_node, "return_statement")
    for ret in return_stmts:
        # Find member_call_expression: $this->hasMany(RelatedModel::class, ...)
        call_exprs = _find_children_by_type(ret, "member_call_expression")
        for call_expr in call_exprs:
            _process_relation_call(call_expr, source, model_name, relations, method_node)
            break  # Only process the outermost call per return


def _process_relation_call(
    call_expr: TSNode,
    source: bytes,
    model_name: str,
    relations: list[Relation],
    method_node: TSNode,
) -> None:
    """Extract relation info from a member_call_expression node."""
    # The member_call_expression structure:
    #   object -> name -> arguments
    # We need the method name (e.g., hasMany) and arguments

    method_name: Optional[str] = None
    args_node: Optional[TSNode] = None

    for child in call_expr.children:
        if child.type == "name":
            method_name = _get_node_text(child, source)
        elif child.type == "arguments":
            args_node = child

    if method_name is None:
        return

    all_relation_methods = set(_ELOQUENT_RELATION_MAP.keys()) | _ELOQUENT_MORPH_METHODS
    if method_name not in all_relation_methods:
        return

    # Extract arguments
    related_model: Optional[str] = None
    foreign_key: Optional[str] = None

    if args_node is not None:
        arg_nodes = [c for c in args_node.children if c.type == "argument"]
        if arg_nodes:
            # First argument: RelatedModel::class or 'RelatedModel'
            related_model = _extract_class_ref(arg_nodes[0], source)
        if len(arg_nodes) >= 2:
            # Second argument: foreign key (string)
            fk_node = arg_nodes[1]
            for subchild in fk_node.children:
                if subchild.type in ("string", "encapsed_string"):
                    foreign_key = _get_string_value(subchild, source)
                    break

    # Derive foreign key conventionally if not provided
    if foreign_key is None:
        if related_model:
            foreign_key = _to_snake_case(related_model) + "_id"
        else:
            foreign_key = _to_snake_case(model_name) + "_id"

    # Build the Relation
    if method_name in _ELOQUENT_MORPH_METHODS:
        # Raw declaration for unknown/morph types
        raw_decl = _get_node_text(method_node, source).strip()
        relations.append(
            Relation(
                from_entity=model_name,
                to_entity=related_model or "unknown",
                type="unknown",
                foreignKey=foreign_key,
                rawDeclaration=raw_decl,
            )
        )
    else:
        rel_type = _ELOQUENT_RELATION_MAP.get(method_name, "unknown")
        relations.append(
            Relation(
                from_entity=model_name,
                to_entity=related_model or "unknown",
                type=rel_type,  # type: ignore[arg-type]
                foreignKey=foreign_key,
            )
        )


def _extract_class_ref(arg_node: TSNode, source: bytes) -> Optional[str]:
    """Extract a class name from a ::class constant reference or string argument."""
    text = _get_node_text(arg_node, source).strip()

    # Pattern: SomeModel::class
    class_const_match = re.match(r"^\\?(\w+)::class$", text)
    if class_const_match:
        return class_const_match.group(1)

    # Pattern: 'SomeModel' or "SomeModel"
    if len(text) >= 2 and text[0] in ("'", '"') and text[-1] in ("'", '"'):
        return text[1:-1]

    # Pattern: bare identifier
    if re.match(r"^\w+$", text):
        return text

    return None


# ---------------------------------------------------------------------------
# SQLAlchemy parser (Task 5.3)
# ---------------------------------------------------------------------------

# Map SQLAlchemy column type names to simple type strings
_SQLALCHEMY_TYPE_MAP: dict[str, str] = {
    "Integer": "integer",
    "SmallInteger": "integer",
    "BigInteger": "integer",
    "String": "string",
    "Text": "string",
    "Unicode": "string",
    "UnicodeText": "string",
    "Boolean": "boolean",
    "DateTime": "datetime",
    "Date": "date",
    "Time": "time",
    "Float": "float",
    "Numeric": "float",
    "LargeBinary": "binary",
    "JSON": "json",
    "Enum": "string",
    "ARRAY": "array",
}


def _is_sqlalchemy_file(source: bytes) -> bool:
    """Quick heuristic check: does this Python file look like it contains SQLAlchemy models?"""
    return (
        b"declarative_base" in source
        or b"DeclarativeBase" in source
        or (b"Base" in source and b"Column" in source)
        or b"db.Model" in source
        or b"sqlalchemy" in source
    )


def _parse_sqlalchemy_file(
    filepath: str,
) -> tuple[list[Entity], list[Relation], list[AnalysisError]]:
    """Parse a single Python file and extract SQLAlchemy Entity and Relation objects.

    Only processes files that match the SQLAlchemy heuristic (contain declarative_base,
    Base with Column, db.Model, or sqlalchemy imports).

    Parameters
    ----------
    filepath:
        Absolute path to the Python file to parse.

    Returns
    -------
    tuple[list[Entity], list[Relation], list[AnalysisError]]
        Extracted entities, extracted relations, and any non-fatal errors.
    """
    entities: list[Entity] = []
    relations: list[Relation] = []
    errors: list[AnalysisError] = []

    try:
        with open(filepath, "rb") as fh:
            source = fh.read()
    except OSError as exc:
        errors.append(AnalysisError(path=filepath, reason=str(exc)))
        return entities, relations, errors

    # Quick pre-check: only parse files that look like SQLAlchemy models
    if not _is_sqlalchemy_file(source):
        return entities, relations, errors

    try:
        parser = Parser(language=_PYTHON_LANGUAGE)
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as exc:  # noqa: BLE001
        errors.append(AnalysisError(path=filepath, reason=f"tree-sitter parse error: {exc}"))
        return entities, relations, errors

    # Find class definitions in the file
    class_defs = _find_children_by_type(root, "class_definition")
    if not class_defs:
        return entities, relations, errors

    for class_node in class_defs:
        # Check if the class inherits from Base or db.Model
        if not _is_sqlalchemy_model_class(class_node, source):
            continue

        # Extract class name
        class_name_node = _find_first_child_by_type(class_node, "identifier")
        if class_name_node is None:
            continue
        class_name = _get_node_text(class_name_node, source)

        # Extract body
        body_node = _find_first_child_by_type(class_node, "block")
        if body_node is None:
            entities.append(Entity(name=class_name))
            continue

        # Look for __tablename__ override
        table_name = _extract_tablename(body_node, source)
        entity_name = table_name if table_name else class_name

        attributes: list[Attribute] = []
        primary_key = "id"
        foreign_keys: dict[str, str] = {}  # column_name -> "table.column"

        # Process assignments in the class body
        for child in body_node.children:
            if child.type == "expression_statement":
                # Look for assignments like: column_name = Column(...)
                assignment = _find_first_child_by_type(child, "assignment")
                if assignment is None:
                    continue

                col_name, col_info = _extract_column_assignment(assignment, source)
                if col_name and col_info:
                    col_type, is_pk, fk_ref = col_info
                    attributes.append(Attribute(name=col_name, type=col_type))
                    if is_pk:
                        primary_key = col_name
                    if fk_ref:
                        foreign_keys[col_name] = fk_ref

                # Also check for relationship(...) assignments
                rel_name, rel_info = _extract_relationship_assignment(assignment, source)
                if rel_name and rel_info:
                    target_model, rel_type, raw_decl = rel_info
                    # Derive foreignKey from foreign_keys dict or convention
                    fk = _derive_foreign_key(target_model, foreign_keys)
                    relations.append(
                        Relation(
                            from_entity=entity_name,
                            to_entity=target_model,
                            type=rel_type,
                            foreignKey=fk,
                            rawDeclaration=raw_decl if rel_type == "unknown" else None,
                        )
                    )

        entity = Entity(
            name=entity_name,
            attributes=attributes,
            primaryKey=primary_key,
        )
        entities.append(entity)

        # Generate relations from ForeignKey references that weren't already covered
        for col_name, fk_ref in foreign_keys.items():
            # fk_ref is like "users.id" or "table.column"
            parts = fk_ref.split(".")
            if len(parts) == 2:
                target_table = parts[0]
                # Check if we already have a relation to this target
                already_has = any(
                    r.from_entity == entity_name and r.foreignKey == col_name
                    for r in relations
                )
                if not already_has:
                    relations.append(
                        Relation(
                            from_entity=entity_name,
                            to_entity=target_table,
                            type="one-to-many",
                            foreignKey=col_name,
                        )
                    )

    return entities, relations, errors


def _is_sqlalchemy_model_class(class_node: TSNode, source: bytes) -> bool:
    """Check if a class_definition inherits from Base, db.Model, or DeclarativeBase."""
    # Look for argument_list (class inheritance)
    arg_list = _find_first_child_by_type(class_node, "argument_list")
    if arg_list is None:
        return False

    arg_text = _get_node_text(arg_list, source)
    # Check for common base classes
    base_patterns = ["Base", "db.Model", "DeclarativeBase"]
    for pattern in base_patterns:
        if pattern in arg_text:
            return True
    return False


def _extract_tablename(body_node: TSNode, source: bytes) -> Optional[str]:
    """Extract __tablename__ = '...' from a class body."""
    for child in body_node.children:
        if child.type == "expression_statement":
            assignment = _find_first_child_by_type(child, "assignment")
            if assignment is None:
                continue
            # Get left side
            left = _find_first_child_by_type(assignment, "identifier")
            if left is None:
                continue
            left_text = _get_node_text(left, source)
            if left_text == "__tablename__":
                # Get right side (string value)
                for ach in assignment.children:
                    if ach.type == "string":
                        val = _get_node_text(ach, source)
                        # Strip quotes
                        if len(val) >= 2 and val[0] in ("'", '"') and val[-1] in ("'", '"'):
                            return val[1:-1]
    return None


def _extract_column_assignment(
    assignment: TSNode, source: bytes
) -> tuple[Optional[str], Optional[tuple[str, bool, Optional[str]]]]:
    """Extract column info from an assignment like: name = Column(String, ...)

    Returns
    -------
    (column_name, (type_str, is_primary_key, foreign_key_ref)) or (None, None)
    """
    # Get left side (identifier = column name)
    children = list(assignment.children)
    if len(children) < 3:
        return None, None

    left_node = children[0]
    if left_node.type != "identifier":
        return None, None

    col_name = _get_node_text(left_node, source)

    # Skip dunder attributes
    if col_name.startswith("__") and col_name.endswith("__"):
        return None, None

    # Get right side - look for a call node with "Column" as function name
    right_node = children[-1]
    if right_node.type != "call":
        return None, None

    # Check if it's a Column(...) call
    func_node = _find_first_child_by_type(right_node, "identifier")
    attr_node = _find_first_child_by_type(right_node, "attribute")

    is_column_call = False
    if func_node and _get_node_text(func_node, source) == "Column":
        is_column_call = True
    elif attr_node:
        # Handle db.Column(...)
        attr_text = _get_node_text(attr_node, source)
        if attr_text.endswith("Column"):
            is_column_call = True

    if not is_column_call:
        return None, None

    # Parse Column arguments
    args_node = _find_first_child_by_type(right_node, "argument_list")
    if args_node is None:
        return col_name, ("string", False, None)

    col_type = "string"
    is_pk = False
    fk_ref: Optional[str] = None

    for arg_child in args_node.children:
        if arg_child.type == "keyword_argument":
            # Handle primary_key=True
            kw_parts = list(arg_child.children)
            if len(kw_parts) >= 3:
                kw_name = _get_node_text(kw_parts[0], source)
                kw_value = _get_node_text(kw_parts[-1], source)
                if kw_name == "primary_key" and kw_value in ("True", "true"):
                    is_pk = True
        elif arg_child.type == "call":
            # Handle ForeignKey("table.column")
            inner_func = _find_first_child_by_type(arg_child, "identifier")
            if inner_func and _get_node_text(inner_func, source) == "ForeignKey":
                inner_args = _find_first_child_by_type(arg_child, "argument_list")
                if inner_args:
                    for inner_arg in inner_args.children:
                        if inner_arg.type == "string":
                            fk_val = _get_node_text(inner_arg, source)
                            if len(fk_val) >= 2 and fk_val[0] in ("'", '"'):
                                fk_ref = fk_val[1:-1]
                            break
        elif arg_child.type == "identifier":
            # First positional identifier = type (e.g., Integer, String)
            type_name = _get_node_text(arg_child, source)
            if type_name in _SQLALCHEMY_TYPE_MAP:
                col_type = _SQLALCHEMY_TYPE_MAP[type_name]
        elif arg_child.type == "call":
            # Could be String(255) or similar
            inner_func = _find_first_child_by_type(arg_child, "identifier")
            if inner_func:
                type_name = _get_node_text(inner_func, source)
                if type_name in _SQLALCHEMY_TYPE_MAP:
                    col_type = _SQLALCHEMY_TYPE_MAP[type_name]
                elif type_name == "ForeignKey":
                    # Already handled above
                    pass

    return col_name, (col_type, is_pk, fk_ref)


def _extract_relationship_assignment(
    assignment: TSNode, source: bytes
) -> tuple[Optional[str], Optional[tuple[str, str, Optional[str]]]]:
    """Extract relationship info from: name = relationship("Model", ...)

    Returns
    -------
    (rel_attr_name, (target_model, relation_type, raw_declaration)) or (None, None)
    """
    children = list(assignment.children)
    if len(children) < 3:
        return None, None

    left_node = children[0]
    if left_node.type != "identifier":
        return None, None

    rel_attr_name = _get_node_text(left_node, source)

    # Get right side - look for a call node with "relationship" as function name
    right_node = children[-1]
    if right_node.type != "call":
        return None, None

    func_node = _find_first_child_by_type(right_node, "identifier")
    attr_node = _find_first_child_by_type(right_node, "attribute")

    is_rel_call = False
    if func_node and _get_node_text(func_node, source) == "relationship":
        is_rel_call = True
    elif attr_node:
        attr_text = _get_node_text(attr_node, source)
        if attr_text.endswith("relationship"):
            is_rel_call = True

    if not is_rel_call:
        return None, None

    # Parse relationship arguments
    args_node = _find_first_child_by_type(right_node, "argument_list")
    if args_node is None:
        return None, None

    target_model: Optional[str] = None
    uselist: Optional[bool] = None
    has_secondary = False
    raw_decl = _get_node_text(right_node, source)

    for arg_child in args_node.children:
        if arg_child.type == "string" and target_model is None:
            # First string argument = target model name
            val = _get_node_text(arg_child, source)
            if len(val) >= 2 and val[0] in ("'", '"'):
                target_model = val[1:-1]
        elif arg_child.type == "keyword_argument":
            kw_parts = list(arg_child.children)
            if len(kw_parts) >= 3:
                kw_name = _get_node_text(kw_parts[0], source)
                kw_value = _get_node_text(kw_parts[-1], source)
                if kw_name == "uselist":
                    uselist = kw_value in ("True", "true")
                elif kw_name == "secondary":
                    has_secondary = True

    if target_model is None:
        return None, None

    # Infer relation type
    if has_secondary:
        rel_type = "many-to-many"
    elif uselist is False:
        rel_type = "one-to-one"
    elif uselist is True or uselist is None:
        # Default: uselist=True means one-to-many
        rel_type = "one-to-many"
    else:
        rel_type = "unknown"

    return rel_attr_name, (target_model, rel_type, raw_decl)


def _derive_foreign_key(
    target_model: str, foreign_keys: dict[str, str]
) -> str:
    """Derive the foreign key column for a relationship target.

    First tries to find a matching FK in the current model's foreign_keys dict.
    Falls back to convention: snake_case(target) + '_id'.
    """
    # Check if there's a FK pointing to the target table
    target_lower = target_model.lower()
    for col_name, fk_ref in foreign_keys.items():
        parts = fk_ref.split(".")
        if len(parts) == 2:
            table = parts[0]
            if table.lower() == target_lower or table.lower() == target_lower + "s":
                return col_name

    # Convention-based fallback
    snake = _to_snake_case(target_model)
    return snake + "_id"


# ---------------------------------------------------------------------------
# SQL migration / raw SQL parser (Task 5.4)
# ---------------------------------------------------------------------------

# SQL type mapping
_SQL_TYPE_MAP: dict[str, str] = {
    "int": "integer",
    "integer": "integer",
    "bigint": "integer",
    "smallint": "integer",
    "tinyint": "integer",
    "varchar": "string",
    "text": "string",
    "char": "string",
    "nvarchar": "string",
    "nchar": "string",
    "ntext": "string",
    "boolean": "boolean",
    "bool": "boolean",
    "timestamp": "datetime",
    "datetime": "datetime",
    "date": "datetime",
    "time": "datetime",
    "float": "float",
    "double": "float",
    "decimal": "float",
    "numeric": "float",
    "real": "float",
}


def _normalize_sql_type(raw_type: str) -> str:
    """Normalize a SQL type string to a simplified type name.

    Uses _SQL_TYPE_MAP for known types. Unknown types are returned as
    the raw type string lowercased.
    """
    # Strip size/precision specifiers: VARCHAR(255) → VARCHAR
    base_type = re.sub(r"\(.*\)", "", raw_type).strip()
    lookup = base_type.lower()
    return _SQL_TYPE_MAP.get(lookup, lookup)


def _is_sql_file(filename: str) -> bool:
    """Check if a filename is a SQL file or migration file.

    Detects:
    - *.sql files
    - *.migration.* files (e.g., 001_create_users.migration.sql)
    """
    lower = filename.lower()
    if lower.endswith(".sql"):
        return True
    if ".migration." in lower:
        return True
    return False


def _parse_sql_file(
    filepath: str,
) -> tuple[list[Entity], list[Relation], list[AnalysisError]]:
    """Parse a SQL file and extract Entity and Relation objects.

    Detects:
    - CREATE TABLE statements → Entity with attributes
    - PRIMARY KEY constraints → Entity.primaryKey
    - FOREIGN KEY constraints (inline in CREATE TABLE or ALTER TABLE) → Relation
    - ALTER TABLE ... ADD FOREIGN KEY → Relation

    Parameters
    ----------
    filepath:
        Absolute path to the SQL file to parse.

    Returns
    -------
    tuple[list[Entity], list[Relation], list[AnalysisError]]
        Extracted entities, extracted relations, and any non-fatal errors.
    """
    entities: list[Entity] = []
    relations: list[Relation] = []
    errors: list[AnalysisError] = []

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            source = fh.read()
    except OSError as exc:
        errors.append(AnalysisError(path=filepath, reason=str(exc)))
        return entities, relations, errors

    if not source.strip():
        # Empty file — not an error, just nothing to parse
        return entities, relations, errors

    try:
        # Parse CREATE TABLE statements
        _parse_create_tables(source, entities, relations)

        # Parse ALTER TABLE ADD FOREIGN KEY statements
        _parse_alter_table_fk(source, relations)
    except Exception as exc:  # noqa: BLE001
        errors.append(AnalysisError(path=filepath, reason=f"SQL parse error: {exc}"))

    return entities, relations, errors


def _parse_create_tables(
    source: str,
    entities: list[Entity],
    relations: list[Relation],
) -> None:
    """Extract entities and inline foreign keys from CREATE TABLE statements."""
    # Find CREATE TABLE statements and extract their bodies using balanced parentheses
    create_table_header_re = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"(?:`?(\w+)`?\.)?`?(\w+)`?"
        r"\s*\(",
        re.IGNORECASE,
    )

    for match in create_table_header_re.finditer(source):
        _schema = match.group(1)  # Optional schema prefix (ignored)
        table_name = match.group(2)

        # Extract body between balanced parentheses
        body = _extract_balanced_parens(source, match.end() - 1)
        if body is None:
            continue

        attributes: list[Attribute] = []
        primary_key = "id"
        found_pk = False

        # Split body by top-level commas (not inside parentheses)
        column_defs = _split_column_defs(body)

        for col_def in column_defs:
            col_def_stripped = col_def.strip()
            if not col_def_stripped:
                continue

            upper = col_def_stripped.upper()

            # Check for PRIMARY KEY constraint (standalone)
            pk_match = re.match(
                r"PRIMARY\s+KEY\s*\(\s*`?(\w+)`?\s*\)",
                col_def_stripped,
                re.IGNORECASE,
            )
            if pk_match:
                primary_key = pk_match.group(1)
                found_pk = True
                continue

            # Check for FOREIGN KEY constraint (inline)
            fk_match = re.match(
                r"(?:CONSTRAINT\s+\w+\s+)?FOREIGN\s+KEY\s*\(\s*`?(\w+)`?\s*\)"
                r"\s+REFERENCES\s+`?(\w+)`?\s*\(\s*`?(\w+)`?\s*\)",
                col_def_stripped,
                re.IGNORECASE,
            )
            if fk_match:
                fk_col = fk_match.group(1)
                ref_table = fk_match.group(2)
                relations.append(
                    Relation(
                        from_entity=table_name,
                        to_entity=ref_table,
                        type="one-to-many",
                        foreignKey=fk_col,
                    )
                )
                continue

            # Check for UNIQUE, INDEX, KEY, CHECK constraints (skip)
            if upper.startswith(("UNIQUE", "INDEX", "KEY", "CHECK", "CONSTRAINT")):
                continue

            # Regular column definition: col_name TYPE [constraints...]
            col_match = re.match(
                r"`?(\w+)`?\s+(\w+(?:\([^)]*\))?)",
                col_def_stripped,
                re.IGNORECASE,
            )
            if col_match:
                col_name = col_match.group(1)
                col_type_raw = col_match.group(2)
                col_type = _normalize_sql_type(col_type_raw)
                attributes.append(Attribute(name=col_name, type=col_type))

                # Check if this column is marked as PRIMARY KEY inline
                if "PRIMARY KEY" in upper or "PRIMARY_KEY" in upper:
                    primary_key = col_name
                    found_pk = True

                # Check for inline REFERENCES (foreign key shorthand)
                ref_match = re.search(
                    r"REFERENCES\s+`?(\w+)`?\s*\(\s*`?(\w+)`?\s*\)",
                    col_def_stripped,
                    re.IGNORECASE,
                )
                if ref_match:
                    ref_table = ref_match.group(1)
                    relations.append(
                        Relation(
                            from_entity=table_name,
                            to_entity=ref_table,
                            type="one-to-many",
                            foreignKey=col_name,
                        )
                    )

        # If no explicit PK was found but we have an 'id' column, default to 'id'
        if not found_pk:
            id_col = next((a for a in attributes if a.name.lower() == "id"), None)
            if id_col:
                primary_key = id_col.name
            elif attributes:
                # Fallback: first column
                primary_key = attributes[0].name

        entities.append(
            Entity(
                name=table_name,
                attributes=attributes,
                primaryKey=primary_key,
            )
        )


def _parse_alter_table_fk(source: str, relations: list[Relation]) -> None:
    """Extract foreign key relations from ALTER TABLE ... ADD FOREIGN KEY statements."""
    alter_fk_re = re.compile(
        r"ALTER\s+TABLE\s+`?(\w+)`?"
        r"\s+ADD\s+(?:CONSTRAINT\s+\w+\s+)?FOREIGN\s+KEY\s*\(\s*`?(\w+)`?\s*\)"
        r"\s+REFERENCES\s+`?(\w+)`?\s*\(\s*`?(\w+)`?\s*\)",
        re.IGNORECASE | re.DOTALL,
    )

    for match in alter_fk_re.finditer(source):
        table_name = match.group(1)
        fk_col = match.group(2)
        ref_table = match.group(3)
        # _ref_col = match.group(4)  # Referenced column (not used in Relation)

        relations.append(
            Relation(
                from_entity=table_name,
                to_entity=ref_table,
                type="one-to-many",
                foreignKey=fk_col,
            )
        )


def _split_column_defs(body: str) -> list[str]:
    """Split a CREATE TABLE body by commas, respecting parenthesized expressions."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []

    for char in body:
        if char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)

    if current:
        parts.append("".join(current))

    return parts


def _extract_balanced_parens(source: str, start: int) -> Optional[str]:
    """Extract content between balanced parentheses starting at position start.

    Parameters
    ----------
    source:
        The full SQL source string.
    start:
        Position of the opening '(' character.

    Returns
    -------
    str or None
        The content between the outermost parentheses (excluding the parens themselves),
        or None if unbalanced.
    """
    if start >= len(source) or source[start] != "(":
        return None

    depth = 0
    i = start
    while i < len(source):
        if source[i] == "(":
            depth += 1
        elif source[i] == ")":
            depth -= 1
            if depth == 0:
                # Return content between outermost parens
                return source[start + 1:i]
        i += 1

    return None


# ---------------------------------------------------------------------------
# Prisma schema parser (Task 5.2)
# ---------------------------------------------------------------------------

# Prisma scalar types that should be treated as attributes (not relations)
_PRISMA_SCALAR_TYPES: set[str] = {
    "String",
    "Int",
    "Float",
    "Boolean",
    "DateTime",
    "Json",
    "Bytes",
    "Decimal",
    "BigInt",
}


def _is_prisma_file(filename: str) -> bool:
    """Check if a filename is a Prisma schema file."""
    lower = filename.lower()
    return lower == "schema.prisma" or lower.endswith(".prisma")


def _parse_prisma_file(
    filepath: str,
) -> tuple[list[Entity], list[Relation], list[AnalysisError]]:
    """Parse a Prisma schema file and extract Entity and Relation objects.

    Detects:
    - ``model ModelName { ... }`` blocks → Entity
    - Scalar fields → Attribute
    - Fields with @id decorator → primaryKey
    - Relation fields (type is a PascalCase non-scalar) → Relation
    - @relation(fields: [...], references: [...]) for foreign key extraction

    Parameters
    ----------
    filepath:
        Absolute path to the Prisma schema file to parse.

    Returns
    -------
    tuple[list[Entity], list[Relation], list[AnalysisError]]
        Extracted entities, extracted relations, and any non-fatal errors.
    """
    entities: list[Entity] = []
    relations: list[Relation] = []
    errors: list[AnalysisError] = []

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            source = fh.read()
    except OSError as exc:
        errors.append(AnalysisError(path=filepath, reason=str(exc)))
        return entities, relations, errors

    if not source.strip():
        return entities, relations, errors

    try:
        # Find all model blocks using regex
        model_blocks = _extract_prisma_model_blocks(source)

        for model_name, model_body in model_blocks:
            entity, model_relations = _parse_prisma_model(model_name, model_body)
            entities.append(entity)
            relations.extend(model_relations)
    except Exception as exc:  # noqa: BLE001
        errors.append(AnalysisError(path=filepath, reason=f"Prisma parse error: {exc}"))

    return entities, relations, errors


def _extract_prisma_model_blocks(source: str) -> list[tuple[str, str]]:
    """Extract all model { ... } blocks from a Prisma schema source.

    Returns a list of (model_name, body_content) tuples.
    The body_content is the text between the outermost braces.
    """
    results: list[tuple[str, str]] = []

    # Regex to find the start of a model block: model ModelName {
    model_start_re = re.compile(r"\bmodel\s+(\w+)\s*\{", re.MULTILINE)

    for match in model_start_re.finditer(source):
        model_name = match.group(1)
        # Find the matching closing brace using balanced braces
        brace_start = match.end() - 1  # position of the '{'
        body = _extract_balanced_braces(source, brace_start)
        if body is not None:
            results.append((model_name, body))

    return results


def _extract_balanced_braces(source: str, start: int) -> Optional[str]:
    """Extract content between balanced braces starting at position start.

    Parameters
    ----------
    source:
        The full source string.
    start:
        Position of the opening '{' character.

    Returns
    -------
    str or None
        The content between the outermost braces (excluding the braces themselves),
        or None if unbalanced.
    """
    if start >= len(source) or source[start] != "{":
        return None

    depth = 0
    i = start
    while i < len(source):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1:i]
        i += 1

    return None


def _parse_prisma_model(
    model_name: str, body: str
) -> tuple[Entity, list[Relation]]:
    """Parse a single Prisma model body and return an Entity and Relations.

    Parameters
    ----------
    model_name:
        The name of the model (e.g., "User").
    body:
        The text content between the model's braces.

    Returns
    -------
    tuple[Entity, list[Relation]]
        The Entity with its attributes and primary key, plus any Relations.
    """
    attributes: list[Attribute] = []
    relations: list[Relation] = []
    primary_key = "id"
    found_pk = False

    lines = body.split("\n")
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("@@"):
            continue

        field_info = _parse_prisma_field_line(stripped)
        if field_info is None:
            continue

        field_name, field_type, is_array, is_optional, decorators = field_info

        # Check for @id decorator → primary key
        if "@id" in decorators:
            primary_key = field_name
            found_pk = True

        # Determine if this is a scalar or relation field
        # Strip optional/array suffixes to get the base type
        base_type = field_type

        if base_type in _PRISMA_SCALAR_TYPES:
            # It's a scalar field → attribute
            attributes.append(Attribute(name=field_name, type=base_type))
        elif base_type.lower() in ("unsupported",):
            # Prisma Unsupported type → treat as attribute
            attributes.append(Attribute(name=field_name, type=base_type))
        elif re.match(r"^[A-Z]", base_type) and base_type not in _PRISMA_SCALAR_TYPES:
            # PascalCase non-scalar type → relation field
            # Determine relation type
            if is_array:
                rel_type: RelationType = "one-to-many"
            else:
                rel_type = "one-to-one"

            # Extract foreign key from @relation annotation if present
            foreign_key = _extract_prisma_relation_fk(decorators, field_name)

            relations.append(
                Relation(
                    from_entity=model_name,
                    to_entity=base_type,
                    type=rel_type,
                    foreignKey=foreign_key,
                )
            )
        else:
            # Unknown type (e.g., enum or lowercase custom type) → attribute
            attributes.append(Attribute(name=field_name, type=base_type))

    if not found_pk:
        # Check if there's an 'id' attribute
        id_attr = next((a for a in attributes if a.name == "id"), None)
        if id_attr:
            primary_key = "id"
        elif attributes:
            primary_key = attributes[0].name

    entity = Entity(name=model_name, attributes=attributes, primaryKey=primary_key)
    return entity, relations


def _parse_prisma_field_line(
    line: str,
) -> Optional[tuple[str, str, bool, bool, str]]:
    """Parse a single Prisma field line.

    Parameters
    ----------
    line:
        A stripped line from inside a model block.

    Returns
    -------
    tuple or None
        (field_name, base_type, is_array, is_optional, decorators_string)
        Returns None if the line is not a valid field definition.
    """
    # Match field pattern: fieldName Type?[] @decorators...
    # Field name starts with a letter or underscore, followed by word chars
    field_re = re.compile(
        r"^(\w+)\s+"            # field name
        r"(\w+)"                # base type
        r"(\[\])?"              # optional array suffix
        r"(\?)?"                # optional marker
        r"(.*?)$"               # rest of line (decorators)
    )

    match = field_re.match(line)
    if match is None:
        return None

    field_name = match.group(1)
    base_type = match.group(2)
    is_array = match.group(3) is not None
    is_optional = match.group(4) is not None
    rest = match.group(5).strip()

    # The rest of the line contains decorators/annotations
    return (field_name, base_type, is_array, is_optional, rest)


def _extract_prisma_relation_fk(decorators: str, field_name: str) -> str:
    """Extract the foreign key from @relation(fields: [...], references: [...]).

    If no @relation annotation is found or no fields are specified,
    falls back to using the field_name itself.

    Parameters
    ----------
    decorators:
        The decorator/annotation string from the field line.
    field_name:
        The field name to use as fallback for the foreign key.

    Returns
    -------
    str
        The foreign key column name.
    """
    # Match @relation(fields: [fieldName], references: [refField])
    relation_re = re.compile(
        r"@relation\s*\([^)]*fields\s*:\s*\[([^\]]+)\]",
        re.IGNORECASE,
    )
    match = relation_re.search(decorators)
    if match:
        # Extract the first field reference
        fields_str = match.group(1).strip()
        # May be comma-separated for composite keys, take the first
        first_field = fields_str.split(",")[0].strip()
        if first_field:
            return first_field

    return field_name


# ---------------------------------------------------------------------------
# ER_Extractor class
# ---------------------------------------------------------------------------


class ER_Extractor:
    """Extracts Entity-Relationship model from a codebase directory.

    Supports:
    - Task 5.1: Eloquent (Laravel PHP) via tree-sitter
    - Task 5.2: Prisma schema (regex-based parsing)
    - Task 5.3: SQLAlchemy (Python) via tree-sitter-python
    - Task 5.4: SQL migrations and raw SQL via regex

    Satisfies Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
    """

    def extract(self, root_path: str) -> ERResult:
        """Scan root_path recursively and extract ER model data.

        Parameters
        ----------
        root_path:
            Absolute path to the root directory of the target codebase.

        Returns
        -------
        ERResult
            Aggregated entities, relations, and non-fatal errors from all
            parsers. Empty arrays when no recognizable ORM/SQL files found.
        """
        entities: list[Entity] = []
        relations: list[Relation] = []
        errors: list[AnalysisError] = []

        seen_entity_names: set[str] = set()

        for dirpath, _dirnames, filenames in os.walk(root_path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)

                # Task 5.1: Eloquent PHP models
                if filename.endswith(".php"):
                    new_entities, new_relations, new_errors = _parse_eloquent_file(filepath)
                    # Deduplicate: keep the first entity encountered for each name (Req 2.5)
                    for entity in new_entities:
                        if entity.name not in seen_entity_names:
                            seen_entity_names.add(entity.name)
                            entities.append(entity)
                    relations.extend(new_relations)
                    errors.extend(new_errors)

                # Task 5.3: SQLAlchemy Python models
                if filename.endswith(".py"):
                    new_entities, new_relations, new_errors = _parse_sqlalchemy_file(filepath)
                    # Deduplicate: keep the first entity encountered for each name (Req 2.5)
                    for entity in new_entities:
                        if entity.name not in seen_entity_names:
                            seen_entity_names.add(entity.name)
                            entities.append(entity)
                    relations.extend(new_relations)
                    errors.extend(new_errors)

                # Task 5.2: Prisma schema files
                if _is_prisma_file(filename):
                    new_entities, new_relations, new_errors = _parse_prisma_file(filepath)
                    # Deduplicate: keep the first entity encountered for each name (Req 2.5)
                    for entity in new_entities:
                        if entity.name not in seen_entity_names:
                            seen_entity_names.add(entity.name)
                            entities.append(entity)
                    relations.extend(new_relations)
                    errors.extend(new_errors)

                # Task 5.4: SQL migrations and raw SQL files
                # Processed AFTER ORM files so deduplication naturally enforces
                # ORM > migration > SQL priority (Req 2.5)
                if _is_sql_file(filename):
                    new_entities, new_relations, new_errors = _parse_sql_file(filepath)
                    # Deduplicate: keep the first entity encountered for each name (Req 2.5)
                    for entity in new_entities:
                        if entity.name not in seen_entity_names:
                            seen_entity_names.add(entity.name)
                            entities.append(entity)
                    relations.extend(new_relations)
                    errors.extend(new_errors)

        return ERResult(entities=entities, relations=relations, errors=errors)
