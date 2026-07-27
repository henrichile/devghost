<p align="center">
  <img src="logo.svg" alt="DevGhost Parser" width="120" />
</p>

<h1 align="center">DevGhost Parser</h1>

<p align="center">
  <strong>Análisis estático de arquitectura para repositorios de código</strong><br/>
  Clona, analiza y documenta la estructura de cualquier codebase automáticamente.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue?logo=python" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/react-19-61dafb?logo=react" alt="React 19" />
  <img src="https://img.shields.io/badge/fastapi-0.115-009688?logo=fastapi" alt="FastAPI" />
  <img src="https://img.shields.io/badge/docker-compose-2496ED?logo=docker" alt="Docker" />
</p>

---

## ¿Qué es DevGhost Parser?

DevGhost Parser es un sistema de análisis estático de arquitectura que, dado un repositorio Git, produce automáticamente:

| Artefacto | Descripción |
|-----------|-------------|
| 🏗️ **Diagrama C4** | Diagrama de componentes en Mermaid.js |
| 📖 **Diccionario ER** | Entidades, atributos y relaciones extraídas de patrones ORM |
| 📝 **ADR** | Architecture Decision Record identificando patrones |
| 🔐 **Matriz RBAC** | Análisis de seguridad y permisos |
| 🧪 **Plan de Testing** | Guía de testing con sugerencias de mejora |
| 👤 **Casos de Uso** | Historias de usuario y casos de uso formales |
| 📊 **Grafo Code Flow** | Grafo dirigido de nodos arquitectónicos y dependencias |
| 🗄️ **Modelo ER** | Diagrama entidad-relación interactivo |

## Arquitectura

```
┌─────────────────────────────────────────────────────┐
│                    Frontend (React)                   │
│  React 19 · TypeScript · Vite · TailwindCSS          │
│  @xyflow/react · Mermaid.js · Zustand                │
└──────────────────────┬──────────────────────────────┘
                       │ SSE / REST
┌──────────────────────┴──────────────────────────────┐
│                   Backend (Python)                    │
│  FastAPI · tree-sitter · LLM (OpenAI-compatible)     │
│  Agentes: CodeFlow · ER · Summary · Artifacts        │
└─────────────────────────────────────────────────────┘
```

## Estructura del Monorepo

```
.
├── backend/              # Motor de análisis Python FastAPI
│   ├── src/              # Paquete dev_ghost_parser
│   │   ├── server.py         # Endpoints REST + SSE
│   │   ├── orchestrator.py   # Orquestador de agentes
│   │   ├── artifacts_generator.py  # Generador de documentación
│   │   ├── llm_client.py     # Cliente LLM (OpenAI-compatible)
│   │   └── models.py         # Modelos de datos compartidos
│   ├── tests/            # Tests unitarios, integración y property-based
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/             # SPA React + TypeScript (Vite)
│   ├── src/
│   │   ├── components/       # DocumentationPanel, MermaidDiagram, etc.
│   │   ├── services/         # API client
│   │   └── types.ts          # Interfaces TypeScript
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── logo.svg
└── README.md
```

## Inicio Rápido

### Con Docker (recomendado)

```bash
docker-compose up --build
```

Esto levanta:
- **Backend** en `http://localhost:8000`
- **Frontend** en `http://localhost:5173`

### Desarrollo Local

#### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn dev_ghost_parser.server:app --reload --host 0.0.0.0 --port 8000
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

## API

### POST /analyze-stream

Analiza un repositorio mediante Server-Sent Events (SSE) con progreso en tiempo real.

**Request:**
```json
{
  "repo_url": "https://github.com/user/repo"
}
```

**Eventos SSE:**
```
data: {"type": "agent_start", "agent": "code_flow", ...}
data: {"type": "agent_progress", "agent": "code_flow", "message": "Analizando..."}
data: {"type": "agent_complete", "agent": "code_flow", ...}
data: {"type": "analysis_complete", "result": { "codeFlow": {...}, "erModel": {...}, "artifacts": {...} }}
```

**Respuesta final (dentro del evento `analysis_complete`):**
```json
{
  "codeFlow": {
    "nodes": [{ "id": "...", "label": "UserService", "type": "Service", "method_names": [...] }],
    "edges": [{ "source": "...", "target": "...", "relation": "imports" }]
  },
  "erModel": {
    "entities": [{ "name": "User", "attributes": [...], "primaryKey": "id" }],
    "relations": [{ "from_entity": "User", "to_entity": "Post", "type": "one-to-many", "foreignKey": "user_id" }]
  },
  "artifacts": {
    "c4Mermaid": "flowchart TD ...",
    "dbDictionary": "## Diccionario ...",
    "adrDocument": "## ADR-001 ...",
    "rbacMatrix": "## Matriz RBAC ...",
    "testPlan": "## Plan de Testing ...",
    "useCases": "## Historias de Usuario ..."
  }
}
```

