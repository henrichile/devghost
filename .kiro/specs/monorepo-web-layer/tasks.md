# Implementation Plan: Monorepo Web Layer

## Overview

This plan restructures DevGhost-Parser into a monorepo with `backend/` (existing Python FastAPI engine), `frontend/` (new React + TypeScript SPA with interactive diagrams and audio tour), and Docker orchestration at root. Tasks are ordered to establish structure first, then build the frontend UI components, then containerize and wire everything together.

## Tasks

- [x] 1. Monorepo directory restructure
  - [x] 1.1 Relocate existing Python project into `backend/` subdirectory
    - Move `src/`, `tests/`, `pyproject.toml`, `.hypothesis/`, `.pytest_cache/` into `backend/`
    - Remove any Python project files (src/, tests/, pyproject.toml) from the repository root
    - Update any internal path references (e.g., in pyproject.toml, conftest.py) to reflect the new location
    - Verify no Python source files remain at monorepo root
    - _Requirements: 1.1, 1.6_

  - [x] 1.2 Update root-level shared configuration files
    - Update `.gitignore` paths to reference `backend/` and `frontend/` subdirectories
    - Update `README.md` with new monorepo structure documentation
    - Ensure shared config files remain at root
    - _Requirements: 1.5_

  - [x] 1.3 Initialize frontend Vite + React + TypeScript project in `frontend/`
    - Scaffold a Vite project with the React + TypeScript template in `frontend/`
    - Ensure `package.json` lists `vite` in `devDependencies`, `react` and `react-dom` in `dependencies`
    - Include `vite.config.ts`, `tsconfig.json`, and `src/main.tsx` entry point
    - _Requirements: 1.2, 2.1_

  - [x] 1.4 Install frontend production and dev dependencies
    - Add `@xyflow/react` as a production dependency
    - Add `lucide-react` as a production dependency
    - Add `tailwindcss` as a development dependency and configure it
    - Verify `npm run build` completes with zero errors from `frontend/`
    - _Requirements: 2.2, 2.3, 2.4, 2.5_

- [x] 2. Checkpoint - Verify monorepo structure
  - Ensure `backend/` passes all existing pytest tests
  - Ensure `frontend/` builds with zero errors via `npm run build`
  - Ensure no Python source files remain at monorepo root
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implement frontend TypeScript types and API service
  - [x] 3.1 Create TypeScript type definitions
    - Create `frontend/src/types.ts` with all interfaces: `CodeFlowNode`, `CodeFlowEdge`, `EntityAttribute`, `EREntity`, `ERRelation`, `AnalysisResponse`, `AnalysisError`
    - Include type aliases: `NodeType`, `EdgeRelation`, `RelationType`
    - _Requirements: 3.5, 3.6_

  - [x] 3.2 Implement API service module with timeout handling
    - Create `frontend/src/services/api.ts`
    - Implement `analyzeRepo(url: string): Promise<AnalysisResponse>` that sends POST to `/analyze`
    - Use `AbortController` with a 130-second timeout
    - Throw typed errors for HTTP 4xx/5xx (extracting `detail`) and for timeout
    - _Requirements: 3.3, 3.10, 3.11_

  - [x] 3.3 Implement URL validation utility
    - Create `frontend/src/utils/validation.ts`
    - Implement `isValidUrl(input: string): boolean` that returns true only for non-empty strings starting with `http://` or `https://`
    - _Requirements: 3.2_

  - [x] 3.4 Write property test for URL validation (Property 1)
    - **Property 1: URL validation rejects all non-HTTP(S) strings**
    - Use fast-check to generate arbitrary strings; assert `isValidUrl` returns `false` for empty/whitespace/non-http(s) strings and `true` for strings starting with `http://` or `https://`
    - Create `frontend/src/utils/validation.property.test.ts`
    - Minimum 100 iterations
    - **Validates: Requirements 3.2**

