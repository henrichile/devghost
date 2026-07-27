# Implementation Plan: LLM Integration and Hero Redesign

## Overview

This plan implements two parallel tracks: (1) integrating an LLM client (Alibaba Cloud MaaS, qwen3.7-plus model) into the DevGhost-Parser backend to enrich node descriptions and audio tour summaries with Spanish text generation, and (2) building the Hero component for the frontend React app. The LLM integration follows a fallback pattern where heuristic logic remains the safety net for any LLM failure.

## Tasks

- [x] 1. Set up LLM client module and add OpenAI dependency
  - [x] 1.1 Add `openai` dependency to `pyproject.toml`
    - Add `openai>=1.0.0,<2` to the `dependencies` list in `pyproject.toml`
    - Use compatible version range format `>=X.Y.Z,<X+1` as required
    - _Requirements: 6.1, 6.2_

  - [x] 1.2 Create `llm_client.py` module
    - Create `backend/src/dev_ghost_parser/llm_client.py`
    - Implement `LLM_Client` class with `__init__`, `available` property, and `complete()` method
    - Read `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` from environment variables
    - Configure `openai.OpenAI` with `timeout=4.0` and `max_retries=0`
    - Set `available=False` when API key is missing/empty or base URL is invalid (not http/https)
    - Catch all OpenAI SDK exceptions (`APIError`, `APITimeoutError`, `APIConnectionError`) in `complete()`, log warning, return `None`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 4.1, 4.2, 4.3, 4.6_

  - [x] 1.3 Write property test for URL configuration validation
    - **Property 1: URL Configuration Validation**
    - **Validates: Requirements 1.3, 1.9**
    - Create `backend/tests/property/test_property_url_config_validation.py`
    - Generate random strings for `LLM_BASE_URL`; verify only http:// or https:// prefixed values activate `available=True`

  - [x] 1.4 Write property test for LLM_Client error containment
    - **Property 8: LLM_Client Error Containment**
    - **Validates: Requirements 4.1, 4.2, 4.3**
    - Create `backend/tests/property/test_property_llm_error_containment.py`
    - Mock OpenAI SDK to raise various exceptions; verify `complete()` returns `None` without propagation

- [x] 2. Integrate LLM into Description_Generator
  - [x] 2.1 Modify `description_generator.py` to accept and use LLM_Client
    - Add `llm_client` parameter to `Description_Generator` constructor (default `None` for backward compatibility)
    - Implement `_from_llm()` method that builds the prompt with node label, type, and method names (up to 10)
    - Include system prompt instructing Spanish description with max 90 characters
    - Implement `_truncate_llm()` method: if >90 chars, truncate to 87 + "..."
    - Validate LLM response: must be ≥5 characters, otherwise discard
    - Modify `generate()` to attempt LLM first (if available), then fall back to existing heuristic logic
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 2.2 Write property test for description prompt completeness
    - **Property 2: Description Prompt Completeness**
    - **Validates: Requirements 2.1, 2.2**
    - Create `backend/tests/property/test_property_description_prompt.py`
    - Generate random Nodes; verify prompt contains label, type, method names, and 90-char instruction

  - [x] 2.3 Write property test for description LLM response handling
    - **Property 3: Description LLM Response Handling**
    - **Validates: Requirements 2.3, 2.4, 2.6**
    - Create `backend/tests/property/test_property_description_response.py`
    - Generate random strings; verify truncation to 90 chars and rejection of strings < 5 chars

  - [x] 2.4 Write property test for description fallback on LLM error
    - **Property 4: Description Fallback on LLM Error**
    - **Validates: Requirements 2.5, 2.6, 2.7**
    - Create `backend/tests/property/test_property_description_fallback.py`
    - Generate error conditions; verify output identical to heuristic-only logic

- [x] 3. Integrate LLM into Summary_Generator
  - [x] 3.1 Modify `summary_generator.py` to accept and use LLM_Client
    - Add `llm_client` parameter to `Summary_Generator` constructor (default `None` for backward compatibility)
    - Implement `_from_llm()` method that sends controller names and entity names to LLM
    - Include system prompt instructing 3-4 sentence Spanish narrative with max 450 characters
    - Validate LLM response: must contain at least one period, truncate if >450 chars (447 + "...")
    - Apply existing `_sanitize()` to LLM result; discard if post-sanitization < 10 chars
    - Modify `generate()` to attempt LLM first (if available), then fall back to existing heuristic logic
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

  - [x] 3.2 Write property test for summary prompt completeness
    - **Property 5: Summary Prompt Completeness**
    - **Validates: Requirements 3.1, 3.2**
    - Create `backend/tests/property/test_property_summary_prompt.py`
    - Generate random controller/entity lists; verify prompt content and 450-char instruction

  - [x] 3.3 Write property test for summary LLM response pipeline
    - **Property 6: Summary LLM Response Pipeline**
    - **Validates: Requirements 3.3, 3.4, 3.8, 3.9**
    - Create `backend/tests/property/test_property_summary_response_pipeline.py`
    - Generate random strings; verify truncation, period validation, sanitization, and post-sanitization length check

  - [x] 3.4 Write property test for summary fallback on LLM error
    - **Property 7: Summary Fallback on LLM Error**
    - **Validates: Requirements 3.5, 3.6, 3.7**
    - Create `backend/tests/property/test_property_summary_fallback.py`
    - Generate error conditions; verify summary maintains existing invariants (≤500 cp, ≤4 sentences)

