# Feature: dev-ghost-parser, Property 9: Los caracteres de control no aparecen sin escapar
"""
Property 9: Los caracteres de control no aparecen sin escapar

**Validates: Requirements 6.3**

Para todo resultado de análisis, ningún carácter en el rango U+0000–U+001F debe
aparecer sin escapar en la cadena JSON de salida (es decir, todos deben representarse
como secuencias \\uXXXX cuando están dentro de valores de cadena).
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.models import (
    Attribute,
    CodeFlowResult,
    Edge,
    Entity,
    ERResult,
    Node,
    Relation,
    SubsystemError,
)
from dev_ghost_parser.output_serializer import Output_Serializer

VALID_TYPES = ["Controller", "Service", "Route", "Middleware", "Repository", "Utility"]
VALID_RELATIONS = ["imports", "calls", "depends_on"]

# Strategy: text that always includes at least one control character U+0000–U+001F
control_char_strategy = st.characters(min_codepoint=0x0000, max_codepoint=0x001F)
text_with_control_chars = st.text(
    alphabet=st.one_of(
        st.characters(min_codepoint=0x0000, max_codepoint=0x001F),
        st.characters(min_codepoint=0x0020, max_codepoint=0x007E),
    ),
    min_size=1,
    max_size=50,
).filter(lambda s: any(ord(c) < 0x20 for c in s))

# Strategy: regular text (no control chars)
regular_text = st.text(
    alphabet=st.characters(min_codepoint=0x0020, max_codepoint=0x007E),
    min_size=1,
    max_size=30,
)


# ---------------------------------------------------------------------------
# Test 1: Control chars in node labels are escaped in JSON output
# ---------------------------------------------------------------------------

@given(
    label_with_control=text_with_control_chars,
    node_type=st.sampled_from(VALID_TYPES),
)
@settings(max_examples=100)
def test_property_9_control_chars_in_node_labels(label_with_control, node_type):
    """
    **Validates: Requirements 6.3**

    When node labels contain control characters U+0000–U+001F, the serialized
    JSON output must represent them as \\uXXXX escape sequences, not as raw bytes.
    """
    nodes = [Node(id="node1", label=label_with_control, type=node_type)]
    code_flow = CodeFlowResult(nodes=nodes)
    er_result = ERResult()
    summary = "Test summary."

    serializer = Output_Serializer()
    output = serializer.serialize(code_flow, er_result, summary, [])

    # Decode to string and scan for unescaped control characters
    json_str = output.decode("utf-8")
    for i, ch in enumerate(json_str):
        assert ord(ch) >= 0x20 or ch in ('\r', '\n', '\t') and False or ord(ch) >= 0x20, (
            f"Unescaped control character U+{ord(ch):04X} found at position {i} "
            f"in JSON output. Label input: {label_with_control!r}"
        )


# ---------------------------------------------------------------------------
# Test 2: Control chars in entity names are escaped in JSON output
# ---------------------------------------------------------------------------

@given(
    entity_name_with_control=text_with_control_chars,
    attr_name_with_control=text_with_control_chars,
)
@settings(max_examples=100)
def test_property_9_control_chars_in_entity_names(
    entity_name_with_control, attr_name_with_control
):
    """
    **Validates: Requirements 6.3**

    When entity names and attribute names contain control characters U+0000–U+001F,
    the serialized JSON output must escape them as \\uXXXX sequences.
    """
    entities = [
        Entity(
            name=entity_name_with_control,
            attributes=[Attribute(name=attr_name_with_control, type="string")],
            primaryKey="id",
        )
    ]
    er_result = ERResult(entities=entities)
    code_flow = CodeFlowResult()
    summary = "Test summary."

    serializer = Output_Serializer()
    output = serializer.serialize(code_flow, er_result, summary, [])

    json_str = output.decode("utf-8")
    for i, ch in enumerate(json_str):
        assert ord(ch) >= 0x20, (
            f"Unescaped control character U+{ord(ch):04X} found at position {i} "
            f"in JSON output. Entity name: {entity_name_with_control!r}, "
            f"Attr name: {attr_name_with_control!r}"
        )


# ---------------------------------------------------------------------------
# Test 3: Control chars in summary string are escaped in JSON output
# ---------------------------------------------------------------------------

@given(summary_with_control=text_with_control_chars)
@settings(max_examples=100)
def test_property_9_control_chars_in_summary(summary_with_control):
    """
    **Validates: Requirements 6.3**

    When the summary string contains control characters U+0000–U+001F,
    the serialized JSON output must escape them as \\uXXXX sequences.
    """
    code_flow = CodeFlowResult()
    er_result = ERResult()

    serializer = Output_Serializer()
    output = serializer.serialize(code_flow, er_result, summary_with_control, [])

    json_str = output.decode("utf-8")
    for i, ch in enumerate(json_str):
        assert ord(ch) >= 0x20, (
            f"Unescaped control character U+{ord(ch):04X} found at position {i} "
            f"in JSON output. Summary input: {summary_with_control!r}"
        )


# ---------------------------------------------------------------------------
# Test 4: Comprehensive - control chars in multiple fields simultaneously
# ---------------------------------------------------------------------------

@given(
    label=text_with_control_chars,
    entity_name=text_with_control_chars,
    summary=text_with_control_chars,
    error_message=text_with_control_chars,
)
@settings(max_examples=100)
def test_property_9_control_chars_comprehensive(
    label, entity_name, summary, error_message
):
    """
    **Validates: Requirements 6.3**

    When control characters appear in node labels, entity names, summary, and
    error messages simultaneously, ALL must be properly escaped in the JSON output.
    No raw byte in range U+0000–U+001F should appear in the output string.
    """
    nodes = [Node(id="n1", label=label, type="Service")]
    code_flow = CodeFlowResult(nodes=nodes)
    entities = [Entity(name=entity_name, attributes=[], primaryKey="id")]
    er_result = ERResult(entities=entities)
    subsystem_errors = [SubsystemError(subsystem="Test", message=error_message)]

    serializer = Output_Serializer()
    # Pass subsystem_errors to trigger the errors key in output
    output = serializer.serialize(code_flow, er_result, summary, subsystem_errors)

    json_str = output.decode("utf-8")
    for i, ch in enumerate(json_str):
        assert ord(ch) >= 0x20, (
            f"Unescaped control character U+{ord(ch):04X} found at position {i} "
            f"in JSON output. Inputs: label={label!r}, entity={entity_name!r}, "
            f"summary={summary!r}, error_msg={error_message!r}"
        )
