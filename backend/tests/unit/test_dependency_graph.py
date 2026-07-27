"""Unit tests for the DependencyGraph class.

Validates Requirements: 2.1, 2.2, 2.3, 2.4, 3.4
"""

from __future__ import annotations

import pytest

from dev_ghost_parser.dependency_graph import (
    AgentStatus,
    CyclicDependencyError,
    DependencyGraph,
)


# ---------------------------------------------------------------------------
# Tests: add_agent
# ---------------------------------------------------------------------------


class TestAddAgent:
    """Tests for add_agent() method."""

    def test_add_single_agent_no_deps(self):
        """An agent with no dependencies has in-degree 0."""
        graph = DependencyGraph()
        graph.add_agent("ast_analyzer", [])
        assert "ast_analyzer" in graph.agents
        assert graph.get_status("ast_analyzer") == AgentStatus.PENDING

    def test_add_agent_with_dependencies(self):
        """An agent with dependencies should track them correctly."""
        graph = DependencyGraph()
        graph.add_agent("ast_analyzer", [])
        graph.add_agent("er_extractor", ["ast_analyzer"])
        assert graph.get_dependencies("er_extractor") == ["ast_analyzer"]
        assert "er_extractor" in graph.get_dependents("ast_analyzer")

    def test_add_multiple_agents_chain(self):
        """A chain of dependencies A -> B -> C."""
        graph = DependencyGraph()
        graph.add_agent("a", [])
        graph.add_agent("b", ["a"])
        graph.add_agent("c", ["b"])
        assert graph.get_dependencies("c") == ["b"]
        assert "c" in graph.get_dependents("b")
        assert "b" in graph.get_dependents("a")

    def test_add_agent_creates_missing_dependency_nodes(self):
        """If a dependency hasn't been added yet, it's auto-created."""
        graph = DependencyGraph()
        graph.add_agent("b", ["a"])
        assert "a" in graph.agents
        assert "b" in graph.agents


# ---------------------------------------------------------------------------
# Tests: validate (cycle detection)
# ---------------------------------------------------------------------------


class TestValidate:
    """Tests for validate() cycle detection."""

    def test_valid_dag_no_error(self):
        """A valid DAG should not raise."""
        graph = DependencyGraph()
        graph.add_agent("a", [])
        graph.add_agent("b", ["a"])
        graph.add_agent("c", ["a"])
        graph.add_agent("d", ["b", "c"])
        graph.validate()  # Should not raise

    def test_simple_cycle_raises(self):
        """A simple A -> B -> A cycle should raise CyclicDependencyError."""
        graph = DependencyGraph()
        graph.add_agent("a", ["b"])
        graph.add_agent("b", ["a"])
        with pytest.raises(CyclicDependencyError):
            graph.validate()

    def test_self_loop_raises(self):
        """An agent depending on itself should raise CyclicDependencyError."""
        graph = DependencyGraph()
        graph.add_agent("a", ["a"])
        with pytest.raises(CyclicDependencyError):
            graph.validate()

    def test_indirect_cycle_raises(self):
        """A -> B -> C -> A should raise CyclicDependencyError."""
        graph = DependencyGraph()
        graph.add_agent("a", ["c"])
        graph.add_agent("b", ["a"])
        graph.add_agent("c", ["b"])
        with pytest.raises(CyclicDependencyError):
            graph.validate()

    def test_empty_graph_valid(self):
        """An empty graph is valid."""
        graph = DependencyGraph()
        graph.validate()  # Should not raise

    def test_single_node_no_deps_valid(self):
        """A single node with no deps is valid."""
        graph = DependencyGraph()
        graph.add_agent("x", [])
        graph.validate()

    def test_diamond_dag_valid(self):
        """A diamond shape (A -> B, A -> C, B -> D, C -> D) is a valid DAG."""
        graph = DependencyGraph()
        graph.add_agent("a", [])
        graph.add_agent("b", ["a"])
        graph.add_agent("c", ["a"])
        graph.add_agent("d", ["b", "c"])
        graph.validate()  # Should not raise


# ---------------------------------------------------------------------------
# Tests: get_ready_agents
# ---------------------------------------------------------------------------


