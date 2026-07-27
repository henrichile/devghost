"""Unit tests for EventBus with SSE sequence counter."""

import asyncio

import pytest

from dev_ghost_parser.agent_models import AgentEvent
from dev_ghost_parser.event_bus import EventBus


@pytest.fixture
def event_queue():
    """Create a fresh asyncio.Queue for testing."""
    return asyncio.Queue()


@pytest.fixture
def event_bus(event_queue):
    """Create an EventBus instance with a fresh queue."""
    return EventBus(event_queue)


class TestSequenceCounter:
    """Verify the atomic sequence counter produces strictly increasing values."""

    @pytest.mark.asyncio
    async def test_first_event_gets_sequence_1(self, event_bus, event_queue):
        await event_bus.emit_agent_start("ast_analyzer", "Starting AST analysis")
        event = event_queue.get_nowait()
        assert event.sequence == 1

    @pytest.mark.asyncio
    async def test_sequence_increases_strictly(self, event_bus, event_queue):
        await event_bus.emit_agent_start("ast_analyzer", "Starting")
        await event_bus.emit_agent_progress("ast_analyzer", "Working")
        await event_bus.emit_agent_complete("ast_analyzer", duration_ms=100)

        events = []
        while not event_queue.empty():
            events.append(event_queue.get_nowait())

        sequences = [e.sequence for e in events]
        assert sequences == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_sequence_never_repeats(self, event_bus, event_queue):
        for i in range(10):
            await event_bus.emit_agent_progress("code_auditor", f"Step {i}")

        events = []
        while not event_queue.empty():
            events.append(event_queue.get_nowait())

        sequences = [e.sequence for e in events]
        assert len(sequences) == len(set(sequences)), "Sequence numbers must be unique"

    @pytest.mark.asyncio
    async def test_sequence_is_monotonically_increasing(self, event_bus, event_queue):
        for _ in range(20):
            await event_bus.emit_agent_progress("er_extractor", "Processing")

        events = []
        while not event_queue.empty():
            events.append(event_queue.get_nowait())

        sequences = [e.sequence for e in events]
        for i in range(1, len(sequences)):
            assert sequences[i] > sequences[i - 1], (
                f"Sequence must be strictly increasing: {sequences[i-1]} -> {sequences[i]}"
            )


class TestEmitAgentStart:
    """Verify agent_start event emission."""

    @pytest.mark.asyncio
    async def test_emits_correct_type(self, event_bus, event_queue):
        await event_bus.emit_agent_start("code_auditor", "Auditing code quality")
        event = event_queue.get_nowait()
        assert event.type == "agent_start"

    @pytest.mark.asyncio
    async def test_emits_correct_agent(self, event_bus, event_queue):
        await event_bus.emit_agent_start("er_extractor", "Extracting entities")
        event = event_queue.get_nowait()
        assert event.agent == "er_extractor"

    @pytest.mark.asyncio
    async def test_emits_correct_message(self, event_bus, event_queue):
        await event_bus.emit_agent_start("doc_generator", "Generating documentation")
        event = event_queue.get_nowait()
        assert event.message == "Generating documentation"

    @pytest.mark.asyncio
    async def test_has_timestamp(self, event_bus, event_queue):
        await event_bus.emit_agent_start("ast_analyzer", "Starting")
        event = event_queue.get_nowait()
        assert event.timestamp is not None
        assert "T" in event.timestamp  # ISO 8601 format


class TestEmitAgentProgress:
    """Verify agent_progress event emission."""

    @pytest.mark.asyncio
    async def test_emits_progress_type(self, event_bus, event_queue):
        await event_bus.emit_agent_progress("code_auditor", "Analyzing files")
        event = event_queue.get_nowait()
        assert event.type == "agent_progress"

    @pytest.mark.asyncio
    async def test_includes_progress_pct(self, event_bus, event_queue):
        await event_bus.emit_agent_progress("code_auditor", "Half done", progress_pct=50.0)
        event = event_queue.get_nowait()
        assert event.progress_pct == 50.0

    @pytest.mark.asyncio
    async def test_progress_pct_optional(self, event_bus, event_queue):
        await event_bus.emit_agent_progress("code_auditor", "Working")
        event = event_queue.get_nowait()
        assert event.progress_pct is None


