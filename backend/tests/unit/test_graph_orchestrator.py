"""
Unit tests for DependencyGraphOrchestrator — foundational phase.

Tests the __init__, register_agent, and _execute_foundational_phase methods.
"""

from __future__ import annotations

import asyncio

import pytest

from dev_ghost_parser.agent_models import AgentEvent, AgentResult
from dev_ghost_parser.base_agent import AgentContext, BaseAgent
from dev_ghost_parser.graph_orchestrator import (
    DependencyGraphOrchestrator,
    FoundationalPhaseError,
)
from dev_ghost_parser.retry_policy import RetryPolicy


# ---------------------------------------------------------------------------
# Test helpers: mock agents
# ---------------------------------------------------------------------------


class MockASTAgent(BaseAgent):
    """A mock AST analyzer that succeeds."""

    name = "ast_analyzer"
    description = "Mock AST analyzer"

    def __init__(self, result_data: dict | None = None) -> None:
        super().__init__()
        self._result_data = result_data or {"nodes": [], "edges": []}

    async def execute(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            agent_name="ast_analyzer",
            success=True,
            data=self._result_data,
        )


class FailingASTAgent(BaseAgent):
    """A mock AST analyzer that always raises an exception."""

    name = "ast_analyzer"
    description = "Failing AST analyzer"

    def __init__(self, error_message: str = "LLM connection failed") -> None:
        super().__init__()
        self._error_message = error_message

    async def execute(self, context: AgentContext) -> AgentResult:
        raise RuntimeError(self._error_message)


class SlowASTAgent(BaseAgent):
    """A mock AST analyzer that takes too long (simulates timeout)."""

    name = "ast_analyzer"
    description = "Slow AST analyzer"

    def __init__(self, delay: float = 10.0) -> None:
        super().__init__()
        self._delay = delay

    @property
    def timeout_seconds(self) -> float:
        return 0.1  # Very short timeout for testing

    async def execute(self, context: AgentContext) -> AgentResult:
        await asyncio.sleep(self._delay)
        return AgentResult(agent_name="ast_analyzer", success=True, data={})


class FailThenSucceedASTAgent(BaseAgent):
    """A mock AST analyzer that fails N times then succeeds."""

    name = "ast_analyzer"
    description = "Flaky AST analyzer"

    def __init__(self, fail_count: int = 1, result_data: dict | None = None) -> None:
        super().__init__()
        self._fail_count = fail_count
        self._attempts = 0
        self._result_data = result_data or {"nodes": ["recovered"]}

    async def execute(self, context: AgentContext) -> AgentResult:
        self._attempts += 1
        if self._attempts <= self._fail_count:
            raise RuntimeError(f"Transient failure (attempt {self._attempts})")
        return AgentResult(
            agent_name="ast_analyzer",
            success=True,
            data=self._result_data,
        )


class MockDownstreamAgent(BaseAgent):
    """A mock downstream agent for registration testing."""

    name = "er_extractor"
    description = "Mock ER extractor"

    @property
    def dependencies(self) -> list[str]:
        return ["ast_analyzer"]

    async def execute(self, context: AgentContext) -> AgentResult:
        return AgentResult(agent_name="er_extractor", success=True, data={})


# ---------------------------------------------------------------------------
# Tests: __init__
# ---------------------------------------------------------------------------


class TestInit:
    """Tests for DependencyGraphOrchestrator.__init__."""

    def test_default_parameters(self) -> None:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )

        assert orch._repo_path == "/tmp/repo"
        assert orch._llm_client is None
        assert orch._event_queue is queue
        assert orch._max_concurrency == 5
        assert orch._global_timeout_seconds == 300.0
        assert orch._agents == {}
        assert orch._sequence_counter == 0

    def test_custom_parameters(self) -> None:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/custom/path",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
            max_concurrency=10,
            global_timeout_seconds=600.0,
        )

        assert orch._max_concurrency == 10
        assert orch._global_timeout_seconds == 600.0


# ---------------------------------------------------------------------------
# Tests: register_agent
# ---------------------------------------------------------------------------


