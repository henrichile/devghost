"""
SSE Event Bus with atomic sequence counter.

Wraps an asyncio.Queue and provides methods to emit AgentEvent instances
with strictly monotonically increasing sequence numbers. Supports
agent lifecycle events (start, progress, complete, error) and
batch-level progress forwarding.

Satisfies Requirements: 6.5, 6.2, 5.5
"""

from __future__ import annotations

import asyncio
import itertools
import threading
from datetime import datetime, timezone
from typing import Optional

from dev_ghost_parser.agent_models import (
    AgentEvent,
    AgentEventType,
    AgentIdentifier,
)


def _now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 with millisecond precision."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


class EventBus:
    """SSE Event Bus with thread-safe monotonically increasing sequence counter.

    Wraps an asyncio.Queue[AgentEvent] and ensures every emitted event
    receives a unique, strictly increasing sequence number via an atomic
    counter (itertools.count protected by a threading.Lock for thread-safety).

    Usage:
        queue = asyncio.Queue()
        bus = EventBus(queue)
        await bus.emit_agent_start("code_auditor", "Analyzing code quality")
        await bus.emit_batch_progress("code_auditor", batch_index=2, total_batches=5)
        await bus.emit_agent_complete("code_auditor", duration_ms=1234)

    Satisfies Requirements: 6.5, 6.2, 5.5
    """

    def __init__(self, event_queue: asyncio.Queue[AgentEvent]) -> None:
        self._queue = event_queue
        self._counter = itertools.count(1)  # Start at 1, strictly increasing
        self._lock = threading.Lock()

    def _next_sequence(self) -> int:
        """Get the next sequence number in a thread-safe manner.

        Uses a threading.Lock to guarantee atomicity even if called
        from multiple threads (e.g., via run_in_executor).
        """
        with self._lock:
            return next(self._counter)

    @property
    def queue(self) -> asyncio.Queue[AgentEvent]:
        """Access the underlying event queue."""
        return self._queue

    async def emit(
        self,
        *,
        type: AgentEventType,
        agent: AgentIdentifier,
        message: str,
        duration_ms: Optional[int] = None,
        result: Optional[dict] = None,
        error: Optional[str] = None,
        progress_pct: Optional[float] = None,
        retry_count: Optional[int] = None,
    ) -> AgentEvent:
        """Emit an event with an auto-assigned sequence number.

        This is the core emission method. All other emit_* methods
        delegate to this one. The sequence number is assigned atomically
        and is guaranteed to be strictly greater than any previously
        assigned sequence number.

        Args:
            type: Event type (agent_start, agent_progress, etc.).
            agent: Agent identifier.
            message: Human-readable event message.
            duration_ms: Duration in ms (for complete events).
            result: Analysis result data (for analysis_complete events).
            error: Error message (for error events, max 1024 chars).
            progress_pct: Progress percentage 0.0-100.0.
            retry_count: Number of retries attempted.

        Returns:
            The emitted AgentEvent with its assigned sequence number.
        """
        # Truncate error to 1024 characters if provided
        if error is not None and len(error) > 1024:
            error = error[:1021] + "..."

        # Ensure error is at least 1 char if provided
        if error is not None and len(error) == 0:
            error = "Unknown error"

        sequence = self._next_sequence()

        event = AgentEvent(
            type=type,
            agent=agent,
            message=message,
            timestamp=_now_iso(),
            sequence=sequence,
            duration_ms=duration_ms,
            result=result,
            error=error,
            progress_pct=progress_pct,
            retry_count=retry_count,
        )

        await self._queue.put(event)
        return event

    async def emit_agent_start(
        self,
        agent: AgentIdentifier,
        description: str,
    ) -> AgentEvent:
        """Emit an agent_start event.

        Called when a sub-agent begins execution.

        Args:
            agent: Agent identifier (e.g., "code_auditor").
            description: Human-readable description of the agent's task.

        Returns:
            The emitted AgentEvent.

        Satisfies Requirements: 6.1
        """
        return await self.emit(
            type="agent_start",
            agent=agent,
            message=description,
        )

    async def emit_agent_progress(
        self,
        agent: AgentIdentifier,
        message: str,
        progress_pct: Optional[float] = None,
    ) -> AgentEvent:
        """Emit an agent_progress event.

        Called when a sub-agent reports incremental progress.

        Args:
            agent: Agent identifier.
            message: Progress description.
            progress_pct: Optional progress percentage (0.0 - 100.0).

        Returns:
            The emitted AgentEvent.

        Satisfies Requirements: 6.2
        """
        return await self.emit(
            type="agent_progress",
            agent=agent,
            message=message,
            progress_pct=progress_pct,
        )

    async def emit_agent_complete(
        self,
        agent: AgentIdentifier,
        duration_ms: int,
        message: Optional[str] = None,
        result: Optional[dict] = None,
    ) -> AgentEvent:
        """Emit an agent_complete event.

        Called when a sub-agent finishes execution successfully.

        Args:
            agent: Agent identifier.
            duration_ms: Elapsed execution time in milliseconds.
            message: Optional completion message (defaults to "Completed {agent}").
            result: Optional result data.

        Returns:
            The emitted AgentEvent.

        Satisfies Requirements: 6.3
        """
        return await self.emit(
            type="agent_complete",
            agent=agent,
            message=message or f"Completed {agent}",
            duration_ms=duration_ms,
            result=result,
        )

    async def emit_agent_error(
        self,
        agent: AgentIdentifier,
        error: str,
        retry_count: int = 0,
        message: Optional[str] = None,
    ) -> AgentEvent:
        """Emit an agent_error event.

        Called when a sub-agent fails after exhausting retries.
        Error messages are automatically truncated to 1024 characters.

        Args:
            agent: Agent identifier.
            error: Error description (will be truncated to 1024 chars).
            retry_count: Number of retries that were attempted.
            message: Optional custom message (defaults to "Agent {agent} failed: {error}").

        Returns:
            The emitted AgentEvent.

        Satisfies Requirements: 6.4
        """
        # Build default message if not provided
        if message is None:
            message = f"Agent {agent} failed: {error}"

        # Truncate message to 2048 chars (AgentEvent limit)
        if len(message) > 2048:
            message = message[:2045] + "..."

        return await self.emit(
            type="agent_error",
            agent=agent,
            message=message,
            error=error,
            retry_count=retry_count,
        )

    async def emit_batch_progress(
        self,
        agent: AgentIdentifier,
        batch_index: int,
        total_batches: int,
    ) -> AgentEvent:
        """Emit a batch-level progress event.

        Emits "Processing batch X/Y" with calculated progress percentage.

        Args:
            agent: Agent identifier processing the batches.
            batch_index: Current batch number (1-indexed).
            total_batches: Total number of batches.

        Returns:
            The emitted AgentEvent.

        Satisfies Requirements: 5.5, 6.2
        """
        progress_pct = (batch_index / total_batches) * 100.0 if total_batches > 0 else 0.0
        message = f"Processing batch {batch_index}/{total_batches}"

        return await self.emit(
            type="agent_progress",
            agent=agent,
            message=message,
            progress_pct=progress_pct,
        )

    async def emit_analysis_complete(
        self,
        agent: AgentIdentifier,
        result: dict,
    ) -> AgentEvent:
        """Emit an analysis_complete event with the final merged result.

        Args:
            agent: Agent identifier (typically the orchestrator agent).
            result: The full analysis result dictionary.

        Returns:
            The emitted AgentEvent.
        """
        return await self.emit(
            type="analysis_complete",
            agent=agent,
            message="Analysis complete",
            result=result,
        )

    async def emit_analysis_error(
        self,
        agent: AgentIdentifier,
        error: str,
    ) -> AgentEvent:
        """Emit an analysis_error event for pipeline-level failures.

        Args:
            agent: Agent identifier.
            error: Error description.

        Returns:
            The emitted AgentEvent.
        """
        # Build message
        message = f"Analysis failed: {error}"
        if len(message) > 2048:
            message = message[:2045] + "..."

        return await self.emit(
            type="analysis_error",
            agent=agent,
            message=message,
            error=error,
        )
