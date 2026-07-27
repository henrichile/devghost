# Feature: interactive-ux-enhancements, Property 2: Serialization includes description for all nodes
"""
Property 2: Serialization includes description for all nodes

Validates: Requirements 1.6

For any CodeFlowResult containing nodes with description fields, the Output_Serializer
SHALL produce JSON where every object in the `codeFlow.nodes` array contains a
"description" key with a string value.
"""

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.models import CodeFlowResult, Edge, Node
from dev_ghost_parser.output_serializer import Output_Serializer

VALID_NODE_TYPES = ["Controller", "Service", "Route", "Middleware", "Repository", "Utility"]
VALID_EDGE_RELATIONS = ["imports", "calls", "depends_on"]


# Strategy: generate a valid Node with a description field
node_strategy = st.builds(
    Node,
    id=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-"),
        min_size=1,
        max_size=40,
    ),
    label=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_"),
        min_size=1,
        max_size=30,
    ),
    type=st.sampled_from(VALID_NODE_TYPES),
    description=st.text(min_size=0, max_size=120),
)


# Strategy: generate a list of nodes (at least 1)
nodes_strategy = st.lists(node_strategy, min_size=1, max_size=10)


# Strategy: generate edges referencing existing node ids
def edges_strategy(nodes):
    if len(nodes) < 2:
        return st.just([])
    node_ids = [n.id for n in nodes]
    edge_st = st.builds(
        Edge,
        source=st.sampled_from(node_ids),
        target=st.sampled_from(node_ids),
        relation=st.sampled_from(VALID_EDGE_RELATIONS),
    )
    return st.lists(edge_st, min_size=0, max_size=5)


# Strategy: generate a CodeFlowResult with nodes that have descriptions
code_flow_strategy = nodes_strategy.flatmap(
    lambda nodes: edges_strategy(nodes).map(
        lambda edges: CodeFlowResult(nodes=nodes, edges=edges, errors=[])
    )
)


@given(code_flow=code_flow_strategy)
@settings(max_examples=100)
def test_property_serialization_includes_description(code_flow):
    """
    **Validates: Requirements 1.6**

    For any CodeFlowResult containing nodes with description fields,
    serializing with Output_Serializer must produce JSON where every
    node object in codeFlow.nodes has a "description" key with a string value.
    """
    serializer = Output_Serializer()

    # Serialize the code flow result
    output_bytes = serializer.serialize(
        code_flow=code_flow,
        er_result=None,
        summary=None,
        subsystem_errors=[],
    )

    # Parse the JSON output
    result = json.loads(output_bytes.decode("utf-8"))

    # Verify codeFlow key exists and has nodes
    assert "codeFlow" in result, "Output missing 'codeFlow' key"
    assert result["codeFlow"] is not None, "codeFlow should not be None"
    assert "nodes" in result["codeFlow"], "codeFlow missing 'nodes' key"

    serialized_nodes = result["codeFlow"]["nodes"]

    # Verify node count matches
    assert len(serialized_nodes) == len(code_flow.nodes), (
        f"Expected {len(code_flow.nodes)} nodes, got {len(serialized_nodes)}"
    )

    # Verify every node has a "description" key with a string value
    for i, node_dict in enumerate(serialized_nodes):
        assert "description" in node_dict, (
            f"Node at index {i} (id={node_dict.get('id', '?')}) "
            f"is missing 'description' key"
        )
        assert isinstance(node_dict["description"], str), (
            f"Node at index {i} (id={node_dict.get('id', '?')}) "
            f"has non-string description: {type(node_dict['description'])}"
        )
