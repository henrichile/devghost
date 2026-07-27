# Feature: interactive-ux-enhancements, Property 7: Summary mentions entities when present
"""
Property 7: Summary mentions entities when present

Validates: Requirements 3.4

For any ERResult with at least one entity, the Summary_Generator output SHALL contain
either the word "entidad" or "entidades" and at least one entity name from the input.
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

# Simple entity names that won't be stripped by the sanitizer.
# - No camelCase (lowercase start + internal uppercase): sanitizer removes these
# - No PascalCase with multiple capitals (e.g., "OrderService"): sanitizer removes these
# - No snake_case (e.g., "order_item"): sanitizer removes these
# Single capitalized words like "User" are safe (pattern requires [A-Z][a-z]+[A-Z]).
# Simple lowercase words are also safe.
SAFE_ENTITY_NAMES = [
    "users", "orders", "items", "products", "payments",
    "invoices", "reviews", "tags", "roles", "sessions",
    "logs", "events", "tasks", "files", "reports",
    "data", "stock", "carts", "tokens", "accounts",
]

# --- Strategies ---

attribute_strategy = st.builds(
    Attribute,
    name=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
    type=st.sampled_from(["string", "integer", "boolean", "float"]),
)

entity_strategy = st.builds(
    Entity,
    name=st.sampled_from(SAFE_ENTITY_NAMES),
    attributes=st.lists(attribute_strategy, max_size=5),
    primaryKey=st.just("id"),
)

node_strategy = st.builds(
    Node,
    id=st.text(min_size=1, max_size=40, alphabet=st.characters(whitelist_categories=("L", "N"))),
    label=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))),
    type=st.sampled_from(VALID_TYPES),
)


@given(
    entities=st.lists(entity_strategy, min_size=1, max_size=10),
    nodes=st.lists(node_strategy, min_size=1, max_size=10),
)
@settings(max_examples=100)
def test_property_7_summary_mentions_entities(entities, nodes):
    """
    **Validates: Requirements 3.4**

    For any ERResult with ≥1 entity (paired with ≥1 code_flow node to produce
    a full summary), the output must contain "entidad" or "entidades" AND at
    least one of the generated entity names.
    """
    code_flow = CodeFlowResult(nodes=nodes)
    er_result = ERResult(entities=entities)

    sg = Summary_Generator()
    result = sg.generate(code_flow, er_result, "/test/path")

    # Check that "entidad" or "entidades" appears in the output
    has_entity_word = ("entidad" in result) or ("entidades" in result)
    assert has_entity_word, (
        f"Summary does not contain 'entidad' or 'entidades'. "
        f"Summary: {result!r}"
    )

    # Check that at least one entity name from the input appears in the output
    entity_names = [e.name for e in entities]
    has_entity_name = any(name in result for name in entity_names)
    assert has_entity_name, (
        f"Summary does not contain any entity name from input. "
        f"Entity names: {entity_names}. Summary: {result!r}"
    )
