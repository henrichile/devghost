# Feature: sub-agent-parallel-analysis, Property 10: SSE Sequence Monotonicity
# Feature: sub-agent-parallel-analysis, Property 11: SSE Error Message Truncation
"""
Property 10: SSE Sequence Monotonicity

For any sequence of AgentEvent objects emitted during a pipeline execution,
the sequence field SHALL be strictly monotonically increasing (each event's
sequence > previous event's sequence).

Property 11: SSE Error Message Truncation

For any error message string of any length, when emitted as an agent_error event,
the error field SHALL be truncated to at most 1024 characters while the retry_count
field accurately reflects the number of retries attempted.

Validates: Requirements 6.5, 1.5, 6.4
"""

from __future__ import annotations

import asyncio
from typing import List

import pytest
from hypothesis import given, settings, strategies as st

from dev_ghost_parser.agent_models import AgentEvent, AgentIdentifier
from dev_ghost_parser.event_bus import EventBus


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

VALID_AGENT_IDENTIFIERS: list[AgentIdentifier] = [
    "ast_analyzer",
    "er_extractor",
    "code_auditor",
    "doc_generator",
    "system_reporter",
]

agent_strategy = st.sampled_from(VALID_AGENT_IDENTIFIERS)

# Number of events to emit in a sequence (1-50)
event_count_strategy = st.integers(min_value=1, max_value=50)

# Random string for error messages (0-10000 characters)
error_string_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z")),
    min_size=0,
    max_size=10000,
)

# Retry count strategy
retry_count_strategy = st.integers(min_value=0, max_value=10)

# Message strategy for general events
message_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z")),
    min_size=1,
    max_size=200,
)

