"""Base agent infrastructure for the multi-agent architecture."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from dev_ghost_parser.retry_policy import RetryPolicy

if TYPE_CHECKING:
    from dev_ghost_parser.agent_models import AgentEvent, AgentResult
    from dev_ghost_parser.event_bus import EventBus
    from dev_ghost_parser.llm_client import LLM_Client


@dataclass
class AgentContext:
    """Shared execution context with dependency results.

    Satisfies Requirements 3.3, 8.5, 7.4, 6.2.

    Fields:
        repo_path: Path to the cloned repository being analyzed.
        llm_client: LLM client instance for agent use.
        event_queue: Async queue for emitting AgentEvent instances.
        dependency_results: Resolved results from upstream agents.
            Key: agent name, Value: AgentResult from that agent.
        event_bus: Optional EventBus for emitting events with sequence numbers.
            When provided, agents use this for progress events to ensure
            proper sequence numbering across all SSE events.
    """

    repo_path: str
    llm_client: "LLM_Client"
    event_queue: asyncio.Queue
    dependency_results: dict[str, "AgentResult"] = field(default_factory=dict)
    event_bus: Optional["EventBus"] = None
    # Key: agent name, Value: AgentResult from that agent


class BaseAgent(ABC):
    """Enhanced base class with dependency, timeout, and retry support.

    Subclasses must set `name` and `description` and implement `execute()`.
    Optionally override `dependencies`, `timeout_seconds`, or `retry_policy`
    to customize execution behavior.
    """

    name: str  # e.g., "ast_analyzer"
    description: str  # e.g., "Analyzes AST structure and code flow"

    def __init__(self) -> None:
        self._context: AgentContext | None = None

    @property
    def dependencies(self) -> list[str]:
        """Agent names this agent depends on (beyond implicit AST).

        Override to declare explicit dependencies. Default: empty list.
        """
        return []

    @property
    def timeout_seconds(self) -> float:
        """Individual timeout for this agent. Default: 60s."""
        return 60.0

    @property
    def retry_policy(self) -> RetryPolicy:
        """Retry configuration for this agent. Default: 2 retries, 1s base."""
        return RetryPolicy()

    def bind_context(self, context: AgentContext) -> None:
        """Bind an AgentContext so emit_progress can push events to the queue."""
        self._context = context

    @abstractmethod
    async def execute(self, context: AgentContext) -> "AgentResult":
        """Execute the agent's analysis. Emits progress events via the queue."""
        ...

    async def emit_progress(self, message: str, progress_pct: float | None = None) -> None:
        """Emit a progress event through the shared EventBus or queue.

        When an EventBus is available in the context, uses it to ensure the
        progress event gets a proper sequence number consistent with all other
        pipeline events. Falls back to direct queue insertion if no EventBus
        is available.

        Satisfies Requirements: 6.2

        Args:
            message: Human-readable progress description.
            progress_pct: Optional progress percentage (0.0 - 100.0).
        """
        if self._context is None:
            return

        # Prefer EventBus for proper sequence numbering (Req 6.5)
        if self._context.event_bus is not None:
            await self._context.event_bus.emit_agent_progress(
                self.name,
                message,
                progress_pct=progress_pct,
            )
            return

        # Fallback: direct queue insertion (without sequence number)
        from dev_ghost_parser.agent_models import AgentEvent

        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"

        event = AgentEvent(
            type="agent_progress",
            agent=self.name,
            message=message,
            timestamp=timestamp,
            progress_pct=progress_pct,
        )
        await self._context.event_queue.put(event)
