"""
Agent Orchestrator for parallel execution of specialized agents.

Coordinates multiple agents running concurrently with structured concurrency
(asyncio.TaskGroup), semaphore-bounded parallelism, and timeout handling.

Satisfies Requirements: 1.1, 1.2, 1.4, 1.5, 1.6, 1.7
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from dev_ghost_parser.agent_models import (
    AgentEvent,
    AgentResult,
    AnalysisResult,
)
from dev_ghost_parser.base_agent import AgentContext, BaseAgent

if TYPE_CHECKING:
    from dev_ghost_parser.llm_client import LLM_Client


# Mapping from agent name to AnalysisResult field
_AGENT_RESULT_FIELD_MAP: dict[str, str] = {
    "ast_analyzer": "code_flow",
    "er_extractor": "er_model",
    "code_auditor": "audit",
    "doc_generator": "artifacts",
    "system_reporter": "system_report",
}


def _now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 with millisecond precision."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


class AgentOrchestrator:
    """Coordinates parallel execution of specialized agents.

    Uses asyncio.TaskGroup for structured concurrency and automatic
    cancellation propagation. A semaphore bounds maximum concurrent
    agent executions.

    Satisfies Requirements: 1.1, 1.2, 1.4, 1.5, 1.6, 1.7
    """

    def __init__(
        self,
        repo_path: str,
        llm_client: "LLM_Client",
        event_queue: asyncio.Queue[AgentEvent],
        max_concurrency: int = 5,
        timeout_seconds: float = 120.0,
    ) -> None:
        self._repo_path = repo_path
        self._llm_client = llm_client
        self._event_queue = event_queue
        self._max_concurrency = max_concurrency
        self._timeout_seconds = timeout_seconds
        self._agents: list[BaseAgent] = []

    def register_agent(self, agent: BaseAgent) -> None:
        """Register an agent to be executed during run_all()."""
        self._agents.append(agent)

    @property
    def agents(self) -> list[BaseAgent]:
        """Return the list of registered agents."""
        return list(self._agents)

    async def run_all(self) -> AnalysisResult:
        """Execute all registered agents in parallel, emit events, return merged result.

        Uses asyncio.TaskGroup for structured concurrency. Applies a global
        timeout; if exceeded, remaining agents are cancelled and timeout errors
        are recorded.

        Returns:
            AnalysisResult with merged data from all successful agents and
            error entries for any that failed or were cancelled.
        """
        semaphore = asyncio.Semaphore(self._max_concurrency)
        results: list[AgentResult | None] = []
        context = AgentContext(
            repo_path=self._repo_path,
            llm_client=self._llm_client,
            event_queue=self._event_queue,
        )

        # Bind context to each agent so they can emit progress events
        for agent in self._agents:
            agent.bind_context(context)

        try:
            results = await asyncio.wait_for(
                self._run_all_agents(semaphore, context),
                timeout=self._timeout_seconds,
            )
        except asyncio.TimeoutError:
            # Timeout: emit error events for agents that didn't produce results
            # The TaskGroup will have been cancelled automatically
            results = await self._handle_timeout(results)

        return self._merge_results(results)

    async def _run_all_agents(
        self,
        semaphore: asyncio.Semaphore,
        context: AgentContext,
    ) -> list[AgentResult | None]:
        """Spawn all agents concurrently using TaskGroup."""
        results: list[AgentResult | None] = [None] * len(self._agents)

        async with asyncio.TaskGroup() as tg:
            for idx, agent in enumerate(self._agents):
                tg.create_task(
                    self._run_agent_indexed(agent, semaphore, context, results, idx)
                )

        return results

    async def _run_agent_indexed(
        self,
        agent: BaseAgent,
        semaphore: asyncio.Semaphore,
        context: AgentContext,
        results: list[AgentResult | None],
        idx: int,
    ) -> None:
        """Run a single agent and store its result at the given index."""
        result = await self._run_agent(agent, semaphore)
        results[idx] = result

    async def _run_agent(
        self,
        agent: BaseAgent,
        semaphore: asyncio.Semaphore,
    ) -> AgentResult | None:
        """Run a single agent with semaphore-bounded concurrency.

        Emits agent_start before execution, agent_complete on success,
        or agent_error on failure. The agent itself emits progress events
        via emit_progress().

        Returns:
            AgentResult on success/failure, or None if cancelled.
        """
        async with semaphore:
            # Emit agent_start event
            await self._emit_event(
                type="agent_start",
                agent=agent.name,
                message=agent.description,
            )

            start_time = time.perf_counter()

            try:
                context = AgentContext(
                    repo_path=self._repo_path,
                    llm_client=self._llm_client,
                    event_queue=self._event_queue,
                )
                result = await agent.execute(context)

                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                result.duration_ms = elapsed_ms

                # Emit agent_complete event
                await self._emit_event(
                    type="agent_complete",
                    agent=agent.name,
                    message=f"Completed {agent.name}",
                    duration_ms=elapsed_ms,
                )

                return result

            except asyncio.CancelledError:
                # Re-raise so TaskGroup can handle cancellation
                raise

            except Exception as exc:
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                error_msg = str(exc) if str(exc) else type(exc).__name__

                # Truncate error message to 1024 chars
                if len(error_msg) > 1024:
                    error_msg = error_msg[:1021] + "..."

                # Ensure error message is at least 1 char
                if not error_msg:
                    error_msg = "Unknown error"

                # Emit agent_error event
                await self._emit_event(
                    type="agent_error",
                    agent=agent.name,
                    message=f"Agent {agent.name} failed: {error_msg}",
                    error=error_msg,
                )

                return AgentResult(
                    agent_name=agent.name,
                    success=False,
                    error_message=error_msg,
                    duration_ms=elapsed_ms,
                )

    async def _handle_timeout(
        self,
        partial_results: list[AgentResult | None],
    ) -> list[AgentResult | None]:
        """Handle timeout by emitting error events for agents without results.

        Args:
            partial_results: Results collected before timeout (may be empty
                             if timeout occurred during TaskGroup setup).

        Returns:
            Updated results list with timeout errors for missing agents.
        """
        # If partial_results is empty (timeout before any results), initialize
        if not partial_results:
            partial_results = [None] * len(self._agents)

        for idx, agent in enumerate(self._agents):
            if idx < len(partial_results) and partial_results[idx] is None:
                error_msg = f"Agent {agent.name} cancelled due to timeout ({self._timeout_seconds}s)"

                # Truncate if needed
                if len(error_msg) > 1024:
                    error_msg = error_msg[:1021] + "..."

                await self._emit_event(
                    type="agent_error",
                    agent=agent.name,
                    message=error_msg,
                    error=error_msg,
                )

                partial_results[idx] = AgentResult(
                    agent_name=agent.name,
                    success=False,
                    error_message=error_msg,
                    duration_ms=0,
                )

        return partial_results

    def _merge_results(self, results: list[AgentResult | None]) -> AnalysisResult:
        """Merge individual agent results into a single AnalysisResult.

        Maps agent_name to AnalysisResult fields:
            ast_analyzer → code_flow
            er_extractor → er_model
            code_auditor → audit
            doc_generator → artifacts
            system_reporter → system_report

        Failed agents are added to the errors list.
        """
        merged = AnalysisResult()

        for result in results:
            if result is None:
                continue

            if result.success:
                field_name = _AGENT_RESULT_FIELD_MAP.get(result.agent_name)
                if field_name:
                    setattr(merged, field_name, result.data)
            else:
                merged.errors.append({
                    "agent": result.agent_name,
                    "error": result.error_message or "Unknown error",
                    "duration_ms": result.duration_ms,
                })

        return merged

    async def _emit_event(
        self,
        type: str,
        agent: str,
        message: str,
        duration_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        """Create and enqueue an AgentEvent."""
        event = AgentEvent(
            type=type,  # type: ignore[arg-type]
            agent=agent,  # type: ignore[arg-type]
            message=message,
            timestamp=_now_iso(),
            duration_ms=duration_ms,
            error=error,
        )
        await self._event_queue.put(event)
