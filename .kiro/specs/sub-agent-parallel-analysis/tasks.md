# Implementation Plan: Sub-Agent Parallel Analysis

## Overview

Replace the flat-parallel orchestration in DevGhost-Parser with a dependency-graph-aware execution engine. Implementation proceeds bottom-up: core data structures first (DAG, retry policy, models), then the orchestrator, work partitioner, SSE enhancements, and finally integration wiring with backward compatibility verification.

## Tasks

- [x] 1. Core data structures and interfaces
  - [x] 1.1 Implement DependencyGraph class
    - Create `backend/src/dev_ghost_parser/dependency_graph.py`
    - Implement `DependencyGraph` with `add_agent()`, `validate()`, `get_ready_agents()`, `mark_completed()`, `mark_failed()` methods
    - Implement cycle detection using DFS-based topological sort
    - Implement transitive failure propagation via BFS/DFS on dependents
    - Define `CyclicDependencyError` exception class
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.4_

  - [x] 1.2 Implement RetryPolicy dataclass
    - Create `backend/src/dev_ghost_parser/retry_policy.py`
    - Implement `RetryPolicy` dataclass with `max_retries`, `base_delay_seconds`, `multiplier` fields
    - Implement `get_delay(attempt)` method returning `base_delay_seconds * (multiplier ** attempt)`
    - _Requirements: 4.1, 4.2, 4.5_

  - [x] 1.3 Enhance BaseAgent interface
    - Modify existing `BaseAgent` abstract class to add `dependencies` property (default: `[]`)
    - Add `timeout_seconds` property (default: `60.0`)
    - Add `retry_policy` property (default: `RetryPolicy()`)
    - Ensure backward compatibility — existing agents that don't override these get defaults
    - _Requirements: 3.1, 3.5, 7.1, 4.5_

  - [x] 1.4 Enhance AgentContext and AgentResult models
    - Add `dependency_results: dict[str, AgentResult]` field to `AgentContext`
    - Create `ExecutionMetadata` dataclass with `total_duration_ms`, `agent_durations`, `retry_counts`, `failed_agents`, `partial_results`
    - Add `metadata: Optional[ExecutionMetadata]` to `AnalysisResult`
    - _Requirements: 3.3, 8.5, 7.4_

  - [x] 1.5 Enhance AgentEvent model with sequence and progress fields
    - Add `sequence: int` field (monotonically increasing)
    - Add `progress_pct: Optional[float]` field (0.0 - 100.0)
    - Add `retry_count: Optional[int]` field
    - Ensure existing fields remain unchanged for backward compatibility
    - _Requirements: 6.5, 6.2, 6.4, 9.2_

- [x] 2. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. DependencyGraphOrchestrator implementation
  - [x] 3.1 Implement orchestrator core with foundational phase
    - Create `backend/src/dev_ghost_parser/graph_orchestrator.py`
    - Implement `DependencyGraphOrchestrator.__init__()` with `repo_path`, `llm_client`, `event_queue`, `max_concurrency`, `global_timeout_seconds`
    - Implement `register_agent()` method
    - Implement `_execute_foundational_phase()` that runs AST analyzer with retry and aborts pipeline on failure
    - _Requirements: 1.1, 1.3, 1.5, 4.4_

  - [x] 3.2 Implement DAG-based parallel execution phase
    - Implement `_execute_parallel_phase()` that builds the DependencyGraph, validates it, and resolves ready agents iteratively
    - Use `asyncio.Semaphore` for concurrency limiting (default: 5)
    - On agent completion, unlock dependents and launch newly-ready agents
    - On agent failure, propagate failure to transitive dependents via `mark_failed()`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.2, 3.4_

  - [x] 3.3 Implement agent execution with retry and timeout
    - Implement `_run_agent_with_retry()` using `asyncio.wait_for()` for per-agent timeout
    - On timeout, cancel agent task and apply retry policy with exponential backoff delay
    - On exception, retry up to `max_retries` with appropriate delays
    - After all retries exhausted, mark agent as failed and emit `agent_error` event
    - _Requirements: 4.1, 4.2, 4.3, 7.2, 7.4_

  - [x] 3.4 Implement result aggregation and metadata
    - Implement `_aggregate_results()` merging all successful `AgentResult` objects into `AnalysisResult`
    - Apply priority-based conflict resolution (last-writer-wins by priority) with warning logs
    - Include partial results with error annotations
    - Populate `ExecutionMetadata` with durations, retry counts, failed agents list
    - Ensure aggregation completes within 50ms of last agent completing
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 2.6_

  - [x] 3.5 Implement SSE event emission with sequence numbers
    - Create a sequence counter (atomic increment) for event ordering
    - Emit `agent_start`, `agent_progress`, `agent_complete`, `agent_error` events at appropriate lifecycle points
    - Truncate error messages to 1024 characters in `agent_error` events
    - Include `retry_count` in error events
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 3.6 Write property tests for DependencyGraph (Properties 1, 2, 3)
    - **Property 1: DAG Cycle Detection** — Generate random directed graphs; verify `validate()` raises for cyclic, passes for acyclic
    - **Property 2: Ready-Set Computation** — Generate random DAGs + completed sets; verify `get_ready_agents()` returns exact correct set
    - **Property 3: Transitive Failure Propagation** — Generate random DAGs + failure point; verify all transitively-dependent agents returned, no independent agents affected
    - **Validates: Requirements 2.2, 2.3, 3.2, 3.4**

  - [x] 3.7 Write property tests for orchestrator context and failure (Properties 4, 5)
    - **Property 4: AST Context Propagation** — Generate random AgentResults; verify all downstream agents receive full AST result in context
    - **Property 5: AST Failure Aborts Pipeline** — Generate random retry policies; verify zero downstream agents execute when AST fails all attempts
    - **Validates: Requirements 1.2, 1.4, 3.3, 1.3, 4.4**

  - [x] 3.8 Write property tests for retry and timeout (Properties 6, 7, 15)
    - **Property 6: Retry Count Adherence** — Generate random max_retries (1-10); verify total attempts = N+1
    - **Property 7: Exponential Backoff Delay** — Generate random base/multiplier; verify delay = B * M^i
    - **Property 15: Timeout Triggers Cancellation and Retry** — Generate random timeout/delay configs; verify cancellation and retry application
    - **Validates: Requirements 4.1, 4.2, 4.3, 7.2**

  - [x] 3.9 Write property tests for result aggregation (Properties 12, 13)
    - **Property 12: Result Merge Preserves All Successful Agent Data** — Generate random successful AgentResults; verify no data lost
    - **Property 13: Priority-Based Conflict Resolution** — Generate overlapping results with different priorities; verify higher priority wins
    - **Validates: Requirements 8.1, 8.3, 8.4**

  - [x] 3.10 Write property test for concurrency limit (Property 14)
    - **Property 14: Concurrency Limit Enforcement** — Generate random agent counts and limits; verify max simultaneous executions never exceeds C
    - **Validates: Requirements 2.5**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. WorkPartitioner implementation
  - [x] 5.1 Implement WorkPartitioner class
    - Create `backend/src/dev_ghost_parser/work_partitioner.py`
    - Implement `should_partition(file_count)` with configurable threshold (default: 50)
    - Implement `create_batches(files)` splitting into batches of configurable size (default: 20)
    - Implement `process_batches()` with async concurrent execution bounded by semaphore
    - Implement batch result merging with error annotations for failed batches
    - Create `BatchResult` dataclass
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 5.2 Write property tests for WorkPartitioner (Properties 8, 9)
    - **Property 8: Work Partitioning Threshold** — Generate random file counts and thresholds; verify threshold logic and no file loss/duplication in batches
    - **Property 9: Batch Merge Preserves Data and Annotates Failures** — Generate random BatchResults; verify all successful data preserved and failures annotated
    - **Validates: Requirements 5.1, 5.3, 5.4**

