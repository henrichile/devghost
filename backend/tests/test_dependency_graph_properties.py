# Feature: sub-agent-parallel-analysis, Property 1: DAG Cycle Detection
# Feature: sub-agent-parallel-analysis, Property 2: Ready-Set Computation
# Feature: sub-agent-parallel-analysis, Property 3: Transitive Failure Propagation
"""
Property-based tests for DependencyGraph.

Tests the core graph operations using randomly generated directed graphs:
- Property 1: Cycle detection correctness
- Property 2: Ready-set computation correctness
- Property 3: Transitive failure propagation correctness

Validates: Requirements 2.2, 2.3, 3.2, 3.4
"""

from __future__ import annotations

from collections import deque

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from dev_ghost_parser.dependency_graph import (
    AgentStatus,
    CyclicDependencyError,
    DependencyGraph,
)


# ---------------------------------------------------------------------------
# Strategies: Graph Generation
# ---------------------------------------------------------------------------

# Agent name strategy: short identifiers
agent_names = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz",
    min_size=1,
    max_size=6,
)


@st.composite
def acyclic_graphs(draw):
    """Generate a random DAG by creating nodes in topological order.

    Nodes are generated in a fixed order; edges only point from earlier
    nodes to later nodes, guaranteeing acyclicity.
    """
    num_nodes = draw(st.integers(min_value=1, max_value=12))
    # Generate unique node names
    names = []
    for i in range(num_nodes):
        name = f"agent_{i}"
        names.append(name)

    # For each node (except the first), randomly pick dependencies from earlier nodes
    adjacency: dict[str, list[str]] = {}
    for i, name in enumerate(names):
        if i == 0:
            adjacency[name] = []
        else:
            # Pick a random subset of earlier nodes as dependencies
            possible_deps = names[:i]
            deps = draw(
                st.lists(
                    st.sampled_from(possible_deps),
                    min_size=0,
                    max_size=min(3, len(possible_deps)),
                    unique=True,
                )
            )
            adjacency[name] = deps

    return adjacency


@st.composite
def cyclic_graphs(draw):
    """Generate a random directed graph that contains at least one cycle.

    Strategy: generate an acyclic graph first, then add a back-edge
    from a later node to an earlier node to create a cycle.
    """
    num_nodes = draw(st.integers(min_value=2, max_value=10))
    names = [f"agent_{i}" for i in range(num_nodes)]

    # Build a base acyclic graph
    adjacency: dict[str, list[str]] = {}
    for i, name in enumerate(names):
        if i == 0:
            adjacency[name] = []
        else:
            possible_deps = names[:i]
            deps = draw(
                st.lists(
                    st.sampled_from(possible_deps),
                    min_size=0,
                    max_size=min(2, len(possible_deps)),
                    unique=True,
                )
            )
            adjacency[name] = deps

    # Add a back-edge to create a cycle: pick a later node and make an earlier node depend on it
    # This means we need to add a dependency from an earlier node to a later node
    # Actually, to create a cycle: pick node_i (earlier) and node_j (later, j > i)
    # and add node_j as a dependency of node_i (back-edge)
    earlier_idx = draw(st.integers(min_value=0, max_value=num_nodes - 2))
    later_idx = draw(st.integers(min_value=earlier_idx + 1, max_value=num_nodes - 1))

    # Add the back-edge: earlier node now depends on later node
    back_dep = names[later_idx]
    if back_dep not in adjacency[names[earlier_idx]]:
        adjacency[names[earlier_idx]].append(back_dep)

    return adjacency


@st.composite
def dag_with_completed_set(draw):
    """Generate a valid DAG and a random subset of nodes as 'completed'."""
    adjacency = draw(acyclic_graphs())
    all_names = list(adjacency.keys())

    # Pick a random subset as completed (respecting topological order so it's realistic)
    # For simplicity, just pick a random subset — the test validates correctness regardless
    completed = draw(
        st.lists(
            st.sampled_from(all_names),
            min_size=0,
            max_size=len(all_names),
            unique=True,
        )
    )

    return adjacency, set(completed)


