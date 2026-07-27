# Feature: interactive-ux-enhancements, Property 1: Description generation invariant
"""
Property 1: Description generation invariant

Validates: Requirements 1.1, 1.2

For any valid Node (with any label, any NodeType, and any FileContext or None),
the Description_Generator SHALL return a non-empty string of at most 120 Unicode characters.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.description_generator import Description_Generator
from dev_ghost_parser.models import FileContext, Node

VALID_TYPES = ["Controller", "Service", "Route", "Middleware", "Repository", "Utility"]

# --- Strategies ---

node_strategy = st.builds(
    Node,
    id=st.text(min_size=1, max_size=40),
    label=st.text(min_size=0, max_size=100),
    type=st.sampled_from(VALID_TYPES),
    description=st.just(""),
)

file_context_strategy = st.builds(
    FileContext,
    imports=st.lists(st.text(min_size=0, max_size=80), max_size=15),
    class_name=st.one_of(st.none(), st.text(min_size=1, max_size=60)),
    method_names=st.lists(st.text(min_size=0, max_size=50), max_size=20),
)

optional_file_context_strategy = st.one_of(st.none(), file_context_strategy)


@given(
    node=node_strategy,
    file_context=optional_file_context_strategy,
)
@settings(max_examples=100)
def test_property_1_description_generation_invariant(node, file_context):
    """
    **Validates: Requirements 1.1, 1.2**

    For any valid Node (with any label, any NodeType, and any FileContext or None),
    the Description_Generator SHALL return a non-empty string of at most 120 Unicode characters.
    """
    generator = Description_Generator()
    result = generator.generate(node, file_context)

    assert isinstance(result, str), (
        f"Expected str, got {type(result).__name__}"
    )
    assert len(result) > 0, (
        f"Description must be non-empty. "
        f"Node: id={node.id!r}, label={node.label!r}, type={node.type!r}. "
        f"FileContext: {file_context!r}"
    )
    assert len(result) <= 120, (
        f"Description length {len(result)} exceeds 120 characters. "
        f"Description: {result!r}. "
        f"Node: id={node.id!r}, label={node.label!r}, type={node.type!r}. "
        f"FileContext: {file_context!r}"
    )
