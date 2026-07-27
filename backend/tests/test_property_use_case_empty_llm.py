"""
Property 4: Empty LLM response produces None

For any valid CodeFlowResult with Controller/Route nodes and methods,
if LLM_Client.complete() returns an empty string, a whitespace-only string,
or None, then generate_use_cases SHALL return None.

**Validates: Requirements 6.4**
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, strategies as st

from dev_ghost_parser.artifacts_generator import Artifacts_Generator
from dev_ghost_parser.models import CodeFlowResult, Edge, Node


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Strategy for generating method names
st_method_name = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_"),
    min_size=1,
    max_size=20,
)

# Strategy for generating node labels
st_label = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_"),
    min_size=1,
    max_size=25,
)

# Strategy for generating node IDs
st_node_id = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=5,
    max_size=15,
)


@st.composite
def st_code_flow_with_controllers(draw):
    """Generate a valid CodeFlowResult with at least one Controller/Route node that has methods."""
    # Generate 1-3 Controller/Route nodes with methods
    num_controllers = draw(st.integers(min_value=1, max_value=3))
    controller_nodes = []
    for i in range(num_controllers):
        node_id = draw(st_node_id.filter(
            lambda x: all(x != n.id for n in controller_nodes)
        ))
        label = draw(st_label)
        node_type = draw(st.sampled_from(["Controller", "Route"]))
        methods = draw(st.lists(st_method_name, min_size=1, max_size=5))
        controller_nodes.append(
            Node(
                id=node_id,
                label=label,
                type=node_type,
                description=f"Test {node_type}",
                method_names=methods,
            )
        )

    # Optionally add Service/Middleware nodes
    extra_nodes = []
    num_extra = draw(st.integers(min_value=0, max_value=2))
    used_ids = {n.id for n in controller_nodes}
    for i in range(num_extra):
        node_id = draw(st_node_id.filter(lambda x: x not in used_ids))
        used_ids.add(node_id)
        label = draw(st_label)
        node_type = draw(st.sampled_from(["Service", "Middleware"]))
        extra_nodes.append(
            Node(
                id=node_id,
                label=label,
                type=node_type,
                description=f"Test {node_type}",
                method_names=[],
            )
        )

    all_nodes = controller_nodes + extra_nodes

    # Generate edges between controllers and extra nodes
    edges = []
    for ctrl in controller_nodes:
        for extra in extra_nodes:
            if draw(st.booleans()):
                relation = draw(st.sampled_from(["calls", "depends_on", "imports"]))
                edges.append(Edge(source=ctrl.id, target=extra.id, relation=relation))

    return CodeFlowResult(nodes=all_nodes, edges=edges, errors=[])


# Strategy for empty/whitespace/None LLM responses
st_empty_response = st.sampled_from(["", " ", "  ", "\n", "\t", "\n\n", None])


# ---------------------------------------------------------------------------
# Property Test: Empty LLM response produces None
# ---------------------------------------------------------------------------


class TestProperty4EmptyLLMResponse:
    """Feature: use-case-generation, Property 4: Empty LLM response produces None"""

    @settings(max_examples=100)
    @given(
        code_flow=st_code_flow_with_controllers(),
        empty_response=st_empty_response,
    )
    def test_property_4_empty_llm_response_returns_none(self, code_flow, empty_response):
        """For any valid CodeFlowResult with Controller/Route nodes and methods,
        if LLM_Client.complete() returns an empty string, whitespace-only string,
        or None, then generate_use_cases SHALL return None.

        **Validates: Requirements 6.4**
        """
        # Arrange: mock LLM client that returns empty/whitespace/None
        mock_llm = MagicMock()
        mock_llm.available = True
        mock_llm.complete = MagicMock(return_value=empty_response)

        generator = Artifacts_Generator(llm_client=mock_llm)

        # Act
        result = generator.generate_use_cases(code_flow)

        # Assert: result must be None for all empty/whitespace/None responses
        assert result is None, (
            f"Expected None for empty LLM response {empty_response!r}, "
            f"but got {result!r}"
        )

        # Verify LLM was actually called (preconditions were met)
        mock_llm.complete.assert_called_once()
