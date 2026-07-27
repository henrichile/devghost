# Implementation Plan: Generación de Casos de Uso

## Overview

Este plan implementa la generación automática de Historias de Usuario y Casos de Uso en el pipeline de DevGhost Parser. El backend añade un nuevo método `generate_use_cases` a `Artifacts_Generator` con helpers para prompt building, integrado en el endpoint SSE `/analyze-stream`. El frontend extiende la interfaz `ArtifactsResponse` y agrega una pestaña "Casos de Uso" al `DocumentationPanel`. Se usan Hypothesis (Python) para property tests del backend y pytest para unit tests.

## Tasks

- [x] 1. Implement backend use case generation logic
  - [x] 1.1 Add `_build_use_case_system_prompt` method to `Artifacts_Generator`
    - Add the private method that returns the system prompt string in Spanish
    - Include all formatting instructions: "Como [rol]", "Precondiciones", "Flujo Principal", "entre 3 y 10 pasos", "español"
    - Follow the exact prompt structure defined in the design document
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 6.1, 6.2, 6.3, 6.5_

  - [x] 1.2 Add `_build_use_case_prompt` method to `Artifacts_Generator`
    - Add the private method that builds the user prompt from `CodeFlowResult` and controller nodes
    - Build a `node_map` and `edges_from` dict for efficient lookup
    - For each Controller/Route node with methods: include label, type, description, method names (capped at 15)
    - Include related Service labels and Middleware labels from edges
    - Skip controllers with no methods
    - Gracefully skip edges referencing non-existent node IDs
    - _Requirements: 1.1, 1.5, 2.3, 2.4, 6.5_

  - [x] 1.3 Add `generate_use_cases` public method to `Artifacts_Generator`
    - Add the public method with signature `generate_use_cases(self, code_flow: "CodeFlowResult | None") -> str | None`
    - Implement guard clauses: return `None` if LLM client missing/unavailable, code_flow is None/empty, or no Controller/Route nodes
    - Filter controllers, call `_build_use_case_prompt` and `_build_use_case_system_prompt`
    - Invoke `self._llm_client.complete(system_prompt, user_prompt)`
    - Return `None` if result is None/empty/whitespace, otherwise return the result
    - _Requirements: 3.3, 3.4, 4.1, 4.2, 4.3, 6.4_

  - [x] 1.4 Write property test: Prompt completeness (Property 1)
    - **Property 1: Prompt completeness — methods, services, and middleware included**
    - Create Hypothesis strategies: `st_node()` for Node generation, `st_code_flow_with_controllers()` for CodeFlowResult with Controller/Route nodes + edges to Service/Middleware nodes
    - Verify the generated user_prompt contains all method names, Service labels, and Middleware labels
    - Min 100 iterations
    - **Validates: Requirements 1.1, 2.3, 2.4, 6.5**

  - [x] 1.5 Write property test: Empty controllers excluded (Property 2)
    - **Property 2: Controllers without methods are excluded from prompt**
    - Generate CodeFlowResult with a mix of Controller/Route nodes — some with methods, some without
    - Verify labels of controllers with empty `method_names` do NOT appear in user_prompt
    - Min 100 iterations
    - **Validates: Requirements 1.5**

  - [x] 1.6 Write property test: Guard clause returns None (Property 3)
    - **Property 3: Guard clause — returns None when preconditions unmet**
    - Test with CodeFlowResult containing zero Controller/Route nodes → returns None without LLM call
    - Test with LLM_Client.available = False → returns None without LLM call
    - Test with code_flow = None → returns None
    - Mock LLM_Client to verify `complete()` is never called
    - Min 100 iterations
    - **Validates: Requirements 3.3, 4.3**

  - [x] 1.7 Write property test: Empty LLM response produces None (Property 4)
    - **Property 4: Empty LLM response produces None**
    - Generate valid CodeFlowResult with controllers+methods
    - Mock LLM_Client.complete() to return "", " ", "\n", or None
    - Verify `generate_use_cases` returns None in all cases
    - Min 100 iterations
    - **Validates: Requirements 6.4**

  - [x] 1.8 Write unit tests for system prompt content
    - Verify `_build_use_case_system_prompt()` contains key instructions: "español", "Como [rol]", "Precondiciones", "Flujo Principal", "entre 3 y 10 pasos", "Flujos Alternativos"
    - Verify prompt instructs LLM to respond in Markdown only, no code blocks
    - _Requirements: 1.6, 2.6, 6.1, 6.2, 6.3_

- [x] 2. Checkpoint - Backend generation logic
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Integrate into backend pipeline
  - [x] 3.1 Add `useCases` key to artifacts generation in `server.py`
    - In the `/analyze-stream` endpoint, add `"useCases": generator.generate_use_cases(_cf)` to the `artifacts_result` dict inside the `asyncio.to_thread` block
    - Ensure the call follows the same pattern as existing artifact generators
    - _Requirements: 4.4, 4.5_

  - [x] 3.2 Write unit test for pipeline integration
    - Mock `Artifacts_Generator.generate_use_cases` and verify it's called during analysis
    - Verify the `artifacts` dict in the SSE `analysis_complete` event contains the `useCases` key
    - _Requirements: 4.4, 4.5_

- [x] 4. Implement frontend changes
  - [x] 4.1 Extend `ArtifactsResponse` TypeScript interface
    - Add `useCases: string | null` field to the `ArtifactsResponse` interface
    - _Requirements: 5.5_

  - [x] 4.2 Add "Casos de Uso" tab to `DocumentationPanel`
    - Add `'usecases'` to the `ArtifactTab` type union
    - Add tab entry `{ id: 'usecases', label: 'Casos de Uso', icon: '👤' }` to the tabs array
    - Extend `getContent` to return `artifacts.useCases` for the `'usecases'` tab
    - Show a fallback message when `artifacts.useCases` is null
    - Ensure existing Copy and Download buttons work with the new tab content
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 4.3 Write unit tests for frontend integration
    - Verify `ArtifactTab` type includes `'usecases'`
    - Verify "Casos de Uso" tab renders when `artifacts.useCases` has content
    - Verify fallback message shows when `artifacts.useCases` is null
    - Verify Copy/Download work with useCases content
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 5. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend uses Python with Hypothesis for property-based tests
- Frontend uses TypeScript for the UI integration
- The implementation follows the exact same pattern as existing artifact generators (generate_c4_diagram, generate_adr, etc.)
- All generated content is in Spanish as specified in requirements

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "4.1"] },
    { "id": 2, "tasks": ["1.4", "1.5", "1.6", "1.7", "1.8"] },
    { "id": 3, "tasks": ["3.1", "4.2"] },
    { "id": 4, "tasks": ["3.2", "4.3"] }
  ]
}
```
