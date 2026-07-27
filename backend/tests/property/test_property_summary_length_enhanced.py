# Feature: interactive-ux-enhancements, Property 8: Summary length invariant
"""
Property 8: Summary length invariant

Validates: Requirements 3.5

For any valid combination of CodeFlowResult and ERResult inputs,
the Summary_Generator output SHALL have at most 500 Unicode code points.
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

# --- Strategies ---

attribute_strategy = st.builds(
    Attribute,
    name=st.text(min_size=1, max_size=30),
    type=st.sampled_from(["string", "integer", "boolean", "DateTime", "float", "uuid"]),
)

entity_strategy = st.builds(
    Entity,
    name=st.text(min_size=1, max_size=80),
    attributes=st.lists(attribute_strategy, max_size=15),
    primaryKey=st.text(min_size=1, max_size=20),
)

node_strategy = st.builds(
    Node,
    id=st.text(min_size=1, max_size=40),
    label=st.text(min_size=1, max_size=100),
    type=st.sampled_from(VALID_TYPES),
    description=st.text(min_size=0, max_size=120),
)


@given(
    nodes=st.lists(node_strategy, max_size=60),
    entities=st.lists(entity_strategy, max_size=30),
    code_flow_none=st.booleans(),
    er_none=st.booleans(),
)
@settings(max_examples=100)
def test_property_8_summary_length_invariant(nodes, entities, code_flow_none, er_none):
    """
    **Validates: Requirements 3.5**

    For any valid combination of CodeFlowResult and ERResult inputs (including None),
    the Summary_Generator output must have at most 500 Unicode code points.
    """
    code_flow = None if code_flow_none else CodeFlowResult(nodes=nodes)
    er_result = None if er_none else ERResult(entities=entities)

    sg = Summary_Generator()
    result = sg.generate(code_flow, er_result, "/test/path")

    assert len(result) <= 500, (
        f"Summary length {len(result)} exceeds 500 code points. "
        f"Summary: {result!r}"
    )


@given(
    nodes=st.lists(
        st.builds(
            Node,
            id=st.text(min_size=1, max_size=40),
            label=st.text(min_size=50, max_size=100),
            type=st.sampled_from(VALID_TYPES),
            description=st.text(min_size=0, max_size=120),
        ),
        min_size=5,
        max_size=60,
    ),
    entities=st.lists(
        st.builds(
            Entity,
            name=st.text(min_size=30, max_size=80),
            attributes=st.lists(attribute_strategy, max_size=10),
            primaryKey=st.text(min_size=1, max_size=20),
        ),
        min_size=1,
        max_size=30,
    ),
)
@settings(max_examples=100)
def test_property_8_summary_length_many_nodes_long_labels(nodes, entities):
    """
    **Validates: Requirements 3.5**

    Edge case: Many nodes with long labels combined with many entities
    with varied names. The summary must still respect the 500 code point limit.
    """
    code_flow = CodeFlowResult(nodes=nodes)
    er_result = ERResult(entities=entities)

    sg = Summary_Generator()
    result = sg.generate(code_flow, er_result, "/test/path")

    assert len(result) <= 500, (
        f"Summary length {len(result)} exceeds 500 code points with many nodes/long labels. "
        f"Summary: {result!r}"
    )


@given(
    nodes=st.lists(
        st.builds(
            Node,
            id=st.text(min_size=1, max_size=40),
            label=st.text(min_size=1, max_size=50),
            type=st.just("Controller"),
            description=st.text(min_size=0, max_size=120),
        ),
        min_size=1,
        max_size=30,
    ).flatmap(
        lambda ctrl_nodes: st.lists(
            st.builds(
                Node,
                id=st.text(min_size=1, max_size=40),
                label=st.text(min_size=1, max_size=50),
                type=st.sampled_from(["Service", "Route", "Middleware", "Repository", "Utility"]),
                description=st.text(min_size=0, max_size=120),
            ),
            min_size=0,
            max_size=30,
        ).map(lambda other_nodes: ctrl_nodes + other_nodes)
    ),
    entities=st.lists(entity_strategy, min_size=1, max_size=20),
)
@settings(max_examples=100)
def test_property_8_summary_length_all_types_present(nodes, entities):
    """
    **Validates: Requirements 3.5**

    Edge case: When all node types are present (triggering long type breakdown
    sentence 3 and purpose inference sentence 4), the summary must still
    respect the 500 code point limit.
    """
    code_flow = CodeFlowResult(nodes=nodes)
    er_result = ERResult(entities=entities)

    sg = Summary_Generator()
    result = sg.generate(code_flow, er_result, "/test/path")

    assert len(result) <= 500, (
        f"Summary length {len(result)} exceeds 500 code points with all types present. "
        f"Summary: {result!r}"
    )
