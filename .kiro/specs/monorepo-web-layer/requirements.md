# Requirements Document

## Introduction

This feature restructures the DevGhost-Parser project into a monorepo layout with three top-level concerns: a Python backend (the existing analysis engine relocated to `backend/`), a React frontend (a new Vite + TypeScript application in `frontend/`) that consumes the analysis API and presents interactive code-flow and ER diagrams with an audio tour, and Docker orchestration (`docker-compose.yml` at root) that wires both services together for local development and production deployment.

## Glossary

- **Monorepo**: A single repository containing multiple distinct projects (backend, frontend) that can be developed, built, and deployed independently while sharing the same version-control history.
- **Backend**: The Python FastAPI service (formerly the top-level project) relocated to the `backend/` subdirectory; exposes `POST /analyze` on port 8000.
- **Frontend**: A React single-page application built with Vite and TypeScript located in `frontend/`; communicates with the Backend API and renders interactive diagrams.
- **Docker_Compose**: The orchestration layer defined in `docker-compose.yml` at repository root that builds and runs Backend and Frontend as containerized services.
- **Backend_Container**: The Docker container running the Python Backend service with Uvicorn.
- **Frontend_Container**: The Docker container serving the built Frontend assets via Nginx or a Node-based static server.
- **CodeFlowGraph**: A visual React Flow-based directed graph component displaying architectural nodes and dependency edges from the Backend analysis.
- **ERDatabaseGraph**: A visual React Flow-based diagram component displaying entities and their relationships from the Backend analysis.
- **AudioTour_Panel**: A UI panel that uses the Web Speech Synthesis API to narrate the executive summary returned by the Backend.
- **Analysis_API**: The `POST /analyze` HTTP endpoint on the Backend that accepts `{"repo_url": "..."}` and returns structured JSON with code-flow, ER model, and summary data.

---

## Requirements

### Requirement 1: Monorepo Directory Restructure

**User Story:** As a developer, I want the project reorganized into a monorepo layout with `backend/` and `frontend/` subdirectories, so that each concern has its own isolated build environment while sharing the same repository.

#### Acceptance Criteria

1. WHEN the restructure is complete, THE Monorepo SHALL contain a `backend/` directory holding all previously top-level Python source files including `src/`, `tests/`, `pyproject.toml`, `.hypothesis/`, and `.pytest_cache/`, with no Python project files remaining at the repository root.
2. WHEN the restructure is complete, THE Monorepo SHALL contain a `frontend/` directory holding a Vite + TypeScript + React application that includes at minimum a `package.json`, `vite.config.ts`, `tsconfig.json`, and a `src/main.tsx` entry point, such that running `npm install` followed by `npm run build` from within `frontend/` completes with zero errors.
3. WHEN the restructure is complete, THE Monorepo SHALL contain a `docker-compose.yml` file at the repository root that defines at least two service entries — one with build context set to `backend/` and one with build context set to `frontend/`.
4. WHEN the restructure is complete, THE Backend SHALL pass all existing tests when `pytest` is executed from within the `backend/` directory, producing the same pass count as before the restructure.
5. IF shared configuration files exist at the root level (e.g., `.gitignore`, `README.md`), THEN THE Monorepo SHALL retain them at the repository root and update any internal path references to reflect the new `backend/` and `frontend/` subdirectory locations.
6. WHEN the restructure is complete, THE Monorepo root SHALL NOT contain any Python source files, `src/`, `tests/`, or `pyproject.toml` that were moved into `backend/`.

---

### Requirement 2: Frontend Application Setup

**User Story:** As a frontend developer, I want a React application initialized with Vite, TypeScript, and the required visualization libraries, so that I can begin building the interactive architecture viewer immediately.

#### Acceptance Criteria