@st.composite
def dag_with_failure_point(draw):
    """Generate a valid DAG and pick a random node as the failure point."""
    adjacency = draw(acyclic_graphs())
    all_names = list(adjacency.keys())

    failure_node = draw(st.sampled_from(all_names))

    return adjacency, failure_node


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def build_graph(adjacency: dict[str, list[str]]) -> DependencyGraph:
    """Build a DependencyGraph from an adjacency dict (node -> dependencies)."""
    graph = DependencyGraph()
    for name, deps in adjacency.items():
        graph.add_agent(name, deps)
    return graph


def compute_expected_ready_set(
    adjacency: dict[str, list[str]],
    completed: set[str],
    failed_or_skipped: set[str],
) -> set[str]:
    """Compute the expected ready set independently from the DependencyGraph.

    An agent is ready if:
    - It is not completed, failed, or skipped
    - All its dependencies are in the completed set
    """
    ready = set()
    for agent, deps in adjacency.items():
        if agent in completed or agent in failed_or_skipped:
            continue
        if all(dep in completed for dep in deps):
            ready.add(agent)
    return ready


def compute_transitive_dependents(
    adjacency: dict[str, list[str]], failed_node: str
) -> set[str]:
    """Compute all nodes transitively reachable from failed_node via dependent edges.

    We build a reverse mapping: for each node, find which other nodes depend on it
    (i.e., which nodes list it as a dependency). Then BFS from the failed node
    through these 'dependent' edges.
    """
    # Build forward adjacency: node -> set of direct dependents
    # (nodes that list this node as a dependency)
    dependents_of: dict[str, set[str]] = {name: set() for name in adjacency}
    for name, deps in adjacency.items():
        for dep in deps:
            if dep in dependents_of:
                dependents_of[dep].add(name)

    # BFS from failed_node through dependents
    visited: set[str] = set()
    queue: deque[str] = deque()

    for dependent in dependents_of.get(failed_node, set()):
        queue.append(dependent)

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        for dependent in dependents_of.get(current, set()):
            if dependent not in visited:
                queue.append(dependent)

    return visited


# ---------------------------------------------------------------------------
# Property 1: DAG Cycle Detection
# ---------------------------------------------------------------------------


@given(adjacency=acyclic_graphs())
@settings(max_examples=100)
def test_property_1_acyclic_graph_validates_successfully(adjacency):
    """
    **Validates: Requirements 2.2**

    For any acyclic directed graph (nodes added in topological order with
    edges only pointing forward), validate() must NOT raise CyclicDependencyError.
    """
    graph = build_graph(adjacency)
    # Should not raise for a valid DAG
    graph.validate()


@given(adjacency=cyclic_graphs())
@settings(max_examples=100)
def test_property_1_cyclic_graph_raises_error(adjacency):
    """
    **Validates: Requirements 2.2**

    For any directed graph that contains at least one back-edge (creating a cycle),
    validate() MUST raise CyclicDependencyError.
    """
    graph = build_graph(adjacency)
    try:
        graph.validate()
        # If validate() didn't raise, the graph might not actually be cyclic
        # (our strategy guarantees a cycle, so this shouldn't happen)
        # Verify independently that a cycle exists
        assert not _has_cycle(adjacency), (
            "Graph has a cycle but validate() did not raise"
        )
    except CyclicDependencyError:
        pass  # Expected behavior


