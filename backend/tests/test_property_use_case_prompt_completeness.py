"""
Property 1: Prompt completeness — methods, services, and middleware included

For any valid CodeFlowResult containing Controller/Route nodes with methods,
and edges connecting them to Service and Middleware nodes, the generated
user_prompt string SHALL contain every method name from those controllers,
every label of connected Service nodes, and every label of connected Middleware nodes.

**Validates: Requirements 1.1, 2.3, 2.4, 6.5**
"""

from __future__ import annotations

import hashlib
import string

from hypothesis import given, settings, strategies as st

from dev_ghost_parser.artifacts_generator import Artifacts_Generator
from dev_ghost_parser.models import CodeFlowResult, Edge, Node


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Strategy for generating a valid node ID (SHA-1-like hex string)
st_node_id = st.text(
    alphabet=string.hexdigits[:16],
    min_size=8,
    max_size=16,
)

# Strategy for generating a clean label (no commas/newlines to avoid ambiguity)
st_label = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters="_",
    ),
    min_size=2,
    max_size=20,
)

# Strategy for generating method names (alphanumeric identifiers)
st_method_name = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters="_",
    ),
    min_size=2,
    max_size=25,
)


@st.composite
def st_node(draw, node_type=None, min_methods=0, max_methods=15):
    """Generate a Node with a given type and random attributes."""
    nid = draw(st_node_id)
    label = draw(st_label)
    ntype = node_type or draw(
        st.sampled_from(["Controller", "Service", "Route", "Middleware", "Repository", "Utility", "Config"])
    )
    description = draw(st.text(min_size=0, max_size=50))
    methods = draw(
        st.lists(st_method_name, min_size=min_methods, max_size=max_methods, unique=True)
    )
    return Node(id=nid, label=label, type=ntype, description=description, method_names=methods)


@st.composite
def st_code_flow_with_controllers(draw):
    """Generate a CodeFlowResult with Controller/Route nodes that have methods,
    plus Service and Middleware nodes connected via edges.

    Guarantees:
    - At least 1 Controller or Route node with at least 1 method
    - 1-3 Service nodes connected to controllers via edges
    - 1-3 Middleware nodes connected to controllers via edges
    """
    # Generate 1-3 Controller/Route nodes with at least 1 method each
    num_controllers = draw(st.integers(min_value=1, max_value=3))
    controllers = [
        draw(st_node(
            node_type=draw(st.sampled_from(["Controller", "Route"])),
            min_methods=1,
            max_methods=15,
        ))
        for _ in range(num_controllers)
    ]

    # Ensure unique IDs for controllers
    for i, ctrl in enumerate(controllers):
        ctrl.id = f"ctrl_{i}_{ctrl.id}"

    # Generate 1-3 Service nodes
    num_services = draw(st.integers(min_value=1, max_value=3))
    services = [
        draw(st_node(node_type="Service", min_methods=0, max_methods=5))
        for _ in range(num_services)
    ]
    for i, svc in enumerate(services):
        svc.id = f"svc_{i}_{svc.id}"

    # Generate 1-3 Middleware nodes
    num_middleware = draw(st.integers(min_value=1, max_value=3))
    middlewares = [
        draw(st_node(node_type="Middleware", min_methods=0, max_methods=5))
        for _ in range(num_middleware)
    ]
    for i, mw in enumerate(middlewares):
        mw.id = f"mw_{i}_{mw.id}"

    # Build edges: each controller connects to at least one service and one middleware
    edges = []
    relation_types = ["calls", "depends_on", "imports"]

    for ctrl in controllers:
        # Connect to at least one service
        target_svc = draw(st.sampled_from(services))
        edges.append(Edge(
            source=ctrl.id,
            target=target_svc.id,
            relation=draw(st.sampled_from(relation_types)),
        ))
        # Connect to at least one middleware
        target_mw = draw(st.sampled_from(middlewares))
        edges.append(Edge(
            source=ctrl.id,
            target=target_mw.id,
            relation=draw(st.sampled_from(relation_types)),
        ))

    all_nodes = controllers + services + middlewares
    return CodeFlowResult(nodes=all_nodes, edges=edges, errors=[])


