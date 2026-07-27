# Feature: precision-analysis-enhancements, Property 9: Serialization Includes Methods Field Capped at 10
"""
Property 9: Serialization Includes Methods Field Capped at 10

**Validates: Requirements 4.1, 4.2, 4.3**

For any CodeFlowResult, the serialized JSON SHALL include a "methods" field
(array of strings) in every node object under codeFlow.nodes. This array SHALL
contain at most 10 elements preserving source order, and SHALL be an empty
array [] when the node has no extracted methods.
"""

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.models import CodeFlowResult, Edge, Node
from dev_ghost_parser.output_serializer import Output_Serializer

VALID_NODE_TYPES = [
    "Controller", "Service", "Route", "Middleware",
    "Repository", "Utility", "Config",
]
VALID_EDGE_RELATIONS = ["imports", "calls", "depends_on"]


# Strategy: generate method name lists with varying sizes (0, 5, 10, 15, 20)
method_names_strategy = st.lists(
    st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_"),
        min_size=1,
        max_size=50,
    ),
    min_size=0,
    max_size=20,
)

# Strategy: generate a valid Node with method_names of varying lengths
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
    method_names=method_names_strategy,
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


# Strategy: generate a CodeFlowResult with nodes that have method_names
code_flow_strategy = nodes_strategy.flatmap(
    lambda nodes: edges_strategy(nodes).map(
        lambda edges: CodeFlowResult(nodes=nodes, edges=edges, errors=[])
    )
)


@given(code_flow=code_flow_strategy)
@settings(max_examples=200)
def test_property_serialization_methods_field_present_and_capped(code_flow):
    """
    **Validates: Requirements 4.1, 4.2, 4.3**

    For any CodeFlowResult, the serialized JSON SHALL include a "methods" field
    (array of strings) in every node object. The array SHALL contain at most 10
    elements preserving source order, and SHALL be [] when node has no methods.
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

    for i, node_dict in enumerate(serialized_nodes):
        original_node = code_flow.nodes[i]

        # 1. "methods" field MUST exist in every serialized node
        assert "methods" in node_dict, (
            f"Node at index {i} (id={node_dict.get('id', '?')}) "
            f"is missing 'methods' key"
        )

        methods = node_dict["methods"]

        # 2. "methods" MUST be a list (array of strings)
        assert isinstance(methods, list), (
            f"Node at index {i}: 'methods' should be a list, "
            f"got {type(methods)}"
        )

        # 3. Every element in the array MUST be a string
        for j, method in enumerate(methods):
            assert isinstance(method, str), (
                f"Node at index {i}, method at index {j}: "
                f"expected str, got {type(method)}"
            )

        # 4. Array length SHALL NOT exceed 10
        assert len(methods) <= 10, (
            f"Node at index {i}: 'methods' has {len(methods)} elements, "
            f"exceeding the cap of 10"
        )

        # 5. When method_names is empty, "methods" SHALL be []
        if len(original_node.method_names) == 0:
            assert methods == [], (
                f"Node at index {i}: method_names is empty but "
                f"'methods' is {methods} instead of []"
            )

        # 6. Order is preserved — first N elements match source order
        expected = original_node.method_names[:10]
        assert methods == expected, (
            f"Node at index {i}: 'methods' order mismatch. "
            f"Expected {expected}, got {methods}"
        )