## Testing

### Backend (pytest + Hypothesis)

```bash
cd backend
pytest                    # Todos los tests
pytest tests/ -v          # Con detalle
pytest -k "property"      # Solo property-based tests
```

### Frontend (Vitest + Testing Library)

```bash
cd frontend
npm run test              # Todos los tests
npx vitest run --reporter=verbose  # Con detalle
```

## Variables de Entorno

Crea un archivo `backend/.env`:

```env
OPENAI_API_KEY=sk-...          # Clave API para generación de artefactos
OPENAI_BASE_URL=               # URL base (opcional, para APIs compatibles)
OPENAI_MODEL=gpt-4o-mini       # Modelo a usar (opcional)
```

## Tecnologías

| Capa | Stack |
|------|-------|
| **Backend** | Python 3.11+, FastAPI, tree-sitter, Hypothesis |
| **Frontend** | React 19, TypeScript, Vite, TailwindCSS, @xyflow/react |
| **Infra** | Docker, Docker Compose, Nginx |
| **IA** | OpenAI API (o compatible), prompt engineering en español |

---

## Librería `dev-ghost-parser` (Python)

> 🚀 **Creada desde cero para esta hackaton.** Esta librería no existía previamente — fue diseñada, implementada y testeada completamente durante el evento. No se reutilizó ninguna librería existente de análisis arquitectónico; todo el pipeline de parsing AST, clasificación de nodos, extracción de relaciones y generación de documentación fue construido desde cero como parte de este proyecto.

El corazón del proyecto es una librería Python publicable como paquete que realiza análisis estático de arquitectura (AST) sobre repositorios de código. Se puede usar de forma programática o a través del servidor FastAPI.

### Uso Programático

```python
from dev_ghost_parser import DevGhost_Parser

parser = DevGhost_Parser()
result: bytes = parser.analyze("/path/to/codebase")
# result es JSON UTF-8 válido (RFC 8259, sin BOM)
```

### Arquitectura Interna

La librería sigue un patrón de orquestación con subsistemas independientes:

```
DevGhost_Parser.analyze(path)
    ├── Validación (4 checks: existencia, permisos, directorio)
    ├── Code_Flow_Analyzer    → CodeFlowResult (nodos + edges)
    ├── ER_Extractor          → ERResult (entidades + relaciones)
    ├── Summary_Generator     → Resumen ejecutivo en texto plano
    └── Output_Serializer     → JSON RFC 8259
```

### Módulos Principales

| Módulo | Responsabilidad |
|--------|----------------|
| `Code_Flow_Analyzer` | Recorre el directorio con `os.walk`, parsea cada archivo con tree-sitter, clasifica nodos arquitectónicos (Controller, Service, Route, Middleware, Repository, Utility, Config) y genera edges de dependencia a partir de imports |
| `ER_Extractor` | Extrae entidades, atributos y relaciones desde patrones ORM: **Eloquent** (PHP), **SQLAlchemy** (Python), **Prisma** (TypeScript), y archivos **SQL** puros (CREATE TABLE/ALTER TABLE) |
| `Description_Generator` | Genera descripciones en español para cada nodo. Usa LLM cuando está disponible (≤90 chars); fallback heurístico basado en nombres de métodos e imports (≤120 chars) |
| `Summary_Generator` | Produce un resumen ejecutivo de 3-4 oraciones en texto plano, sin markdown ni identificadores técnicos |
| `Artifacts_Generator` | Genera documentación arquitectónica (C4, ADR, RBAC, Testing, Casos de Uso) invocando al LLM con prompts especializados |
| `LLM_Client` | Cliente OpenAI-compatible que lee configuración de variables de entorno |
| `Output_Serializer` | Serializa todos los resultados en JSON UTF-8 conforme a RFC 8259 |

### Análisis AST con tree-sitter

El `Code_Flow_Analyzer` utiliza **tree-sitter** para parsear código fuente en 9 lenguajes, extrayendo:

- **Nombres de clases** — detecta la clase principal de cada archivo
- **Métodos públicos** — extrae hasta 15 métodos por archivo, filtrados por visibilidad
- **Imports/dependencias** — parsea sentencias de importación específicas por lenguaje para construir edges

