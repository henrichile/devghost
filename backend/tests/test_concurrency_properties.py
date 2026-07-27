# Feature: sub-agent-parallel-analysis, Property 14: Concurrency Limit Enforcement
"""
Property-based test for DependencyGraphOrchestrator concurrency limiting.

Verifies that the maximum number of simultaneously executing agents never
exceeds the configured concurrency limit C, for any combination of agent
counts and concurrency settings.

Validates: Requirements 2.5
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.agent_models import AgentEvent, AgentResult
from dev_ghost_parser.base_agent import AgentContext, BaseAgent
from dev_ghost_parser.graph_orchestrator import DependencyGraphOrchestrator
from dev_ghost_parser.retry_policy import RetryPolicy


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Random concurrency limit between 1 and 5
concurrency_limits = st.integers(min_value=1, max_value=5)

# Random number of parallel agents between 2 and 10
num_agents_strategy = st.integers(min_value=2, max_value=10)


# ---------------------------------------------------------------------------
# Mock Agent Classes
# ---------------------------------------------------------------------------


class MockASTAgentForConcurrency(BaseAgent):
    """Mock AST agent that completes immediately."""

    name = "ast_analyzer"
    description = "Mock AST analyzer for concurrency test"

    def __init__(self) -> None:
        super().__init__()

    @property
    def timeout_seconds(self) -> float:
        return 10.0

    @property
    def retry_policy(self) -> RetryPolicy:
        return RetryPolicy(max_retries=0, base_delay_seconds=0.01, multiplier=1.5)

    async def execute(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            agent_name="ast_analyzer",
            success=True,
            data={"ast": "data"},
            duration_ms=5,
        )


class ConcurrencyTrackingAgent(BaseAgent):
    """Mock agent that tracks concurrent execution count using a shared lock and counter.

    Records the peak concurrent execution count observed during its execution.
    Uses asyncio.Lock to protect the shared counter for correctness.
    """

    description = "Concurrency tracking agent"

    def __init__(
        self,
        agent_name: str,
        concurrent_counter: dict[str, int],
        lock: asyncio.Lock,
        peak_tracker: dict[str, int],
    ) -> None:
        super().__init__()
        self.name = agent_name
        self._counter = concurrent_counter  # {"count": N}
        self._lock = lock
        self._peak_tracker = peak_tracker  # {"peak": N}

    @property
    def timeout_seconds(self) -> float:
        return 10.0

    @property
    def retry_policy(self) -> RetryPolicy:
        return RetryPolicy(max_retries=0, base_delay_seconds=0.01, multiplier=1.5)

    async def execute(self, context: AgentContext) -> AgentResult:
        # Increment concurrent count
        async with self._lock:
            self._counter["count"] += 1
            current = self._counter["count"]
            if current > self._peak_tracker["peak"]:
                self._peak_tracker["peak"] = current

        # Simulate work (brief sleep to allow other agents to start concurrently)
        await asyncio.sleep(0.03)

        # Decrement concurrent count
        async with self._lock:
            self._counter["count"] -= 1

        return AgentResult(
            agent_name=self.name,
            success=True,
            data={"processed": True},
            duration_ms=30,
        )


# ---------------------------------------------------------------------------
# Property 14: Concurrency Limit Enforcement
# ---------------------------------------------------------------------------


@given(
    max_concurrency=concurrency_limits,
    num_agents=num_agents_strategy,
)
@settings(max_examples=100, deadline=None)
def test_property_14_concurrency_limit_enforcement(max_concurrency: int, num_agents: int):
    """
    **Validates: Requirements 2.5**

    For any configured concurrency limit C and any number of agents N,
    the number of simultaneously executing agents at any point in time
    SHALL never exceed C.
    """

    async def _run():
        event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        mock_llm = MagicMock()

        orchestrator = DependencyGraphOrchestrator(
            repo_path="/tmp/test_repo",
            llm_client=mock_llm,
            event_queue=event_queue,
            max_concurrency=max_concurrency,
            global_timeout_seconds=30.0,
        )

        # Register the AST agent (foundational phase)
        ast_agent = MockASTAgentForConcurrency()
        orchestrator.register_agent(ast_agent)

        # Shared concurrency tracking state (protected by asyncio.Lock)
        lock = asyncio.Lock()
        concurrent_counter = {"count": 0}
        peak_tracker = {"peak": 0}

        # Create N downstream agents (all independent — depend only on AST)
        for i in range(num_agents):
            agent = ConcurrencyTrackingAgent(
                agent_name=f"downstream_{i}",
                concurrent_counter=concurrent_counter,
                lock=lock,
                peak_tracker=peak_tracker,
            )
            orchestrator.register_agent(agent)

        # Run the pipeline
        result = await orchestrator.run_pipeline()

        # Verify: the peak concurrent execution count never exceeded the limit
        assert peak_tracker["peak"] <= max_concurrency, (
            f"Concurrency limit violated! "
            f"Peak concurrent agents: {peak_tracker['peak']}, "
            f"Configured limit: {max_concurrency}, "
            f"Total agents: {num_agents}"
        )

        # Verify: all agents completed successfully
        # (metadata should show all agents ran)
        assert result.metadata is not None
        assert len(result.metadata.failed_agents) == 0, (
            f"Some agents failed unexpectedly: {result.metadata.failed_agents}"
        )

    asyncio.run(_run())
