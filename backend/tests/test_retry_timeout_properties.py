# Feature: sub-agent-parallel-analysis, Property 6: Retry Count Adherence
# Feature: sub-agent-parallel-analysis, Property 7: Exponential Backoff Delay Computation
# Feature: sub-agent-parallel-analysis, Property 15: Timeout Triggers Cancellation and Retry
"""
Property-based tests for retry and timeout behavior.

Tests the retry/timeout mechanisms using randomly generated configurations:
- Property 6: Total attempts = max_retries + 1 when agent always fails
- Property 7: Exponential backoff delay = base * (multiplier ** attempt)
- Property 15: Timeout triggers cancellation and retry is applied

Validates: Requirements 4.1, 4.2, 4.3, 7.2
"""

from __future__ import annotations

import asyncio
import math
from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.agent_models import AgentResult
from dev_ghost_parser.base_agent import AgentContext, BaseAgent
from dev_ghost_parser.graph_orchestrator import DependencyGraphOrchestrator
from dev_ghost_parser.retry_policy import RetryPolicy


# ---------------------------------------------------------------------------
# Mock Agents
# ---------------------------------------------------------------------------


class AlwaysFailingAgent(BaseAgent):
    """A mock agent that always raises an exception and counts attempts."""

    def __init__(self, name: str, max_retries: int) -> None:
        super().__init__()
        self.name = name
        self.description = f"Mock failing agent: {name}"
        self._max_retries = max_retries
        self._attempts = 0

    @property
    def retry_policy(self) -> RetryPolicy:
        return RetryPolicy(
            max_retries=self._max_retries,
            base_delay_seconds=0.001,
            multiplier=1.5,
        )

    @property
    def timeout_seconds(self) -> float:
        return 5.0

    async def execute(self, context: AgentContext) -> AgentResult:
        self._attempts += 1
        raise RuntimeError(f"Intentional failure on attempt {self._attempts}")


class SlowAgent(BaseAgent):
    """A mock agent that sleeps longer than its timeout."""

    def __init__(self, name: str, sleep_seconds: float, timeout: float, max_retries: int) -> None:
        super().__init__()
        self.name = name
        self.description = f"Mock slow agent: {name}"
        self._sleep_seconds = sleep_seconds
        self._timeout = timeout
        self._max_retries = max_retries
        self._attempts = 0

    @property
    def retry_policy(self) -> RetryPolicy:
        return RetryPolicy(
            max_retries=self._max_retries,
            base_delay_seconds=0.001,
            multiplier=1.5,
        )

    @property
    def timeout_seconds(self) -> float:
        return self._timeout

    async def execute(self, context: AgentContext) -> AgentResult:
        self._attempts += 1
        await asyncio.sleep(self._sleep_seconds)
        # Should never reach here if timeout is shorter than sleep
        return AgentResult(
            agent_name=self.name,
            success=True,
            data={"completed": True},
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_context() -> AgentContext:
    """Create a minimal AgentContext for testing."""
    mock_llm = MagicMock()
    event_queue: asyncio.Queue = asyncio.Queue()
    return AgentContext(
        repo_path="/tmp/test_repo",
        llm_client=mock_llm,
        event_queue=event_queue,
    )


def _create_orchestrator(context: AgentContext) -> DependencyGraphOrchestrator:
    """Create a DependencyGraphOrchestrator with the given context."""
    return DependencyGraphOrchestrator(
        repo_path=context.repo_path,
        llm_client=context.llm_client,
        event_queue=context.event_queue,
        max_concurrency=5,
        global_timeout_seconds=60.0,
    )


# ---------------------------------------------------------------------------
# Property 6: Retry Count Adherence
# ---------------------------------------------------------------------------


@given(max_retries=st.integers(min_value=1, max_value=10))
@settings(max_examples=100, deadline=None)
def test_property_6_retry_count_adherence(max_retries):
    """
    **Validates: Requirements 4.1, 4.2, 4.3**

    For any max_retries N (1-10), when an agent always fails, the total
    number of execution attempts must equal exactly N+1 (one initial attempt
    plus N retries), and the final result must be success=False.
    """

    async def _run():
        context = _create_context()
        orchestrator = _create_orchestrator(context)

        agent = AlwaysFailingAgent(name="test_agent", max_retries=max_retries)

        result = await orchestrator._run_agent_with_retry(agent, context)

        # Verify total attempts = max_retries + 1
        assert agent._attempts == max_retries + 1, (
            f"Expected {max_retries + 1} attempts, got {agent._attempts}"
        )

        # Verify the result is a failure
        assert result.success is False, (
            f"Expected success=False, got success={result.success}"
        )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Property 7: Exponential Backoff Delay Computation
# ---------------------------------------------------------------------------


@given(
    base_delay=st.floats(min_value=0.01, max_value=2.0, allow_nan=False, allow_infinity=False),
    multiplier=st.floats(min_value=1.5, max_value=4.0, allow_nan=False, allow_infinity=False),
    max_retries=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=100, deadline=None)
def test_property_7_exponential_backoff_delay(base_delay, multiplier, max_retries):
    """
    **Validates: Requirements 4.2**

    For any RetryPolicy with base_delay_seconds=B and multiplier=M,
    the delay before retry attempt i (0-indexed) must equal B * M^i.
    Uses math.isclose() for float comparison.
    """
    policy = RetryPolicy(
        max_retries=max_retries,
        base_delay_seconds=base_delay,
        multiplier=multiplier,
    )

    for i in range(max_retries):
        actual_delay = policy.get_delay(i)
        expected_delay = base_delay * (multiplier ** i)

        assert math.isclose(actual_delay, expected_delay, rel_tol=1e-9), (
            f"Delay mismatch at attempt {i}.\n"
            f"  base_delay={base_delay}, multiplier={multiplier}\n"
            f"  Expected: {expected_delay}\n"
            f"  Actual: {actual_delay}"
        )


# ---------------------------------------------------------------------------
# Property 15: Timeout Triggers Cancellation and Retry
# ---------------------------------------------------------------------------


@given(
    timeout_seconds=st.floats(min_value=0.01, max_value=0.05, allow_nan=False, allow_infinity=False),
    max_retries=st.integers(min_value=1, max_value=3),
)
@settings(max_examples=100, deadline=None)
def test_property_15_timeout_triggers_cancellation_and_retry(timeout_seconds, max_retries):
    """
    **Validates: Requirements 7.2**

    For any short timeout_seconds (0.01-0.1), when an agent takes longer
    than the timeout, it must be cancelled and retry applied. After all
    retries are exhausted, the result must indicate timeout failure and
    the number of attempts must equal max_retries + 1.
    """

    async def _run():
        context = _create_context()
        orchestrator = _create_orchestrator(context)

        # Agent sleep time is 10x the timeout to guarantee timeout
        sleep_time = timeout_seconds * 10

        agent = SlowAgent(
            name="slow_agent",
            sleep_seconds=sleep_time,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

        result = await orchestrator._run_agent_with_retry(agent, context)

        # Verify total attempts = max_retries + 1
        assert agent._attempts == max_retries + 1, (
            f"Expected {max_retries + 1} attempts, got {agent._attempts}"
        )

        # Verify the result indicates failure
        assert result.success is False, (
            f"Expected success=False after timeout, got success={result.success}"
        )

        # Verify the error message mentions timeout
        assert result.error_message is not None, "Expected an error message"
        assert "timed out" in result.error_message.lower(), (
            f"Expected 'timed out' in error message, got: {result.error_message}"
        )

    asyncio.run(_run())