- [x] 6. SSE event bus enhancement
  - [x] 6.1 Implement SSE sequence counter and event bus
    - Create or enhance event bus module with atomic sequence counter
    - Ensure all events emitted get strictly increasing sequence numbers
    - Add progress percentage forwarding for batch-level progress
    - Emit batch completion events: "Processing batch X/Y"
    - _Requirements: 6.5, 6.2, 5.5_

  - [x] 6.2 Write property tests for SSE events (Properties 10, 11)
    - **Property 10: SSE Sequence Monotonicity** — Generate random event sequences; verify strictly increasing sequence numbers
    - **Property 11: SSE Error Message Truncation** — Generate random strings (0-10000 chars); verify truncation to 1024 characters max
    - **Validates: Requirements 6.5, 1.5, 6.4**

- [x] 7. Integration and backward compatibility wiring
  - [x] 7.1 Wire DependencyGraphOrchestrator into existing endpoints
    - Replace the existing flat-parallel orchestration in `server.py` with `DependencyGraphOrchestrator`
    - Ensure `/analyze` endpoint returns same JSON schema (codeFlow, erModel, artifacts, nodeInspections, systemReport)
    - Ensure `/analyze-stream` endpoint emits same SSE event types
    - Preserve HTTP error codes (403, 404, 400, 500, 504)
    - Preserve `AnalyzeRequest` validation with `repo_url` field
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [x] 7.2 Update existing agents to use enhanced BaseAgent interface
    - Update `ast_analyzer` with `timeout_seconds=90`, `retry_policy=RetryPolicy(max_retries=2, base_delay_seconds=1.0)`
    - Update `er_extractor` with `timeout_seconds=60`
    - Update `code_auditor` with `timeout_seconds=120`, `retry_policy=RetryPolicy(base_delay_seconds=1.5)`, integrate `WorkPartitioner`
    - Update `doc_generator` with `timeout_seconds=90`, integrate `WorkPartitioner`
    - Update `system_reporter` with `timeout_seconds=30`, `retry_policy=RetryPolicy(max_retries=1, base_delay_seconds=0.5)`
    - _Requirements: 1.1, 4.5, 7.1, 5.1_

  - [x] 7.3 Implement global timeout handling
    - Add global pipeline timeout (default: 300s) that cancels all running agents
    - Return partial results for completed agents on global timeout
    - Return HTTP 504 for timeout on `/analyze` endpoint
    - _Requirements: 7.3, 9.3_

  - [x] 7.4 Write backward compatibility unit tests
    - Verify `/analyze` response JSON schema matches existing format
    - Verify `/analyze-stream` SSE event types are unchanged
    - Verify HTTP error codes (403, 404, 400, 500, 504) are correct
    - Verify `AnalyzeRequest` validation accepts existing format
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis with `@settings(max_examples=100)`
- Unit tests validate specific examples and edge cases
- The implementation uses Python with asyncio for all async operations
- All existing agent implementations must retain backward compatibility via default property values

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.5"] },
    { "id": 1, "tasks": ["1.3", "1.4"] },
    { "id": 2, "tasks": ["3.1", "5.1", "6.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.6", "5.2", "6.2"] },
    { "id": 4, "tasks": ["3.4", "3.5", "3.7", "3.8"] },
    { "id": 5, "tasks": ["3.9", "3.10", "7.1", "7.2"] },
    { "id": 6, "tasks": ["7.3", "7.4"] }
  ]
}
```
