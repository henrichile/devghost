"""
DAG-aware orchestrator with retry, timeout, and dependency resolution.

Replaces the flat-parallel AgentOrchestrator with a two-phase pipeline:
1. Foundational phase: AST analyzer runs first with retry/backoff.
2. Parallel phase: Remaining agents execute respecting the dependency graph.

Uses EventBus for all SSE event emission, ensuring atomic sequence numbering
and consistent event formatting across the entire pipeline.

Satisfies Requirements: 1.1, 1.3, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 3.2, 3.4, 4.4, 6.1, 6.2, 6.3, 6.4, 6.5, 7.3, 9.3
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from dev_ghost_parser.agent_models import (
    AgentEvent,
    AgentResult,
    AnalysisResult,
    ExecutionMetadata,
)
from dev_ghost_parser.base_agent import AgentContext, BaseAgent
from dev_ghost_parser.dependency_graph import CyclicDependencyError, DependencyGraph
from dev_ghost_parser.event_bus import EventBus

if TYPE_CHECKING:
    from dev_ghost_parser.llm_client import LLM_Client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agent priority for conflict resolution (higher = wins)
# ---------------------------------------------------------------------------

AGENT_PRIORITY: dict[str, int] = {
    "ast_analyzer": 100,
    "er_extractor": 80,
    "code_auditor": 60,
    "doc_generator": 40,
    "system_reporter": 20,
}

# Mapping from agent name to the corresponding AnalysisResult field name
AGENT_FIELD_MAP: dict[str, str] = {
    "ast_analyzer": "code_flow",
    "er_extractor": "er_model",
    "code_auditor": "audit",
    "doc_generator": "artifacts",
    "system_reporter": "system_report",
}


class FoundationalPhaseError(Exception):
    """Raised when the AST foundational phase fails after all retries.

    This error aborts the entire pipeline since downstream agents
    depend on AST results.
    """

    def __init__(self, message: str = "AST foundational phase failed after all retries") -> None:
        super().__init__(message)


class DependencyGraphOrchestrator:
    """DAG-aware orchestrator with retry, timeout, and partitioning support.

    Executes analysis in two phases:
    1. Foundational phase: The ast_analyzer runs first with retry policy.
       If it fails after all retries, the pipeline aborts.
    2. Parallel phase: Remaining agents execute respecting their declared
       dependencies, bounded by a concurrency semaphore.

    All SSE events are emitted through an EventBus instance which provides
    atomic, strictly monotonically increasing sequence numbers and consistent
    error truncation (1024 chars) and retry_count handling.

    Satisfies Requirements: 1.1, 1.3, 1.5, 4.4, 6.1, 6.2, 6.3, 6.4, 6.5
    """

    def __init__(
        self,
        repo_path: str,
        llm_client: "LLM_Client",
        event_queue: asyncio.Queue[AgentEvent],
        max_concurrency: int = 5,
        global_timeout_seconds: float = 300.0,
    ) -> None:
        self._repo_path = repo_path
        self._llm_client = llm_client
        self._event_queue = event_queue
        self._max_concurrency = max_concurrency
        self._global_timeout_seconds = global_timeout_seconds
        self._agents: dict[str, BaseAgent] = {}
        self._sequence_counter = 0
        # Use EventBus for all event emission — provides atomic sequence
        # numbering and consistent error/message handling.
        self._event_bus = EventBus(event_queue)

    @property
    def event_bus(self) -> EventBus:
        """Access the EventBus used for SSE event emission."""
        return self._event_bus

    def register_agent(self, agent: BaseAgent) -> None:
        """Register an agent to be executed during the pipeline.

        Args:
            agent: A BaseAgent instance. Must have a unique `name` attribute.
        """
        self._agents[agent.name] = agent

    @property
    def agents(self) -> dict[str, BaseAgent]:
        """Return the dictionary of registered agents."""
        return dict(self._agents)

    async def run_pipeline(self) -> AnalysisResult:
        """Execute full pipeline: AST phase → DAG-resolved parallel phase.

        1. Runs the foundational AST phase (with retry), bounded by global timeout.
        2. On success, proceeds to the DAG-based parallel phase with remaining timeout.
        3. On global timeout during the parallel phase, cancels all running agents
           and returns partial results for agents that completed before the timeout.
        4. Aggregates and returns results from all phases via _aggregate_results().

        Returns:
            AnalysisResult with merged data from all successful agents.
            On global timeout, returns partial results with a timeout error entry.

        Raises:
            FoundationalPhaseError: If the AST analyzer fails after all retries.
            CyclicDependencyError: If the dependency graph contains a cycle.

        Satisfies Requirements: 7.3, 9.3
        """
        pipeline_start = time.perf_counter()

        # Phase 1: Foundational AST analysis (bounded by global timeout)
        try:
            ast_result = await asyncio.wait_for(
                self._execute_foundational_phase(),
                timeout=self._global_timeout_seconds,
            )
        except asyncio.TimeoutError:
            # Global timeout during foundational phase — no partial results possible
            total_duration_ms = int((time.perf_counter() - pipeline_start) * 1000)
            logger.error(
                "Global pipeline timeout (%.1fs) reached during foundational phase",
                self._global_timeout_seconds,
            )
            return self._aggregate_results(
                results=[],
                total_duration_ms=total_duration_ms,
                global_timeout_error=(
                    f"Global pipeline timeout ({self._global_timeout_seconds}s) "
                    "reached during foundational AST phase"
                ),
            )

        # Calculate remaining timeout for the parallel phase
        foundational_duration = time.perf_counter() - pipeline_start
        remaining_timeout = self._global_timeout_seconds - foundational_duration

        if remaining_timeout <= 0:
            # No time left for the parallel phase — return AST result only
            total_duration_ms = int((time.perf_counter() - pipeline_start) * 1000)
            logger.warning(
                "No remaining time for parallel phase after foundational phase "
                "(%.2fs of %.1fs used)",
                foundational_duration,
                self._global_timeout_seconds,
            )
            return self._aggregate_results(
                results=[ast_result],
                total_duration_ms=total_duration_ms,
                global_timeout_error=(
                    f"Global pipeline timeout ({self._global_timeout_seconds}s) "
                    "exhausted after foundational phase"
                ),
            )

        # Phase 2: DAG-based parallel execution (bounded by remaining timeout)
        try:
            parallel_results = await asyncio.wait_for(
                self._execute_parallel_phase(ast_result),
                timeout=remaining_timeout,
            )
        except asyncio.TimeoutError:
            # Global timeout during parallel phase — gather partial results
            total_duration_ms = int((time.perf_counter() - pipeline_start) * 1000)
            logger.error(
                "Global pipeline timeout (%.1fs) reached during parallel phase "
                "(%.2fs remaining after foundational phase)",
                self._global_timeout_seconds,
                remaining_timeout,
            )
            # Collect whatever partial results were stored before the timeout
            partial_results = self._collect_partial_results_on_timeout(ast_result)
            return self._aggregate_results(
                results=partial_results,
                total_duration_ms=total_duration_ms,
                global_timeout_error=(
                    f"Global pipeline timeout ({self._global_timeout_seconds}s) "
                    "reached during parallel phase — partial results returned"
                ),
            )

        # Aggregate all results (AST + parallel phase)
        all_results = [ast_result] + parallel_results
        total_duration_ms = int((time.perf_counter() - pipeline_start) * 1000)

        return self._aggregate_results(all_results, total_duration_ms)

    async def run_all(self) -> AnalysisResult:
        """Backward-compatible alias for run_pipeline().

        Existing tests and code may reference this method name from the
        original AgentOrchestrator. Delegates to run_pipeline().
        """
        return await self.run_pipeline()

    async def _execute_foundational_phase(self) -> AgentResult:
        """Run AST analyzer with retry. Abort pipeline on failure.

        Finds the registered agent with name "ast_analyzer", then executes it
        with its configured retry policy and timeout:
        1. On timeout, cancels and retries with exponential backoff.
        2. On exception, retries with exponential backoff.
        3. After all retries exhausted, raises FoundationalPhaseError.
        4. On success, emits agent_complete event and returns the AgentResult.

        Returns:
            AgentResult from the successful AST analysis.

        Raises:
            FoundationalPhaseError: If all retry attempts are exhausted.
            ValueError: If no agent named "ast_analyzer" is registered.

        Satisfies Requirements: 1.1, 1.3, 1.5, 6.1, 6.3, 6.4
        """
        ast_agent = self._agents.get("ast_analyzer")
        if ast_agent is None:
            raise ValueError(
                "No agent named 'ast_analyzer' is registered. "
                "The foundational phase requires an AST analyzer agent."
            )

        retry_policy = ast_agent.retry_policy
        max_attempts = retry_policy.max_retries + 1  # initial + retries
        timeout = ast_agent.timeout_seconds

        context = AgentContext(
            repo_path=self._repo_path,
            llm_client=self._llm_client,
            event_queue=self._event_queue,
            event_bus=self._event_bus,
        )
        ast_agent.bind_context(context)

        # Emit agent_start event (Req 6.1)
        await self._event_bus.emit_agent_start(
            ast_agent.name,
            ast_agent.description,
        )

        last_error: str = "Unknown error"
        start_time = time.perf_counter()

        for attempt in range(max_attempts):
            try:
                result = await asyncio.wait_for(
                    ast_agent.execute(context),
                    timeout=timeout,
                )

                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                result.duration_ms = elapsed_ms

                # Success — emit agent_complete event (Req 6.3)
                await self._event_bus.emit_agent_complete(
                    ast_agent.name,
                    duration_ms=elapsed_ms,
                )

                return result

            except asyncio.TimeoutError:
                last_error = (
                    f"Agent {ast_agent.name} timed out after {timeout}s "
                    f"(attempt {attempt + 1}/{max_attempts})"
                )
                logger.warning(last_error)

            except asyncio.CancelledError:
                # Propagate cancellation — don't retry on external cancellation
                raise

            except Exception as exc:
                last_error = str(exc) if str(exc) else type(exc).__name__
                logger.warning(
                    "Agent %s failed (attempt %d/%d): %s",
                    ast_agent.name,
                    attempt + 1,
                    max_attempts,
                    last_error,
                )

            # If we have more attempts remaining, wait with exponential backoff
            if attempt < max_attempts - 1:
                delay = retry_policy.get_delay(attempt)
                logger.info(
                    "Retrying %s in %.2fs (attempt %d/%d)",
                    ast_agent.name,
                    delay,
                    attempt + 2,
                    max_attempts,
                )
                await asyncio.sleep(delay)

        # All retries exhausted — emit agent_error (Req 6.4) and abort pipeline
        # EventBus handles error truncation to 1024 chars automatically
        await self._event_bus.emit_agent_error(
            ast_agent.name,
            error=last_error,
            retry_count=retry_policy.max_retries,
        )

        raise FoundationalPhaseError(
            f"AST foundational phase failed after {max_attempts} attempts. "
            f"Last error: {last_error}"
        )

    async def _execute_parallel_phase(
        self, ast_result: AgentResult
    ) -> list[AgentResult]:
        """Execute remaining agents respecting the dependency graph.

        Builds a DAG from all registered agents except "ast_analyzer", validates
        it for cycles, then iteratively launches ready agents bounded by a
        concurrency semaphore. On completion of an agent, newly-ready dependents
        are launched. On failure, transitive dependents are marked as skipped.

        On external cancellation (e.g., from global timeout), handles
        CancelledError gracefully and stores completed results for partial
        retrieval.

        Satisfies Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.2, 3.4, 7.3

        Args:
            ast_result: The successful result from the foundational AST phase.

        Returns:
            List of AgentResults from all parallel-phase agents (successful and failed).

        Raises:
            CyclicDependencyError: If the dependency graph contains a cycle.
        """
        # 1. Build the DependencyGraph from all registered agents EXCEPT "ast_analyzer"
        graph = DependencyGraph()
        parallel_agents: dict[str, BaseAgent] = {}

        for name, agent in self._agents.items():
            if name == "ast_analyzer":
                continue
            parallel_agents[name] = agent
            # Each agent declares its dependencies; add "ast_analyzer" implicitly
            # if it's not already in the declared list (all post-AST agents depend on AST)
            deps = list(agent.dependencies)
            if "ast_analyzer" not in deps:
                deps.append("ast_analyzer")
            graph.add_agent(name, deps)

        # Also register "ast_analyzer" in the graph so dependency edges resolve
        graph.add_agent("ast_analyzer", [])

        # 2. Validate the graph — raise CyclicDependencyError if cycle detected
        graph.validate()

        # 3. Create a concurrency semaphore
        semaphore = asyncio.Semaphore(self._max_concurrency)

        # 4. Mark "ast_analyzer" as completed (it already ran in foundational phase)
        graph.mark_completed("ast_analyzer")
        completed: set[str] = {"ast_analyzer"}

        # Storage for results — also stored on self for partial retrieval on timeout
        results: list[AgentResult] = []
        self._parallel_phase_results = results
        self._parallel_phase_ast_result = ast_result

        # If no parallel agents to run, return immediately
        if not parallel_agents:
            return results

        # Track in-flight tasks: asyncio.Task -> agent_name
        pending_tasks: dict[asyncio.Task, str] = {}  # type: ignore[type-arg]

        async def _run_bounded(agent: BaseAgent, ctx: AgentContext) -> AgentResult:
            """Run an agent bounded by the concurrency semaphore."""
            async with semaphore:
                return await self._run_agent_with_retry(agent, ctx)

        def _build_context_for(agent_name: str) -> AgentContext:
            """Build execution context for an agent including dependency results."""
            dep_results: dict[str, AgentResult] = {}
            # Always include ast_result
            dep_results["ast_analyzer"] = ast_result
            # Include results from other declared dependencies
            agent = parallel_agents[agent_name]
            for dep_name in agent.dependencies:
                # Find the result in our completed results list
                for r in results:
                    if r.agent_name == dep_name and r.success:
                        dep_results[dep_name] = r
                        break
            return AgentContext(
                repo_path=self._repo_path,
                llm_client=self._llm_client,
                event_queue=self._event_queue,
                dependency_results=dep_results,
                event_bus=self._event_bus,
            )

        def _launch_ready_agents() -> None:
            """Find ready agents and launch them as tasks."""
            ready = graph.get_ready_agents(completed)
            for agent_name in ready:
                if agent_name == "ast_analyzer":
                    continue
                if agent_name not in parallel_agents:
                    continue
                # Only launch if not already in-flight
                if any(n == agent_name for n in pending_tasks.values()):
                    continue
                agent = parallel_agents[agent_name]
                ctx = _build_context_for(agent_name)
                task = asyncio.create_task(_run_bounded(agent, ctx))
                pending_tasks[task] = agent_name

        # 5. Get initial ready agents and launch them
        _launch_ready_agents()

        # 6. Process completions iteratively until all agents are done or skipped
        try:
            while pending_tasks:
                # Wait for the first task to complete
                done, _ = await asyncio.wait(
                    pending_tasks.keys(),
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for task in done:
                    agent_name = pending_tasks.pop(task)

                    try:
                        result = task.result()
                    except asyncio.CancelledError:
                        # Agent was cancelled (e.g., by global timeout propagation)
                        result = AgentResult(
                            agent_name=agent_name,  # type: ignore[arg-type]
                            success=False,
                            error_message="Cancelled by global pipeline timeout",
                            duration_ms=0,
                        )

                    if result.success:
                        # 7. Agent completed successfully
                        graph.mark_completed(agent_name)
                        completed.add(agent_name)
                        results.append(result)
                        # Launch newly ready dependents
                        _launch_ready_agents()
                    else:
                        # 8. Agent failed — propagate failure to transitive dependents
                        skipped_agents = graph.mark_failed(agent_name)
                        results.append(result)

                        # Emit error events for skipped agents
                        for skipped_name in skipped_agents:
                            await self._event_bus.emit_agent_error(
                                skipped_name,
                                error=f"Upstream dependency '{agent_name}' failed",
                                retry_count=0,
                                message=(
                                    f"Agent {skipped_name} skipped: upstream "
                                    f"dependency '{agent_name}' failed"
                                ),
                            )
                            # Create a failed result for the skipped agent
                            results.append(AgentResult(
                                agent_name=skipped_name,  # type: ignore[arg-type]
                                success=False,
                                error_message=(
                                    f"Skipped: upstream dependency '{agent_name}' failed"
                                ),
                                duration_ms=0,
                            ))

        except asyncio.CancelledError:
            # Global timeout fired — cancel all pending tasks gracefully
            for task in pending_tasks:
                task.cancel()
            # Wait briefly for tasks to acknowledge cancellation
            if pending_tasks:
                await asyncio.gather(*pending_tasks.keys(), return_exceptions=True)
            # Re-raise so the caller (wait_for) can handle it
            raise

        return results

    async def _run_agent_with_retry(
        self, agent: BaseAgent, context: AgentContext
    ) -> AgentResult:
        """Execute agent with timeout and retry policy.

        Unlike `_execute_foundational_phase()`, this method does NOT raise on
        failure — it returns a failed AgentResult instead. Designed for
        non-AST agents in the parallel execution phase.

        Steps:
        1. Get agent's timeout_seconds and retry_policy.
        2. Calculate max_attempts = retry_policy.max_retries + 1.
        3. Emit agent_start event.
        4. For each attempt:
           a. Try asyncio.wait_for(agent.execute(context), timeout).
           b. On success: record duration, emit agent_complete, return result.
           c. On TimeoutError: log warning, prepare to retry.
           d. On Exception: log warning, prepare to retry.
           e. If more attempts remain: wait with retry_policy.get_delay(attempt).
        5. After all retries exhausted: emit agent_error, return failed AgentResult.

        Satisfies Requirements: 4.1, 4.2, 4.3, 6.1, 6.3, 6.4, 7.2, 7.4

        Args:
            agent: The agent to execute.
            context: The execution context (with dependency_results populated).

        Returns:
            AgentResult — success or failure (never raises).
        """
        retry_policy = agent.retry_policy
        max_attempts = retry_policy.max_retries + 1  # initial + retries
        timeout = agent.timeout_seconds

        # Bind context so the agent can emit progress events
        agent.bind_context(context)

        # Emit agent_start event (Req 6.1)
        await self._event_bus.emit_agent_start(
            agent.name,
            agent.description,
        )

        last_error: str = "Unknown error"
        start_time = time.perf_counter()

        for attempt in range(max_attempts):
            try:
                result = await asyncio.wait_for(
                    agent.execute(context),
                    timeout=timeout,
                )

                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                result.duration_ms = elapsed_ms

                # Success — emit agent_complete event (Req 6.3)
                await self._event_bus.emit_agent_complete(
                    agent.name,
                    duration_ms=elapsed_ms,
                )

                return result

            except asyncio.TimeoutError:
                last_error = (
                    f"Agent {agent.name} timed out after {timeout}s "
                    f"(attempt {attempt + 1}/{max_attempts})"
                )
                logger.warning(last_error)

            except asyncio.CancelledError:
                # Propagate cancellation — don't retry on external cancellation
                raise

            except Exception as exc:
                last_error = str(exc) if str(exc) else type(exc).__name__
                logger.warning(
                    "Agent %s failed (attempt %d/%d): %s",
                    agent.name,
                    attempt + 1,
                    max_attempts,
                    last_error,
                )

            # If we have more attempts remaining, wait with exponential backoff
            if attempt < max_attempts - 1:
                delay = retry_policy.get_delay(attempt)
                logger.info(
                    "Retrying %s in %.2fs (attempt %d/%d)",
                    agent.name,
                    delay,
                    attempt + 2,
                    max_attempts,
                )
                await asyncio.sleep(delay)

        # All retries exhausted — emit agent_error (Req 6.4) and return failed result
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        # EventBus handles error truncation to 1024 chars automatically
        await self._event_bus.emit_agent_error(
            agent.name,
            error=last_error,
            retry_count=retry_policy.max_retries,
        )

        return AgentResult(
            agent_name=agent.name,
            success=False,
            error_message=last_error,
            duration_ms=elapsed_ms,
        )

    def _collect_partial_results_on_timeout(
        self, ast_result: AgentResult
    ) -> list[AgentResult]:
        """Collect partial results after a global timeout during parallel phase.

        Returns the AST result plus any results from agents that completed
        before the timeout fired. This relies on the results list stored in
        self._parallel_phase_results during _execute_parallel_phase().

        Satisfies Requirements: 7.3

        Args:
            ast_result: The successful AST result from the foundational phase.

        Returns:
            List of AgentResults including AST and any completed parallel agents.
        """
        partial = [ast_result]
        # Retrieve results that were stored by _execute_parallel_phase before timeout
        stored_results = getattr(self, "_parallel_phase_results", None)
        if stored_results:
            partial.extend(stored_results)
        return partial

    def _aggregate_results(
        self,
        results: list[AgentResult],
        total_duration_ms: int,
        global_timeout_error: str | None = None,
    ) -> AnalysisResult:
        """Merge all AgentResult objects into a single AnalysisResult.

        Implements priority-based conflict resolution: when multiple agents
        produce data for the same AnalysisResult field, the agent with higher
        priority (per AGENT_PRIORITY) wins and a warning is logged.

        Includes partial results with error annotations and populates
        ExecutionMetadata with durations, retry counts, and failed agents.

        When global_timeout_error is provided, adds it to the errors list
        to indicate the pipeline was cut short by the global timeout.

        Satisfies Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 2.6, 7.3

        Args:
            results: List of AgentResult objects from all pipeline phases.
            total_duration_ms: Total pipeline execution time in milliseconds.
            global_timeout_error: Optional error message when global timeout fired.

        Returns:
            AnalysisResult with all successful data merged and metadata populated.
        """
        # Track which agent wrote each field (for conflict resolution)
        field_owners: dict[str, str] = {}  # field_name -> agent_name that wrote it

        # Build AnalysisResult fields
        analysis_fields: dict[str, Any] = {
            "code_flow": None,
            "er_model": None,
            "audit": None,
            "artifacts": None,
            "system_report": None,
        }

        # Metadata accumulators
        errors: list[dict] = []
        agent_durations: dict[str, int] = {}
        retry_counts: dict[str, int] = {}
        failed_agents: list[str] = []
        partial_results: list[str] = []

        for result in results:
            agent_name = result.agent_name
            agent_durations[agent_name] = result.duration_ms

            # Track retry counts from retry policy (retries = max_retries used)
            agent = self._agents.get(agent_name)
            if agent is not None:
                retries_used = agent.retry_policy.max_retries if not result.success else 0
                # For successful results that required retries, we can't easily
                # know the exact count here — record 0 for success.
                # For failed results, record the max_retries (all were exhausted).
                retry_counts[agent_name] = retries_used

            if not result.success:
                # Record failure
                failed_agents.append(agent_name)
                errors.append({
                    "agent": agent_name,
                    "error": result.error_message or "Unknown error",
                    "duration_ms": result.duration_ms,
                })

                # Check if this agent has partial data (e.g., from batch failures)
                if result.data is not None:
                    partial_results.append(agent_name)
                    # Include partial data with the field mapping
                    target_field = AGENT_FIELD_MAP.get(agent_name)
                    if target_field and target_field in analysis_fields:
                        # Wrap partial data with error annotation
                        annotated_data = result.data
                        if isinstance(annotated_data, dict):
                            annotated_data = {
                                **annotated_data,
                                "_partial": True,
                                "_error": result.error_message or "Unknown error",
                            }
                        self._resolve_field_conflict(
                            analysis_fields,
                            field_owners,
                            target_field,
                            agent_name,
                            annotated_data,
                        )
                continue

            # Successful result — map to the appropriate AnalysisResult field
            target_field = AGENT_FIELD_MAP.get(agent_name)
            if target_field and target_field in analysis_fields and result.data is not None:
                self._resolve_field_conflict(
                    analysis_fields,
                    field_owners,
                    target_field,
                    agent_name,
                    result.data,
                )

        # Add global timeout error if the pipeline was cut short
        if global_timeout_error:
            errors.append({
                "agent": "pipeline",
                "error": global_timeout_error,
                "duration_ms": total_duration_ms,
            })

        # Build ExecutionMetadata
        metadata = ExecutionMetadata(
            total_duration_ms=total_duration_ms,
            agent_durations=agent_durations,
            retry_counts=retry_counts,
            failed_agents=failed_agents,
            partial_results=partial_results,
        )

        return AnalysisResult(
            code_flow=analysis_fields["code_flow"],
            er_model=analysis_fields["er_model"],
            audit=analysis_fields["audit"],
            artifacts=analysis_fields["artifacts"],
            system_report=analysis_fields["system_report"],
            errors=errors,
            metadata=metadata,
        )

    def _resolve_field_conflict(
        self,
        analysis_fields: dict[str, Any],
        field_owners: dict[str, str],
        target_field: str,
        agent_name: str,
        data: Any,
    ) -> None:
        """Apply priority-based conflict resolution for a field assignment.

        If the field is already populated by another agent, compare priorities.
        The higher-priority agent's data wins. A warning is logged on conflict.

        Args:
            analysis_fields: Mutable dict of field_name -> current data.
            field_owners: Mutable dict tracking which agent owns each field.
            target_field: The AnalysisResult field to write to.
            agent_name: The agent attempting to write.
            data: The data the agent wants to write.
        """
        current_owner = field_owners.get(target_field)

        if current_owner is None:
            # No conflict — first writer
            analysis_fields[target_field] = data
            field_owners[target_field] = agent_name
            return

        # Conflict detected — resolve by priority
        current_priority = AGENT_PRIORITY.get(current_owner, 0)
        new_priority = AGENT_PRIORITY.get(agent_name, 0)

        logger.warning(
            "Conflict on field '%s': agent '%s' (priority %d) vs '%s' (priority %d). "
            "Higher priority wins.",
            target_field,
            agent_name,
            new_priority,
            current_owner,
            current_priority,
        )

        if new_priority > current_priority:
            # New agent has higher priority — overwrite
            analysis_fields[target_field] = data
            field_owners[target_field] = agent_name
        # Otherwise, keep existing (current owner has higher or equal priority)
