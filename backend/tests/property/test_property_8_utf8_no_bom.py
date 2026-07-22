# Feature: dev-ghost-parser, Property 8: La salida es UTF-8 sin BOM
"""
Property 8: La salida es UTF-8 sin BOM

Validates: Requirements 4.1, 6.2

Para todo resultado de análisis, los bytes de salida no deben comenzar con la secuencia
de marca de orden de bytes UTF-8 (EF BB BF), y deben ser decodificables como UTF-8 válido.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.models import (
    AnalysisError,
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

VALID_NODE_TYPES = ["Controller", "Service", "Route", "Middleware", "Repository", "Utility"]
VALID_EDGE_RELATIONS = ["imports", "calls", "depends_on"]
VALID_RELATION_TYPES = ["one-to-one", "one-to-many", "many-to-many", "unknown"]

# --- Strategies ---

attribute_strategy = st.builds(
    Attribute,
    name=st.text(min_size=1, max_size=30),
    type=st.text(min_size=1, max_size=20),
)

node_strategy = st.builds(
    Node,
    id=st.text(min_size=1, max_size=40),
    label=st.text(min_size=1, max_size=50),
    type=st.sampled_from(VALID_NODE_TYPES),
)

edge_strategy = st.builds(
    Edge,
    source=st.text(min_size=1, max_size=40),
    target=st.text(min_size=1, max_size=40),
    relation=st.sampled_from(VALID_EDGE_RELATIONS),
)

entity_strategy = st.builds(
    Entity,
    name=st.text(min_size=1, max_size=50),
    attributes=st.lists(attribute_strategy, max_size=10),
    primaryKey=st.text(min_size=1, max_size=20),
)

relation_strategy = st.builds(
    Relation,
    from_entity=st.text(min_size=1, max_size=50),
    to_entity=st.text(min_size=1, max_size=50),
    type=st.sampled_from(VALID_RELATION_TYPES),
    foreignKey=st.text(min_size=1, max_size=30),
    rawDeclaration=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
)

analysis_error_strategy = st.builds(
    AnalysisError,
    path=st.text(min_size=1, max_size=50),
    reason=st.text(min_size=1, max_size=100),
)

code_flow_strategy = st.builds(
    CodeFlowResult,
    nodes=st.lists(node_strategy, max_size=20),
    edges=st.lists(edge_strategy, max_size=20),
    errors=st.lists(analysis_error_strategy, max_size=5),
)

er_result_strategy = st.builds(
    ERResult,
    entities=st.lists(entity_strategy, max_size=15),
    relations=st.lists(relation_strategy, max_size=10),
    errors=st.lists(analysis_error_strategy, max_size=5),
)

summary_strategy = st.text(min_size=0, max_size=500)

subsystem_error_strategy = st.builds(
    SubsystemError,
    subsystem=st.sampled_from(["Code_Flow_Analyzer", "ER_Extractor", "Summary_Generator"]),
    message=st.text(min_size=1, max_size=100),
)

UTF8_BOM = b"\xef\xbb\xbf"


@given(
    code_flow=st.one_of(st.none(), code_flow_strategy),
    er_result=st.one_of(st.none(), er_result_strategy),
    summary=st.one_of(st.none(), summary_strategy),
    subsystem_errors=st.lists(subsystem_error_strategy, max_size=5),
)
@settings(max_examples=100)
def test_property_8_utf8_no_bom(code_flow, er_result, summary, subsystem_errors):
    """
    **Validates: Requirements 4.1, 6.2**

    For any combination of analysis results passed to Output_Serializer,
    the output bytes must NOT start with the UTF-8 BOM sequence (EF BB BF)
    and must be decodable as valid UTF-8.
    """
    serializer = Output_Serializer()
    output = serializer.serialize(code_flow, er_result, summary, subsystem_errors)

    # Verify output is bytes
    assert isinstance(output, bytes), (
        f"Output must be bytes, got {type(output).__name__}"
    )

    # Verify no BOM at the start
    assert not output.startswith(UTF8_BOM), (
        f"Output starts with UTF-8 BOM (EF BB BF). First 10 bytes: {output[:10]!r}"
    )

    # Verify valid UTF-8 decoding
    try:
        output.decode("utf-8")
    except UnicodeDecodeError as e:
        raise AssertionError(
            f"Output is not valid UTF-8: {e}. First 50 bytes: {output[:50]!r}"
        ) from e


@given(
    summary=st.text(
        alphabet=st.characters(
            categories=("L", "M", "N", "P", "S", "Z"),
            include_characters="áéíóúñ中文日本語한국어العربيةθωμ€£¥",
        ),
        min_size=1,
        max_size=200,
    ),
)
@settings(max_examples=100)
def test_property_8_utf8_no_bom_unicode_heavy(summary):
    """
    **Validates: Requirements 4.1, 6.2**

    Edge case: When the summary contains heavy Unicode content (multi-byte characters),
    the output must still be valid UTF-8 without BOM.
    """
    code_flow = CodeFlowResult(
        nodes=[Node(id="n1", label="TestNode", type="Service")]
    )
    er_result = ERResult(
        entities=[Entity(name="Users", attributes=[], primaryKey="id")]
    )

    serializer = Output_Serializer()
    output = serializer.serialize(code_flow, er_result, summary, [])

    assert isinstance(output, bytes)
    assert not output.startswith(UTF8_BOM), (
        f"Output starts with UTF-8 BOM with Unicode-heavy summary. "
        f"First 10 bytes: {output[:10]!r}"
    )

    try:
        output.decode("utf-8")
    except UnicodeDecodeError as e:
        raise AssertionError(
            f"Output with Unicode-heavy summary is not valid UTF-8: {e}"
        ) from e
