# Feature: interactive-ux-enhancements, Property 6: Summary uses Spanish architectural type names
"""
Property 6: Summary uses Spanish architectural type names

Validates: Requirements 3.3

For any CodeFlowResult containing Controller-type nodes, the Summary_Generator
output SHALL contain the Spanish term "controlador" (or its plural "controladores")
and SHALL NOT contain the English term "Controller" as a standalone word.
"""

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.models import (
    CodeFlowResult,
    Entity,
    ERResult,
    Node,
)
from dev_ghost_parser.summary_generator import Summary_Generator

VALID_TYPES = ["Controller", "Service", "Route", "Middleware", "Repository", "Utility"]

# Use simple single lowercase words for entity names to avoid sanitization issues
_SIMPLE_ENTITY_NAMES = st.sampled_from([
    "users", "orders", "products", "payments", "sessions",
    "accounts", "items", "categories", "messages", "tasks",
])

entity_strategy = st.builds(
    Entity,
    name=_SIMPLE_ENTITY_NAMES,
)

# Strategy for Controller-type nodes with simple labels
controller_node_strategy = st.builds(
    Node,
    id=st.from_regex(r"[a-f0-9]{8}", fullmatch=True),
    label=st.sampled_from(["main", "app", "handler", "manager", "core"]),
    type=st.just("Controller"),
)

# Strategy for other node types
other_node_strategy = st.builds(
    Node,
    id=st.from_regex(r"[a-f0-9]{8}", fullmatch=True),
    label=st.sampled_from(["helper", "util", "service", "router", "store"]),
    type=st.sampled_from(["Service", "Route", "Middleware", "Repository", "Utility"]),
)


@given(
    controller_nodes=st.lists(controller_node_strategy, min_size=1, max_size=5),
    other_nodes=st.lists(other_node_strategy, min_size=0, max_size=5),
    entities=st.lists(entity_strategy, min_size=1, max_size=5),
)
@settings(max_examples=100)
def test_property_6_summary_contains_spanish_controller_name(
    controller_nodes, other_nodes, entities
):
    """
    **Validates: Requirements 3.3**

    For any CodeFlowResult with at least one Controller-type node and an ERResult
    with at least one entity, the summary SHALL contain "controlador" or "controladores"
    and SHALL NOT contain standalone "Controller".
    """
    all_nodes = controller_nodes + other_nodes
    code_flow = CodeFlowResult(nodes=all_nodes)
    er_result = ERResult(entities=entities)

    sg = Summary_Generator()
    result = sg.generate(code_flow, er_result, "/test/path")

    # The summary must contain the Spanish term for Controller
    has_spanish_name = ("controlador" in result.lower())
    assert has_spanish_name, (
        f"Summary does not contain 'controlador' or 'controladores'. "
        f"Summary: {result!r}"
    )

    # The summary must NOT contain standalone "Controller" (English term)
    has_english_controller = re.search(r"\bController\b", result)
    assert has_english_controller is None, (
        f"Summary contains standalone English 'Controller'. "
        f"Summary: {result!r}"
    )