class TestRegisterAgent:
    """Tests for register_agent method."""

    def test_register_single_agent(self) -> None:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        agent = MockASTAgent()
        orch.register_agent(agent)

        assert "ast_analyzer" in orch.agents
        assert orch.agents["ast_analyzer"] is agent

    def test_register_multiple_agents(self) -> None:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        ast_agent = MockASTAgent()
        downstream_agent = MockDownstreamAgent()

        orch.register_agent(ast_agent)
        orch.register_agent(downstream_agent)

        assert len(orch.agents) == 2
        assert "ast_analyzer" in orch.agents
        assert "er_extractor" in orch.agents

    def test_register_overwrites_same_name(self) -> None:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        agent1 = MockASTAgent(result_data={"version": 1})
        agent2 = MockASTAgent(result_data={"version": 2})

        orch.register_agent(agent1)
        orch.register_agent(agent2)

        assert len(orch.agents) == 1
        assert orch.agents["ast_analyzer"] is agent2


# ---------------------------------------------------------------------------
# Tests: _execute_foundational_phase
# ---------------------------------------------------------------------------


class TestExecuteFoundationalPhase:
    """Tests for _execute_foundational_phase method."""

    async def test_success_on_first_attempt(self) -> None:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        expected_data = {"nodes": [1, 2, 3], "edges": []}
        orch.register_agent(MockASTAgent(result_data=expected_data))

        result = await orch._execute_foundational_phase()

        assert result.success is True
        assert result.data == expected_data
        assert result.agent_name == "ast_analyzer"
        assert result.duration_ms >= 0

    async def test_emits_start_and_complete_events(self) -> None:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        orch.register_agent(MockASTAgent())

        await orch._execute_foundational_phase()

        events: list[AgentEvent] = []
        while not queue.empty():
            events.append(await queue.get())

        assert len(events) == 2
        assert events[0].type == "agent_start"
        assert events[0].agent == "ast_analyzer"
        assert events[1].type == "agent_complete"
        assert events[1].agent == "ast_analyzer"
        assert events[1].duration_ms is not None
        assert events[1].duration_ms >= 0

    async def test_events_have_increasing_sequence(self) -> None:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        orch.register_agent(MockASTAgent())

        await orch._execute_foundational_phase()

        events: list[AgentEvent] = []
        while not queue.empty():
            events.append(await queue.get())

        sequences = [e.sequence for e in events]
        assert sequences == sorted(sequences)
        assert len(set(sequences)) == len(sequences)  # All unique

    async def test_raises_value_error_if_no_ast_agent(self) -> None:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )

        with pytest.raises(ValueError, match="No agent named 'ast_analyzer'"):
            await orch._execute_foundational_phase()

    async def test_raises_foundational_phase_error_after_all_retries(self) -> None:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        orch.register_agent(FailingASTAgent(error_message="Connection refused"))

        with pytest.raises(FoundationalPhaseError, match="AST foundational phase failed"):
            await orch._execute_foundational_phase()

    async def test_emits_error_event_on_failure(self) -> None:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        orch.register_agent(FailingASTAgent(error_message="LLM timeout"))

        with pytest.raises(FoundationalPhaseError):
            await orch._execute_foundational_phase()

        events: list[AgentEvent] = []
        while not queue.empty():
            events.append(await queue.get())

        # Should have: agent_start + agent_error
        error_events = [e for e in events if e.type == "agent_error"]
        assert len(error_events) == 1
        assert error_events[0].agent == "ast_analyzer"
        assert error_events[0].error is not None
        assert error_events[0].retry_count == 2  # default max_retries

    async def test_retries_then_succeeds(self) -> None:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        agent = FailThenSucceedASTAgent(fail_count=1)
        orch.register_agent(agent)

        result = await orch._execute_foundational_phase()

        assert result.success is True
        assert result.data == {"nodes": ["recovered"]}
        assert agent._attempts == 2  # 1 failure + 1 success

    async def test_retries_with_custom_policy(self) -> None:
        """Agent with custom retry policy (max_retries=1) fails after 2 attempts total."""

        class CustomRetryASTAgent(FailingASTAgent):
            @property
            def retry_policy(self) -> RetryPolicy:
                return RetryPolicy(max_retries=1, base_delay_seconds=0.01, multiplier=2.0)

        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        orch.register_agent(CustomRetryASTAgent())

        with pytest.raises(FoundationalPhaseError):
            await orch._execute_foundational_phase()

        # Check error event has correct retry_count
        events: list[AgentEvent] = []
        while not queue.empty():
            events.append(await queue.get())

        error_events = [e for e in events if e.type == "agent_error"]
        assert len(error_events) == 1
        assert error_events[0].retry_count == 1  # max_retries=1

    async def test_timeout_triggers_retry(self) -> None:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        agent = SlowASTAgent(delay=10.0)
        orch.register_agent(agent)

        with pytest.raises(FoundationalPhaseError, match="AST foundational phase failed"):
            await orch._execute_foundational_phase()

    async def test_run_pipeline_success(self) -> None:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        expected_data = {"nodes": ["main"], "components": []}
        orch.register_agent(MockASTAgent(result_data=expected_data))

        result = await orch.run_pipeline()

        assert result.code_flow == expected_data
        assert result.errors == []

    async def test_run_pipeline_aborts_on_ast_failure(self) -> None:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        orch.register_agent(FailingASTAgent())

        with pytest.raises(FoundationalPhaseError):
            await orch.run_pipeline()