1. WHEN the Frontend is initialized, THE Frontend SHALL use Vite as the build tool with the React + TypeScript template, verifiable by the presence of `vite` in `devDependencies` and `react`, `react-dom` in `dependencies` of `frontend/package.json`.
2. WHEN the Frontend is initialized, THE Frontend SHALL include `@xyflow/react` as a production dependency for rendering directed graphs.
3. WHEN the Frontend is initialized, THE Frontend SHALL include `lucide-react` as a production dependency for iconography.
4. WHEN the Frontend is initialized, THE Frontend SHALL include `tailwindcss` as a development dependency for utility-first CSS styling.
5. WHEN `npm run build` is executed from within `frontend/`, THE Frontend SHALL produce a static bundle in `frontend/dist/` containing at minimum an `index.html` file and associated JS/CSS assets, servable by any static HTTP server.

---

### Requirement 3: Frontend UI Components

**User Story:** As a user, I want a web interface with a repository URL input, tabbed graph views, and an audio narration panel, so that I can interactively explore a codebase's architecture.

#### Acceptance Criteria

1. THE Frontend SHALL render a Header component containing a text input (maximum 2048 characters) for entering a repository URL and a submit button labeled "Analyze" that triggers a request to the Analysis_API.
2. IF the repository URL input is empty or does not begin with "http://" or "https://", THEN THE Frontend SHALL disable the "Analyze" button and SHALL NOT send a request to the Analysis_API.
3. WHEN the user submits a repository URL, THE Frontend SHALL send a POST request to `http://localhost:8000/analyze` with the body `{"repo_url": "<user_input>"}`, disable the "Analyze" button, and display a visible loading indicator (such as a spinner or progress bar) until the response is received or 130 seconds have elapsed, whichever comes first.
4. WHEN the Analysis_API returns a successful response, THE Frontend SHALL render a tabbed interface with two tabs: "Code Flow Graph" and "ER Database Graph", with "Code Flow Graph" selected as the default active tab.
5. WHEN the "Code Flow Graph" tab is active, THE CodeFlowGraph component SHALL render all nodes from `response.codeFlow.nodes` and all edges from `response.codeFlow.edges` using `@xyflow/react`, with each node displaying its `label` and assigning a distinct visual indicator (unique background color or icon) per node `type` value so that any two nodes with different `type` values are visually distinguishable.
6. WHEN the "ER Database Graph" tab is active, THE ERDatabaseGraph component SHALL render all entities from `response.erModel.entities` as nodes displaying entity `name` and `attributes`, and all relations from `response.erModel.relations` as edges annotated with relationship `type`.
7. IF the API response contains a null value for `codeFlow` or `erModel`, THEN THE Frontend SHALL display an informational message within the corresponding tab indicating that the analysis for that subsystem produced no results, instead of rendering an empty graph.
8. THE Frontend SHALL render an AudioTour_Panel component that displays the `summary` text from the API response and provides a "Play" button.
9. WHEN the user clicks the "Play" button in the AudioTour_Panel, THE AudioTour_Panel SHALL use the Web Speech Synthesis API (`window.speechSynthesis`) to read the summary text aloud; WHEN the summary is currently being spoken, THE AudioTour_Panel SHALL replace the "Play" button with a "Stop" button that cancels speech playback and restores the "Play" button.
10. IF the Analysis_API returns an error response (HTTP 4xx or 5xx), THEN THE Frontend SHALL display the error message from the response `detail` field in a visible alert or banner element, without exposing raw stack traces or internal server paths, and SHALL re-enable the "Analyze" button.
11. IF the 130-second timeout elapses before receiving a response, THEN THE Frontend SHALL cancel the pending request, hide the loading indicator, re-enable the "Analyze" button, and display a message indicating the request timed out.

---

### Requirement 4: Backend Dockerization

**User Story:** As a DevOps engineer, I want the Python backend packaged as a Docker container, so that it runs consistently across all environments with all tree-sitter dependencies pre-installed.

#### Acceptance Criteria

