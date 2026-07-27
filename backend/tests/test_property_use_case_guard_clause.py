"""
Property 3: Guard clause — returns None when preconditions unmet

For any CodeFlowResult that contains zero nodes of type Controller or Route,
OR when the LLM_Client.available property is False, OR when code_flow is None,
`generate_use_cases` SHALL return None without invoking the LLM.

**Validates: Requirements 3.3, 4.3**
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import pytest
from hypothesis import given, settings, HealthCheck, strategies as st

from dev_ghost_parser.models import CodeFlowResult, Edge, Node
from dev_ghost_parser.artifacts_generator import Artifacts_Generator


# ---------------------------------------------------------------------------
# Valid non-controller/route node types (types that should NOT trigger LLM)
# ---------------------------------------------------------------------------

NON_CONTROLLER_TYPES = ["Service", "Middleware", "Repository", "Utility", "Config"]


# ---------------------------------------------------------------------------
# Hypothesis strategies (lightweight for fast generation)
# ---------------------------------------------------------------------------

# Strategy for generating a node ID
st_node_id = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=10)

# Strategy for generating a node label
st_node_label = st.text(alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1, max_size=15)

# Strategy for generating method names
st_method_names = st.lists(
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    min_size=0,
    max_size=5,
)


@st.composite
def st_non_controller_node(draw):
    """Generate a Node that is NOT a Controller or Route."""
    return Node(
        id=draw(st_node_id),
        label=draw(st_node_label),
        type=draw(st.sampled_from(NON_CONTROLLER_TYPES)),
        description=draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=0, max_size=20)),
        method_names=draw(st_method_names),
    )


@st.composite
def st_code_flow_no_controllers(draw):
    """Generate a CodeFlowResult with only non-Controller/Route nodes (0-10 nodes)."""
    num_nodes = draw(st.integers(min_value=0, max_value=10))
    nodes = [draw(st_non_controller_node()) for _ in range(num_nodes)]
    return CodeFlowResult(nodes=nodes, edges=[], errors=[])


@st.composite
def st_valid_code_flow_with_controllers(draw):
    """Generate a valid CodeFlowResult with at least one Controller/Route node with methods.

    Used to verify guard clause when LLM is unavailable or code_flow is None.
    """
    # Generate at least one controller with methods
    ctrl_node = Node(
        id=draw(st_node_id),
        label=draw(st_node_label),
        type=draw(st.sampled_from(["Controller", "Route"])),
        description=draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=0, max_size=20)),
        method_names=draw(st.lists(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
            min_size=1,
            max_size=5,
        )),
    )

    # Optionally add more non-controller nodes
    extra_nodes = draw(st.lists(st_non_controller_node(), min_size=0, max_size=3))

    return CodeFlowResult(nodes=[ctrl_node] + extra_nodes, edges=[], errors=[])


# ---------------------------------------------------------------------------
# Property Test: Guard clause returns None when preconditions unmet
# ---------------------------------------------------------------------------


class TestProperty3GuardClause:
    """Feature: use-case-generation, Property 3: Guard clause returns None"""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(code_flow=st_code_flow_no_controllers())
    def test_no_controller_or_route_nodes_returns_none(self, code_flow):
        """When CodeFlowResult contains zero Controller/Route nodes,
        generate_use_cases SHALL return None without invoking the LLM.

        **Validates: Requirements 3.3, 4.3**
        """
        mock_llm = MagicMock()
        mock_llm.available = True

        generator = Artifacts_Generator(llm_client=mock_llm)
        result = generator.generate_use_cases(code_flow)

        assert result is None, (
            f"Expected None when no Controller/Route nodes present, got: {result!r}"
        )
        mock_llm.complete.assert_not_called()

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(code_flow=st_valid_code_flow_with_controllers())
    def test_llm_unavailable_returns_none(self, code_flow):
        """When LLM_Client.available is False, generate_use_cases SHALL return None
        without invoking complete().

        **Validates: Requirements 3.3, 4.3**
        """
        mock_llm = MagicMock()
        mock_llm.available = False

        generator = Artifacts_Generator(llm_client=mock_llm)
        result = generator.generate_use_cases(code_flow)

        assert result is None, (
            f"Expected None when LLM unavailable, got: {result!r}"
        )
        mock_llm.complete.assert_not_called()

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=st.data())
    def test_code_flow_none_returns_none(self, data):
        """When code_flow is None, generate_use_cases SHALL return None
        without invoking complete().

        **Validates: Requirements 3.3, 4.3**
        """
        mock_llm = MagicMock()
        mock_llm.available = True

        generator = Artifacts_Generator(llm_client=mock_llm)
        result = generator.generate_use_cases(None)

        assert result is None, (
            f"Expected None when code_flow is None, got: {result!r}"
        )
        mock_llm.complete.assert_not_called()