# ---------------------------------------------------------------------------
# Test helpers for _run_agent_with_retry
# ---------------------------------------------------------------------------


class MockDownstreamSuccessAgent(BaseAgent):
    """A mock downstream agent that succeeds."""

    name = "er_extractor"
    description = "Mock ER extractor"

    @property
    def dependencies(self) -> list[str]:
        return ["ast_analyzer"]

    @property
    def timeout_seconds(self) -> float:
        return 5.0

    def __init__(self, result_data: dict | None = None) -> None:
        super().__init__()
        self._result_data = result_data or {"entities": ["User", "Order"]}

    async def execute(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            agent_name="er_extractor",
            success=True,
            data=self._result_data,
        )


class FailingDownstreamAgent(BaseAgent):
    """A mock downstream agent that always fails."""

    name = "er_extractor"
    description = "Failing ER extractor"

    @property
    def timeout_seconds(self) -> float:
        return 5.0

    @property
    def retry_policy(self) -> RetryPolicy:
        return RetryPolicy(max_retries=2, base_delay_seconds=0.01, multiplier=2.0)

    def __init__(self, error_message: str = "Parse error") -> None:
        super().__init__()
        self._error_message = error_message

    async def execute(self, context: AgentContext) -> AgentResult:
        raise RuntimeError(self._error_message)


class SlowDownstreamAgent(BaseAgent):
    """A mock downstream agent that times out."""

    name = "code_auditor"
    description = "Slow code auditor"

    @property
    def timeout_seconds(self) -> float:
        return 0.05  # Very short timeout for testing

    @property
    def retry_policy(self) -> RetryPolicy:
        return RetryPolicy(max_retries=1, base_delay_seconds=0.01, multiplier=2.0)

    async def execute(self, context: AgentContext) -> AgentResult:
        await asyncio.sleep(10.0)
        return AgentResult(agent_name="code_auditor", success=True, data={})


class FlakyDownstreamAgent(BaseAgent):
    """A mock downstream agent that fails N times then succeeds."""

    name = "doc_generator"
    description = "Flaky doc generator"

    @property
    def timeout_seconds(self) -> float:
        return 5.0

    @property
    def retry_policy(self) -> RetryPolicy:
        return RetryPolicy(max_retries=3, base_delay_seconds=0.01, multiplier=2.0)

    def __init__(self, fail_count: int = 1) -> None:
        super().__init__()
        self._fail_count = fail_count
        self._attempts = 0

    async def execute(self, context: AgentContext) -> AgentResult:
        self._attempts += 1
        if self._attempts <= self._fail_count:
            raise RuntimeError(f"Transient failure (attempt {self._attempts})")
        return AgentResult(
            agent_name="doc_generator",
            success=True,
            data={"docs": "generated"},
        )


# ---------------------------------------------------------------------------
# Tests: _run_agent_with_retry
# ---------------------------------------------------------------------------