# Event type choices for generating varied event sequences
event_type_choices = st.sampled_from([
    "start",
    "progress",
    "complete",
    "error",
    "batch_progress",
])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_async(coro):
    """Run an async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _emit_random_events(
    bus: EventBus,
    count: int,
    agent: AgentIdentifier,
    event_types: List[str],
) -> List[AgentEvent]:
    """Emit a sequence of events through the bus and collect them from the queue."""
    events: List[AgentEvent] = []

    for i, etype in enumerate(event_types[:count]):
        if etype == "start":
            event = await bus.emit_agent_start(agent, f"Starting task {i}")
        elif etype == "progress":
            event = await bus.emit_agent_progress(agent, f"Progress {i}", progress_pct=float(i))
        elif etype == "complete":
            event = await bus.emit_agent_complete(agent, duration_ms=100 * (i + 1))
        elif etype == "error":
            event = await bus.emit_agent_error(agent, f"Error {i}", retry_count=0)
        elif etype == "batch_progress":
            event = await bus.emit_batch_progress(agent, batch_index=i + 1, total_batches=count)
        else:
            event = await bus.emit_agent_progress(agent, f"Fallback {i}")
        events.append(event)

    return events


# ---------------------------------------------------------------------------
# Property 10: SSE Sequence Monotonicity
# ---------------------------------------------------------------------------


class TestProperty10SSESequenceMonotonicity:
    """Feature: sub-agent-parallel-analysis, Property 10: SSE Sequence Monotonicity"""

    @settings(max_examples=100)
    @given(
        count=event_count_strategy,
        agent=agent_strategy,
        event_types=st.lists(event_type_choices, min_size=50, max_size=50),
    )
    def test_property_10_sequence_strictly_increasing(
        self, count: int, agent: AgentIdentifier, event_types: List[str]
    ):
        """Emit N random events through an EventBus and verify that sequence
        numbers are strictly monotonically increasing.

        **Validates: Requirements 6.5, 1.5**
        """

        async def _run():
            queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
            bus = EventBus(queue)
            events = await _emit_random_events(bus, count, agent, event_types)
            return events

        events = _run_async(_run())

        # Verify we got the expected number of events
        assert len(events) == count

        # Verify strict monotonicity: each sequence > previous
        for i in range(1, len(events)):
            assert events[i].sequence > events[i - 1].sequence, (
                f"Sequence not strictly increasing at index {i}: "
                f"{events[i - 1].sequence} >= {events[i].sequence}"
            )

    @settings(max_examples=100)
    @given(
        count=event_count_strategy,
        agent=agent_strategy,
    )
    def test_property_10_sequence_starts_at_one_or_higher(
        self, count: int, agent: AgentIdentifier
    ):
        """Verify that the first event in a fresh EventBus has sequence >= 1.

        **Validates: Requirements 6.5**
        """

        async def _run():
            queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
            bus = EventBus(queue)
            event = await bus.emit_agent_start(agent, "First event")
            return event

        event = _run_async(_run())
        assert event.sequence >= 1, f"First sequence should be >= 1, got {event.sequence}"

    @settings(max_examples=100)
    @given(
        count=st.integers(min_value=2, max_value=50),
        agent=agent_strategy,
    )
    def test_property_10_no_duplicate_sequences(
        self, count: int, agent: AgentIdentifier
    ):
        """Verify that no two events share the same sequence number.

        **Validates: Requirements 6.5, 1.5**
        """

        async def _run():
            queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
            bus = EventBus(queue)
            events = []
            for i in range(count):
                event = await bus.emit_agent_progress(agent, f"Event {i}")
                events.append(event)
            return events

        events = _run_async(_run())
        sequences = [e.sequence for e in events]
        assert len(sequences) == len(set(sequences)), (
            f"Duplicate sequence numbers found: {sequences}"
        )


# ---------------------------------------------------------------------------
# Property 11: SSE Error Message Truncation
# ---------------------------------------------------------------------------


class TestProperty11SSEErrorMessageTruncation:
    """Feature: sub-agent-parallel-analysis, Property 11: SSE Error Message Truncation"""

    @settings(max_examples=100)
    @given(
        error_msg=error_string_strategy,
        agent=agent_strategy,
        retry_count=retry_count_strategy,
    )
    def test_property_11_error_truncated_to_1024_chars(
        self, error_msg: str, agent: AgentIdentifier, retry_count: int
    ):
        """For any error string of length 0-10000, the emitted event's error field
        SHALL be at most 1024 characters.

        **Validates: Requirements 6.4**
        """

        async def _run():
            queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
            bus = EventBus(queue)
            event = await bus.emit_agent_error(agent, error_msg, retry_count=retry_count)
            return event

        event = _run_async(_run())

        # The error field must be at most 1024 characters
        assert event.error is not None
        assert len(event.error) <= 1024, (
            f"Error field exceeds 1024 chars: got {len(event.error)} "
            f"(original length: {len(error_msg)})"
        )

    @settings(max_examples=100)
    @given(
        error_msg=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z")),
            min_size=1,
            max_size=1024,
        ),
        agent=agent_strategy,
        retry_count=retry_count_strategy,
    )
    def test_property_11_short_errors_preserved(
        self, error_msg: str, agent: AgentIdentifier, retry_count: int
    ):
        """Error messages that are already <= 1024 chars should be preserved as-is.

        **Validates: Requirements 6.4**
        """

        async def _run():
            queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
            bus = EventBus(queue)
            event = await bus.emit_agent_error(agent, error_msg, retry_count=retry_count)
            return event

        event = _run_async(_run())

        # Short errors should be preserved unchanged
        assert event.error == error_msg, (
            f"Short error was modified: expected {error_msg!r}, got {event.error!r}"
        )

    @settings(max_examples=100)
    @given(
        error_msg=error_string_strategy,
        agent=agent_strategy,
        retry_count=retry_count_strategy,
    )
    def test_property_11_retry_count_preserved(
        self, error_msg: str, agent: AgentIdentifier, retry_count: int
    ):
        """The retry_count field SHALL accurately reflect the retries attempted.

        **Validates: Requirements 6.4**
        """

        async def _run():
            queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
            bus = EventBus(queue)
            event = await bus.emit_agent_error(agent, error_msg, retry_count=retry_count)
            return event

        event = _run_async(_run())

        # retry_count must match what was passed
        assert event.retry_count == retry_count, (
            f"retry_count mismatch: expected {retry_count}, got {event.retry_count}"
        )
