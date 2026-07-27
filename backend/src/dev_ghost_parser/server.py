"""
DevGhost-Parser HTTP server — FastAPI + uvicorn.

Exposes a POST /analyze endpoint that:
1. Receives {"repo_url": "https://github.com/..."}.
2. Clones the repository (shallow, depth 1) into a temporary directory.
3. Runs DevGhost_Parser().analyze(temp_dir).
4. Cleans up the temporary directory.
5. Returns the JSON analysis result to the client.

CORS is enabled for all origins so a React frontend can consume the API.

Run with:
    uvicorn dev_ghost_parser.server:app --reload
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from starlette.responses import StreamingResponse

from . import DevGhost_Parser
from .llm_client import LLM_Client
from .artifacts_generator import Artifacts_Generator
from .sse_utils import serialize_event_to_sse
from .agents import get_all_agents
from .agent_models import AgentEvent, AnalysisResult
from .graph_orchestrator import (
    DependencyGraphOrchestrator,
    FoundationalPhaseError,
)
from .dependency_graph import CyclicDependencyError


def create_orchestrator_with_all_agents(
    repo_path: str,
    llm_client: "LLM_Client",
    event_queue: "asyncio.Queue[AgentEvent]",
    **kwargs,
) -> DependencyGraphOrchestrator:
    """Create a DependencyGraphOrchestrator with all 5 agents pre-registered.

    This is a convenience function that replaces the old flat-parallel
    orchestrator creation. It creates a DAG-based orchestrator with all
    agents registered and ready to run.

    Args:
        repo_path: Path to the cloned repository.
        llm_client: LLM client for agents that need language model access.
        event_queue: Async queue for streaming agent events.
        **kwargs: Additional keyword arguments passed to DependencyGraphOrchestrator
                  (e.g., max_concurrency, global_timeout_seconds).

    Returns:
        A fully configured DependencyGraphOrchestrator with all agents registered.
    """
    orch = DependencyGraphOrchestrator(
        repo_path=repo_path,
        llm_client=llm_client,
        event_queue=event_queue,
        **kwargs,
    )
    for agent in get_all_agents():
        orch.register_agent(agent)
    return orch

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="DevGhost-Parser API",
    description="Static architecture analysis for Git repositories.",
    version="0.1.0",
)

# Enable CORS for any frontend origin (React dev server, production, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    repo_url: str

    @field_validator("repo_url")
    @classmethod
    def validate_repo_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("La URL del repositorio no puede estar vacía")
        if not (v.startswith("https://") or v.startswith("http://")):
            raise ValueError("La URL del repositorio debe comenzar con http:// o https://")
        return v


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/")
async def health() -> dict[str, str]:
    """Health check endpoint used by Docker Compose."""
    return {"status": "ok"}


def _check_repo_accessibility(repo_url: str) -> None:
    """Pre-check whether a repository is accessible before cloning.

    Uses `git ls-remote` which is fast and doesn't download any data.
    Raises HTTPException with a user-friendly message if the repo is
    private, doesn't exist, or is unreachable.
    """
    try:
        # GIT_TERMINAL_PROMPT=0 prevents git from hanging waiting for credentials
        env = {"GIT_TERMINAL_PROMPT": "0"}
        result = subprocess.run(
            ["git", "ls-remote", "--exit-code", repo_url],
            capture_output=True,
            text=True,
            timeout=15,
            env={**__import__("os").environ, **env},
        )

        if result.returncode != 0:
            stderr = result.stderr.strip().lower()

            # Private repo or requires authentication
            if "could not read username" in stderr or "authentication" in stderr:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Este repositorio parece ser privado o requiere autenticación. "
                        "DevGhost-Parser solo soporta repositorios públicos."
                    ),
                )

            # Repository not found (404 from GitHub/GitLab)
            if "not found" in stderr or "repository" in stderr and "not exist" in stderr:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"Repositorio no encontrado: '{repo_url}'. "
                        "Verifica que la URL sea correcta y que el repositorio exista."
                    ),
                )

            # Generic access error
            raise HTTPException(
                status_code=400,
                detail=f"No se puede acceder al repositorio: {result.stderr.strip()}",
            )

    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504,
            detail="La verificación de accesibilidad del repositorio expiró. El servidor puede estar inaccesible.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error al verificar la accesibilidad del repositorio: {exc}",
        )


@app.post("/analyze")
async def analyze(request: AnalyzeRequest) -> Any:
    """Clone a repository and return its architecture analysis as JSON.

    Uses the DependencyGraphOrchestrator to run the AST foundational phase
    first, then executes remaining agents in parallel respecting the
    dependency graph. Maps the structured AnalysisResult to the existing
    response schema.

    Backward compatible: existing fields (codeFlow, erModel, artifacts,
    nodeInspections, systemReport) remain unchanged.

    Satisfies Requirements: 9.1, 9.2, 9.3, 9.4
    """

    # Pre-check: verify the repo is public and accessible before cloning
    _check_repo_accessibility(request.repo_url)

    tmp_dir = tempfile.mkdtemp(prefix="devghost_")

    try:
        # Shallow clone (only latest commit, no history)
        result = subprocess.run(
            ["git", "clone", "--depth", "1", request.repo_url, tmp_dir],
            capture_output=True,
            text=True,
            timeout=120,
            env={**__import__("os").environ, "GIT_TERMINAL_PROMPT": "0"},
        )

        if result.returncode != 0:
            stderr = result.stderr.strip().lower()

            if "could not read username" in stderr or "authentication" in stderr:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Este repositorio parece ser privado o requiere autenticación. "
                        "DevGhost-Parser solo soporta repositorios públicos."
                    ),
                )

            if "not found" in stderr:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"Repositorio no encontrado: '{request.repo_url}'. "
                        "Verifica que la URL sea correcta y que el repositorio exista."
                    ),
                )

            raise HTTPException(
                status_code=400,
                detail=f"Error al clonar el repositorio: {result.stderr.strip()}",
            )

        # Run the analysis using the DependencyGraphOrchestrator (DAG-based)
        llm_client = LLM_Client()
        event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()

        orch = create_orchestrator_with_all_agents(
            repo_path=tmp_dir,
            llm_client=llm_client,
            event_queue=event_queue,
            global_timeout_seconds=600.0,
        )

        try:
            analysis = await orch.run_all()
        except FoundationalPhaseError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"El análisis falló en la fase fundacional (AST): {exc}",
            )
        except CyclicDependencyError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Error interno de dependencias cíclicas: {exc}",
            )

        # Check if the pipeline timed out (partial results returned)
        # The orchestrator returns partial results with a timeout error entry
        has_timeout_error = any(
            e.get("agent") == "pipeline" and "timeout" in e.get("error", "").lower()
            for e in (analysis.errors or [])
        )
        if has_timeout_error:
            # Return HTTP 504 with partial results indication
            raise HTTPException(
                status_code=504,
                detail="El análisis del pipeline expiró después de 300 segundos.",
            )

        # Build backward-compatible response
        response: dict[str, Any] = {}

        # Map AnalysisResult fields to existing response schema
        response["codeFlow"] = analysis.code_flow if analysis.code_flow else {}
        response["erModel"] = analysis.er_model if analysis.er_model else {}

        # Map doc_generator artifacts keys to frontend camelCase format
        raw_artifacts = analysis.artifacts if analysis.artifacts else {}
        response["artifacts"] = {
            "c4Mermaid": raw_artifacts.get("c4_diagram"),
            "dbDictionary": raw_artifacts.get("db_dictionary"),
            "adrDocument": raw_artifacts.get("adr"),
            "rbacMatrix": raw_artifacts.get("rbac_matrix"),
            "testPlan": raw_artifacts.get("test_plan"),
            "useCases": raw_artifacts.get("use_cases"),
            "useCasesDoc": raw_artifacts.get("use_cases_doc"),
        } if raw_artifacts else {}
        # code_auditor data goes to audit field in AnalysisResult but the API
        # exposes it as nodeInspections. Use node_inspections first (may be
        # populated directly), falling back to audit (from code_auditor agent).
        response["nodeInspections"] = (
            analysis.node_inspections
            if analysis.node_inspections
            else (analysis.audit if analysis.audit else {})
        )

        # Add systemReport (Req 9.1) — always present for backward compat
        if analysis.system_report is not None:
            response["systemReport"] = analysis.system_report
        else:
            response["systemReport"] = {}

        return response

    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504,
            detail="La clonación del repositorio expiró después de 120 segundos.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"El análisis falló: {exc}",
        )
    finally:
        # Always clean up the temp directory
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# SSE Streaming endpoint
# ---------------------------------------------------------------------------

# Overall timeout for the streaming analysis (300 seconds)
_STREAM_TIMEOUT_SECONDS = 300


def _now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 with millisecond precision."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _make_sse_event(type: str, agent: str, message: str, **kwargs) -> str:
    """Create an SSE-formatted event string."""
    event_data: dict[str, Any] = {
        "type": type,
        "agent": agent,
        "message": message,
        "timestamp": _now_iso(),
    }
    event_data.update(kwargs)
    return f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"


@app.post("/analyze-stream")
async def analyze_stream(request: AnalyzeRequest) -> StreamingResponse:
    """Stream analysis events as SSE while running the full analysis pipeline.

    Uses the DependencyGraphOrchestrator for DAG-based execution and emits
    real-time SSE progress events via the event_queue.

    Satisfies Requirements: 9.1, 9.2, 9.3, 9.4
    """
    # Validate request — returns HTTP error before stream begins
    _check_repo_accessibility(request.repo_url)

    # Clone repository to temp directory
    tmp_dir = tempfile.mkdtemp(prefix="devghost_stream_")

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", request.repo_url, tmp_dir],
            capture_output=True,
            text=True,
            timeout=120,
            env={**__import__("os").environ, "GIT_TERMINAL_PROMPT": "0"},
        )

        if result.returncode != 0:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            stderr = result.stderr.strip().lower()

            if "could not read username" in stderr or "authentication" in stderr:
                raise HTTPException(
                    status_code=403,
                    detail="Este repositorio parece ser privado o requiere autenticación.",
                )
            if "not found" in stderr:
                raise HTTPException(
                    status_code=404,
                    detail=f"Repositorio no encontrado: '{request.repo_url}'.",
                )
            raise HTTPException(
                status_code=400,
                detail=f"Error al clonar: {result.stderr.strip()}",
            )

    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=504, detail="Clonación expiró (120s).")
    except Exception as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Error: {exc}")

    async def event_generator() -> AsyncGenerator[str, None]:
        """Run the full analysis pipeline emitting SSE events from the orchestrator."""
        try:
            llm_client = LLM_Client()
            event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()

            orch = create_orchestrator_with_all_agents(
                repo_path=tmp_dir,
                llm_client=llm_client,
                event_queue=event_queue,
                global_timeout_seconds=_STREAM_TIMEOUT_SECONDS,
            )

            # Run the pipeline in a background task so we can consume events
            pipeline_task = asyncio.create_task(orch.run_all())

            # Consume events from the queue until the pipeline completes
            while not pipeline_task.done():
                try:
                    event = await asyncio.wait_for(
                        event_queue.get(),
                        timeout=1.0,
                    )
                    if event is None:
                        break
                    yield serialize_event_to_sse(event)
                except asyncio.TimeoutError:
                    # No event available yet, check if pipeline is done
                    continue

            # Drain any remaining events in the queue
            while not event_queue.empty():
                event = event_queue.get_nowait()
                if event is None:
                    continue
                yield serialize_event_to_sse(event)

            # Get the pipeline result
            try:
                analysis = pipeline_task.result()
            except FoundationalPhaseError as exc:
                yield _make_sse_event(
                    "analysis_error", "ast_analyzer",
                    f"Error fatal en fase fundacional: {exc}",
                    error=str(exc)[:1024],
                )
                return
            except CyclicDependencyError as exc:
                yield _make_sse_event(
                    "analysis_error", "ast_analyzer",
                    f"Error de dependencias cíclicas: {exc}",
                    error=str(exc)[:1024],
                )
                return
            except Exception as exc:
                yield _make_sse_event(
                    "analysis_error", "ast_analyzer",
                    f"Error fatal: {exc}",
                    error=str(exc)[:1024],
                )
                return

            # Build the final result matching the expected JSON schema
            analysis_result: dict[str, Any] = {}
            analysis_result["codeFlow"] = analysis.code_flow if analysis.code_flow else {}
            analysis_result["erModel"] = analysis.er_model if analysis.er_model else {}

            # Map doc_generator artifacts keys to frontend camelCase format
            raw_artifacts = analysis.artifacts if analysis.artifacts else {}
            analysis_result["artifacts"] = {
                "c4Mermaid": raw_artifacts.get("c4_diagram"),
                "dbDictionary": raw_artifacts.get("db_dictionary"),
                "adrDocument": raw_artifacts.get("adr"),
                "rbacMatrix": raw_artifacts.get("rbac_matrix"),
                "testPlan": raw_artifacts.get("test_plan"),
                "useCases": raw_artifacts.get("use_cases"),
                "useCasesDoc": raw_artifacts.get("use_cases_doc"),
            } if raw_artifacts else {}
            # code_auditor data goes to audit field in AnalysisResult but the API
            # exposes it as nodeInspections. Use node_inspections first, fall back to audit.
            analysis_result["nodeInspections"] = (
                analysis.node_inspections
                if analysis.node_inspections
                else (analysis.audit if analysis.audit else {})
            )
            if analysis.system_report is not None:
                analysis_result["systemReport"] = analysis.system_report
            else:
                analysis_result["systemReport"] = {}

            # Include errors if any occurred during the pipeline
            if analysis.errors:
                analysis_result["errors"] = analysis.errors

            # Emit analysis_complete with the full result
            yield _make_sse_event(
                "analysis_complete", "ast_analyzer",
                "Análisis completo",
                result=analysis_result,
            )

        except Exception as exc:
            yield _make_sse_event(
                "analysis_error", "ast_analyzer",
                f"Error fatal: {exc}",
                error=str(exc)[:1024],
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )


# ---------------------------------------------------------------------------
# Artifacts endpoint
# ---------------------------------------------------------------------------


class ArtifactsRequest(BaseModel):
    repo_url: str

    @field_validator("repo_url")
    @classmethod
    def validate_repo_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("La URL del repositorio no puede estar vacía")
        if not (v.startswith("https://") or v.startswith("http://")):
            raise ValueError("La URL del repositorio debe comenzar con http:// o https://")
        return v


@app.post("/api/artifacts")
async def generate_artifacts(request: ArtifactsRequest) -> Any:
    """Clone a repository, analyze it, and generate documentation artifacts using LLM."""

    _check_repo_accessibility(request.repo_url)

    tmp_dir = tempfile.mkdtemp(prefix="devghost_artifacts_")

    try:
        # Shallow clone
        result = subprocess.run(
            ["git", "clone", "--depth", "1", request.repo_url, tmp_dir],
            capture_output=True,
            text=True,
            timeout=120,
            env={**__import__("os").environ, "GIT_TERMINAL_PROMPT": "0"},
        )

        if result.returncode != 0:
            raise HTTPException(
                status_code=400,
                detail=f"Error al clonar el repositorio: {result.stderr.strip()}",
            )

        # Run the analysis to get code flow and ER data
        raw_bytes: bytes = DevGhost_Parser().analyze(tmp_dir)
        analysis_result: dict = json.loads(raw_bytes.decode("utf-8"))

        # Extract code_flow and er_result from analysis
        from .models import CodeFlowResult, ERResult, Node, Entity, Attribute, Relation

        code_flow = None
        er_result = None

        if analysis_result.get("codeFlow"):
            cf = analysis_result["codeFlow"]
            nodes = [
                Node(
                    id=n.get("id", ""),
                    label=n.get("label", ""),
                    type=n.get("type", "Utility"),
                    description=n.get("description", ""),
                    method_names=n.get("methods", []),
                )
                for n in cf.get("nodes", [])
            ]
            code_flow = CodeFlowResult(nodes=nodes)

        if analysis_result.get("erModel"):
            er = analysis_result["erModel"]
            entities = [
                Entity(
                    name=e.get("name", ""),
                    attributes=[
                        Attribute(name=a.get("name", ""), type=a.get("type", ""))
                        for a in e.get("attributes", [])
                    ],
                    primaryKey=e.get("primaryKey", "id"),
                )
                for e in er.get("entities", [])
            ]
            relations = []
            for r in er.get("relations", []):
                relations.append(
                    Relation(
                        from_entity=r.get("from", ""),
                        to_entity=r.get("to", ""),
                        type=r.get("type", "unknown"),
                        foreignKey=r.get("foreignKey", ""),
                    )
                )
            er_result = ERResult(entities=entities, relations=relations)

        # Generate artifacts with LLM
        llm_client = LLM_Client()
        generator = Artifacts_Generator(llm_client=llm_client)

        c4_diagram = generator.generate_c4_diagram(code_flow, er_result)
        db_dictionary = generator.generate_db_dictionary(er_result)
        adr = generator.generate_adr(code_flow, er_result)
        rbac_matrix = generator.generate_rbac_matrix(code_flow)
        test_plan = generator.generate_test_plan(code_flow, tmp_dir)

        return {
            "c4Mermaid": c4_diagram,
            "dbDictionary": db_dictionary,
            "adrDocument": adr,
            "rbacMatrix": rbac_matrix,
            "testPlan": test_plan,
        }

    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504,
            detail="La clonación del repositorio expiró.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"La generación de artefactos falló: {exc}",
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Method descriptions endpoint
# ---------------------------------------------------------------------------


class DescribeMethodsRequest(BaseModel):
    component_name: str
    component_type: str
    methods: list[str]


@app.post("/api/describe-methods")
async def describe_methods(request: DescribeMethodsRequest) -> Any:
    """Use LLM to generate short descriptions for each method of a component."""
    llm_client = LLM_Client()

    if not llm_client.available or not request.methods:
        # Fallback: return empty descriptions
        return {
            "descriptions": {m: "" for m in request.methods}
        }

    methods_str = ", ".join(request.methods[:20])
    system_prompt = (
        "Para cada metodo/funcion listado, genera una descripcion breve (max 15 palabras) "
        "en español de lo que probablemente hace, basandote en su nombre y el contexto del componente. "
        "Responde SOLO en formato: nombre_metodo: descripcion\n"
        "Un metodo por linea. Sin numeracion, sin bullets, sin explicaciones adicionales."
    )
    user_prompt = (
        f"Componente: {request.component_name} (tipo: {request.component_type})\n"
        f"Metodos: {methods_str}"
    )

    result = llm_client.complete(system_prompt, user_prompt)

    descriptions: dict[str, str] = {}
    if result:
        for line in result.strip().split("\n"):
            if ":" in line:
                parts = line.split(":", 1)
                method_name = parts[0].strip()
                desc = parts[1].strip()
                descriptions[method_name] = desc

    # Fill any missing methods with empty string
    for m in request.methods:
        if m not in descriptions:
            descriptions[m] = ""

    return {"descriptions": descriptions}


# ---------------------------------------------------------------------------
# Code audit endpoint
# ---------------------------------------------------------------------------


class AuditRequest(BaseModel):
    component_name: str
    component_type: str
    methods: list[str]
    description: str = ""


@app.post("/api/audit")
async def audit_code(request: AuditRequest) -> Any:
    """Use LLM to audit code quality and suggest improvements for a component."""
    llm_client = LLM_Client()

    if not llm_client.available or not request.methods:
        return {"audit": None}

    methods_str = ", ".join(request.methods[:20])
    system_prompt = (
        "Eres un auditor de codigo senior. Analiza el componente y sus metodos para identificar:\n\n"
        "## Calidad General\n"
        "Puntuacion de 1-10 y justificacion breve.\n\n"
        "## Buenas Practicas Detectadas\n"
        "Lista lo que esta bien implementado.\n\n"
        "## Oportunidades de Mejora\n"
        "Para cada problema encontrado indica:\n"
        "- Severidad (critica/media/baja)\n"
        "- Descripcion del problema\n"
        "- Sugerencia de solucion con ejemplo de codigo\n\n"
        "## Riesgos de Seguridad\n"
        "Posibles vulnerabilidades basadas en los nombres de funciones y el tipo de componente.\n\n"
        "## Refactorizaciones Sugeridas\n"
        "Patrones de diseno o mejoras estructurales recomendadas.\n\n"
        "Responde en español, formato Markdown. Se conciso pero actionable."
    )
    user_prompt = (
        f"Componente: {request.component_name}\n"
        f"Tipo: {request.component_type}\n"
        f"Descripcion: {request.description or 'no disponible'}\n"
        f"Metodos: {methods_str}"
    )

    result = llm_client.complete(system_prompt, user_prompt)
    return {"audit": result}


# ---------------------------------------------------------------------------
# Method deep analysis endpoint
# ---------------------------------------------------------------------------


class AnalyzeMethodRequest(BaseModel):
    method_name: str
    component_name: str
    component_type: str
    all_methods: list[str] = []
    description: str = ""
    dependencies: list[str] = []
    dependents: list[str] = []
    source_code: str = ""


@app.post("/api/analyze-method")
async def analyze_method(request: AnalyzeMethodRequest) -> Any:
    """Use LLM to generate a deep analysis of a specific method/function."""
    llm_client = LLM_Client()

    if not llm_client.available:
        return {"analysis": None}

    deps_str = ", ".join(request.dependencies[:10]) if request.dependencies else "ninguna detectada"
    dependents_str = ", ".join(request.dependents[:10]) if request.dependents else "ninguno detectado"
    siblings_str = ", ".join(request.all_methods[:15]) if request.all_methods else ""
    code_section = f"\n\nCODIGO FUENTE REAL de la funcion (MUESTRA ESTE CODIGO TAL CUAL):\n```\n{request.source_code}\n```" if request.source_code else "\n\nCODIGO FUENTE: No disponible (no se pudo extraer del repositorio)"

    system_prompt = (
        "Eres un analista de código senior con experiencia en arquitectura de software, "
        "patrones de diseño y seguridad. Genera un análisis EXHAUSTIVO y PROFESIONAL.\n\n"
        "REGLAS DE FORMATO ESTRICTAS:\n"
        "- Responde en español con Markdown para headings/texto\n"
        "- Para TODAS las tablas usa HTML: <table><thead><tr><th>...</th></tr></thead><tbody><tr><td>...</td></tr></tbody></table>\n"
        "- Para diagramas usa EXCLUSIVAMENTE bloques ```mermaid con sintaxis Mermaid válida\n"
        "- NUNCA uses plantUML (@startuml, @enduml). SIEMPRE Mermaid.\n"
        "- NUNCA uses tablas markdown (| col |). SIEMPRE tablas HTML.\n"
        "- NUNCA uses comentarios // para explicar. Usa texto Markdown normal.\n"
        "- Separa SIEMPRE las secciones con saltos de línea\n\n"
        "REGLA CRÍTICA SOBRE CÓDIGO:\n"
        "- Si recibes 'CODIGO FUENTE REAL', muéstralo en un bloque ```typescript (o el lenguaje correcto).\n"
        "- NO inventes ni modifiques el código real.\n"
        "- Si NO hay código real, indica: 'Código fuente no disponible.'\n\n"
        "ESTRUCTURA OBLIGATORIA:\n\n"
        "## Análisis de `nombre_función`\n\n"
        "### Código Fuente\n"
        "Bloque de código con el lenguaje correcto.\n\n"
        "### Propósito y Responsabilidad\n"
        "QUÉ hace, POR QUÉ existe, patrón de diseño que implementa.\n\n"
        "### Parámetros y Retorno\n"
        "Tabla HTML con: Parámetro, Tipo, Descripción, Validaciones.\n\n"
        "### Flujo de Ejecución\n"
        "Tabla HTML con: Paso, Acción, Componentes, Fallos posibles.\n"
        "Luego un diagrama Mermaid de secuencia:\n"
        "```mermaid\n"
        "sequenceDiagram\n"
        "    participant Cliente\n"
        "    participant Servicio\n"
        "    Cliente->>Servicio: llamada()\n"
        "    Servicio-->>Cliente: respuesta\n"
        "```\n\n"
        "### Análisis de Calidad\n"
        "Tabla HTML: Criterio, Nota 1-10, Justificación.\n\n"
        "### Vulnerabilidades y Riesgos\n"
        "Tabla HTML: Severidad, Tipo, Descripción, Mitigación.\n\n"
        "### Mejoras Recomendadas\n"
        "Lista priorizada con código corregido de ejemplo.\n\n"
        "SÉ EXHAUSTIVO y BIEN FORMATEADO."
    )

    user_prompt = (
        f"Funcion a analizar: `{request.method_name}`\n"
        f"Componente: {request.component_name} (tipo: {request.component_type})\n"
        f"Descripcion del componente: {request.description or 'no disponible'}\n"
        f"Otros metodos del mismo componente: {siblings_str}\n"
        f"Dependencias del componente (usa): {deps_str}\n"
        f"Consumidores del componente (usado por): {dependents_str}"
        f"{code_section}"
    )

    result = llm_client.complete(system_prompt, user_prompt)
    return {"analysis": result}
