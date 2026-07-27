"""Unit tests for the AgentOrchestrator class.

Validates Requirements: 1.1, 1.2, 1.4, 1.5, 1.6, 1.7
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from dev_ghost_parser.agent_models import AgentResult, AnalysisResult
from dev_ghost_parser.base_agent import AgentContext, BaseAgent
from dev_ghost_parser.orchestrator import AgentOrchestrator


# ---------------------------------------------------------------------------
# Test helpers: concrete agent implementations for testing
# ---------------------------------------------------------------------------


class FakeAgent(BaseAgent):
    """A fast agent that succeeds with configurable data."""

    def __init__(self, name: str, description: str, data: dict | None = None, delay: float = 0.0):
        super().__init__()
        self.name = name
        self.description = description
        self._data = data or {"result": f"{name}_output"}
        self._delay = delay

    async def execute(self, context: AgentContext) -> AgentResult:
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        await self.emit_progress(f"{self.name} working...")
        return AgentResult(
            agent_name=self.name,
            success=True,
            data=self._data,
        )


class FailingAgent(BaseAgent):
    """An agent that raises an exception."""

    def __init__(self, name: str, description: str, error_msg: str = "Something broke"):
        super().__init__()
        self.name = name
        self.description = description
        self._error_msg = error_msg

    async def execute(self, context: AgentContext) -> AgentResult:
        await self.emit_progress(f"{self.name} starting...")
        raise RuntimeError(self._error_msg)


class SlowAgent(BaseAgent):
    """An agent that sleeps for a long time (to test timeout)."""

    def __init__(self, name: str, description: str, delay: float = 300.0):
        super().__init__()
        self.name = name
        self.description = description
        self._delay = delay

    async def execute(self, context: AgentContext) -> AgentResult:
        await self.emit_progress(f"{self.name} starting long task...")
        await asyncio.sleep(self._delay)
        return AgentResult(agent_name=self.name, success=True, data={})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_llm_client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def event_queue() -> asyncio.Queue:
    return asyncio.Queue()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOrchestratorInit:
    """Tests for orchestrator initialization and agent registration."""

    def test_register_agent(self, mock_llm_client, event_queue):
        orch = AgentOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        agent = FakeAgent(name="ast_analyzer", description="Analyzes AST")
        orch.register_agent(agent)
        assert len(orch.agents) == 1
        assert orch.agents[0].name == "ast_analyzer"

    def test_default_settings(self, mock_llm_client, event_queue):
        orch = AgentOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        assert orch._max_concurrency == 5
        assert orch._timeout_seconds == 120.0


class TestOrchestratorRunAll:
    """Tests for run_all() parallel execution."""

    @pytest.mark.asyncio
    async def test_single_agent_success(self, mock_llm_client, event_queue):
        """A single successful agent should produce a merged result."""
        orch = AgentOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        orch.register_agent(FakeAgent(
            name="ast_analyzer",
            description="Analyzes AST structure",
            data={"functions": ["main"]},
        ))

        result = await orch.run_all()

        assert isinstance(result, AnalysisResult)
        assert result.code_flow == {"functions": ["main"]}
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_multiple_agents_success(self, mock_llm_client, event_queue):
        """Multiple successful agents should all have their results merged."""
        orch = AgentOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        orch.register_agent(FakeAgent(
            name="ast_analyzer", description="AST", data={"ast": "data"}
        ))
        orch.register_agent(FakeAgent(
            name="er_extractor", description="ER", data={"entities": []}
        ))
        orch.register_agent(FakeAgent(
            name="system_reporter", description="System", data={"tech": "python"}
        ))

        result = await orch.run_all()

        assert result.code_flow == {"ast": "data"}
        assert result.er_model == {"entities": []}
        assert result.system_report == {"tech": "python"}
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_parallel_execution_faster_than_sequential(self, mock_llm_client, event_queue):
        """Parallel execution wall-clock time should be less than sum of individual times."""
        import time

        orch = AgentOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        # Each agent takes 0.1s
        orch.register_agent(FakeAgent(name="ast_analyzer", description="AST", delay=0.1))
        orch.register_agent(FakeAgent(name="er_extractor", description="ER", delay=0.1))
        orch.register_agent(FakeAgent(name="code_auditor", description="Audit", delay=0.1))

        start = time.perf_counter()
        await orch.run_all()
        elapsed = time.perf_counter() - start

        # Sequential would be ~0.3s; parallel should be ~0.1s
        # Use generous threshold to avoid flaky tests
        assert elapsed < 0.25, f"Expected parallel execution but took {elapsed:.3f}s"

    @pytest.mark.asyncio
    async def test_fault_isolation(self, mock_llm_client, event_queue):
        """A failing agent should not prevent other agents from completing."""
        orch = AgentOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        orch.register_agent(FakeAgent(
            name="ast_analyzer", description="AST", data={"code": "ok"}
        ))
        orch.register_agent(FailingAgent(
            name="er_extractor", description="ER", error_msg="DB connection failed"
        ))
        orch.register_agent(FakeAgent(
            name="system_reporter", description="System", data={"stack": "py"}
        ))

        result = await orch.run_all()

        # Successful agents should have their results
        assert result.code_flow == {"code": "ok"}
        assert result.system_report == {"stack": "py"}

        # Failed agent should be in errors
        assert len(result.errors) == 1
        assert result.errors[0]["agent"] == "er_extractor"
        assert "DB connection failed" in result.errors[0]["error"]

    @pytest.mark.asyncio
    async def test_all_agents_fail(self, mock_llm_client, event_queue):
        """If all agents fail, result should have all errors and no data."""
        orch = AgentOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        orch.register_agent(FailingAgent(name="ast_analyzer", description="AST"))
        orch.register_agent(FailingAgent(name="er_extractor", description="ER"))

        result = await orch.run_all()

        assert result.code_flow is None
        assert result.er_model is None
        assert len(result.errors) == 2


class TestOrchestratorTimeout:
    """Tests for timeout handling."""

    @pytest.mark.asyncio
    async def test_timeout_cancels_slow_agents(self, mock_llm_client, event_queue):
        """Agents exceeding the timeout should be cancelled with error entries."""
        orch = AgentOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
            timeout_seconds=0.2,  # Very short timeout for testing
        )
        orch.register_agent(SlowAgent(name="ast_analyzer", description="AST", delay=10.0))
        orch.register_agent(SlowAgent(name="er_extractor", description="ER", delay=10.0))

        result = await orch.run_all()

        # Both agents should have timeout errors
        assert len(result.errors) == 2
        assert all("timeout" in e["error"].lower() for e in result.errors)

    @pytest.mark.asyncio
    async def test_fast_agents_complete_before_timeout(self, mock_llm_client, event_queue):
        """Fast agents should complete normally even with a timeout set."""
        orch = AgentOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
            timeout_seconds=5.0,
        )
        orch.register_agent(FakeAgent(
            name="ast_analyzer", description="AST", data={"fast": True}, delay=0.01
        ))

        result = await orch.run_all()

        assert result.code_flow == {"fast": True}
        assert result.errors == []


class TestOrchestratorEvents:
    """Tests for event emission."""

    @pytest.mark.asyncio
    async def test_emits_start_and_complete_events(self, mock_llm_client, event_queue):
        """Successful agent should emit agent_start and agent_complete events."""
        orch = AgentOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        orch.register_agent(FakeAgent(name="ast_analyzer", description="Analyzes AST"))

        await orch.run_all()

        events = []
        while not event_queue.empty():
            events.append(await event_queue.get())

        # Should have: agent_start, agent_progress (from emit_progress), agent_complete
        event_types = [e.type for e in events]
        assert "agent_start" in event_types
        assert "agent_progress" in event_types
        assert "agent_complete" in event_types

    @pytest.mark.asyncio
    async def test_emits_error_event_on_failure(self, mock_llm_client, event_queue):
        """Failing agent should emit agent_start and agent_error events."""
        orch = AgentOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        orch.register_agent(FailingAgent(
            name="code_auditor", description="Audits code", error_msg="Parse error"
        ))

        await orch.run_all()

        events = []
        while not event_queue.empty():
            events.append(await event_queue.get())

        event_types = [e.type for e in events]
        assert "agent_start" in event_types
        assert "agent_error" in event_types

        error_event = next(e for e in events if e.type == "agent_error")
        assert error_event.agent == "code_auditor"
        assert "Parse error" in error_event.error

    @pytest.mark.asyncio
    async def test_event_has_duration_on_complete(self, mock_llm_client, event_queue):
        """agent_complete events should have a non-negative duration_ms."""
        orch = AgentOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        orch.register_agent(FakeAgent(name="ast_analyzer", description="AST", delay=0.05))

        await orch.run_all()

        events = []
        while not event_queue.empty():
            events.append(await event_queue.get())

        complete_event = next(e for e in events if e.type == "agent_complete")
        assert complete_event.duration_ms is not None
        assert complete_event.duration_ms >= 0


class TestOrchestratorSemaphore:
    """Tests for semaphore-bounded concurrency."""

    @pytest.mark.asyncio
    async def test_max_concurrency_respected(self, mock_llm_client, event_queue):
        """No more than max_concurrency agents should run simultaneously."""
        max_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        class TrackingAgent(BaseAgent):
            def __init__(self, name: str):
                super().__init__()
                self.name = name
                self.description = f"Agent {name}"

            async def execute(self, context: AgentContext) -> AgentResult:
                nonlocal max_concurrent, current_concurrent
                async with lock:
                    current_concurrent += 1
                    max_concurrent = max(max_concurrent, current_concurrent)
                await asyncio.sleep(0.05)
                async with lock:
                    current_concurrent -= 1
                return AgentResult(agent_name=self.name, success=True, data={})

        orch = AgentOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
            max_concurrency=2,
        )

        # Register more agents than max_concurrency
        for i in range(5):
            orch.register_agent(TrackingAgent(name=f"ast_analyzer"))

        await orch.run_all()

        assert max_concurrent <= 2


class TestOrchestratorResultMerging:
    """Tests for result merging logic."""

    @pytest.mark.asyncio
    async def test_merge_maps_agent_names_to_fields(self, mock_llm_client, event_queue):
        """Each agent's results should map to the correct AnalysisResult field."""
        orch = AgentOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        orch.register_agent(FakeAgent(
            name="ast_analyzer", description="AST", data={"flow": "data"}
        ))
        orch.register_agent(FakeAgent(
            name="er_extractor", description="ER", data={"tables": []}
        ))
        orch.register_agent(FakeAgent(
            name="code_auditor", description="Audit", data={"issues": 0}
        ))
        orch.register_agent(FakeAgent(
            name="doc_generator", description="Docs", data={"docs": "readme"}
        ))
        orch.register_agent(FakeAgent(
            name="system_reporter", description="System", data={"stack": "py"}
        ))

        result = await orch.run_all()

        assert result.code_flow == {"flow": "data"}
        assert result.er_model == {"tables": []}
        assert result.audit == {"issues": 0}
        assert result.artifacts == {"docs": "readme"}
        assert result.system_report == {"stack": "py"}
