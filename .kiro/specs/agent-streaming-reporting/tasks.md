# Implementation Plan: Agent Streaming & Reporting

## Overview

This plan transforms the DevGhost Parser backend from a monolithic synchronous `/analyze` endpoint into a multi-agent architecture with real-time SSE streaming. The backend uses Python/FastAPI with asyncio for parallel agent execution, and the frontend uses TypeScript/React with Fetch ReadableStream for consuming SSE events. A new System Reporter agent detects technology stacks and generates setup instructions, surfaced through a dedicated dashboard tab.

## Tasks

- [x] 1. Define data models and base agent infrastructure
  - [x] 1.1 Create Pydantic/dataclass models for Agent Events, TechStack, SystemReportResult, AgentResult, and AnalysisResult
    - Create `backend/src/dev_ghost_parser/agent_models.py`
    - Define `AgentEvent`, `AgentEventType`, `AgentIdentifier`, `TechStackEntry`, `TechStack`, `SystemReportResult`, `AgentResult`, `AnalysisResult` dataclasses/models
    - Include validation constraints (message 1-2048 chars, error 1-1024 chars, duration_ms >= 0)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 1.2 Create BaseAgent abstract class and AgentContext
    - Create `backend/src/dev_ghost_parser/base_agent.py`
    - Define `BaseAgent` ABC with `name`, `description`, abstract `execute()`, and `emit_progress()` method
    - Define `AgentContext` dataclass holding repo_path, llm_client, and event_queue reference
    - _Requirements: 1.1, 1.2_

  - [x] 1.3 Write property tests for AgentEvent schema validation (Property 6)
    - **Property 6: Event schema validity**
    - Use Hypothesis to generate random AgentEvent instances and verify all field constraints
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.5, 3.6**

  - [x] 1.4 Write property test for SSE serialization format (Property 5)
    - **Property 5: SSE format serialization**
    - Use Hypothesis to generate valid AgentEvent objects and verify serialization starts with `data: `, contains parseable JSON, and ends with `\n\n`
    - **Validates: Requirements 2.8**

- [x] 2. Implement Agent Orchestrator
  - [x] 2.1 Create AgentOrchestrator class with parallel execution
    - Create `backend/src/dev_ghost_parser/orchestrator.py`
    - Implement `run_all()` using `asyncio.TaskGroup` for structured concurrency
    - Implement semaphore-bounded `_run_agent()` for max concurrency control (default 5)
    - Implement 120-second timeout with cancellation of remaining agents
    - Emit agent_start, agent_progress, agent_complete/agent_error events to the shared asyncio.Queue
    - Merge individual agent results into a single AnalysisResult
    - _Requirements: 1.1, 1.2, 1.4, 1.5, 1.6, 1.7_

  - [x] 2.2 Write property test for fault isolation (Property 2)
    - **Property 2: Fault isolation preserves successful results**
    - Use Hypothesis to randomly select subsets of agents to fail, verify remaining agents' results are preserved
    - **Validates: Requirements 1.3**

  - [x] 2.3 Write property test for result merging completeness (Property 3)
    - **Property 3: Result merging completeness**
    - Use Hypothesis to generate random agent result dictionaries, verify merged output contains all fields
    - **Validates: Requirements 1.4**

  - [x] 2.4 Write property test for event lifecycle ordering (Property 4)
    - **Property 4: Agent event lifecycle ordering**
    - Use Hypothesis to generate randomized agent execution scenarios, verify event sequence per agent is start → progress+ → complete|error
    - **Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.10**

