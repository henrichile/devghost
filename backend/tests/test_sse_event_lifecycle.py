"""
Tests for SSE event lifecycle: verifies the complete event emission
with sequence numbers across the orchestrator pipeline.

Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5

Verifies:
- agent_start emitted when an agent begins
- agent_progress forwarded from agents with proper sequence numbers
- agent_complete emitted on success with duration_ms
- agent_error emitted on failure with truncated error and retry_count
- All events have strictly monotonically increasing sequence numbers
- EventBus integration provides consistent sequence numbering
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from dev_ghost_parser.agent_models import AgentEvent, AgentResult
from dev_ghost_parser.base_agent import AgentContext, BaseAgent
from dev_ghost_parser.graph_orchestrator import (
    DependencyGraphOrchestrator,
    FoundationalPhaseError,
)
from dev_ghost_parser.retry_policy import RetryPolicy


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class SuccessfulAgent(BaseAgent):
    """Agent that succeeds and emits progress events."""

    def __init__(self, name: str, description: str = "Test agent", data: dict | None = None):
        super().__init__()
        self.name = name
        self.description = description
        self._data = data or {"result": f"{name}_output"}

    async def execute(self, context: AgentContext) -> AgentResult:
        # Emit progress events (Req 6.2) — should get sequence numbers via EventBus
        await self.emit_progress("Starting analysis...")
        await self.emit_progress("Processing files...", progress_pct=50.0)
        await self.emit_progress("Finalizing...", progress_pct=100.0)
        return AgentResult(
            agent_name=self.name,
            success=True,
            data=self._data,
        )


class FailingAgent(BaseAgent):
    """Agent that always raises an exception."""

    def __init__(self, name: str, description: str = "Failing agent", error_msg: str = "Boom"):
        super().__init__()
        self.name = name
        self.description = description
        self._error_msg = error_msg

    @property
    def retry_policy(self) -> RetryPolicy:
        return RetryPolicy(max_retries=1, base_delay_seconds=0.01, multiplier=1.0)

    @property
    def timeout_seconds(self) -> float:
        return 5.0

    async def execute(self, context: AgentContext) -> AgentResult:
        raise RuntimeError(self._error_msg)


class LongErrorAgent(BaseAgent):
    """Agent that fails with a very long error message (>1024 chars)."""

    def __init__(self, name: str):
        super().__init__()
        self.name = name
        self.description = "Agent with long error"

    @property
    def retry_policy(self) -> RetryPolicy:
        return RetryPolicy(max_retries=0, base_delay_seconds=0.01, multiplier=1.0)

    @property
    def timeout_seconds(self) -> float:
        return 5.0

    async def execute(self, context: AgentContext) -> AgentResult:
        # Create an error message longer than 1024 chars
        long_msg = "X" * 2000
        raise RuntimeError(long_msg)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_llm_client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def event_queue() -> asyncio.Queue:
    return asyncio.Queue()


def _collect_events(queue: asyncio.Queue) -> list[AgentEvent]:
    """Drain all events from the queue."""
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


# ---------------------------------------------------------------------------
# Tests: Complete Event Lifecycle
# ---------------------------------------------------------------------------


class TestSSEEventLifecycleSuccess:
    """Verify full event lifecycle for a successful pipeline run."""

    @pytest.mark.asyncio
    async def test_successful_pipeline_emits_complete_lifecycle(
        self, mock_llm_client, event_queue
    ):
        """A successful pipeline should emit: agent_start → agent_progress → agent_complete
        for each agent, all with proper sequence numbers.

        **Validates: Requirements 6.1, 6.2, 6.3, 6.5**
        """
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        orch.register_agent(SuccessfulAgent(
            name="ast_analyzer",
            description="Analyzes AST structure",
            data={"ast": "tree"},
        ))
        orch.register_agent(SuccessfulAgent(
            name="code_auditor",
            description="Audits code quality",
            data={"issues": 0},
        ))

        await orch.run_pipeline()

        events = _collect_events(event_queue)

        # Verify all events have sequence numbers > 0
        for event in events:
            assert event.sequence > 0, f"Event {event.type} for {event.agent} has seq=0"

        # Verify strict monotonicity of sequence numbers
        sequences = [e.sequence for e in events]
        for i in range(1, len(sequences)):
            assert sequences[i] > sequences[i - 1], (
                f"Sequence not strictly increasing: {sequences[i - 1]} >= {sequences[i]} "
                f"at events [{events[i - 1].type}:{events[i - 1].agent}, "
                f"{events[i].type}:{events[i].agent}]"
            )

        # Verify agent_start events present for both agents
        start_events = [e for e in events if e.type == "agent_start"]
        start_agents = {e.agent for e in start_events}
        assert "ast_analyzer" in start_agents
        assert "code_auditor" in start_agents

        # Verify agent_progress events with proper sequence numbers
        progress_events = [e for e in events if e.type == "agent_progress"]
        assert len(progress_events) >= 3  # At least 3 from ast_analyzer

        # Verify agent_complete events present for both agents
        complete_events = [e for e in events if e.type == "agent_complete"]
        complete_agents = {e.agent for e in complete_events}
        assert "ast_analyzer" in complete_agents
        assert "code_auditor" in complete_agents

        # Verify duration_ms is set on complete events
        for ce in complete_events:
            assert ce.duration_ms is not None
            assert ce.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_progress_events_have_sequence_numbers(
        self, mock_llm_client, event_queue
    ):
        """Progress events emitted by agents should have proper sequence numbers
        when EventBus is used.

        **Validates: Requirements 6.2, 6.5**
        """
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        orch.register_agent(SuccessfulAgent(
            name="ast_analyzer",
            description="AST Analysis",
        ))

        await orch.run_pipeline()

        events = _collect_events(event_queue)
        progress_events = [e for e in events if e.type == "agent_progress"]

        # All progress events should have sequence > 0
        for pe in progress_events:
            assert pe.sequence > 0, "Progress event missing sequence number"

        # Progress events should be interleaved in the overall sequence
        # (between start and complete)
        start_seq = next(e.sequence for e in events if e.type == "agent_start")
        complete_seq = next(e.sequence for e in events if e.type == "agent_complete")

        for pe in progress_events:
            if pe.agent == "ast_analyzer":
                assert start_seq < pe.sequence < complete_seq, (
                    f"Progress event seq {pe.sequence} not between start ({start_seq}) "
                    f"and complete ({complete_seq})"
                )

    @pytest.mark.asyncio
    async def test_progress_pct_passed_through(
        self, mock_llm_client, event_queue
    ):
        """Progress percentage should be correctly forwarded via EventBus.

        **Validates: Requirements 6.2**
        """
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        orch.register_agent(SuccessfulAgent(
            name="ast_analyzer",
            description="AST Analysis",
        ))

        await orch.run_pipeline()

        events = _collect_events(event_queue)
        progress_events = [e for e in events if e.type == "agent_progress"]

        # Should have progress events with progress_pct values
        pct_values = [e.progress_pct for e in progress_events if e.progress_pct is not None]
        assert 50.0 in pct_values
        assert 100.0 in pct_values


class TestSSEEventLifecycleFailure:
    """Verify event lifecycle for failed agents."""

    @pytest.mark.asyncio
    async def test_failed_agent_emits_error_with_retry_count(
        self, mock_llm_client, event_queue
    ):
        """A failed agent should emit agent_error with retry_count after all retries.

        **Validates: Requirements 6.4, 6.5**
        """
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        orch.register_agent(SuccessfulAgent(
            name="ast_analyzer",
            description="AST",
            data={"ast": "ok"},
        ))
        orch.register_agent(FailingAgent(
            name="code_auditor",
            description="Audit",
            error_msg="Parse error in main.py",
        ))

        await orch.run_pipeline()

        events = _collect_events(event_queue)

        # Find the error event for code_auditor
        error_events = [e for e in events if e.type == "agent_error" and e.agent == "code_auditor"]
        assert len(error_events) == 1

        error_event = error_events[0]
        assert error_event.error is not None
        assert "Parse error in main.py" in error_event.error
        assert error_event.retry_count == 1  # FailingAgent has max_retries=1
        assert error_event.sequence > 0

    @pytest.mark.asyncio
    async def test_error_message_truncated_to_1024_chars(
        self, mock_llm_client, event_queue
    ):
        """Error messages longer than 1024 chars should be truncated.

        **Validates: Requirements 6.4**
        """
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        orch.register_agent(SuccessfulAgent(
            name="ast_analyzer",
            description="AST",
            data={"ast": "ok"},
        ))
        orch.register_agent(LongErrorAgent(name="code_auditor"))

        await orch.run_pipeline()

        events = _collect_events(event_queue)
        error_events = [e for e in events if e.type == "agent_error" and e.agent == "code_auditor"]
        assert len(error_events) == 1

        error_event = error_events[0]
        assert error_event.error is not None
        assert len(error_event.error) <= 1024, (
            f"Error not truncated: {len(error_event.error)} chars"
        )

    @pytest.mark.asyncio
    async def test_foundational_failure_emits_error_event(
        self, mock_llm_client, event_queue
    ):
        """When the AST foundational phase fails, it should emit agent_error
        with retry_count before raising FoundationalPhaseError.

        **Validates: Requirements 6.4, 6.5**
        """
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        orch.register_agent(FailingAgent(
            name="ast_analyzer",
            description="AST Analysis",
            error_msg="Cannot parse",
        ))

        with pytest.raises(FoundationalPhaseError):
            await orch.run_pipeline()

        events = _collect_events(event_queue)

        # Should have agent_start and then agent_error
        start_events = [e for e in events if e.type == "agent_start"]
        error_events = [e for e in events if e.type == "agent_error"]

        assert len(start_events) == 1
        assert start_events[0].agent == "ast_analyzer"

        assert len(error_events) == 1
        assert error_events[0].agent == "ast_analyzer"
        assert error_events[0].retry_count == 1  # FailingAgent has max_retries=1
        assert error_events[0].error is not None
        assert "Cannot parse" in error_events[0].error

        # Verify sequence ordering: start before error
        assert start_events[0].sequence < error_events[0].sequence


class TestSSESequenceMonotonicity:
    """Verify sequence numbers are strictly monotonically increasing."""

    @pytest.mark.asyncio
    async def test_all_events_have_increasing_sequences(
        self, mock_llm_client, event_queue
    ):
        """All events across the entire pipeline must have strictly increasing
        sequence numbers, regardless of which agent emitted them.

        **Validates: Requirements 6.5**
        """
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        orch.register_agent(SuccessfulAgent(
            name="ast_analyzer", description="AST", data={"ast": "data"}
        ))
        orch.register_agent(SuccessfulAgent(
            name="er_extractor", description="ER", data={"er": "data"}
        ))
        orch.register_agent(SuccessfulAgent(
            name="code_auditor", description="Audit", data={"audit": "data"}
        ))

        await orch.run_pipeline()

        events = _collect_events(event_queue)

        # All events should have sequences
        assert len(events) > 0
        for event in events:
            assert event.sequence > 0

        # Strict monotonicity
        for i in range(1, len(events)):
            assert events[i].sequence > events[i - 1].sequence, (
                f"Sequence violation at index {i}: "
                f"event[{i-1}]=(type={events[i-1].type}, agent={events[i-1].agent}, "
                f"seq={events[i-1].sequence}) >= "
                f"event[{i}]=(type={events[i].type}, agent={events[i].agent}, "
                f"seq={events[i].sequence})"
            )

    @pytest.mark.asyncio
    async def test_no_duplicate_sequence_numbers(
        self, mock_llm_client, event_queue
    ):
        """No two events should share the same sequence number.

        **Validates: Requirements 6.5**
        """
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        orch.register_agent(SuccessfulAgent(
            name="ast_analyzer", description="AST", data={"ast": "data"}
        ))
        orch.register_agent(SuccessfulAgent(
            name="code_auditor", description="Audit", data={"audit": "data"}
        ))

        await orch.run_pipeline()

        events = _collect_events(event_queue)
        sequences = [e.sequence for e in events]
        assert len(sequences) == len(set(sequences)), (
            f"Duplicate sequence numbers found: {sequences}"
        )

    @pytest.mark.asyncio
    async def test_sequence_starts_at_one(
        self, mock_llm_client, event_queue
    ):
        """The first event emitted should have sequence=1.

        **Validates: Requirements 6.5**
        """
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        orch.register_agent(SuccessfulAgent(
            name="ast_analyzer", description="AST", data={"ast": "data"}
        ))

        await orch.run_pipeline()

        events = _collect_events(event_queue)
        assert events[0].sequence == 1


class TestEventBusIntegration:
    """Verify that the orchestrator correctly uses EventBus."""

    @pytest.mark.asyncio
    async def test_orchestrator_exposes_event_bus(
        self, mock_llm_client, event_queue
    ):
        """The orchestrator should expose its EventBus for external access.

        **Validates: Requirements 6.5**
        """
        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        assert orch.event_bus is not None
        assert orch.event_bus.queue is event_queue

    @pytest.mark.asyncio
    async def test_event_bus_shared_with_agents_via_context(
        self, mock_llm_client, event_queue
    ):
        """Agents should receive the EventBus through their context,
        enabling proper sequence numbering on progress events.

        **Validates: Requirements 6.2, 6.5**
        """
        context_captured = {}

        class ContextCapturingAgent(BaseAgent):
            def __init__(self, name: str):
                super().__init__()
                self.name = name
                self.description = f"Captures context: {name}"

            async def execute(self, context: AgentContext) -> AgentResult:
                context_captured[self.name] = context
                return AgentResult(agent_name=self.name, success=True, data={})

        orch = DependencyGraphOrchestrator(
            repo_path="/tmp/repo",
            llm_client=mock_llm_client,
            event_queue=event_queue,
        )
        orch.register_agent(ContextCapturingAgent(name="ast_analyzer"))
        orch.register_agent(ContextCapturingAgent(name="code_auditor"))

        await orch.run_pipeline()

        # Both agents should have received the EventBus in their context
        assert "ast_analyzer" in context_captured
        assert context_captured["ast_analyzer"].event_bus is not None
        assert context_captured["ast_analyzer"].event_bus is orch.event_bus

        assert "code_auditor" in context_captured
        assert context_captured["code_auditor"].event_bus is not None
        assert context_captured["code_auditor"].event_bus is orch.event_bus