#### Grammars tree-sitter incluidos

| Lenguaje | Paquete |
|----------|---------|
| JavaScript | `tree-sitter-javascript` |
| TypeScript | `tree-sitter-typescript` |
| Python | `tree-sitter-python` |
| PHP | `tree-sitter-php` |
| Ruby | `tree-sitter-ruby` |
| Go | `tree-sitter-go` |
| Rust | `tree-sitter-rust` |
| Java | `tree-sitter-java` |
| C# | `tree-sitter-c-sharp` |

#### Clasificación de Nodos

Cada archivo se clasifica en un `NodeType` basándose en convenciones de nomenclatura:

```
*Controller* / *Ctrl*      → Controller
*Service* / *Svc*          → Service
*Route* / *Router*         → Route
*Middleware* / *Guard*     → Middleware
*Repository* / *Repo*      → Repository
*Config* / *Settings*      → Config
(todo lo demás)            → Utility
```

#### Modelo de Datos de Salida

```python
@dataclass
class Node:
    id: str              # SHA-1 del path relativo (estable)
    label: str           # Nombre de la clase o archivo
    type: NodeType       # "Controller" | "Service" | "Route" | ...
    description: str     # ≤120 chars, en español
    method_names: list[str]  # Métodos extraídos (máx 15)

@dataclass
class Edge:
    source: str          # ID del nodo origen
    target: str          # ID del nodo destino
    relation: str        # "imports" | "calls" | "depends_on"

@dataclass
class CodeFlowResult:
    nodes: list[Node]
    edges: list[Edge]    # Integridad referencial garantizada
    errors: list[AnalysisError]
```

### Extractor ER

Soporta múltiples ORMs y formatos de schema:

| Fuente | Detección |
|--------|-----------|
| **Eloquent (PHP)** | Modelos que extienden `Model`, `$fillable`, `$casts`, métodos de relación (`hasMany`, `belongsTo`, etc.) |
| **SQLAlchemy (Python)** | Clases con `Base`, `Column()`, `relationship()`, `ForeignKey()` |
| **Prisma (TypeScript)** | Archivos `.prisma` con bloques `model`, `@relation`, tipos de campo |
| **SQL puro** | `CREATE TABLE`, `ALTER TABLE ... ADD FOREIGN KEY`, tipos de columna |

### Sistema Multi-Agente (SSE Pipeline)

Para el endpoint `/analyze-stream`, la librería emplea un orquestador de agentes concurrentes:

| Agente | Función |
|--------|---------|
| `ASTAnalyzerAgent` | Ejecuta Code_Flow_Analyzer |
| `ERExtractorAgent` | Ejecuta ER_Extractor |
| `DocGeneratorAgent` | Ejecuta Artifacts_Generator (C4, ADR, RBAC, Testing, Casos de Uso) |
| `SystemReporterAgent` | Genera el resumen ejecutivo |
| `CodeAuditorAgent` | Auditoría de calidad de código |

Los agentes se ejecutan concurrentemente con tolerancia a fallos: si un agente falla, los demás continúan y el error se reporta en la respuesta final.

### Manejo de Errores

La librería sigue un principio de **nunca propagar excepciones**:
- Errores de validación → JSON con `errors[]`
- Errores de subsistema → `SubsystemError` serializado en la respuesta
- Archivos ilegibles → `AnalysisError` por archivo (non-fatal)
- Resultados parciales se entregan siempre que sea posible

### Dependencias

```toml
[dependencies]
tree-sitter = "0.24.0"
tree-sitter-javascript = "0.23.1"
tree-sitter-typescript = "0.23.2"
tree-sitter-python = "0.23.6"
tree-sitter-php = "0.23.4"
tree-sitter-ruby = "0.23.1"
tree-sitter-go = "0.23.4"
tree-sitter-rust = "0.23.2"
tree-sitter-java = "0.23.5"
tree-sitter-c-sharp = "0.23.1"
fastapi = "0.115.6"
uvicorn = "0.34.0"
openai = ">=1.0.0,<2"
python-dotenv = ">=1.0.0,<2"

[dev-dependencies]
pytest = "8.3.4"
hypothesis = "6.123.1"
pytest-asyncio = ">=0.23.0"
```

---

## Lenguajes Soportados

El análisis estático soporta repositorios en:

JavaScript · TypeScript · Python · PHP · Ruby · Go · Rust · Java · C#

## Licencia

Proyecto privado.
