"""Dependency graph for managing agent execution order.

Implements a directed acyclic graph (DAG) that models dependencies between
sub-agents. Provides cycle detection via DFS-based topological sort and
transitive failure propagation via BFS on dependents.

Satisfies Requirements: 2.1, 2.2, 2.3, 2.4, 3.4
"""

from __future__ import annotations

from collections import deque
from enum import Enum, auto


class CyclicDependencyError(Exception):
    """Raised when the dependency graph contains a cycle."""

    def __init__(self, cycle: list[str] | None = None) -> None:
        if cycle:
            path = " -> ".join(cycle)
            super().__init__(f"Cyclic dependency detected: {path}")
        else:
            super().__init__("Cyclic dependency detected in the agent graph")
        self.cycle = cycle


class AgentStatus(Enum):
    """Execution status of an agent within the graph."""

    PENDING = auto()
    COMPLETED = auto()
    FAILED = auto()
    SKIPPED = auto()


class DependencyGraph:
    """DAG structure for managing agent execution order.

    The graph tracks:
    - Which agents depend on which other agents (adjacency list of dependents).
    - In-degree counts for determining ready agents.
    - Agent statuses (pending, completed, failed, skipped).

    Usage:
        graph = DependencyGraph()
        graph.add_agent("ast_analyzer", [])
        graph.add_agent("er_extractor", ["ast_analyzer"])
        graph.validate()  # raises CyclicDependencyError if cycle exists
        ready = graph.get_ready_agents(completed=set())
    """

    def __init__(self) -> None:
        # agent -> set of agents that depend ON this agent (dependents/children)
        self._adjacency: dict[str, set[str]] = {}
        # agent -> number of unresolved dependencies
        self._in_degree: dict[str, int] = {}
        # agent -> list of its declared dependencies (parents)
        self._dependencies: dict[str, list[str]] = {}
        # agent -> current status
        self._status: dict[str, AgentStatus] = {}

    @property
    def agents(self) -> list[str]:
        """Return list of all registered agent names."""
        return list(self._adjacency.keys())

    def add_agent(self, name: str, dependencies: list[str]) -> None:
        """Register an agent with its declared dependencies.

        Args:
            name: Unique agent identifier.
            dependencies: List of agent names that must complete before this agent.

        The agent is added to the graph. Edges are created from each dependency
        to this agent (dependency -> this agent is a dependent).
        """
        if name not in self._adjacency:
            self._adjacency[name] = set()
            self._in_degree[name] = 0
            self._status[name] = AgentStatus.PENDING

        self._dependencies[name] = list(dependencies)

        for dep in dependencies:
            # Ensure the dependency node exists
            if dep not in self._adjacency:
                self._adjacency[dep] = set()
                self._in_degree[dep] = 0
                self._status[dep] = AgentStatus.PENDING

            # Add edge: dep -> name (name depends on dep, so dep has name as dependent)
            if name not in self._adjacency[dep]:
                self._adjacency[dep].add(name)
                self._in_degree[name] += 1

    def validate(self) -> None:
        """Validate that the graph contains no cycles.

        Uses DFS-based cycle detection (coloring approach):
        - WHITE (0): unvisited
        - GRAY (1): currently in recursion stack (visiting)
        - BLACK (2): fully processed

        Raises:
            CyclicDependencyError: If a cycle is detected in the graph.
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {node: WHITE for node in self._adjacency}
        path: list[str] = []

        def dfs(node: str) -> list[str] | None:
            color[node] = GRAY
            path.append(node)

            for neighbor in self._adjacency[node]:
                if color[neighbor] == GRAY:
                    # Found a cycle - extract the cycle from path
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    return cycle
                if color[neighbor] == WHITE:
                    result = dfs(neighbor)
                    if result is not None:
                        return result

            path.pop()
            color[node] = BLACK
            return None

        for node in self._adjacency:
            if color[node] == WHITE:
                cycle = dfs(node)
                if cycle is not None:
                    raise CyclicDependencyError(cycle)

    def get_ready_agents(self, completed: set[str]) -> list[str]:
        """Return agents whose dependencies are all resolved.

        An agent is ready if:
        - Its status is PENDING (not completed, failed, or skipped).
        - All of its declared dependencies are in the completed set.

        Args:
            completed: Set of agent names that have completed successfully.

        Returns:
            List of agent names that are ready to execute.
        """
        ready = []
        for agent in self._adjacency:
            if self._status[agent] != AgentStatus.PENDING:
                continue
            deps = self._dependencies.get(agent, [])
            if all(dep in completed for dep in deps):
                ready.append(agent)
        return ready

    def mark_completed(self, name: str) -> None:
        """Mark an agent as completed.

        Updates the agent's status to COMPLETED.

        Args:
            name: The agent name to mark as completed.
        """
        if name not in self._status:
            return
        self._status[name] = AgentStatus.COMPLETED

    def mark_failed(self, name: str) -> list[str]:
        """Mark agent as failed and return all transitively dependent agents.

        Uses BFS to find all agents that transitively depend on the failed
        agent. These agents are marked as SKIPPED since their upstream
        dependency cannot be satisfied.

        Args:
            name: The agent name that failed.

        Returns:
            List of all transitively dependent agent names that were skipped.
        """
        if name not in self._status:
            return []

        self._status[name] = AgentStatus.FAILED

        # BFS to find all transitive dependents
        skipped: list[str] = []
        queue: deque[str] = deque()

        # Start BFS from the direct dependents of the failed agent
        for dependent in self._adjacency.get(name, set()):
            if self._status[dependent] == AgentStatus.PENDING:
                queue.append(dependent)

        visited: set[str] = set()
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)

            if self._status[current] == AgentStatus.PENDING:
                self._status[current] = AgentStatus.SKIPPED
                skipped.append(current)

                # Add this agent's dependents to the queue
                for dependent in self._adjacency.get(current, set()):
                    if dependent not in visited:
                        queue.append(dependent)

        return skipped

    def get_status(self, name: str) -> AgentStatus | None:
        """Get the current status of an agent.

        Args:
            name: The agent name.

        Returns:
            The agent's status, or None if the agent is not registered.
        """
        return self._status.get(name)

    def get_dependencies(self, name: str) -> list[str]:
        """Get the declared dependencies of an agent.

        Args:
            name: The agent name.

        Returns:
            List of dependency agent names. Empty list if agent not found.
        """
        return self._dependencies.get(name, [])

    def get_dependents(self, name: str) -> set[str]:
        """Get direct dependents of an agent.

        Args:
            name: The agent name.

        Returns:
            Set of agent names that directly depend on this agent.
        """
        return self._adjacency.get(name, set()).copy()
