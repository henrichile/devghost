# Implementation Plan: Backlog Generation

## Overview

Este plan implementa la generación automática de Product Backlog en el pipeline de DevGhost Parser. El backend añade un nuevo método `generate_backlog` a `Artifacts_Generator` con helpers para prompt building que incluyen cálculo de centralidad y detección de servicios transversales, integrado en el endpoint SSE `/analyze-stream`. El frontend extiende la interfaz `ArtifactsResponse` y agrega una pestaña "Backlog" al `DocumentationPanel`. Se usan Hypothesis (Python) para property tests del backend y pytest para unit tests.

## Tasks

- [ ] 1. Implement backend backlog generation logic
  - [ ] 1.1 Add `_build_backlog_system_prompt` method to `Artifacts_Generator`
    - Add the private method that returns the system prompt string instructing the LLM
    - Include instructions: output in Markdown with hierarchical headings (## sections, ### épicas, #### historias)
    - Include "Como [rol], quiero [acción], para [beneficio]" format
    - Include Fibonacci scale for story points (1, 2, 3, 5, 8, 13)
    - Include priority levels (Alta, Media, Baja)
    - Include grouping in épicas by functional domain
    - Include summary table at the beginning with totals
    - Include HU-XXX identifiers and acceptance criteria per story
    - Include ordering by descending priority within each epic
    - Include instruction to generate in Spanish
    - _Requirements: 1.1, 1.6, 2.1, 2.2, 2.3, 3.1, 3.5, 4.1, 4.2, 4.3, 4.4, 7.3, 7.6_

  - [ ] 1.2 Add `_build_backlog_prompt` method to `Artifacts_Generator`
    - Add the private method that builds the user prompt from `CodeFlowResult` and filtered controller nodes
    - For each controller with methods: include label, type, method names
    - Include connected services, repositories, and middleware labels via edges lookup
    - Compute and include in-degree (incoming edges count) for each controller node
    - Compute and include out-degree (dependency count) per controller for complexity estimation
    - Identify cross-cutting services (Service nodes connected to 2+ controllers) and list them with their connected controller labels
    - Skip controllers with no methods (already filtered by caller)
    - _Requirements: 1.1, 1.2, 1.3, 2.4, 3.2, 3.4, 7.1, 7.5_

  - [ ] 1.3 Add `generate_backlog` public method to `Artifacts_Generator`
    - Add the public method with signature `generate_backlog(self, code_flow: "CodeFlowResult | None") -> str | None`
    - Implement guard clauses: return `None` if LLM client missing/unavailable, code_flow is None or has no nodes, or no Controller/Route nodes with methods
    - Filter controllers to only those with `method_names` non-empty
    - Call `_build_backlog_prompt` and `_build_backlog_system_prompt`
    - Invoke `self._llm_client.complete(system_prompt, user_prompt)`
    - Return `None` if result is None/empty/whitespace, otherwise return the result
    - _Requirements: 1.5, 4.5, 5.1, 5.2, 5.3, 5.6, 7.4_

  - [ ]* 1.4 Write property test: Prompt completeness (Property 1)
    - **Property 1: Prompt completeness — all structural context is included**
    - Create Hypothesis strategies: `st_node()` for Node generation, `st_code_flow_with_controllers()` for CodeFlowResult with Controller/Route nodes + edges to Service/Repository/Middleware nodes
    - Verify the generated user prompt contains all controller labels, all method names of those controllers, and labels of all directly connected services, repositories, and middleware
    - Min 100 iterations
    - **Validates: Requirements 1.1, 1.2, 1.3, 7.1, 7.5**

  - [ ]* 1.5 Write property test: Controllers without methods excluded (Property 2)
    - **Property 2: Controllers without methods are excluded**
    - Generate CodeFlowResult with a mix of Controller/Route nodes — some with methods, some without
    - Verify labels of controllers with empty `method_names` do NOT appear in the constructed prompt
    - Min 100 iterations
    - **Validates: Requirements 1.5**

  - [ ]* 1.6 Write property test: Cross-cutting services identified (Property 3)
    - **Property 3: Cross-cutting services are identified**
    - Generate CodeFlowResult where a Service node has incoming edges from 2+ Controller/Route nodes
    - Verify the prompt construction identifies that service as cross-cutting and includes it with connected controller labels
    - Min 100 iterations
    - **Validates: Requirements 2.4**

  - [ ]* 1.7 Write property test: Graph centrality metrics included (Property 4)
    - **Property 4: Graph centrality metrics are included**
    - Generate CodeFlowResult with edges connecting to Controller/Route nodes
    - Verify the constructed prompt includes the in-degree count for each Controller/Route node
    - Min 100 iterations
    - **Validates: Requirements 3.2, 3.4**

  - [ ]* 1.8 Write property test: No controllers yields None (Property 5)
    - **Property 5: No controllers or routes yields None**
    - Generate CodeFlowResult with zero Controller/Route nodes (only Service, Utility, Middleware, Repository, Config nodes)
    - Verify `generate_backlog` returns None without calling LLM
    - Min 100 iterations
    - **Validates: Requirements 4.5**

  - [ ]* 1.9 Write property test: LLM unavailable yields None (Property 6)
    - **Property 6: LLM unavailable yields None**
    - Generate valid CodeFlowResult with controllers and methods
    - Set LLM_Client.available = False
    - Verify `generate_backlog` returns None without calling LLM complete()
    - Min 100 iterations
    - **Validates: Requirements 5.3**

  - [ ]* 1.10 Write property test: LLM empty response yields None (Property 7)
    - **Property 7: LLM empty response yields None**
    - Generate valid CodeFlowResult with controllers and methods
    - Mock LLM_Client.complete() to return "", " ", "\n", or None
    - Verify `generate_backlog` returns None in all cases
    - Min 100 iterations
    - **Validates: Requirements 7.4**

  - [ ]* 1.11 Write unit tests for system prompt and integration
    - Verify `_build_backlog_system_prompt()` contains key instructions: "español", "Fibonacci", "Alta, Media, Baja", "HU-", "Como", "criterios de aceptación", Markdown headings
    - Verify `generate_backlog` calls `LLM_Client.complete` with correct system and user prompts (mock)
    - Verify guard clauses return None for edge cases (None code_flow, empty nodes list)
    - _Requirements: 1.6, 3.1, 3.3, 4.2, 5.3, 7.4_

- [ ] 2. Checkpoint - Backend generation logic
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Integrate into backend pipeline
  - [ ] 3.1 Add `backlog` key to artifacts generation in `server.py`
    - In the `/analyze-stream` endpoint, add `"backlog": generator.generate_backlog(_cf)` to the `artifacts_result` dict inside the `asyncio.to_thread` block
    - Emit SSE events: `agent_start "backlog_generator"`, `agent_progress "Generando backlog..."`, `agent_complete "Backlog generado"`
    - Follow the same pattern as existing artifact generators (useCases, c4Mermaid, etc.)
    - _Requirements: 5.4, 5.5_

  - [ ]* 3.2 Write unit test for pipeline integration
    - Mock `Artifacts_Generator.generate_backlog` and verify it's called during analysis
    - Verify the `artifacts` dict in the SSE `analysis_complete` event contains the `backlog` key
    - Verify SSE events are emitted for the backlog agent
    - _Requirements: 5.4, 5.5_

- [ ] 4. Implement frontend changes
  - [ ] 4.1 Extend `ArtifactsResponse` TypeScript interface
    - Add `backlog: string | null` field to the `ArtifactsResponse` interface
    - _Requirements: 6.5_

  - [ ] 4.2 Add "Backlog" tab to `DocumentationPanel`
    - Add `'backlog'` to the `ArtifactTab` type union
    - Add tab entry `{ id: 'backlog', label: 'Backlog', icon: '📋' }` to the tabs array
    - Extend `getContent` to return `artifacts.backlog` for the `'backlog'` tab
    - Show a fallback message "No se pudo generar el backlog. Intenta analizar nuevamente." when `artifacts.backlog` is null
    - Ensure existing Copy and Download buttons work with the new tab content
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 4.3 Write unit tests for frontend integration
    - Verify `ArtifactTab` type includes `'backlog'`
    - Verify "Backlog" tab with 📋 icon renders in DocumentationPanel
    - Verify MarkdownRenderer is used when `artifacts.backlog` has content
    - Verify fallback message shows when `artifacts.backlog` is null
    - Verify Copy/Download buttons work with backlog content
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ] 5. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend uses Python with Hypothesis for property-based tests
- Frontend uses TypeScript for the UI integration
- The implementation follows the exact same pattern as the use-case-generation artifact (generate_use_cases)
- All generated content is in Spanish as specified in requirements
- Cross-cutting service detection and centrality metrics are key differentiators from the use-case prompt builder

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "4.1"] },
    { "id": 2, "tasks": ["1.4", "1.5", "1.6", "1.7", "1.8", "1.9", "1.10", "1.11"] },
    { "id": 3, "tasks": ["3.1", "4.2"] },
    { "id": 4, "tasks": ["3.2", "4.3"] }
  ]
}
```
