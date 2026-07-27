"""Unit tests for task 5.1: methods field serialization in output_serializer.py."""

import json

from dev_ghost_parser.models import Node, CodeFlowResult
from dev_ghost_parser.output_serializer import Output_Serializer, _code_flow_to_dict


def test_methods_field_present_with_methods():
    """Methods field should contain the node's method_names."""
    node = Node(
        id="abc",
        label="MyService",
        type="Service",
        description="test",
        method_names=["get_user", "create_user", "delete_user"],
    )
    cf = CodeFlowResult(nodes=[node], edges=[])
    result = _code_flow_to_dict(cf)
    assert result["nodes"][0]["methods"] == ["get_user", "create_user", "delete_user"]


def test_methods_field_empty_when_no_methods():
    """Methods field should be an empty array when method_names is empty."""
    node = Node(id="abc", label="MyService", type="Service", description="test", method_names=[])
    cf = CodeFlowResult(nodes=[node], edges=[])
    result = _code_flow_to_dict(cf)
    assert result["nodes"][0]["methods"] == []


def test_methods_field_capped_at_10():
    """Methods field should contain at most 10 elements."""
    methods = [f"method_{i}" for i in range(15)]
    node = Node(id="abc", label="MyService", type="Service", description="test", method_names=methods)
    cf = CodeFlowResult(nodes=[node], edges=[])
    result = _code_flow_to_dict(cf)
    assert len(result["nodes"][0]["methods"]) == 10
    assert result["nodes"][0]["methods"] == methods[:10]


def test_methods_preserves_order():
    """Methods field should preserve source order."""
    methods = ["z_last", "a_first", "m_middle"]
    node = Node(id="abc", label="MyService", type="Service", description="test", method_names=methods)
    cf = CodeFlowResult(nodes=[node], edges=[])
    result = _code_flow_to_dict(cf)
    assert result["nodes"][0]["methods"] == ["z_last", "a_first", "m_middle"]


def test_methods_in_full_serialization():
    """Methods field should appear in the full JSON output from Output_Serializer."""
    node = Node(
        id="abc", label="MyConfig", type="Config", description="Config test", method_names=["connect", "disconnect"]
    )
    cf = CodeFlowResult(nodes=[node], edges=[])
    serializer = Output_Serializer()
    output = serializer.serialize(code_flow=cf, er_result=None, summary="Test summary", subsystem_errors=[])
    parsed = json.loads(output)
    assert parsed["codeFlow"]["nodes"][0]["methods"] == ["connect", "disconnect"]


def test_methods_empty_in_full_serialization():
    """Empty methods should serialize as empty JSON array in full output."""
    node = Node(id="abc", label="MyConfig", type="Config", description="Config test", method_names=[])
    cf = CodeFlowResult(nodes=[node], edges=[])
    serializer = Output_Serializer()
    output = serializer.serialize(code_flow=cf, er_result=None, summary="Test summary", subsystem_errors=[])
    parsed = json.loads(output)
    assert parsed["codeFlow"]["nodes"][0]["methods"] == []