1. THE Backend SHALL have a `backend/Dockerfile` that builds a container image based on a Python 3.11 base image and completes the build without errors when `docker build` is invoked from the `backend/` directory.
2. WHEN the Backend_Container is built, THE Backend_Container SHALL install all dependencies listed in `pyproject.toml` including tree-sitter language grammars and FastAPI/Uvicorn, such that `python -c "import dev_ghost_parser"` executes without import errors inside the container.
3. WHEN the Backend_Container is built, THE Backend_Container SHALL install `git` so that the `POST /analyze` endpoint can clone repositories, verifiable by `git --version` returning a valid version string inside the container.
4. WHEN the Backend_Container starts, THE Backend_Container SHALL run the FastAPI application using Uvicorn bound to `0.0.0.0:8000` and accept HTTP requests within 30 seconds of container start.
5. THE Backend_Container SHALL expose port 8000 for HTTP traffic from other containers or the host network.
6. WHEN the Backend_Container is running, THE Backend_Container SHALL respond to `GET /docs` with an HTTP 200 status, confirming the FastAPI application is serving requests and available for health verification.
7. IF the Backend_Container fails to start the Uvicorn process, THEN THE Backend_Container SHALL exit with a non-zero exit code within 10 seconds of the failure.

---

### Requirement 5: Frontend Dockerization

**User Story:** As a DevOps engineer, I want the React frontend packaged as a Docker container with a production-optimized build, so that it serves static assets efficiently.

#### Acceptance Criteria

1. THE Frontend SHALL have a `frontend/Dockerfile` that uses a multi-stage build: a build stage using a Node 20+ image to compile the Vite application, and a serve stage using Nginx to serve the static `dist/` output.
2. WHEN the Frontend_Container is built, THE build stage SHALL run `npm install` and `npm run build` to produce the optimized static bundle.
3. WHEN the Frontend_Container starts, THE Frontend_Container SHALL serve the built assets on port 80 using Nginx with cache-control headers that set a max-age of at least 1 year for hashed static assets (JS, CSS, images with content hashes in filenames) and no-cache for `index.html`.
4. THE Frontend_Container SHALL include an Nginx configuration that proxies POST requests matching `/analyze` to the Backend_Container at `http://backend:8000/analyze`, with a proxy read timeout of 120 seconds, enabling the frontend to communicate with the backend without CORS issues in production.
5. THE Frontend_Container SHALL expose port 80 for HTTP traffic.
6. IF the Backend_Container is unreachable when the Frontend_Container proxies a request to `/analyze`, THEN THE Frontend_Container SHALL return an HTTP 502 response to the client within 10 seconds.

---

### Requirement 6: Docker Compose Orchestration

**User Story:** As a developer, I want a single `docker-compose up` command to start both backend and frontend, so that I can run the full application stack locally without manual service management.

#### Acceptance Criteria

1. THE Docker_Compose file SHALL define two services: `backend` (built from `backend/Dockerfile`) and `frontend` (built from `frontend/Dockerfile`).
2. WHEN `docker-compose up` is executed, THE Docker_Compose SHALL build both service images if they do not already exist, and WHEN `docker-compose up --build` is executed, THE Docker_Compose SHALL rebuild both service images regardless of cache.
3. THE Docker_Compose SHALL map the Backend_Container port 8000 to host port 8000 for direct API access during development.
4. THE Docker_Compose SHALL map the Frontend_Container port 80 to host port 5173 for browser access during development.
5. THE Docker_Compose SHALL define a shared Docker network so that the Frontend_Container can reach the Backend_Container using the service hostname `backend`.
6. THE Docker_Compose SHALL configure the `frontend` service with a `depends_on` condition that waits for the `backend` service to report a healthy status via a health check before starting the frontend container.
7. THE Docker_Compose SHALL define a health check for the `backend` service that sends an HTTP request to `http://localhost:8000/` and considers the service healthy when it receives a response within 5 seconds, retrying up to 3 times at 10-second intervals.
8. IF `docker-compose up` is executed and either service image fails to build, THEN THE Docker_Compose SHALL exit with a non-zero status code and shall not start any services.