- [x] 4. Checkpoint - Backend LLM integration verification
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Wire LLM_Client into the orchestration pipeline
  - [x] 5.1 Update `__init__.py` to instantiate and inject LLM_Client
    - Import `LLM_Client` from `llm_client` module
    - Instantiate `LLM_Client()` once in the orchestration function
    - Pass `llm_client` instance to `Description_Generator` and `Summary_Generator` constructors
    - _Requirements: 4.5_

  - [x] 5.2 Write property test for heuristic equivalence when LLM unavailable
    - **Property 9: Heuristic Equivalence When LLM Unavailable**
    - **Validates: Requirements 4.5**
    - Create `backend/tests/property/test_property_heuristic_equivalence.py`
    - Generate random CodeFlowResult and ERResult; compare output with LLM unavailable vs. heuristic-only

- [x] 6. Checkpoint - Full backend integration verification
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Set up frontend project structure
  - [x] 7.1 Initialize React/TypeScript frontend project
    - Create `backend/frontend/package.json` with React, TypeScript, and build tooling
    - Create `backend/frontend/tsconfig.json` with strict TypeScript configuration
    - Set up directory structure: `src/components/`, `src/styles/`
    - Add `vitest` and `@testing-library/react` as dev dependencies
    - _Requirements: 5.1_

- [x] 8. Implement Hero Component
  - [x] 8.1 Create `InitialHeroState.tsx` component
    - Create `backend/frontend/src/components/InitialHeroState.tsx`
    - Implement `HeroProps` interface with `onAnalyze: (repoUrl: string) => void` callback
    - Add state for `repoUrl` with URL validation regex `^https?://.+`
    - Render: logo with `ghost-float` class, tagline (≤120 chars), URL input (maxLength 2048), analyze button
    - Button disabled when URL is invalid or empty
    - Call `onAnalyze(repoUrl.trim())` on button click when valid
    - Add `aria-label` on input and `aria-disabled` on button for accessibility
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 8.2 Create `hero.css` styles with responsive layout and animation
    - Create `backend/frontend/src/styles/hero.css`
    - Implement flexbox centering with `min-height: 100vh`
    - Logo: minimum 32×32px rendered size, width: 120px
    - Define `@keyframes ghost-float` with 3-second cycle duration
    - Apply `.ghost-float` animation class
    - Form layout: column on <640px, row on ≥640px
    - Ensure WCAG 2.1 AA contrast ratios (4.5:1 normal text, 3:1 large text)
    - _Requirements: 5.2, 5.7, 5.8, 5.9_

  - [x] 8.3 Write unit tests for Hero Component
    - Create `backend/frontend/src/components/__tests__/InitialHeroState.test.tsx`
    - Test: renders logo, tagline, input, and button
    - Test: button disabled with empty URL
    - Test: button enabled with valid URL (https://github.com/user/repo)
    - Test: submit calls `onAnalyze` with trimmed URL
    - Test: logo has `ghost-float` CSS class
    - _Requirements: 5.1, 5.2, 5.6_

  - [x] 8.4 Write property test for Hero URL validation
    - **Property 10: Hero URL Validation**
    - **Validates: Requirements 5.6**
    - Create `backend/frontend/src/components/__tests__/InitialHeroState.property.test.tsx`
    - Use `fast-check` to generate random strings; verify only `http://` or `https://` prefixed URLs enable the button

- [x] 9. Wire Hero Component into App
  - [x] 9.1 Integrate `InitialHeroState` into `App.tsx`
    - Create or modify `backend/frontend/src/App.tsx`
    - Show `InitialHeroState` when no analysis has been submitted
    - On `onAnalyze` callback, transition to results view (replace Hero)
    - Import and apply `hero.css` styles
    - _Requirements: 5.1, 5.5_

- [x] 10. Final checkpoint - Full system verification
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis (backend) and fast-check (frontend)
- Unit tests validate specific examples and edge cases
- Backend uses Python 3.11+ with pytest and Hypothesis
- Frontend uses TypeScript with React, vitest, and React Testing Library
- The LLM_Client is backward-compatible: when `LLM_API_KEY` is not set, behavior is identical to current heuristic-only mode

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "7.1"] },
    { "id": 1, "tasks": ["1.3", "1.4", "2.1", "8.1", "8.2"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "3.1", "8.3", "8.4"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4", "5.1", "9.1"] },
    { "id": 4, "tasks": ["5.2"] }
  ]
}
```