# ---------------------------------------------------------------------------
# Property Test: Prompt completeness
# ---------------------------------------------------------------------------


class TestProperty1PromptCompleteness:
    """Feature: use-case-generation, Property 1: Prompt completeness"""

    @settings(max_examples=100)
    @given(code_flow=st_code_flow_with_controllers())
    def test_prompt_contains_all_method_names(self, code_flow: CodeFlowResult):
        """The user_prompt SHALL contain every method name from Controller/Route
        nodes that have methods (capped at 15 per controller).

        **Validates: Requirements 1.1, 2.3, 2.4, 6.5**
        """
        generator = Artifacts_Generator(llm_client=None)
        controllers = [n for n in code_flow.nodes if n.type in ("Controller", "Route")]

        # Only consider controllers with methods (the prompt skips those without)
        controllers_with_methods = [c for c in controllers if c.method_names]

        user_prompt = generator._build_use_case_prompt(code_flow, controllers)

        for ctrl in controllers_with_methods:
            for method in ctrl.method_names[:15]:
                assert method in user_prompt, (
                    f"Method '{method}' from controller '{ctrl.label}' "
                    f"not found in user_prompt.\nPrompt:\n{user_prompt}"
                )

    @settings(max_examples=100)
    @given(code_flow=st_code_flow_with_controllers())
    def test_prompt_contains_all_service_labels(self, code_flow: CodeFlowResult):
        """The user_prompt SHALL contain every Service node label that is
        connected to a Controller/Route via edges.

        **Validates: Requirements 1.1, 2.3, 2.4, 6.5**
        """
        generator = Artifacts_Generator(llm_client=None)
        controllers = [n for n in code_flow.nodes if n.type in ("Controller", "Route")]
        controllers_with_methods = [c for c in controllers if c.method_names]

        node_map = {n.id: n for n in code_flow.nodes}
        edges_from: dict[str, list[Edge]] = {}
        for edge in code_flow.edges:
            edges_from.setdefault(edge.source, []).append(edge)

        user_prompt = generator._build_use_case_prompt(code_flow, controllers)

        for ctrl in controllers_with_methods:
            related = edges_from.get(ctrl.id, [])
            service_labels = [
                node_map[e.target].label
                for e in related
                if e.target in node_map and node_map[e.target].type == "Service"
            ]
            for label in service_labels:
                assert label in user_prompt, (
                    f"Service label '{label}' connected to controller "
                    f"'{ctrl.label}' not found in user_prompt.\nPrompt:\n{user_prompt}"
                )

    @settings(max_examples=100)
    @given(code_flow=st_code_flow_with_controllers())
    def test_prompt_contains_all_middleware_labels(self, code_flow: CodeFlowResult):
        """The user_prompt SHALL contain every Middleware node label that is
        connected to a Controller/Route via edges.

        **Validates: Requirements 1.1, 2.3, 2.4, 6.5**
        """
        generator = Artifacts_Generator(llm_client=None)
        controllers = [n for n in code_flow.nodes if n.type in ("Controller", "Route")]
        controllers_with_methods = [c for c in controllers if c.method_names]

        node_map = {n.id: n for n in code_flow.nodes}
        edges_from: dict[str, list[Edge]] = {}
        for edge in code_flow.edges:
            edges_from.setdefault(edge.source, []).append(edge)

        user_prompt = generator._build_use_case_prompt(code_flow, controllers)

        for ctrl in controllers_with_methods:
            related = edges_from.get(ctrl.id, [])
            middleware_labels = [
                node_map[e.target].label
                for e in related
                if e.target in node_map and node_map[e.target].type == "Middleware"
            ]
            for label in middleware_labels:
                assert label in user_prompt, (
                    f"Middleware label '{label}' connected to controller "
                    f"'{ctrl.label}' not found in user_prompt.\nPrompt:\n{user_prompt}"
                )