class TestRunAgentWithRetry:
    """Tests for _run_agent_with_retry method."""

    async def test_success_on_first_attempt(self) -> None:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        agent = MockDownstreamSuccessAgent(result_data={"entities": ["User"]})
        context = AgentContext(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )

        result = await orch._run_agent_with_retry(agent, context)

        assert result.success is True
        assert result.data == {"entities": ["User"]}
        assert result.agent_name == "er_extractor"
        assert result.duration_ms >= 0

    async def test_emits_start_and_complete_events_on_success(self) -> None:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        agent = MockDownstreamSuccessAgent()
        context = AgentContext(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )

        await orch._run_agent_with_retry(agent, context)

        events: list[AgentEvent] = []
        while not queue.empty():
            events.append(await queue.get())

        assert len(events) == 2
        assert events[0].type == "agent_start"
        assert events[0].agent == "er_extractor"
        assert events[1].type == "agent_complete"
        assert events[1].agent == "er_extractor"
        assert events[1].duration_ms is not None
        assert events[1].duration_ms >= 0

    async def test_returns_failed_result_after_all_retries(self) -> None:
        """Unlike _execute_foundational_phase, this does NOT raise."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        agent = FailingDownstreamAgent(error_message="Connection refused")
        context = AgentContext(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )

        result = await orch._run_agent_with_retry(agent, context)

        assert result.success is False
        assert result.agent_name == "er_extractor"
        assert "Connection refused" in (result.error_message or "")
        assert result.duration_ms >= 0

    async def test_emits_error_event_on_failure(self) -> None:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        agent = FailingDownstreamAgent(error_message="LLM timeout")
        context = AgentContext(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )

        await orch._run_agent_with_retry(agent, context)

        events: list[AgentEvent] = []
        while not queue.empty():
            events.append(await queue.get())

        # Should have: agent_start + agent_error
        error_events = [e for e in events if e.type == "agent_error"]
        assert len(error_events) == 1
        assert error_events[0].agent == "er_extractor"
        assert error_events[0].error is not None
        assert error_events[0].retry_count == 2  # max_retries

    async def test_retries_then_succeeds(self) -> None:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        agent = FlakyDownstreamAgent(fail_count=2)
        context = AgentContext(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )

        result = await orch._run_agent_with_retry(agent, context)

        assert result.success is True
        assert result.data == {"docs": "generated"}
        assert agent._attempts == 3  # 2 failures + 1 success

    async def test_timeout_triggers_retry_and_returns_failed(self) -> None:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        agent = SlowDownstreamAgent()
        context = AgentContext(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )

        result = await orch._run_agent_with_retry(agent, context)

        # Should return failed result, NOT raise
        assert result.success is False
        assert result.agent_name == "code_auditor"
        assert "timed out" in (result.error_message or "")

    async def test_events_have_increasing_sequence(self) -> None:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        agent = MockDownstreamSuccessAgent()
        context = AgentContext(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )

        await orch._run_agent_with_retry(agent, context)

        events: list[AgentEvent] = []
        while not queue.empty():
            events.append(await queue.get())

        sequences = [e.sequence for e in events]
        assert sequences == sorted(sequences)
        assert len(set(sequences)) == len(sequences)  # All unique

    async def test_does_not_raise_on_failure(self) -> None:
        """Key difference from foundational phase: no exception raised."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        agent = FailingDownstreamAgent(error_message="Fatal error")
        context = AgentContext(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )

        # This should NOT raise — it returns a failed result
        result = await orch._run_agent_with_retry(agent, context)
        assert result.success is False
        assert result.error_message == "Fatal error"


# ---------------------------------------------------------------------------
# Test helpers: mock agents for parallel phase
# ---------------------------------------------------------------------------


class MockSuccessAgent(BaseAgent):
    """A mock agent that succeeds with configurable data and dependencies."""

    def __init__(
        self,
        name: str,
        description: str = "Mock agent",
        result_data: dict | None = None,
        deps: list[str] | None = None,
        delay: float = 0.0,
    ) -> None:
        super().__init__()
        self.name = name
        self.description = description
        self._result_data = result_data or {"output": f"{name}_data"}
        self._deps = deps or []
        self._delay = delay
        self.received_context: AgentContext | None = None

    @property
    def dependencies(self) -> list[str]:
        return self._deps

    async def execute(self, context: AgentContext) -> AgentResult:
        self.received_context = context
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        return AgentResult(
            agent_name=self.name,
            success=True,
            data=self._result_data,
        )


