# Feature: precision-analysis-enhancements, Property 6: Description From Methods Uses Purpose Map or Direct Listing
# Feature: precision-analysis-enhancements, Property 7: Description Invariant (Including Config)
# Feature: precision-analysis-enhancements, Property 8: Config Description Template
"""
Properties 6, 7 & 8: Description generation with methods, invariant with Config, and Config template.

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from dev_ghost_parser.description_generator import (
    Description_Generator,
    _METHOD_PURPOSE_MAP,
    _TYPE_PREFIXES,
)
from dev_ghost_parser.models import FileContext, Node, NodeType

# --- Constants ---

ALL_NODE_TYPES: list[NodeType] = [
    "Controller", "Service", "Route", "Middleware", "Repository", "Utility", "Config"
]

# Keywords from _METHOD_PURPOSE_MAP that we can use to construct matching method names
PURPOSE_MAP_KEYWORDS = list(_METHOD_PURPOSE_MAP.keys())

# Config domain keywords recognized by _config_description
CONFIG_DOMAIN_KEYWORDS = [
    "database", "redis", "auth", "mail", "email", "cache",
    "cors", "swagger", "logging", "queue", "session",
    "security", "aws", "firebase", "payment", "storage",
]

# --- Strategies ---

node_type_strategy = st.sampled_from(ALL_NODE_TYPES)

# Strategy for method names that WILL match the PURPOSE_MAP
matching_method_name_strategy = st.sampled_from(PURPOSE_MAP_KEYWORDS).map(
    lambda kw: kw + "_handler"  # e.g. "get_handler", "create_handler"
)

# Strategy for method names that will NOT match the PURPOSE_MAP
# Use random strings that don't contain any PURPOSE_MAP keyword
non_matching_method_name_strategy = st.from_regex(
    r"[a-z]{2}x[a-z]{2}q[a-z]{2}", fullmatch=True
)

# Strategy for general method names (mix of matching and non-matching)
general_method_name_strategy = st.one_of(
    matching_method_name_strategy,
    non_matching_method_name_strategy,
    st.text(alphabet=st.characters(whitelist_categories=("L", "N", "Pc")), min_size=1, max_size=50),
)

node_strategy = st.builds(
    Node,
    id=st.text(min_size=1, max_size=40),
    label=st.text(min_size=0, max_size=100),
    type=node_type_strategy,
    description=st.just(""),
    method_names=st.just([]),
)

file_context_with_matching_methods = st.builds(
    FileContext,
    imports=st.lists(st.text(min_size=0, max_size=80), max_size=5),
    class_name=st.one_of(st.none(), st.text(min_size=1, max_size=60)),
    method_names=st.lists(matching_method_name_strategy, min_size=1, max_size=10),
)

file_context_with_non_matching_methods = st.builds(
    FileContext,
    imports=st.just([]),  # Empty imports to avoid import-based description
    class_name=st.one_of(st.none(), st.text(min_size=1, max_size=60)),
    method_names=st.lists(non_matching_method_name_strategy, min_size=1, max_size=10),
)

file_context_general = st.builds(
    FileContext,
    imports=st.lists(st.text(min_size=0, max_size=80), max_size=15),
    class_name=st.one_of(st.none(), st.text(min_size=1, max_size=60)),
    method_names=st.lists(general_method_name_strategy, max_size=20),
)

optional_file_context_strategy = st.one_of(st.none(), file_context_general)


# ---------------------------------------------------------------------------
# Property 6: Description From Methods Uses Purpose Map or Direct Listing
# ---------------------------------------------------------------------------


@given(
    node=node_strategy,
    file_context=file_context_with_matching_methods,
)
@settings(max_examples=150)
def test_property_6a_description_from_methods_uses_purpose_map(node, file_context):
    """
    **Validates: Requirements 3.1, 3.5**

    For any Node with a FileContext containing method_names where at least one
    normalized name matches a keyword in METHOD_PURPOSE_MAP, the generated description
    SHALL contain the NodeType prefix followed by at least one (and at most 3) inferred
    purpose strings from the map.
    """
    generator = Description_Generator()
    result = generator.generate(node, file_context)

    # The description should contain the NodeType prefix
    prefix = _TYPE_PREFIXES.get(node.type, "Componente que gestiona")
    assert result.startswith(prefix), (
        f"Description should start with prefix '{prefix}' but got: {result!r}. "
        f"Node type: {node.type}, methods: {file_context.method_names}"
    )

    # Extract the purpose portion (after the prefix and space)
    purpose_portion = result[len(prefix):].strip()
    # Remove potential truncation suffix
    if purpose_portion.endswith("..."):
        purpose_portion = purpose_portion[:-3]

    # Check that the purpose portion contains at least one PURPOSE_MAP value
    all_purposes = list(_METHOD_PURPOSE_MAP.values())
    found_purposes = [p for p in all_purposes if p in purpose_portion]
    assert len(found_purposes) >= 1, (
        f"Description should contain at least one purpose from PURPOSE_MAP. "
        f"Got: {result!r}. Purpose portion: {purpose_portion!r}. "
        f"Methods: {file_context.method_names}"
    )

    # Count purposes (split by comma to check at most 3)
    # Purposes are separated by ", "
    purpose_items = [p.strip() for p in purpose_portion.split(",")]
    assert len(purpose_items) <= 3, (
        f"Description should have at most 3 purpose items but got {len(purpose_items)}. "
        f"Description: {result!r}"
    )


@given(
    node=node_strategy,
    file_context=file_context_with_non_matching_methods,
)
@settings(max_examples=150)
def test_property_6b_description_no_match_lists_methods_directly(node, file_context):
    """
    **Validates: Requirements 3.2**

    For any Node with method_names where NO name matches the PURPOSE_MAP,
    the description SHALL list up to 3 method names directly with the NodeType prefix.
    """
    # Ensure none of our method names match the PURPOSE_MAP when normalized
    generator = Description_Generator()

    # Verify our methods don't match (double-check the strategy)
    for method in file_context.method_names:
        normalized = Description_Generator._normalize_method_name(method)
        matches_any = any(kw in normalized for kw in _METHOD_PURPOSE_MAP)
        assume(not matches_any)

    result = generator.generate(node, file_context)

    # The description should contain the NodeType prefix
    prefix = _TYPE_PREFIXES.get(node.type, "Componente que gestiona")
    assert result.startswith(prefix), (
        f"Description should start with prefix '{prefix}' but got: {result!r}. "
        f"Node type: {node.type}, methods: {file_context.method_names}"
    )

    # Should list up to 3 method names directly
    # The format is: "prefix method1, method2 y method3"
    # Verify at least one method name appears in the description
    methods_limited = file_context.method_names[:3]
    # At least the first method should appear in the description
    assert methods_limited[0] in result, (
        f"First method '{methods_limited[0]}' should appear in description. "
        f"Got: {result!r}"
    )

    # If there are 2+ methods, "y" connector should be present
    if len(methods_limited) >= 2:
        assert " y " in result, (
            f"Description with {len(methods_limited)} methods should contain ' y ' connector. "
            f"Got: {result!r}"
        )


# ---------------------------------------------------------------------------
# Property 7: Description Invariant (Including Config)
# ---------------------------------------------------------------------------


@given(
    node=st.builds(
        Node,
        id=st.text(min_size=1, max_size=40),
        label=st.text(min_size=0, max_size=100),
        type=node_type_strategy,
        description=st.just(""),
        method_names=st.just([]),
    ),
    file_context=optional_file_context_strategy,
)
@settings(max_examples=200)
def test_property_7_description_invariant_including_config(node, file_context):
    """
    **Validates: Requirements 3.4, 3.6**

    For any valid Node (with any NodeType including "Config") and any FileContext
    (or None), the Description_Generator SHALL return a non-empty string of at most
    120 Unicode characters. If the generated text exceeds 120 characters, it SHALL
    be truncated to 117 characters followed by "...".
    """
    generator = Description_Generator()
    result = generator.generate(node, file_context)

    # Must be a non-empty string
    assert isinstance(result, str), (
        f"Expected str, got {type(result).__name__}"
    )
    assert len(result) > 0, (
        f"Description must be non-empty. "
        f"Node: id={node.id!r}, label={node.label!r}, type={node.type!r}. "
        f"FileContext: {file_context!r}"
    )

    # Must not exceed 120 Unicode characters
    assert len(result) <= 120, (
        f"Description length {len(result)} exceeds 120 characters. "
        f"Description: {result!r}. "
        f"Node: id={node.id!r}, label={node.label!r}, type={node.type!r}. "
        f"FileContext: {file_context!r}"
    )

    # If truncated, must end with "..." and be exactly 120 chars
    if result.endswith("..."):
        # If it ends with "..." it should be because truncation was applied
        # The total length should be exactly 120 when truncation occurs
        # (though it could also naturally end with "..." at <=120 chars)
        assert len(result) <= 120, (
            f"Truncated description should be at most 120 characters. "
            f"Got length: {len(result)}"
        )


@given(
    node=st.builds(
        Node,
        id=st.text(min_size=1, max_size=40),
        label=st.text(min_size=0, max_size=100),
        type=node_type_strategy,
        description=st.just(""),
        method_names=st.just([]),
    ),
    file_context=st.builds(
        FileContext,
        imports=st.just([]),
        class_name=st.none(),
        # Generate many long method names to force truncation
        method_names=st.lists(
            st.text(
                alphabet=st.characters(whitelist_categories=("L",)),
                min_size=20,
                max_size=50,
            ),
            min_size=3,
            max_size=10,
        ),
    ),
)
@settings(max_examples=100)
def test_property_7b_truncation_format(node, file_context):
    """
    **Validates: Requirements 3.4**

    When the generated text exceeds 120 characters, it SHALL be truncated
    to 117 characters followed by "...".
    """
    generator = Description_Generator()
    result = generator.generate(node, file_context)

    # Must never exceed 120 chars
    assert len(result) <= 120, (
        f"Description length {len(result)} exceeds 120 characters. "
        f"Description: {result!r}"
    )

    # If truncation was applied (ends with "..."), verify format
    if result.endswith("..."):
        assert len(result) == 120, (
            f"Truncated description should be exactly 120 characters. "
            f"Got length: {len(result)}. Description: {result!r}"
        )


# ---------------------------------------------------------------------------
# Property 8: Config Description Template
# ---------------------------------------------------------------------------


@given(
    label=st.text(min_size=0, max_size=80),
)
@settings(max_examples=150)
def test_property_8a_config_description_starts_with_configuracion(label):
    """
    **Validates: Requirements 3.3**

    For any Node with type "Config" and a FileContext that is None or has empty
    method_names and empty imports, the Description_Generator SHALL return a
    description starting with "Configuración".
    """
    node = Node(id="test-id", label=label, type="Config", description="")
    generator = Description_Generator()

    # Test with None FileContext
    result_none = generator.generate(node, None)
    assert result_none.startswith("Configuración"), (
        f"Config node with None FileContext should produce description starting with "
        f"'Configuración'. Got: {result_none!r}. Label: {label!r}"
    )

    # Test with empty FileContext
    empty_context = FileContext(imports=[], class_name=None, method_names=[])
    result_empty = generator.generate(node, empty_context)
    assert result_empty.startswith("Configuración"), (
        f"Config node with empty FileContext should produce description starting with "
        f"'Configuración'. Got: {result_empty!r}. Label: {label!r}"
    )


@given(
    domain_keyword=st.sampled_from(CONFIG_DOMAIN_KEYWORDS),
    prefix=st.text(
        alphabet=st.characters(whitelist_categories=("L",)),
        min_size=0,
        max_size=10,
    ),
    suffix=st.text(
        alphabet=st.characters(whitelist_categories=("L",)),
        min_size=0,
        max_size=10,
    ),
)
@settings(max_examples=150)
def test_property_8b_config_description_includes_domain_context(
    domain_keyword, prefix, suffix
):
    """
    **Validates: Requirements 3.3**

    When the node label contains a recognizable domain substring (e.g., "database",
    "redis", "auth"), the description SHALL include that domain context.
    """
    # Construct a label that contains the domain keyword
    label = f"{prefix}{domain_keyword}{suffix}"
    node = Node(id="test-id", label=label, type="Config", description="")
    generator = Description_Generator()

    # With None FileContext
    result = generator.generate(node, None)
    assert result.startswith("Configuración"), (
        f"Config node should produce description starting with 'Configuración'. "
        f"Got: {result!r}. Label: {label!r}"
    )

    # The description should include "de" indicating domain context
    # Format: "Configuración de [dominio]"
    assert "Configuración de " in result, (
        f"Config node with domain keyword '{domain_keyword}' in label should produce "
        f"'Configuración de [domain]'. Got: {result!r}. Label: {label!r}"
    )

    # Also test with empty FileContext
    empty_context = FileContext(imports=[], class_name=None, method_names=[])
    result_empty = generator.generate(node, empty_context)
    assert "Configuración de " in result_empty, (
        f"Config node with domain keyword '{domain_keyword}' and empty FileContext "
        f"should produce 'Configuración de [domain]'. Got: {result_empty!r}. Label: {label!r}"
    )
