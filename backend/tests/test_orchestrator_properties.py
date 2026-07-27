# Feature: sub-agent-parallel-analysis, Property 4: AST Context Propagation
# Feature: sub-agent-parallel-analysis, Property 5: AST Failure Aborts Pipeline
"""
Property-based tests for DependencyGraphOrchestrator.

Tests orchestrator behavior using randomly generated agent results and retry policies:
- Property 4: All downstream agents receive full AST result in their context
- Property 5: When AST fails all retries, zero downstream agents execute

Validates: Requirements 1.2, 1.4, 3.3, 1.3, 4.4
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.agent_models import AgentEvent, AgentResult
from dev_ghost_parser.base_agent import AgentContext, BaseAgent
from dev_ghost_parser.graph_orchestrator import (
    DependencyGraphOrchestrator,
    FoundationalPhaseError,
)
from dev_ghost_parser.retry_policy import RetryPolicy


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for generating random AST result data (arbitrary nested dicts)
ast_result_data = st.fixed_dictionaries(
    {},
    optional={
        "nodes": st.lists(st.text(min_size=1, max_size=20), max_size=10),
        "edges": st.lists(
            st.fixed_dictionaries(
                {"src": st.text(min_size=1, max_size=10), "dst": st.text(min_size=1, max_size=10)}
            ),
            max_size=10,
        ),
        "components": st.dictionaries(
            st.text(min_size=1, max_size=10),
            st.integers(min_value=0, max_value=100),
            max_size=5,
        ),
        "metadata": st.fixed_dictionaries(
            {},
            optional={
                "file_count": st.integers(min_value=1, max_value=1000),
                "language": st.sampled_from(["python", "typescript", "java", "rust"]),
            },
        ),
    },
)

# Strategy for number of downstream agents
num_downstream_agents = st.integers(min_value=1, max_value=6)

# Strategy for generating random retry policies (for Property 5)
retry_policies = st.builds(
    RetryPolicy,
    max_retries=st.integers(min_value=0, max_value=5),
    base_delay_seconds=st.floats(min_value=0.001, max_value=0.01),
    multiplier=st.floats(min_value=1.5, max_value=3.0),
)


# ---------------------------------------------------------------------------
# Mock Agent Classes
# ---------------------------------------------------------------------------


class MockASTAgent(BaseAgent):
    """Mock AST agent that returns a predetermined result."""

    name = "ast_analyzer"
    description = "Mock AST analyzer"

    def __init__(self, result_data: Any, retry_pol: RetryPolicy | None = None) -> None:
        super().__init__()
        self._result_data = result_data
        self._retry_pol = retry_pol or RetryPolicy(
            max_retries=0, base_delay_seconds=0.01, multiplier=1.5
        )

    @property
    def timeout_seconds(self) -> float:
        return 10.0

    @property
    def retry_policy(self) -> RetryPolicy:
        return self._retry_pol

    async def execute(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            agent_name="ast_analyzer",
            success=True,
            data=self._result_data,
            duration_ms=10,
        )


class MockFailingASTAgent(BaseAgent):
    """Mock AST agent that always raises an exception."""

    name = "ast_analyzer"
    description = "Mock failing AST analyzer"

    def __init__(self, retry_pol: RetryPolicy) -> None:
        super().__init__()
        self._retry_pol = retry_pol
        self.execution_count = 0

    @property
    def timeout_seconds(self) -> float:
        return 10.0

    @property
    def retry_policy(self) -> RetryPolicy:
        return self._retry_pol

    async def execute(self, context: AgentContext) -> AgentResult:
        self.execution_count += 1
        raise RuntimeError("AST analysis failed permanently")


class MockDownstreamAgent(BaseAgent):
    """Mock downstream agent that captures the context it receives."""

    description = "Mock downstream agent"

    def __init__(self, agent_name: str) -> None:
        super().__init__()
        self.name = agent_name
        self.received_context: AgentContext | None = None
        self.execution_count = 0

    @property
    def timeout_seconds(self) -> float:
        return 10.0

    @property
    def retry_policy(self) -> RetryPolicy:
        return RetryPolicy(max_retries=0, base_delay_seconds=0.01, multiplier=1.5)

    async def execute(self, context: AgentContext) -> AgentResult:
        self.received_context = context
        self.execution_count += 1
        return AgentResult(
            agent_name=self.name,
            success=True,
            data={"processed": True},
            duration_ms=5,
        )


# ---------------------------------------------------------------------------
# Property 4: AST Context Propagation
# ---------------------------------------------------------------------------


@given(result_data=ast_result_data, n_agents=num_downstream_agents)
@settings(max_examples=100, deadline=None)
def test_property_4_ast_context_propagation(result_data, n_agents):
    """
    **Validates: Requirements 1.2, 1.4, 3.3**

    For any set of downstream agents and a successful AST result, when the
    orchestrator passes context to each downstream agent, every downstream
    agent's context.dependency_results SHALL contain the full AST AgentResult data.
    """

    async def _run():
        event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        mock_llm = MagicMock()

        orchestrator = DependencyGraphOrchestrator(
            repo_path="/tmp/test_repo",
            llm_client=mock_llm,
            event_queue=event_queue,
            max_concurrency=5,
            global_timeout_seconds=30.0,
        )

        # Register the AST agent with the generated result data
        ast_agent = MockASTAgent(result_data=result_data)
        orchestrator.register_agent(ast_agent)

        # Create and register N downstream agents
        downstream_agents: list[MockDownstreamAgent] = []
        for i in range(n_agents):
            agent = MockDownstreamAgent(agent_name=f"downstream_{i}")
            downstream_agents.append(agent)
            orchestrator.register_agent(agent)

        # Run the pipeline
        await orchestrator.run_pipeline()

        # Verify: each downstream agent received the full AST result in context
        for agent in downstream_agents:
            assert agent.received_context is not None, (
                f"Agent '{agent.name}' did not receive a context"
            )
            assert "ast_analyzer" in agent.received_context.dependency_results, (
                f"Agent '{agent.name}' context missing 'ast_analyzer' in dependency_results"
            )

            ast_dep_result = agent.received_context.dependency_results["ast_analyzer"]

            # Verify it's the full AgentResult
            assert isinstance(ast_dep_result, AgentResult), (
                f"Agent '{agent.name}' received non-AgentResult for ast_analyzer"
            )
            assert ast_dep_result.agent_name == "ast_analyzer"
            assert ast_dep_result.success is True
            assert ast_dep_result.data == result_data, (
                f"Agent '{agent.name}' received different AST data.\n"
                f"  Expected: {result_data}\n"
                f"  Got: {ast_dep_result.data}"
            )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Property 5: AST Failure Aborts Pipeline
# ---------------------------------------------------------------------------


@given(retry_pol=retry_policies)
@settings(max_examples=100, deadline=None)
def test_property_5_ast_failure_aborts_pipeline(retry_pol):
    """
    **Validates: Requirements 1.3, 4.4**

    For any retry policy configuration, if the AST_Analyzer fails on every
    attempt (initial + retries), the orchestrator SHALL execute zero downstream
    agents and raise a FoundationalPhaseError.
    """

    async def _run():
        event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        mock_llm = MagicMock()

        orchestrator = DependencyGraphOrchestrator(
            repo_path="/tmp/test_repo",
            llm_client=mock_llm,
            event_queue=event_queue,
            max_concurrency=5,
            global_timeout_seconds=30.0,
        )

        # Register a failing AST agent with the generated retry policy
        ast_agent = MockFailingASTAgent(retry_pol=retry_pol)
        orchestrator.register_agent(ast_agent)

        # Create downstream agents with execution counters
        downstream_agents: list[MockDownstreamAgent] = []
        for i in range(3):
            agent = MockDownstreamAgent(agent_name=f"downstream_{i}")
            downstream_agents.append(agent)
            orchestrator.register_agent(agent)

        # Run the pipeline — should raise FoundationalPhaseError
        pipeline_raised = False
        try:
            await orchestrator.run_pipeline()
        except FoundationalPhaseError:
            pipeline_raised = True

        # Verify: pipeline raised FoundationalPhaseError
        assert pipeline_raised, (
            "run_pipeline() should raise FoundationalPhaseError when AST fails all retries"
        )

        # Verify: zero downstream agents were executed
        for agent in downstream_agents:
            assert agent.execution_count == 0, (
                f"Downstream agent '{agent.name}' was executed {agent.execution_count} times "
                f"but should have been 0 (AST failed, pipeline aborted)"
            )

        # Verify: AST agent was attempted exactly max_retries + 1 times
        expected_attempts = retry_pol.max_retries + 1
        assert ast_agent.execution_count == expected_attempts, (
            f"AST agent executed {ast_agent.execution_count} times "
            f"but expected {expected_attempts} (1 initial + {retry_pol.max_retries} retries)"
        )

    asyncio.run(_run())