def _has_cycle(adjacency: dict[str, list[str]]) -> bool:
    """Independent cycle detection using DFS coloring."""
    # Build the forward adjacency (node -> set of nodes it points to)
    # In our representation, adjacency[node] = dependencies (parents)
    # The DependencyGraph stores edges as dep -> dependent
    # So the actual graph edges are: for each (node, deps), dep -> node
    forward: dict[str, set[str]] = {name: set() for name in adjacency}
    for name, deps in adjacency.items():
        for dep in deps:
            if dep in forward:
                forward[dep].add(name)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in forward}

    def dfs(node: str) -> bool:
        color[node] = GRAY
        for neighbor in forward[node]:
            if color[neighbor] == GRAY:
                return True
            if color[neighbor] == WHITE and dfs(neighbor):
                return True
        color[node] = BLACK
        return False

    for node in forward:
        if color[node] == WHITE:
            if dfs(node):
                return True
    return False


# ---------------------------------------------------------------------------
# Property 2: Ready-Set Computation
# ---------------------------------------------------------------------------


@given(data=dag_with_completed_set())
@settings(max_examples=100)
def test_property_2_ready_set_computation(data):
    """
    **Validates: Requirements 2.3, 3.2**

    For any valid DAG and any subset of nodes marked as 'completed',
    get_ready_agents(completed) must return exactly the set of agents whose
    declared dependencies are ALL in the completed set and who are not
    themselves completed, failed, or skipped.
    """
    adjacency, completed = data

    graph = build_graph(adjacency)
    graph.validate()  # Ensure it's a valid DAG

    # Mark completed agents in the graph
    for agent in completed:
        graph.mark_completed(agent)

    # Get ready agents from the implementation
    actual_ready = set(graph.get_ready_agents(completed=completed))

    # Compute expected ready set independently
    expected_ready = compute_expected_ready_set(
        adjacency, completed, failed_or_skipped=set()
    )

    assert actual_ready == expected_ready, (
        f"Ready set mismatch.\n"
        f"  Adjacency: {adjacency}\n"
        f"  Completed: {completed}\n"
        f"  Expected ready: {expected_ready}\n"
        f"  Actual ready: {actual_ready}"
    )


# ---------------------------------------------------------------------------
# Property 3: Transitive Failure Propagation
# ---------------------------------------------------------------------------


@given(data=dag_with_failure_point())
@settings(max_examples=100)
def test_property_3_transitive_failure_propagation(data):
    """
    **Validates: Requirements 3.4**

    For any valid DAG and any node marked as failed:
    1. All agents transitively reachable from the failed agent (via dependent edges)
       must be returned as skipped.
    2. No agent that is NOT transitively dependent on the failed agent should be affected.
    """
    adjacency, failure_node = data

    graph = build_graph(adjacency)
    graph.validate()  # Ensure it's a valid DAG

    # Mark the node as failed and get the skipped list
    actual_skipped = set(graph.mark_failed(failure_node))

    # Compute expected transitive dependents independently
    expected_skipped = compute_transitive_dependents(adjacency, failure_node)

    # The failed node itself should NOT be in the skipped list (it's FAILED, not SKIPPED)
    assert failure_node not in actual_skipped, (
        f"The failed node '{failure_node}' should not be in the skipped list"
    )

    # All transitively dependent agents should be skipped
    assert actual_skipped == expected_skipped, (
        f"Transitive failure propagation mismatch.\n"
        f"  Adjacency: {adjacency}\n"
        f"  Failed node: {failure_node}\n"
        f"  Expected skipped: {expected_skipped}\n"
        f"  Actual skipped: {actual_skipped}"
    )

    # Verify that the failed node has FAILED status
    assert graph.get_status(failure_node) == AgentStatus.FAILED

    # Verify all skipped agents have SKIPPED status
    for agent in actual_skipped:
        assert graph.get_status(agent) == AgentStatus.SKIPPED, (
            f"Agent '{agent}' should have SKIPPED status but has {graph.get_status(agent)}"
        )

    # Verify no independent agent is affected
    all_agents = set(adjacency.keys())
    independent_agents = all_agents - expected_skipped - {failure_node}
    for agent in independent_agents:
        assert graph.get_status(agent) == AgentStatus.PENDING, (
            f"Independent agent '{agent}' should remain PENDING but has "
            f"{graph.get_status(agent)}"
        )
