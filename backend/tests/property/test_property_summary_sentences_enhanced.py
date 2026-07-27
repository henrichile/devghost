# Feature: interactive-ux-enhancements, Property 5: Enhanced summary sentence count
"""
Property 5: Enhanced summary sentence count

Validates: Requirements 3.1

For any CodeFlowResult with at least one node AND ERResult with at least one entity,
the Summary_Generator SHALL produce a summary containing 3 or 4 sentences
(delimited by period followed by space or end of string).
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.models import (
    Attribute,
    CodeFlowResult,
    Entity,
    ERResult,
    Node,
)
from dev_ghost_parser.summary_generator import Summary_Generator

VALID_TYPES = ["Controller", "Service", "Route", "Middleware", "Repository", "Utility"]

# Use simple single-word entity names to avoid sanitization stripping them
SIMPLE_ENTITY_NAMES = [
    "User", "Order", "Product", "Item", "Cart", "Payment",
    "Invoice", "Stock", "Review", "Tag", "Role", "Token",
    "Session", "Log", "Event", "Task", "File", "Report",
]

# --- Strategies ---

attribute_strategy = st.builds(
    Attribute,
    name=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
    type=st.sampled_from(["string", "integer", "boolean", "float"]),
)

entity_strategy = st.builds(
    Entity,
    name=st.sampled_from(SIMPLE_ENTITY_NAMES),
    attributes=st.lists(attribute_strategy, max_size=5),
    primaryKey=st.just("id"),
)

node_strategy = st.builds(
    Node,
    id=st.text(min_size=1, max_size=40, alphabet=st.characters(whitelist_categories=("L", "N"))),
    label=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))),
    type=st.sampled_from(VALID_TYPES),
)


def count_sentences(text: str) -> int:
    """Count sentences by splitting on '.' and filtering empty parts."""
    parts = text.split(".")
    return len([p for p in parts if p.strip()])


@given(
    nodes=st.lists(node_strategy, min_size=1, max_size=20),
    entities=st.lists(entity_strategy, min_size=1, max_size=10),
)
@settings(max_examples=100)
def test_property_5_enhanced_summary_sentence_count(nodes, entities):
    """
    **Validates: Requirements 3.1**

    For any CodeFlowResult with ≥1 node AND ERResult with ≥1 entity,
    the Summary_Generator must produce a summary containing 3 or 4 sentences.
    """
    code_flow = CodeFlowResult(nodes=nodes)
    er_result = ERResult(entities=entities)

    sg = Summary_Generator()
    result = sg.generate(code_flow, er_result, "/test/path")

    sentence_count = count_sentences(result)

    assert sentence_count in (3, 4), (
        f"Expected 3 or 4 sentences, got {sentence_count}. "
        f"Summary: {result!r}"
    )