- [x] 3. Implement Specialized Agents (Backend)
  - [x] 3.1 Implement ASTAnalyzerAgent wrapping existing Code_Flow_Analyzer
    - Create `backend/src/dev_ghost_parser/agents/ast_analyzer_agent.py`
    - Wrap existing `Code_Flow_Analyzer` logic as an async agent
    - Emit progress events during analysis phases
    - _Requirements: 1.2, 2.2, 2.3, 2.4_

  - [x] 3.2 Implement ERExtractorAgent wrapping existing ER_Extractor
    - Create `backend/src/dev_ghost_parser/agents/er_extractor_agent.py`
    - Wrap existing `ER_Extractor` logic as an async agent
    - Emit progress events during extraction phases
    - _Requirements: 1.2, 2.2, 2.3, 2.4_

  - [x] 3.3 Implement CodeAuditorAgent wrapping node inspection logic
    - Create `backend/src/dev_ghost_parser/agents/code_auditor_agent.py`
    - Extract node inspection logic from `server.py` into an async agent
    - Emit progress events per node inspected
    - _Requirements: 1.2, 2.2, 2.3, 2.4_

  - [x] 3.4 Implement DocGeneratorAgent wrapping Artifacts_Generator
    - Create `backend/src/dev_ghost_parser/agents/doc_generator_agent.py`
    - Wrap existing `Artifacts_Generator` logic as an async agent
    - Emit progress events per artifact generated
    - _Requirements: 1.2, 2.2, 2.3, 2.4_

  - [x] 3.5 Implement SystemReporterAgent (new agent)
    - Create `backend/src/dev_ghost_parser/agents/system_reporter_agent.py`
    - Implement `_scan_config_files()` to detect config files (package.json, pyproject.toml, Dockerfile, etc.) in root and first-level subdirectories
    - Implement `_extract_tech_stack()` to parse config files and produce TechStack entries (language, framework, database, infrastructure categories)
    - Implement `_generate_instructions()` using LLM with heuristic fallback
    - Implement `_generate_description()` using LLM with heuristic fallback (max 500 chars)
    - Handle case where no config files found (return `could_not_determine=True`)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 3.6 Write property test for config file detection (Property 11)
    - **Property 11: Configuration file detection**
    - Use Hypothesis to generate directory structures with various config files and verify all are detected
    - **Validates: Requirements 6.1, 6.2**

  - [x] 3.7 Write property test for project description length constraint (Property 13)
    - **Property 13: Project description length constraint**
    - Use Hypothesis to verify generated descriptions never exceed 500 characters
    - **Validates: Requirements 6.4**

- [x] 4. Checkpoint - Backend agents and orchestrator
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement SSE Streaming Endpoint
  - [x] 5.1 Create POST /analyze-stream endpoint with StreamingResponse
    - Add endpoint to `backend/src/dev_ghost_parser/server.py`
    - Accept same AnalyzeRequest body as `/analyze`
    - Validate request before starting stream (return HTTP error on invalid input)
    - Clone repository, create orchestrator with asyncio.Queue
    - Return `StreamingResponse` with `media_type="text/event-stream"` and CORS headers
    - Read from queue and yield SSE-formatted events (`data: {json}\n\n`)
    - Emit `analysis_complete` with full merged result when all agents finish
    - Implement 300-second overall timeout with `analysis_error` emission
    - Close connection after final event
    - _Requirements: 2.1, 2.6, 2.7, 2.8, 2.9, 2.11_

  - [x] 5.2 Refactor existing /analyze endpoint to use AgentOrchestrator
    - Modify `/analyze` endpoint to use the same AgentOrchestrator internally
    - Collect results synchronously (no SSE) and return combined response
    - Add optional `systemReport` field to response when System Reporter succeeds
    - Omit `systemReport` field gracefully when System Reporter fails
    - Maintain backward compatibility with existing response schema
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 5.3 Write unit tests for SSE endpoint response headers and format
    - Verify content-type is `text/event-stream`
    - Verify CORS headers are present
    - Verify backward compatibility of `/analyze` response schema
    - _Requirements: 2.7, 8.1_

- [x] 6. Implement Frontend SSE Client
  - [x] 6.1 Create `useAnalysisStream` React hook
    - Create `frontend/src/hooks/useAnalysisStream.ts`
    - Implement Fetch API with ReadableStream to POST to `/analyze-stream`
    - Parse SSE events (split on `\n\n`, extract `data:` prefix, parse JSON)
    - Manage state: `idle`, `connecting`, `streaming`, `complete`, `error`
    - Handle HTTP errors before stream begins (4xx/5xx)
    - Handle connection loss mid-stream with retry capability
    - Implement 120-second inactivity timeout
    - Skip malformed JSON events silently and continue processing
    - On `analysis_complete`, store result and transition to `complete` state
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x] 6.2 Create TypeScript interfaces for frontend event models
    - Create `frontend/src/types/streaming.ts`
    - Define `AgentEvent`, `AgentEventType`, `AgentIdentifier`, `TechStackEntry`, `SystemReport`, `AgentPanelEntry` interfaces
    - _Requirements: 3.1, 3.7_

  - [x] 6.3 Write property test for malformed JSON resilience (Property 7)
    - **Property 7: Malformed JSON resilience**
    - Use fast-check to generate sequences of valid and invalid JSON, verify all valid events are parsed
    - **Validates: Requirements 4.6**

