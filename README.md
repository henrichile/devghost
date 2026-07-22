# DevGhost-Parser

Static architecture analysis system for software codebases. Given a repository URL, DevGhost-Parser clones it, analyzes the code structure using tree-sitter, and produces:

- **Code Flow Graph** — directed graph of architectural nodes (services, controllers, routes) and their dependency edges
- **ER Database Model** — entities, attributes, and relationships extracted from ORM patterns
- **Executive Summary** — plain-text narrative of the codebase architecture

## Monorepo Structure

```
.
├── backend/          # Python FastAPI analysis engine
│   ├── src/          # Source code (dev_ghost_parser package)
│   ├── tests/        # Unit, integration, and property tests
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/         # React + TypeScript SPA (Vite)
│   ├── src/          # Components, services, types
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
├── docker-compose.yml
├── .gitignore
└── README.md
```

## Backend

The backend is a Python FastAPI service that exposes a `POST /analyze` endpoint. It accepts a repository URL, clones it, and runs static analysis using tree-sitter grammars for multiple languages (JavaScript, TypeScript, Python, PHP, Ruby, Go, Rust, Java, C#).

### Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Run

```bash
cd backend
uvicorn dev_ghost_parser.server:app --reload --host 0.0.0.0 --port 8000
```

### Test

```bash
cd backend
pytest
```

## Frontend

The frontend is a React single-page application built with Vite and TypeScript. It provides an interactive UI with:

- Repository URL input and analysis trigger
- Tabbed graph views (Code Flow and ER diagrams) using `@xyflow/react`
- Audio narration of the executive summary via Web Speech Synthesis API

### Setup

```bash
cd frontend
npm install
```

### Development

```bash
cd frontend
npm run dev
```

### Build

```bash
cd frontend
npm run build
```

### Test

```bash
cd frontend
npx vitest --run
```

## Docker

Both services are containerized and orchestrated with Docker Compose.

### Run the full stack

```bash
docker-compose up --build
```

This starts:
- **Backend** on `http://localhost:8000` (FastAPI + Uvicorn)
- **Frontend** on `http://localhost:5173` (Nginx serving static assets, proxying `/analyze` to backend)

### Stop

```bash
docker-compose down
```

## API

### POST /analyze

Analyzes a repository and returns structured architecture data.

**Request:**
```json
{
  "repo_url": "https://github.com/user/repo"
}
```

**Response:**
```json
{
  "codeFlow": {
    "nodes": [{ "id": "...", "label": "UserService", "type": "Service" }],
    "edges": [{ "source": "...", "target": "...", "relation": "imports" }]
  },
  "erModel": {
    "entities": [{ "name": "User", "attributes": [...], "primaryKey": "id" }],
    "relations": [{ "from": "User", "to": "Post", "type": "one-to-many", "foreignKey": "user_id" }]
  },
  "summary": "This codebase is a REST API with 3 services..."
}
```

## License

Private project.