class MockFailingAgent(BaseAgent):
    """A mock agent that always fails."""

    def __init__(
        self,
        name: str,
        description: str = "Failing agent",
        error_msg: str = "Agent failed",
        deps: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.name = name
        self.description = description
        self._error_msg = error_msg
        self._deps = deps or []

    @property
    def dependencies(self) -> list[str]:
        return self._deps

    @property
    def retry_policy(self) -> RetryPolicy:
        # No retries for faster testing
        return RetryPolicy(max_retries=0, base_delay_seconds=0.01)

    async def execute(self, context: AgentContext) -> AgentResult:
        raise RuntimeError(self._error_msg)


# ---------------------------------------------------------------------------
# Tests: _execute_parallel_phase
# ---------------------------------------------------------------------------


class TestExecuteParallelPhase:
    """Tests for _execute_parallel_phase method."""

    async def test_no_parallel_agents_returns_empty(self) -> None:
        """If only AST agent is registered, parallel phase returns empty list."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        orch.register_agent(MockASTAgent())

        ast_result = AgentResult(
            agent_name="ast_analyzer", success=True, data={"nodes": []}
        )
        results = await orch._execute_parallel_phase(ast_result)

        assert results == []

    async def test_single_downstream_agent_success(self) -> None:
        """A single downstream agent with AST dependency should execute and return."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        orch.register_agent(MockASTAgent())
        er_agent = MockSuccessAgent(
            name="er_extractor", result_data={"entities": ["User"]}
        )
        orch.register_agent(er_agent)

        ast_result = AgentResult(
            agent_name="ast_analyzer", success=True, data={"nodes": [1]}
        )
        results = await orch._execute_parallel_phase(ast_result)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].agent_name == "er_extractor"
        assert results[0].data == {"entities": ["User"]}

    async def test_ast_result_in_context(self) -> None:
        """Downstream agents should receive AST result in dependency_results."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        orch.register_agent(MockASTAgent())
        er_agent = MockSuccessAgent(name="er_extractor")
        orch.register_agent(er_agent)

        ast_result = AgentResult(
            agent_name="ast_analyzer", success=True, data={"shared": "context"}
        )
        await orch._execute_parallel_phase(ast_result)

        assert er_agent.received_context is not None
        assert "ast_analyzer" in er_agent.received_context.dependency_results
        assert (
            er_agent.received_context.dependency_results["ast_analyzer"] is ast_result
        )

    async def test_multiple_independent_agents_run_parallel(self) -> None:
        """Multiple agents with only AST dependency should all execute."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        orch.register_agent(MockASTAgent())
        orch.register_agent(MockSuccessAgent(name="er_extractor", delay=0.01))
        orch.register_agent(MockSuccessAgent(name="code_auditor", delay=0.01))
        orch.register_agent(MockSuccessAgent(name="doc_generator", delay=0.01))

        ast_result = AgentResult(
            agent_name="ast_analyzer", success=True, data={}
        )
        results = await orch._execute_parallel_phase(ast_result)

        assert len(results) == 3
        agent_names = {r.agent_name for r in results}
        assert agent_names == {"er_extractor", "code_auditor", "doc_generator"}
        assert all(r.success for r in results)

    async def test_chained_dependencies(self) -> None:
        """Agent B depends on Agent A; B should only run after A completes."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        orch.register_agent(MockASTAgent())
        agent_a = MockSuccessAgent(
            name="er_extractor", result_data={"er": "model"}
        )
        agent_b = MockSuccessAgent(
            name="code_auditor", deps=["er_extractor"]
        )
        orch.register_agent(agent_a)
        orch.register_agent(agent_b)

        ast_result = AgentResult(
            agent_name="ast_analyzer", success=True, data={}
        )
        results = await orch._execute_parallel_phase(ast_result)

        assert len(results) == 2
        # Both should succeed
        assert all(r.success for r in results)
        # code_auditor should have received er_extractor's result
        assert agent_b.received_context is not None
        dep_results = agent_b.received_context.dependency_results
        assert "er_extractor" in dep_results
        assert dep_results["er_extractor"].data == {"er": "model"}

    async def test_failure_propagation_skips_dependents(self) -> None:
        """When an agent fails, its transitive dependents should be skipped."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        orch.register_agent(MockASTAgent())
        # er_extractor will fail
        orch.register_agent(MockFailingAgent(name="er_extractor"))
        # code_auditor depends on er_extractor → should be skipped
        orch.register_agent(MockSuccessAgent(
            name="code_auditor", deps=["er_extractor"]
        ))
        # doc_generator is independent → should succeed
        orch.register_agent(MockSuccessAgent(name="doc_generator"))

        ast_result = AgentResult(
            agent_name="ast_analyzer", success=True, data={}
        )
        results = await orch._execute_parallel_phase(ast_result)

        result_map = {r.agent_name: r for r in results}
        # er_extractor failed
        assert result_map["er_extractor"].success is False
        # code_auditor was skipped
        assert result_map["code_auditor"].success is False
        assert "skipped" in result_map["code_auditor"].error_message.lower()
        # doc_generator succeeded
        assert result_map["doc_generator"].success is True

    async def test_failure_emits_error_events_for_skipped(self) -> None:
        """Skipped agents should have error events emitted."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        orch.register_agent(MockASTAgent())
        orch.register_agent(MockFailingAgent(name="er_extractor"))
        orch.register_agent(MockSuccessAgent(
            name="code_auditor", deps=["er_extractor"]
        ))

        ast_result = AgentResult(
            agent_name="ast_analyzer", success=True, data={}
        )
        await orch._execute_parallel_phase(ast_result)

        events: list[AgentEvent] = []
        while not queue.empty():
            events.append(await queue.get())

        # Find error event for code_auditor (skipped)
        skipped_errors = [
            e
            for e in events
            if e.type == "agent_error" and e.agent == "code_auditor"
        ]
        assert len(skipped_errors) == 1
        assert "upstream" in skipped_errors[0].error.lower()

    async def test_concurrency_limit_respected(self) -> None:
        """No more than max_concurrency agents should run simultaneously."""
        max_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        class TrackingAgent(BaseAgent):
            def __init__(self, name: str):
                super().__init__()
                self.name = name
                self.description = f"Tracking agent {name}"

            @property
            def retry_policy(self) -> RetryPolicy:
                return RetryPolicy(max_retries=0, base_delay_seconds=0.01)

            async def execute(self, context: AgentContext) -> AgentResult:
                nonlocal max_concurrent, current_concurrent
                async with lock:
                    current_concurrent += 1
                    max_concurrent = max(max_concurrent, current_concurrent)
                await asyncio.sleep(0.05)
                async with lock:
                    current_concurrent -= 1
                return AgentResult(agent_name=self.name, success=True, data={})

        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
            max_concurrency=2,
        )
        orch.register_agent(MockASTAgent())
        # Register 5 independent agents
        for i in range(5):
            orch.register_agent(TrackingAgent(name=f"agent_{i}"))

        ast_result = AgentResult(
            agent_name="ast_analyzer", success=True, data={}
        )
        await orch._execute_parallel_phase(ast_result)

        assert max_concurrent <= 2

    async def test_run_pipeline_with_parallel_agents(self) -> None:
        """run_pipeline() should execute both AST and parallel phases."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        orch.register_agent(MockASTAgent(result_data={"ast": "data"}))
        orch.register_agent(MockSuccessAgent(
            name="er_extractor", result_data={"entities": []}
        ))

        result = await orch.run_pipeline()

        assert result.code_flow == {"ast": "data"}
        assert result.errors == []

    async def test_run_pipeline_with_failed_parallel_agent(self) -> None:
        """run_pipeline() should report errors for failed parallel agents."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        orch.register_agent(MockASTAgent(result_data={"ast": "ok"}))
        orch.register_agent(MockFailingAgent(name="er_extractor"))

        result = await orch.run_pipeline()

        assert result.code_flow == {"ast": "ok"}
        assert len(result.errors) >= 1
        failed_agents = [e["agent"] for e in result.errors]
        assert "er_extractor" in failed_agents

    async def test_cyclic_dependency_raises_error(self) -> None:
        """A cyclic dependency should raise CyclicDependencyError."""
        from dev_ghost_parser.dependency_graph import CyclicDependencyError

        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        orch.register_agent(MockASTAgent())
        # Create a cycle: A depends on B, B depends on A
        orch.register_agent(MockSuccessAgent(
            name="er_extractor", deps=["code_auditor"]
        ))
        orch.register_agent(MockSuccessAgent(
            name="code_auditor", deps=["er_extractor"]
        ))

        ast_result = AgentResult(
            agent_name="ast_analyzer", success=True, data={}
        )
        with pytest.raises(CyclicDependencyError):
            await orch._execute_parallel_phase(ast_result)


# ---------------------------------------------------------------------------
# Tests: _aggregate_results
# ---------------------------------------------------------------------------


class TestAggregateResults:
    """Tests for _aggregate_results method."""

    def _make_orchestrator(self) -> DependencyGraphOrchestrator:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        # Register agents so _aggregate_results can look up retry policies
        orch.register_agent(MockASTAgent())
        orch.register_agent(MockSuccessAgent(name="er_extractor"))
        orch.register_agent(MockSuccessAgent(name="code_auditor"))
        orch.register_agent(MockSuccessAgent(name="doc_generator"))
        orch.register_agent(MockSuccessAgent(name="system_reporter"))
        return orch

    def test_merge_all_successful_agents(self) -> None:
        """All successful results are mapped to their respective fields."""
        orch = self._make_orchestrator()
        results = [
            AgentResult(agent_name="ast_analyzer", success=True, data={"nodes": [1]}, duration_ms=100),
            AgentResult(agent_name="er_extractor", success=True, data={"entities": ["User"]}, duration_ms=200),
            AgentResult(agent_name="code_auditor", success=True, data={"issues": []}, duration_ms=150),
            AgentResult(agent_name="doc_generator", success=True, data={"docs": "api.md"}, duration_ms=120),
            AgentResult(agent_name="system_reporter", success=True, data={"stack": "python"}, duration_ms=50),
        ]

        analysis = orch._aggregate_results(results, total_duration_ms=500)

        assert analysis.code_flow == {"nodes": [1]}
        assert analysis.er_model == {"entities": ["User"]}
        assert analysis.audit == {"issues": []}
        assert analysis.artifacts == {"docs": "api.md"}
        assert analysis.system_report == {"stack": "python"}
        assert analysis.errors == []

    def test_metadata_populated_correctly(self) -> None:
        """ExecutionMetadata should contain durations, retries, and failed list."""
        orch = self._make_orchestrator()
        results = [
            AgentResult(agent_name="ast_analyzer", success=True, data={}, duration_ms=100),
            AgentResult(agent_name="er_extractor", success=True, data={}, duration_ms=200),
            AgentResult(agent_name="code_auditor", success=False, error_message="timeout", duration_ms=300),
        ]

        analysis = orch._aggregate_results(results, total_duration_ms=600)

        assert analysis.metadata is not None
        assert analysis.metadata.total_duration_ms == 600
        assert analysis.metadata.agent_durations["ast_analyzer"] == 100
        assert analysis.metadata.agent_durations["er_extractor"] == 200
        assert analysis.metadata.agent_durations["code_auditor"] == 300
        assert "code_auditor" in analysis.metadata.failed_agents
        assert "ast_analyzer" not in analysis.metadata.failed_agents

    def test_failed_agents_in_errors_list(self) -> None:
        """Failed agents should appear in the errors list."""
        orch = self._make_orchestrator()
        results = [
            AgentResult(agent_name="ast_analyzer", success=True, data={}, duration_ms=50),
            AgentResult(agent_name="er_extractor", success=False, error_message="Parse error", duration_ms=100),
        ]

        analysis = orch._aggregate_results(results, total_duration_ms=200)

        assert len(analysis.errors) == 1
        assert analysis.errors[0]["agent"] == "er_extractor"
        assert analysis.errors[0]["error"] == "Parse error"

    def test_partial_results_included_with_annotation(self) -> None:
        """Failed agents with data should be included as partial results."""
        orch = self._make_orchestrator()
        results = [
            AgentResult(agent_name="ast_analyzer", success=True, data={"nodes": [1]}, duration_ms=50),
            AgentResult(
                agent_name="code_auditor",
                success=False,
                data={"issues": ["warning1"]},
                error_message="Batch 3 failed",
                duration_ms=200,
            ),
        ]

        analysis = orch._aggregate_results(results, total_duration_ms=300)

        assert "code_auditor" in analysis.metadata.partial_results
        # Partial data annotated with _partial and _error
        assert analysis.audit is not None
        assert analysis.audit["_partial"] is True
        assert analysis.audit["_error"] == "Batch 3 failed"
        assert analysis.audit["issues"] == ["warning1"]

    def test_priority_conflict_resolution_higher_wins(self) -> None:
        """When two agents write the same field, higher priority wins."""
        orch = self._make_orchestrator()
        # Simulate conflict: both ast_analyzer (priority 100) and
        # system_reporter (priority 20) trying to write "code_flow"
        # In practice this is unlikely, but we test the mechanism.
        # We'll artificially make two results claim the same field
        # by using ast_analyzer (code_flow) and then a second
        # result that also maps to code_flow.

        # For this test, we override AGENT_FIELD_MAP temporarily
        # Instead, let's test with two results for the same agent name
        # Actually, the realistic test: two agents with different priorities
        # both map to the same field. We'll patch AGENT_FIELD_MAP.
        from unittest.mock import patch

        custom_map = {
            "ast_analyzer": "code_flow",
            "er_extractor": "code_flow",  # Conflict! Both write to code_flow
            "code_auditor": "audit",
            "doc_generator": "artifacts",
            "system_reporter": "system_report",
        }

        with patch("dev_ghost_parser.graph_orchestrator.AGENT_FIELD_MAP", custom_map):
            results = [
                AgentResult(agent_name="er_extractor", success=True, data={"er": "data"}, duration_ms=100),
                AgentResult(agent_name="ast_analyzer", success=True, data={"ast": "data"}, duration_ms=200),
            ]

            analysis = orch._aggregate_results(results, total_duration_ms=300)

            # ast_analyzer has priority 100 > er_extractor (80), so ast wins
            assert analysis.code_flow == {"ast": "data"}

    def test_priority_conflict_lower_first_higher_overwrites(self) -> None:
        """If lower priority writes first, higher priority overwrites."""
        orch = self._make_orchestrator()
        from unittest.mock import patch

        custom_map = {
            "ast_analyzer": "code_flow",
            "er_extractor": "code_flow",  # Conflict
            "code_auditor": "audit",
            "doc_generator": "artifacts",
            "system_reporter": "system_report",
        }

        with patch("dev_ghost_parser.graph_orchestrator.AGENT_FIELD_MAP", custom_map):
            # er_extractor (priority 80) writes first, then ast_analyzer (priority 100) writes
            results = [
                AgentResult(agent_name="er_extractor", success=True, data={"er": "first"}, duration_ms=100),
                AgentResult(agent_name="ast_analyzer", success=True, data={"ast": "second"}, duration_ms=200),
            ]

            analysis = orch._aggregate_results(results, total_duration_ms=300)

            # ast_analyzer (100) > er_extractor (80) → ast wins
            assert analysis.code_flow == {"ast": "second"}

    def test_priority_conflict_higher_first_not_overwritten(self) -> None:
        """If higher priority writes first, lower priority does NOT overwrite."""
        orch = self._make_orchestrator()
        from unittest.mock import patch

        custom_map = {
            "ast_analyzer": "code_flow",
            "er_extractor": "code_flow",  # Conflict
            "code_auditor": "audit",
            "doc_generator": "artifacts",
            "system_reporter": "system_report",
        }

        with patch("dev_ghost_parser.graph_orchestrator.AGENT_FIELD_MAP", custom_map):
            # ast_analyzer (priority 100) writes first, then er_extractor (priority 80) writes
            results = [
                AgentResult(agent_name="ast_analyzer", success=True, data={"ast": "first"}, duration_ms=200),
                AgentResult(agent_name="er_extractor", success=True, data={"er": "second"}, duration_ms=100),
            ]

            analysis = orch._aggregate_results(results, total_duration_ms=300)

            # ast_analyzer (100) > er_extractor (80) → ast keeps its value
            assert analysis.code_flow == {"ast": "first"}

    def test_no_data_loss_all_fields_preserved(self) -> None:
        """No data from a successful agent is lost during merge."""
        orch = self._make_orchestrator()
        ast_data = {"nodes": [1, 2, 3], "edges": [{"a": "b"}]}
        er_data = {"entities": ["User", "Order"], "relations": ["has_many"]}

        results = [
            AgentResult(agent_name="ast_analyzer", success=True, data=ast_data, duration_ms=50),
            AgentResult(agent_name="er_extractor", success=True, data=er_data, duration_ms=80),
        ]

        analysis = orch._aggregate_results(results, total_duration_ms=200)

        assert analysis.code_flow == ast_data
        assert analysis.er_model == er_data

    def test_empty_results_list(self) -> None:
        """Aggregating empty results should produce empty AnalysisResult."""
        orch = self._make_orchestrator()
        analysis = orch._aggregate_results([], total_duration_ms=0)

        assert analysis.code_flow is None
        assert analysis.er_model is None
        assert analysis.audit is None
        assert analysis.artifacts is None
        assert analysis.system_report is None
        assert analysis.errors == []
        assert analysis.metadata is not None
        assert analysis.metadata.total_duration_ms == 0

    async def test_run_pipeline_uses_aggregate_results(self) -> None:
        """run_pipeline() should use _aggregate_results and populate metadata."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=None,  # type: ignore[arg-type]
            event_queue=queue,
        )
        orch.register_agent(MockASTAgent(result_data={"ast": "data"}))
        orch.register_agent(MockSuccessAgent(
            name="er_extractor", result_data={"entities": ["User"]}
        ))

        result = await orch.run_pipeline()

        assert result.code_flow == {"ast": "data"}
        assert result.er_model == {"entities": ["User"]}
        assert result.metadata is not None
        assert result.metadata.total_duration_ms >= 0
        assert "ast_analyzer" in result.metadata.agent_durations
        assert "er_extractor" in result.metadata.agent_durations
        assert result.errors == []