- [x] 7. Implement Process Panel Component
  - [x] 7.1 Create ProcessPanel component with real-time agent activity log
    - Create `frontend/src/components/ProcessPanel.tsx`
    - Display panel on right side (~40% viewport width) during analysis
    - Render agent entries with animated "running" indicator on `agent_start`
    - Update entries with latest progress message on `agent_progress`
    - Mark entries as completed (checkmark + duration) on `agent_complete`
    - Mark entries with red error indicator on `agent_error`
    - Show initial state "agents are initializing" before events arrive
    - Implement auto-scroll behavior (pauses on manual scroll-up, resumes at bottom)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.8_

  - [x] 7.2 Implement elapsed time formatting and duration display
    - Format elapsed timestamps as `+M:SS` (e.g., "+0:05", "+1:23")
    - Format duration as `X.Ys` (e.g., "12.3s", "0.5s")
    - Truncate messages longer than 200 characters with ellipsis
    - _Requirements: 5.3, 5.4, 5.7_

  - [x] 7.3 Write property tests for duration formatting (Property 9)
    - **Property 9: Duration formatting**
    - Use fast-check to generate random non-negative integers and verify format matches `X.Ys` pattern
    - **Validates: Requirements 5.4**

  - [x] 7.4 Write property tests for elapsed time formatting (Property 10)
    - **Property 10: Elapsed time formatting**
    - Use fast-check to generate random elapsed ms values and verify format matches `+M:SS` pattern
    - **Validates: Requirements 5.7**

  - [x] 7.5 Write property test for message truncation (Property 8)
    - **Property 8: Progress message truncation**
    - Use fast-check to generate arbitrary-length strings and verify output ≤ 203 chars with correct ellipsis handling
    - **Validates: Requirements 5.3**

- [x] 8. Checkpoint - SSE streaming end-to-end
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement System Report Dashboard Tab
  - [x] 9.1 Create SystemReportTab component with three sections
    - Create `frontend/src/components/SystemReportTab.tsx`
    - Render "Technology Stack" section with entries grouped by category (language, framework, database, infrastructure) as badges/list items
    - Omit categories with zero items
    - Render "How to Run" section with Markdown→HTML conversion (headings, code blocks, lists, inline code)
    - Render "Project Description" section with Markdown→HTML conversion
    - Show loading indicator while data is loading
    - Show placeholder message when data is unavailable
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [x] 9.2 Integrate SystemReportTab into DashboardLayout navigation
    - Add "System Report" tab to the existing dashboard tab navigation bar
    - Assign distinct icon from existing tabs (Code Flow, ER Database, Architecture)
    - Wire SystemReport data from analysis result to the tab component
    - _Requirements: 7.1_

  - [x] 9.3 Write property test for category filtering (Property 14)
    - **Property 14: Technology stack category filtering**
    - Use fast-check to generate TechStack with varying categories and verify only non-empty categories are rendered
    - **Validates: Requirements 7.3**

  - [x] 9.4 Write property test for Markdown rendering (Property 15)
    - **Property 15: Markdown to HTML rendering**
    - Use fast-check to generate Markdown strings with headings/code/lists and verify corresponding HTML elements exist
    - **Validates: Requirements 7.4, 7.5**

- [x] 10. Integration and wiring
  - [x] 10.1 Wire frontend to use useAnalysisStream hook in the main analysis flow
    - Update `InitialHeroState` or equivalent entry component to use `useAnalysisStream` instead of direct fetch
    - Show ProcessPanel during streaming state
    - Transition to Dashboard on `analysis_complete`
    - Handle error states with retry UI
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.1_

  - [x] 10.2 Create agents package __init__ and register all 5 agents in orchestrator
    - Create `backend/src/dev_ghost_parser/agents/__init__.py`
    - Register ASTAnalyzerAgent, ERExtractorAgent, CodeAuditorAgent, DocGeneratorAgent, SystemReporterAgent
    - Ensure orchestrator instantiates all agents from registry
    - _Requirements: 1.2_

  - [x] 10.3 Write integration tests for /analyze-stream end-to-end with mock LLM
    - Test full SSE flow with a mock LLM client
    - Verify event ordering, schema, and final analysis_complete payload
    - _Requirements: 2.1, 2.6, 2.8_

  - [x] 10.4 Write integration test for /analyze backward compatibility
    - Verify existing response fields unchanged
    - Verify systemReport field present on success, absent on failure
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend uses Python with Hypothesis for property-based tests
- Frontend uses TypeScript with fast-check for property-based tests
- The existing `/analyze` endpoint remains fully backward compatible
- Agents wrap existing analysis logic rather than rewriting it from scratch

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "6.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "2.1", "3.1", "3.2", "3.3", "3.4", "3.5"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "3.6", "3.7", "10.2"] },
    { "id": 3, "tasks": ["5.1", "5.2"] },
    { "id": 4, "tasks": ["5.3", "6.1"] },
    { "id": 5, "tasks": ["6.3", "7.1", "7.2"] },
    { "id": 6, "tasks": ["7.3", "7.4", "7.5", "9.1"] },
    { "id": 7, "tasks": ["9.2", "9.3", "9.4"] },
    { "id": 8, "tasks": ["10.1", "10.3", "10.4"] }
  ]
}
```
