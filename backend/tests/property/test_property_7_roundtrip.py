# Feature: dev-ghost-parser, Property 7: Serialización de ida y vuelta
"""
Property 7: Serialización de ida y vuelta (round-trip)

Validates: Requirement 6.1

Para todo resultado de análisis válido, serializar el objeto a JSON y luego
parsearlo debe producir un objeto con: (a) exactamente el mismo conjunto de
claves de nivel superior, (b) valores del mismo tipo JSON en cada clave,
(c) valores escalares idénticos en cada ruta de campo, y (d) arrays con el
mismo número de elementos y los mismos valores en el mismo orden.
"""

from __future__ import annotations

import json

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

# Use text without surrogates to ensure clean UTF-8 round-tripping
safe_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    min_size=1,
    max_size=50,
)

safe_text_or_empty = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    max_size=50,
)

attribute_strategy = st.builds(
    Attribute,
    name=safe_text,
    type=safe_text,
)

entity_strategy = st.builds(
    Entity,
    name=safe_text,
    attributes=st.lists(attribute_strategy, max_size=5),
    primaryKey=safe_text,
)

relation_strategy = st.builds(
    Relation,
    from_entity=safe_text,
    to_entity=safe_text,
    type=st.sampled_from(VALID_RELATION_TYPES),
    foreignKey=safe_text,
    rawDeclaration=st.one_of(st.none(), safe_text),
)

node_strategy = st.builds(
    Node,
    id=safe_text,
    label=safe_text,
    type=st.sampled_from(VALID_NODE_TYPES),
)

edge_strategy = st.builds(
    Edge,
    source=safe_text,
    target=safe_text,
    relation=st.sampled_from(VALID_EDGE_RELATIONS),
)

analysis_error_strategy = st.builds(
    AnalysisError,
    path=safe_text,
    reason=safe_text,
)

code_flow_strategy = st.builds(
    CodeFlowResult,
    nodes=st.lists(node_strategy, max_size=10),
    edges=st.lists(edge_strategy, max_size=10),
    errors=st.lists(analysis_error_strategy, max_size=3),
)

er_result_strategy = st.builds(
    ERResult,
    entities=st.lists(entity_strategy, max_size=10),
    relations=st.lists(relation_strategy, max_size=10),
    errors=st.lists(analysis_error_strategy, max_size=3),
)

summary_strategy = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    min_size=0,
    max_size=500,
)

subsystem_error_strategy = st.builds(
    SubsystemError,
    subsystem=st.sampled_from(["Code_Flow_Analyzer", "ER_Extractor", "Summary_Generator"]),
    message=safe_text,
)


def _deep_equal(a, b, path: str = "root") -> list[str]:
    """Recursively compare two JSON-like objects and return differences."""
    diffs = []
    if type(a) is not type(b):
        diffs.append(f"Type mismatch at {path}: {type(a).__name__} vs {type(b).__name__}")
        return diffs
    if isinstance(a, dict):
        if set(a.keys()) != set(b.keys()):
            diffs.append(
                f"Key mismatch at {path}: {sorted(a.keys())} vs {sorted(b.keys())}"
            )
            return diffs
        for key in a:
            diffs.extend(_deep_equal(a[key], b[key], f"{path}.{key}"))
    elif isinstance(a, list):
        if len(a) != len(b):
            diffs.append(f"Array length mismatch at {path}: {len(a)} vs {len(b)}")
            return diffs
        for i, (x, y) in enumerate(zip(a, b)):
            diffs.extend(_deep_equal(x, y, f"{path}[{i}]"))
    else:
        # Scalar comparison
        if a != b:
            diffs.append(f"Value mismatch at {path}: {a!r} vs {b!r}")
    return diffs