class TestGetReadyAgents:
    """Tests for get_ready_agents() method."""

    def test_all_roots_are_ready(self):
        """Agents with no dependencies are immediately ready."""
        graph = DependencyGraph()
        graph.add_agent("a", [])
        graph.add_agent("b", [])
        graph.add_agent("c", ["a"])
        ready = graph.get_ready_agents(completed=set())
        assert sorted(ready) == ["a", "b"]

    def test_agent_ready_after_deps_complete(self):
        """An agent becomes ready when all its deps are in the completed set."""
        graph = DependencyGraph()
        graph.add_agent("a", [])
        graph.add_agent("b", ["a"])
        graph.add_agent("c", ["a", "b"])

        # Initially only 'a' is ready
        ready = graph.get_ready_agents(completed=set())
        assert ready == ["a"]

        # After 'a' completes, 'b' becomes ready
        graph.mark_completed("a")
        ready = graph.get_ready_agents(completed={"a"})
        assert ready == ["b"]

        # After 'b' completes, 'c' becomes ready
        graph.mark_completed("b")
        ready = graph.get_ready_agents(completed={"a", "b"})
        assert ready == ["c"]

    def test_no_agents_ready_if_deps_pending(self):
        """If deps haven't completed, the agent is not ready."""
        graph = DependencyGraph()
        graph.add_agent("a", [])
        graph.add_agent("b", ["a"])
        ready = graph.get_ready_agents(completed=set())
        assert "b" not in ready

    def test_completed_agents_not_returned(self):
        """Already completed agents should not appear in ready list."""
        graph = DependencyGraph()
        graph.add_agent("a", [])
        graph.mark_completed("a")
        ready = graph.get_ready_agents(completed={"a"})
        assert ready == []

    def test_failed_agents_not_returned(self):
        """Failed agents should not appear in ready list."""
        graph = DependencyGraph()
        graph.add_agent("a", [])
        graph.mark_failed("a")
        ready = graph.get_ready_agents(completed=set())
        assert ready == []


# ---------------------------------------------------------------------------
# Tests: mark_completed
# ---------------------------------------------------------------------------


class TestMarkCompleted:
    """Tests for mark_completed() method."""

    def test_marks_status_completed(self):
        """mark_completed sets status to COMPLETED."""
        graph = DependencyGraph()
        graph.add_agent("a", [])
        graph.mark_completed("a")
        assert graph.get_status("a") == AgentStatus.COMPLETED

    def test_mark_nonexistent_agent_no_error(self):
        """Marking a nonexistent agent should not raise."""
        graph = DependencyGraph()
        graph.mark_completed("nonexistent")  # Should not raise


# ---------------------------------------------------------------------------
# Tests: mark_failed (transitive failure propagation)
# ---------------------------------------------------------------------------


class TestMarkFailed:
    """Tests for mark_failed() and transitive failure propagation."""

    def test_marks_status_failed(self):
        """mark_failed sets the agent status to FAILED."""
        graph = DependencyGraph()
        graph.add_agent("a", [])
        graph.mark_failed("a")
        assert graph.get_status("a") == AgentStatus.FAILED

    def test_direct_dependents_skipped(self):
        """Direct dependents of a failed agent are marked SKIPPED."""
        graph = DependencyGraph()
        graph.add_agent("a", [])
        graph.add_agent("b", ["a"])
        graph.add_agent("c", ["a"])

        skipped = graph.mark_failed("a")
        assert sorted(skipped) == ["b", "c"]
        assert graph.get_status("b") == AgentStatus.SKIPPED
        assert graph.get_status("c") == AgentStatus.SKIPPED

    def test_transitive_dependents_skipped(self):
        """Transitive dependents (A -> B -> C) are all skipped."""
        graph = DependencyGraph()
        graph.add_agent("a", [])
        graph.add_agent("b", ["a"])
        graph.add_agent("c", ["b"])

        skipped = graph.mark_failed("a")
        assert sorted(skipped) == ["b", "c"]
        assert graph.get_status("b") == AgentStatus.SKIPPED
        assert graph.get_status("c") == AgentStatus.SKIPPED

    def test_independent_agents_not_affected(self):
        """Agents not depending on the failed agent remain PENDING."""
        graph = DependencyGraph()
        graph.add_agent("a", [])
        graph.add_agent("b", ["a"])
        graph.add_agent("c", [])  # Independent

        skipped = graph.mark_failed("a")
        assert skipped == ["b"]
        assert graph.get_status("c") == AgentStatus.PENDING

    def test_already_completed_agents_not_skipped(self):
        """Agents that already completed are not affected by failure propagation."""
        graph = DependencyGraph()
        graph.add_agent("a", [])
        graph.add_agent("b", ["a"])
        graph.add_agent("c", ["b"])

        graph.mark_completed("b")
        skipped = graph.mark_failed("a")
        # 'b' is already COMPLETED, so only 'c' (which depends on 'b') might be skipped
        # But 'c' is a dependent of 'b', not directly of 'a', so it's only reached via 'b'
        # Since 'b' is COMPLETED (not PENDING), the BFS doesn't propagate through it
        assert "b" not in skipped

    def test_diamond_failure_propagation(self):
        """In a diamond (A -> B, A -> C, B -> D, C -> D), failing A skips all."""
        graph = DependencyGraph()
        graph.add_agent("a", [])
        graph.add_agent("b", ["a"])
        graph.add_agent("c", ["a"])
        graph.add_agent("d", ["b", "c"])

        skipped = graph.mark_failed("a")
        assert sorted(skipped) == ["b", "c", "d"]

    def test_mark_nonexistent_agent_returns_empty(self):
        """Marking a nonexistent agent as failed returns empty list."""
        graph = DependencyGraph()
        result = graph.mark_failed("nonexistent")
        assert result == []
