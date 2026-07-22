# Feature: dev-ghost-parser, Property 6: El resumen está libre de caracteres prohibidos
"""
Property 6: El resumen está libre de caracteres prohibidos

**Validates: Requisitos 3.2**

Para todo código base analizado, el campo `summary` no debe contener ninguno de los
caracteres del conjunto {*, #, `, _, ~, >, <} ni caracteres de control en el rango
U+0000–U+001F.
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
from dev_ghost_parser.summary_generator import Summary_Generator, _sanitize

VALID_TYPES = ["Controller", "Service", "Route", "Middleware", "Repository", "Utility"]

# The set of prohibited characters per Requirement 3.2
PROHIBITED_CHARS = set("*#`_~><")


# ---------------------------------------------------------------------------
# Approach 1: Test _sanitize() directly with arbitrary text inputs
# ---------------------------------------------------------------------------


@given(text=st.text(min_size=1, max_size=600))
@settings(max_examples=100)
def test_property_6_sanitize_removes_prohibited(text):
    """
    **Validates: Requisitos 3.2**

    For any arbitrary text input (including special chars and control chars),
    _sanitize must produce output free of prohibited characters and control
    characters U+0000–U+001F.
    """
    result = _sanitize(text)
    for ch in result:
        assert ch not in PROHIBITED_CHARS, (
            f"Prohibited character {ch!r} (U+{ord(ch):04X}) found in sanitized output. "
            f"Input: {text!r}, Output: {result!r}"
        )
        assert ord(ch) >= 0x20, (
            f"Control character U+{ord(ch):04X} found in sanitized output. "
            f"Input: {text!r}, Output: {result!r}"
        )


# ---------------------------------------------------------------------------
# Approach 2: Test Summary_Generator().generate() with inputs containing
# prohibited characters in entity names and node labels
# ---------------------------------------------------------------------------

# Strategy: generate entity names that may contain prohibited/control chars
entity_name_strategy = st.text(min_size=1, max_size=50)

attribute_strategy = st.builds(
    Attribute,
    name=st.text(min_size=1, max_size=20),
    type=st.text(min_size=1, max_size=20),
)

entity_strategy = st.builds(
    Entity,
    name=entity_name_strategy,
    attributes=st.lists(attribute_strategy, max_size=5),
    primaryKey=st.text(min_size=1, max_size=20),
)

node_strategy = st.builds(
    Node,
    id=st.text(min_size=1, max_size=40),
    label=st.text(min_size=1, max_size=50),
    type=st.sampled_from(VALID_TYPES),
)


@given(
    entity_names=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=5),
    node_types=st.lists(st.sampled_from(VALID_TYPES), min_size=1, max_size=10),
)
@settings(max_examples=100)
def test_property_6_generate_no_prohibited_chars(entity_names, node_types):
    """
    **Validates: Requisitos 3.2**

    When Summary_Generator.generate() receives CodeFlowResult and ERResult with
    entity names containing arbitrary text (including prohibited characters),
    the resulting summary must be free of prohibited characters and control chars.
    """
    nodes = [
        Node(id=str(i), label=f"node{i}", type=t)
        for i, t in enumerate(node_types)
    ]
    entities = [
        Entity(name=n, attributes=[], primaryKey="id")
        for n in entity_names
    ]
    code_flow = CodeFlowResult(nodes=nodes)
    er_result = ERResult(entities=entities)

    result = Summary_Generator().generate(code_flow, er_result, "/path")

    for ch in result:
        assert ch not in PROHIBITED_CHARS, (
            f"Prohibited character {ch!r} (U+{ord(ch):04X}) found in generated summary. "
            f"Entity names: {entity_names!r}, Summary: {result!r}"
        )
        assert ord(ch) >= 0x20, (
            f"Control character U+{ord(ch):04X} found in generated summary. "
            f"Entity names: {entity_names!r}, Summary: {result!r}"
        )


@given(
    nodes=st.lists(node_strategy, min_size=1, max_size=15),
    entities=st.lists(entity_strategy, max_size=10),
    code_flow_none=st.booleans(),
    er_none=st.booleans(),
)
@settings(max_examples=100)
def test_property_6_generate_all_combinations_no_prohibited(
    nodes, entities, code_flow_none, er_none
):
    """
    **Validates: Requisitos 3.2**

    For any combination of analysis results (including None inputs),
    the Summary_Generator must produce output free of prohibited characters
    and control characters U+0000–U+001F.
    """
    code_flow = None if code_flow_none else CodeFlowResult(nodes=nodes)
    er_result = None if er_none else ERResult(entities=entities)

    result = Summary_Generator().generate(code_flow, er_result, "/test/path")

    for ch in result:
        assert ch not in PROHIBITED_CHARS, (
            f"Prohibited character {ch!r} (U+{ord(ch):04X}) found in summary. "
            f"Summary: {result!r}"
        )
        assert ord(ch) >= 0x20, (
            f"Control character U+{ord(ch):04X} found in summary. "
            f"Summary: {result!r}"
        )