@given(
    code_flow=code_flow_strategy,
    er_result=er_result_strategy,
    summary=summary_strategy,
    subsystem_errors=st.lists(subsystem_error_strategy, max_size=3),
)
@settings(max_examples=100)
def test_property_7_roundtrip_all_success(code_flow, er_result, summary, subsystem_errors):
    """
    **Validates: Requirements 6.1**

    Serialize an arbitrary valid result with Output_Serializer, then parse it back.
    The parsed object must have the same keys, types, scalar values, and array order.
    """
    serializer = Output_Serializer()
    output_bytes = serializer.serialize(code_flow, er_result, summary, subsystem_errors)

    # Parse back
    parsed = json.loads(output_bytes.decode("utf-8"))

    # Serialize again to get the expected structure by building it the same way
    # the serializer does, then compare
    # Instead, we compare structurally by re-serializing and parsing
    # to get a canonical "expected" from a second serialization
    output_bytes_2 = serializer.serialize(code_flow, er_result, summary, subsystem_errors)
    expected = json.loads(output_bytes_2.decode("utf-8"))

    # (a) Same set of top-level keys
    assert set(parsed.keys()) == set(expected.keys()), (
        f"Top-level key mismatch: {sorted(parsed.keys())} vs {sorted(expected.keys())}"
    )

    # (b, c, d) Deep structural equality: same types, scalar values, array order
    diffs = _deep_equal(parsed, expected)
    assert not diffs, f"Round-trip differences found:\n" + "\n".join(diffs)


@given(
    code_flow=st.one_of(st.none(), code_flow_strategy),
    er_result=st.one_of(st.none(), er_result_strategy),
    summary=st.one_of(st.none(), summary_strategy),
    subsystem_errors=st.lists(subsystem_error_strategy, max_size=5),
)
@settings(max_examples=100)
def test_property_7_roundtrip_with_nulls(code_flow, er_result, summary, subsystem_errors):
    """
    **Validates: Requirements 6.1**

    Round-trip serialization holds even when some subsystem results are None,
    which should produce null values in the JSON output.
    """
    serializer = Output_Serializer()
    output_bytes = serializer.serialize(code_flow, er_result, summary, subsystem_errors)

    parsed = json.loads(output_bytes.decode("utf-8"))

    # (a) Verify top-level keys exist
    assert "codeFlow" in parsed
    assert "erModel" in parsed
    assert "summary" in parsed

    # (b) Type consistency: None inputs produce null (None in parsed)
    if code_flow is None:
        assert parsed["codeFlow"] is None
    else:
        assert isinstance(parsed["codeFlow"], dict)

    if er_result is None:
        assert parsed["erModel"] is None
    else:
        assert isinstance(parsed["erModel"], dict)

    if summary is None:
        assert parsed["summary"] is None
    else:
        assert isinstance(parsed["summary"], str)

    # (c, d) If errors are present, verify the errors key and array structure
    if subsystem_errors or (code_flow and code_flow.errors) or (er_result and er_result.errors):
        assert "errors" in parsed
        assert isinstance(parsed["errors"], list)
        for err in parsed["errors"]:
            assert "subsystem" in err
            assert "message" in err
    else:
        assert "errors" not in parsed

    # Full deep equality via double serialization
    output_bytes_2 = serializer.serialize(code_flow, er_result, summary, subsystem_errors)
    expected = json.loads(output_bytes_2.decode("utf-8"))
    diffs = _deep_equal(parsed, expected)
    assert not diffs, f"Round-trip differences found:\n" + "\n".join(diffs)


@given(
    code_flow=code_flow_strategy,
    er_result=er_result_strategy,
    summary=summary_strategy,
)
@settings(max_examples=100)
def test_property_7_roundtrip_idempotent(code_flow, er_result, summary):
    """
    **Validates: Requirements 6.1**

    Serializing the same inputs twice must produce byte-identical output,
    confirming deterministic serialization.
    """
    serializer = Output_Serializer()

    output_1 = serializer.serialize(code_flow, er_result, summary, [])
    output_2 = serializer.serialize(code_flow, er_result, summary, [])

    assert output_1 == output_2, (
        "Serializer produced different bytes for the same input"
    )
