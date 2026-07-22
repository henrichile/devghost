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

import json
import shutil
import subprocess
import tempfile
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from . import DevGhost_Parser

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
    """Clone a repository and return its architecture analysis as JSON."""

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

        # Run the analysis
        raw_bytes: bytes = DevGhost_Parser().analyze(tmp_dir)
        analysis_result: dict = json.loads(raw_bytes.decode("utf-8"))

        return analysis_result

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