class TestEmitAgentComplete:
    """Verify agent_complete event emission."""

    @pytest.mark.asyncio
    async def test_emits_complete_type(self, event_bus, event_queue):
        await event_bus.emit_agent_complete("ast_analyzer", duration_ms=500)
        event = event_queue.get_nowait()
        assert event.type == "agent_complete"

    @pytest.mark.asyncio
    async def test_includes_duration(self, event_bus, event_queue):
        await event_bus.emit_agent_complete("ast_analyzer", duration_ms=1234)
        event = event_queue.get_nowait()
        assert event.duration_ms == 1234

    @pytest.mark.asyncio
    async def test_default_message(self, event_bus, event_queue):
        await event_bus.emit_agent_complete("er_extractor", duration_ms=100)
        event = event_queue.get_nowait()
        assert event.message == "Completed er_extractor"

    @pytest.mark.asyncio
    async def test_custom_message(self, event_bus, event_queue):
        await event_bus.emit_agent_complete(
            "code_auditor", duration_ms=200, message="Audit done"
        )
        event = event_queue.get_nowait()
        assert event.message == "Audit done"


class TestEmitAgentError:
    """Verify agent_error event emission."""

    @pytest.mark.asyncio
    async def test_emits_error_type(self, event_bus, event_queue):
        await event_bus.emit_agent_error("code_auditor", error="Connection timeout")
        event = event_queue.get_nowait()
        assert event.type == "agent_error"

    @pytest.mark.asyncio
    async def test_includes_error_message(self, event_bus, event_queue):
        await event_bus.emit_agent_error("code_auditor", error="Timeout")
        event = event_queue.get_nowait()
        assert event.error == "Timeout"

    @pytest.mark.asyncio
    async def test_includes_retry_count(self, event_bus, event_queue):
        await event_bus.emit_agent_error("code_auditor", error="Failed", retry_count=2)
        event = event_queue.get_nowait()
        assert event.retry_count == 2

    @pytest.mark.asyncio
    async def test_truncates_error_to_1024_chars(self, event_bus, event_queue):
        long_error = "x" * 2000
        await event_bus.emit_agent_error("code_auditor", error=long_error)
        event = event_queue.get_nowait()
        assert len(event.error) <= 1024

    @pytest.mark.asyncio
    async def test_default_error_message_format(self, event_bus, event_queue):
        await event_bus.emit_agent_error("code_auditor", error="Network failure")
        event = event_queue.get_nowait()
        assert event.message == "Agent code_auditor failed: Network failure"


class TestEmitBatchProgress:
    """Verify batch-level progress forwarding."""

    @pytest.mark.asyncio
    async def test_batch_progress_message_format(self, event_bus, event_queue):
        await event_bus.emit_batch_progress("code_auditor", batch_index=3, total_batches=5)
        event = event_queue.get_nowait()
        assert event.message == "Processing batch 3/5"

    @pytest.mark.asyncio
    async def test_batch_progress_calculates_percentage(self, event_bus, event_queue):
        await event_bus.emit_batch_progress("code_auditor", batch_index=2, total_batches=4)
        event = event_queue.get_nowait()
        assert event.progress_pct == 50.0

    @pytest.mark.asyncio
    async def test_batch_progress_first_batch(self, event_bus, event_queue):
        await event_bus.emit_batch_progress("doc_generator", batch_index=1, total_batches=5)
        event = event_queue.get_nowait()
        assert event.progress_pct == 20.0

    @pytest.mark.asyncio
    async def test_batch_progress_last_batch(self, event_bus, event_queue):
        await event_bus.emit_batch_progress("doc_generator", batch_index=5, total_batches=5)
        event = event_queue.get_nowait()
        assert event.progress_pct == 100.0

    @pytest.mark.asyncio
    async def test_batch_progress_is_agent_progress_type(self, event_bus, event_queue):
        await event_bus.emit_batch_progress("code_auditor", batch_index=1, total_batches=3)
        event = event_queue.get_nowait()
        assert event.type == "agent_progress"

    @pytest.mark.asyncio
    async def test_batch_progress_zero_total_batches(self, event_bus, event_queue):
        await event_bus.emit_batch_progress("code_auditor", batch_index=0, total_batches=0)
        event = event_queue.get_nowait()
        assert event.progress_pct == 0.0


class TestQueueProperty:
    """Verify queue access."""

    def test_queue_accessible(self, event_bus, event_queue):
        assert event_bus.queue is event_queue


class TestEmitReturnValue:
    """Verify emit methods return the created event."""

    @pytest.mark.asyncio
    async def test_emit_returns_event(self, event_bus):
        event = await event_bus.emit_agent_start("ast_analyzer", "Testing")
        assert isinstance(event, AgentEvent)
        assert event.sequence == 1

    @pytest.mark.asyncio
    async def test_emit_batch_returns_event(self, event_bus):
        event = await event_bus.emit_batch_progress("code_auditor", batch_index=1, total_batches=2)
        assert isinstance(event, AgentEvent)
        assert event.message == "Processing batch 1/2"
