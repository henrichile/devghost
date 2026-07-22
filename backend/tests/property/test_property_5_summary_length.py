# Feature: dev-ghost-parser, Property 5: El resumen respeta el límite de 500 puntos de código
"""
Property 5: El resumen respeta el límite de 500 puntos de código

Validates: Requisito 3.4

Para todo código base analizado, la longitud en puntos de código Unicode del campo
`summary` en la salida debe ser menor o igual a 500.
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
    name=st.text(min_size=1, max_size=20),
    type=st.text(min_size=1, max_size=20),
)

entity_strategy = st.builds(
    Entity,
    name=st.text(min_size=1, max_size=100),
    attributes=st.lists(attribute_strategy, max_size=10),
    primaryKey=st.text(min_size=1, max_size=20),
)

node_strategy = st.builds(
    Node,
    id=st.text(min_size=1, max_size=40),
    label=st.text(min_size=1, max_size=50),
    type=st.sampled_from(VALID_TYPES),
)


@given(
    nodes=st.lists(node_strategy, max_size=50),
    entities=st.lists(entity_strategy, max_size=20),
    code_flow_none=st.booleans(),
    er_none=st.booleans(),
)
@settings(max_examples=100)
def test_property_5_summary_length(nodes, entities, code_flow_none, er_none):
    """
    **Validates: Requisito 3.4**

    For any combination of analysis results (nodes, entities, or None inputs),
    the Summary_Generator must produce a summary with at most 500 Unicode code points.
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
    entities=st.lists(
        st.builds(
            Entity,
            name=st.text(min_size=50, max_size=200),
            attributes=st.lists(attribute_strategy, max_size=10),
            primaryKey=st.text(min_size=1, max_size=20),
        ),
        min_size=1,
        max_size=20,
    ),
)
@settings(max_examples=100)
def test_property_5_summary_length_long_entity_names(entities):
    """
    **Validates: Requisito 3.4**

    Edge case: Even when entity names are very long (which would make sentences long),
    the summary must still respect the 500 code point limit.
    """
    er_result = ERResult(entities=entities)
    code_flow = CodeFlowResult(
        nodes=[Node(id="n1", label="App", type="Controller")]
    )

    sg = Summary_Generator()
    result = sg.generate(code_flow, er_result, "/test/path")

    assert len(result) <= 500, (
        f"Summary length {len(result)} exceeds 500 code points with long entity names. "
        f"Summary: {result!r}"
    )


@given(
    entities=st.lists(
        st.builds(
            Entity,
            name=st.text(min_size=1, max_size=50),
            attributes=st.lists(attribute_strategy, max_size=5),
            primaryKey=st.text(min_size=1, max_size=10),
        ),
        min_size=10,
        max_size=50,
    ),
)
@settings(max_examples=100)
def test_property_5_summary_length_many_entities(entities):
    """
    **Validates: Requisito 3.4**

    Edge case: With many entities (which triggers listing in the summary),
    the summary must still respect the 500 code point limit.
    """
    er_result = ERResult(entities=entities)
    code_flow = CodeFlowResult(
        nodes=[Node(id="n1", label="Main", type="Service")]
    )

    sg = Summary_Generator()
    result = sg.generate(code_flow, er_result, "/test/path")

    assert len(result) <= 500, (
        f"Summary length {len(result)} exceeds 500 code points with many entities. "
        f"Summary: {result!r}"
    )


def test_property_5_summary_length_all_none():
    """
    **Validates: Requisito 3.4**

    Edge case: When both inputs are None, the summary (fixed message)
    must still respect the 500 code point limit.
    """
    sg = Summary_Generator()
    result = sg.generate(None, None, "/test/path")

    assert len(result) <= 500, (
        f"Summary length {len(result)} exceeds 500 code points with all-None inputs. "
        f"Summary: {result!r}"
    )