- [x] 4. Implement frontend UI components
  - [x] 4.1 Implement App root component with state management
    - Create `frontend/src/App.tsx` managing `AppState`: `repoUrl`, `loading`, `response`, `error`, `activeTab`
    - Wire API service calls and state transitions
    - Compose Header, TabView, AudioTourPanel, ErrorBanner, LoadingIndicator
    - _Requirements: 3.1, 3.3, 3.4_

  - [x] 4.2 Implement Header component with URL input and validation
    - Create `frontend/src/components/Header.tsx`
    - Render text input (max 2048 chars) and "Analyze" button
    - Disable button when URL is invalid (empty or non-http(s)) or when loading
    - Call `onAnalyze(url)` on submit
    - _Requirements: 3.1, 3.2_

  - [x] 4.3 Implement LoadingIndicator and ErrorBanner components
    - Create `frontend/src/components/LoadingIndicator.tsx` — spinner/progress shown during analysis
    - Create `frontend/src/components/ErrorBanner.tsx` — displays error message string without internal paths
    - _Requirements: 3.3, 3.10, 3.11_

  - [x] 4.4 Implement TabView component
    - Create `frontend/src/components/TabView.tsx`
    - Render two tabs: "Code Flow Graph" and "ER Database Graph"
    - Default to "Code Flow Graph" as active tab
    - Conditionally render the active graph component
    - _Requirements: 3.4_

  - [x] 4.5 Implement CodeFlowGraph component with typed node styling
    - Create `frontend/src/components/CodeFlowGraph.tsx`
    - Use `@xyflow/react` to render nodes and edges from `response.codeFlow`
    - Map each `NodeType` to a distinct background color or icon via a `getNodeStyle(type)` function
    - Display `label` on each node
    - If `codeFlow` is null, render informational "no results" message
    - _Requirements: 3.5, 3.7_

  - [x] 4.6 Write property test for node type visual mapping (Property 2)
    - **Property 2: Distinct node types produce distinct visual indicators**
    - Use fast-check to generate pairs of different `NodeType` values; assert `getNodeStyle` returns different styles
    - Create `frontend/src/components/CodeFlowGraph.property.test.ts`
    - Minimum 100 iterations
    - **Validates: Requirements 3.5**

  - [x] 4.7 Implement ERDatabaseGraph component
    - Create `frontend/src/components/ERDatabaseGraph.tsx`
    - Use `@xyflow/react` to render entities as nodes showing `name` and `attributes`
    - Render relations as edges annotated with relationship `type`
    - If `erModel` is null, render informational "no results" message
    - _Requirements: 3.6, 3.7_

  - [x] 4.8 Implement AudioTourPanel component with Web Speech API
    - Create `frontend/src/components/AudioTourPanel.tsx`
    - Display the `summary` text from the API response
    - Provide "Play" button that uses `window.speechSynthesis` to narrate the summary
    - While speaking, show "Stop" button that cancels playback and restores "Play"
    - If `speechSynthesis` is unavailable, disable Play with a tooltip
    - _Requirements: 3.8, 3.9_

  - [x] 4.9 Write unit tests for frontend components
    - Set up Vitest + React Testing Library in `frontend/`
    - Test Header renders input + button and disables on invalid URL
    - Test TabView defaults to Code Flow tab
    - Test ErrorBanner displays message
    - Test AudioTourPanel play/stop toggle
    - Test null data shows informational message in graph components
    - _Requirements: 3.1, 3.2, 3.4, 3.7, 3.8, 3.9, 3.10_

- [x] 5. Checkpoint - Verify frontend functionality
  - Ensure `npm run build` passes with zero errors from `frontend/`
  - Ensure all frontend tests pass via `npx vitest --run`
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Backend Dockerization
  - [x] 6.1 Create Backend Dockerfile
    - Create `backend/Dockerfile` based on Python 3.11 base image
    - Install all dependencies from `pyproject.toml` including tree-sitter grammars, FastAPI, Uvicorn
    - Install `git` in the container
    - Set CMD to run Uvicorn bound to `0.0.0.0:8000`
    - Ensure container exits with non-zero code if Uvicorn fails to start
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.7_

  - [x] 6.2 Write smoke test for Backend Dockerfile
    - Verify image builds without errors
    - Verify `python -c "import dev_ghost_parser"` runs without import errors
    - Verify `git --version` returns valid output
    - Verify `GET /docs` returns HTTP 200 within 30 seconds of start
    - _Requirements: 4.1, 4.2, 4.3, 4.6_

- [x] 7. Frontend Dockerization
  - [x] 7.1 Create Frontend Dockerfile with multi-stage build
    - Create `frontend/Dockerfile` with build stage (Node 20+ running `npm install` and `npm run build`) and serve stage (Nginx serving `dist/`)
    - Expose port 80
    - _Requirements: 5.1, 5.2, 5.5_

  - [x] 7.2 Create Nginx configuration for frontend container
    - Create `frontend/nginx.conf`
    - Set cache-control max-age of 1 year for hashed static assets (JS, CSS, images)
    - Set no-cache for `index.html`
    - Configure reverse proxy for `POST /analyze` to `http://backend:8000/analyze` with 120-second proxy read timeout
    - Return 502 within 10 seconds if backend is unreachable
    - _Requirements: 5.3, 5.4, 5.6_

- [x] 8. Docker Compose orchestration
  - [x] 8.1 Create `docker-compose.yml` at repository root
    - Define `backend` service with build context `./backend`, port mapping `8000:8000`
    - Define `frontend` service with build context `./frontend`, port mapping `5173:80`
    - Configure shared Docker network for inter-service communication
    - Add health check for `backend`: `curl -f http://localhost:8000/` with 10s interval, 5s timeout, 3 retries
    - Set `frontend` `depends_on` with `condition: service_healthy`
    - Ensure `docker-compose up --build` rebuilds both images
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure backend tests pass from `backend/` directory
  - Ensure frontend builds and tests pass from `frontend/` directory
  - Ensure `docker-compose.yml` is valid YAML with correct service definitions
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties defined in the design (fast-check for TypeScript)
- The backend Python code is relocated but NOT modified — existing functionality is preserved
- Frontend uses TypeScript throughout; backend remains Python
- Integration tests with running containers are left for CI pipeline and are not included as coding tasks here

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4"] },
    { "id": 3, "tasks": ["3.1", "3.2", "3.3"] },
    { "id": 4, "tasks": ["3.4", "4.1", "4.2", "4.3"] },
    { "id": 5, "tasks": ["4.4", "4.5", "4.7", "4.8"] },
    { "id": 6, "tasks": ["4.6", "4.9"] },
    { "id": 7, "tasks": ["6.1", "7.1"] },
    { "id": 8, "tasks": ["6.2", "7.2"] },
    { "id": 9, "tasks": ["8.1"] }
  ]
}
```
