"""
Backward compatibility unit tests for the sub-agent parallel analysis architecture.

Verifies that:
1. /analyze response JSON schema matches existing format (Req 9.1)
2. /analyze-stream SSE event types are unchanged (Req 9.2)
3. HTTP error codes (403, 404, 400, 500, 504) are correct (Req 9.3)
4. AnalyzeRequest validation accepts existing format (Req 9.4)

Satisfies Requirements: 9.1, 9.2, 9.3, 9.4
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from dev_ghost_parser.agent_models import (
    AgentEvent,
    AnalysisResult,
    ExecutionMetadata,
)
from dev_ghost_parser.event_bus import EventBus
from dev_ghost_parser.graph_orchestrator import (
    DependencyGraphOrchestrator,
    FoundationalPhaseError,
)
from dev_ghost_parser.dependency_graph import CyclicDependencyError
from dev_ghost_parser.server import AnalyzeRequest, app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Response schema test — /analyze returns expected JSON fields (Req 9.1)
# ---------------------------------------------------------------------------


class TestResponseSchema:
    """Verify run_pipeline() result maps to expected JSON: codeFlow, erModel, artifacts, nodeInspections, systemReport."""

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_compat")
    @patch("shutil.rmtree")
    def test_response_has_all_required_fields(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Response must contain codeFlow, erModel, artifacts, nodeInspections, systemReport (Req 9.1)."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        # Create a mock orchestrator that returns known data from run_pipeline
        mock_orch = MagicMock()

        async def mock_run_pipeline():
            return AnalysisResult(
                code_flow={"nodes": [{"id": "1", "label": "App"}], "edges": []},
                er_model={"entities": [{"name": "User"}], "relations": []},
                artifacts={"c4Mermaid": "graph TD;A-->B"},
                audit={"issues": ["unused import"]},
                system_report={"tech_stack": {"entries": []}, "setup_instructions": "npm install"},
                node_inspections=None,
                metadata=ExecutionMetadata(
                    total_duration_ms=5000,
                    agent_durations={"ast_analyzer": 1200},
                    retry_counts={},
                    failed_agents=[],
                    partial_results=[],
                ),
            )

        mock_orch.run_all = mock_run_pipeline
        mock_create_orch.return_value = mock_orch

        response = client.post("/analyze", json={"repo_url": "https://github.com/user/repo"})

        assert response.status_code == 200
        data = response.json()

        # All 5 required fields must be present (Req 9.1)
        assert "codeFlow" in data
        assert "erModel" in data
        assert "artifacts" in data
        assert "nodeInspections" in data
        assert "systemReport" in data

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_compat")
    @patch("shutil.rmtree")
    def test_response_values_match_orchestrator_output(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Response field values must accurately reflect orchestrator AnalysisResult data."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        mock_orch = MagicMock()

        async def mock_run_pipeline():
            return AnalysisResult(
                code_flow={"nodes": [{"id": "n1", "label": "Controller"}]},
                er_model={"entities": [{"name": "Order", "attributes": []}]},
                artifacts={"readme": "# Project"},
                audit={"findings": ["perf issue"]},
                system_report={"tech_stack": {"entries": [{"name": "Python", "category": "language"}]}},
                node_inspections={"inspections": ["i1"]},
            )

        mock_orch.run_all = mock_run_pipeline
        mock_create_orch.return_value = mock_orch

        response = client.post("/analyze", json={"repo_url": "https://github.com/user/repo"})

        assert response.status_code == 200
        data = response.json()

        assert data["codeFlow"] == {"nodes": [{"id": "n1", "label": "Controller"}]}
        assert data["erModel"] == {"entities": [{"name": "Order", "attributes": []}]}
        assert data["artifacts"] == {"readme": "# Project"}
        # nodeInspections uses node_inspections when available, falls back to audit
        assert data["nodeInspections"] == {"inspections": ["i1"]}
        assert data["systemReport"]["tech_stack"]["entries"][0]["name"] == "Python"

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_compat")
    @patch("shutil.rmtree")
    def test_null_fields_become_empty_dicts(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """When agents return None, fields should be empty dicts (not null) for backward compat."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        mock_orch = MagicMock()

        async def mock_run_pipeline():
            return AnalysisResult(
                code_flow=None,
                er_model=None,
                artifacts=None,
                audit=None,
                system_report=None,
                node_inspections=None,
            )

        mock_orch.run_all = mock_run_pipeline
        mock_create_orch.return_value = mock_orch

        response = client.post("/analyze", json={"repo_url": "https://github.com/user/repo"})

        assert response.status_code == 200
        data = response.json()

        assert data["codeFlow"] == {}
        assert data["erModel"] == {}
        assert data["artifacts"] == {}
        assert data["nodeInspections"] == {}
        assert data["systemReport"] == {}


# ---------------------------------------------------------------------------
# 2. SSE event types test — /analyze-stream emits correct event types (Req 9.2)
# ---------------------------------------------------------------------------


class TestSSEEventTypes:
    """Verify event_bus supports all required SSE event types: agent_start, agent_progress, agent_complete, agent_error, analysis_complete, analysis_error."""

    @pytest.mark.asyncio
    async def test_event_bus_emits_agent_start(self):
        """EventBus.emit_agent_start produces type='agent_start' (Req 9.2)."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        bus = EventBus(queue)

        event = await bus.emit_agent_start("ast_analyzer", "Analyzing AST")

        assert event.type == "agent_start"
        assert event.agent == "ast_analyzer"
        assert event.message == "Analyzing AST"
        assert event.sequence >= 1

    @pytest.mark.asyncio
    async def test_event_bus_emits_agent_progress(self):
        """EventBus.emit_agent_progress produces type='agent_progress' (Req 9.2)."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        bus = EventBus(queue)

        event = await bus.emit_agent_progress("code_auditor", "Processing files", progress_pct=50.0)

        assert event.type == "agent_progress"
        assert event.agent == "code_auditor"
        assert event.progress_pct == 50.0

    @pytest.mark.asyncio
    async def test_event_bus_emits_agent_complete(self):
        """EventBus.emit_agent_complete produces type='agent_complete' (Req 9.2)."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        bus = EventBus(queue)

        event = await bus.emit_agent_complete("er_extractor", duration_ms=1500)

        assert event.type == "agent_complete"
        assert event.agent == "er_extractor"
        assert event.duration_ms == 1500

    @pytest.mark.asyncio
    async def test_event_bus_emits_agent_error(self):
        """EventBus.emit_agent_error produces type='agent_error' (Req 9.2)."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        bus = EventBus(queue)

        event = await bus.emit_agent_error("doc_generator", error="Timeout", retry_count=2)

        assert event.type == "agent_error"
        assert event.agent == "doc_generator"
        assert event.error == "Timeout"
        assert event.retry_count == 2

    @pytest.mark.asyncio
    async def test_event_bus_emits_analysis_complete(self):
        """EventBus.emit_analysis_complete produces type='analysis_complete' (Req 9.2)."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        bus = EventBus(queue)

        result_data = {"codeFlow": {}, "erModel": {}}
        event = await bus.emit_analysis_complete("ast_analyzer", result=result_data)

        assert event.type == "analysis_complete"
        assert event.result == result_data

    @pytest.mark.asyncio
    async def test_event_bus_emits_analysis_error(self):
        """EventBus.emit_analysis_error produces type='analysis_error' (Req 9.2)."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        bus = EventBus(queue)

        event = await bus.emit_analysis_error("ast_analyzer", error="Pipeline failed")

        assert event.type == "analysis_error"
        assert event.error == "Pipeline failed"

    @pytest.mark.asyncio
    async def test_all_event_types_supported(self):
        """EventBus supports all 6 required event types without errors (Req 9.2)."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        bus = EventBus(queue)

        events = []
        events.append(await bus.emit_agent_start("ast_analyzer", "Starting"))
        events.append(await bus.emit_agent_progress("ast_analyzer", "Working", progress_pct=25.0))
        events.append(await bus.emit_agent_complete("ast_analyzer", duration_ms=100))
        events.append(await bus.emit_agent_error("ast_analyzer", error="oops", retry_count=1))
        events.append(await bus.emit_analysis_complete("ast_analyzer", result={}))
        events.append(await bus.emit_analysis_error("ast_analyzer", error="fatal"))

        expected_types = {
            "agent_start", "agent_progress", "agent_complete",
            "agent_error", "analysis_complete", "analysis_error",
        }
        actual_types = {e.type for e in events}
        assert actual_types == expected_types


# ---------------------------------------------------------------------------
# 3. HTTP error codes test (Req 9.3)
# ---------------------------------------------------------------------------


class TestHTTPErrorCodes:
    """Verify HTTP error codes are consistent with existing error handling."""

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    def test_403_private_repo(self, mock_check, client):
        """Private/auth-required repos return 403 (Req 9.3)."""
        from fastapi import HTTPException

        mock_check.side_effect = HTTPException(
            status_code=403,
            detail="Este repositorio parece ser privado o requiere autenticación.",
        )

        response = client.post("/analyze", json={"repo_url": "https://github.com/private/repo"})
        assert response.status_code == 403

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    def test_404_repo_not_found(self, mock_check, client):
        """Non-existent repos return 404 (Req 9.3)."""
        from fastapi import HTTPException

        mock_check.side_effect = HTTPException(
            status_code=404,
            detail="Repositorio no encontrado.",
        )

        response = client.post("/analyze", json={"repo_url": "https://github.com/no/exist"})
        assert response.status_code == 404

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_compat_err")
    @patch("shutil.rmtree")
    def test_400_clone_failure(self, mock_rmtree, mock_mkdtemp, mock_subprocess, mock_check, client):
        """Clone failure returns 400 (Req 9.3)."""
        mock_check.return_value = None
        mock_subprocess.return_value = MagicMock(
            returncode=128,
            stderr="fatal: repository not accessible",
        )

        response = client.post("/analyze", json={"repo_url": "https://github.com/bad/clone"})
        assert response.status_code == 400

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_compat_err")
    @patch("shutil.rmtree")
    def test_500_foundational_phase_error(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """FoundationalPhaseError returns 500 (Req 9.3)."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        mock_orch = MagicMock()

        async def mock_run_pipeline():
            raise FoundationalPhaseError("AST analysis failed after all retries")

        mock_orch.run_all = mock_run_pipeline
        mock_create_orch.return_value = mock_orch

        response = client.post("/analyze", json={"repo_url": "https://github.com/user/repo"})
        assert response.status_code == 500
        assert "fase fundacional" in response.json()["detail"].lower() or "AST" in response.json()["detail"]

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_compat_err")
    @patch("shutil.rmtree")
    def test_500_cyclic_dependency_error(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """CyclicDependencyError returns 500 (Req 9.3)."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        mock_orch = MagicMock()

        async def mock_run_pipeline():
            raise CyclicDependencyError("Cycle detected in agent graph")

        mock_orch.run_all = mock_run_pipeline
        mock_create_orch.return_value = mock_orch

        response = client.post("/analyze", json={"repo_url": "https://github.com/user/repo"})
        assert response.status_code == 500
        assert "cíclic" in response.json()["detail"].lower() or "cicl" in response.json()["detail"].lower()

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_compat_err")
    @patch("shutil.rmtree")
    def test_504_pipeline_timeout(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Pipeline timeout returns 504 (Req 9.3).

        The server detects timeout via a pipeline error entry in the
        AnalysisResult.errors list with agent='pipeline' and 'timeout' in the error.
        """
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        mock_orch = MagicMock()

        async def mock_run_pipeline():
            return AnalysisResult(
                code_flow={},
                er_model={},
                artifacts={},
                system_report={},
                node_inspections={},
                errors=[{"agent": "pipeline", "error": "Global timeout exceeded"}],
            )

        mock_orch.run_all = mock_run_pipeline
        mock_create_orch.return_value = mock_orch

        response = client.post("/analyze", json={"repo_url": "https://github.com/user/repo"})
        assert response.status_code == 504

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_compat_err")
    @patch("shutil.rmtree")
    def test_504_clone_timeout(self, mock_rmtree, mock_mkdtemp, mock_subprocess, mock_check, client):
        """Clone timeout returns 504 (Req 9.3)."""
        import subprocess as sp

        mock_check.return_value = None
        mock_subprocess.side_effect = sp.TimeoutExpired(cmd="git clone", timeout=120)

        response = client.post("/analyze", json={"repo_url": "https://github.com/user/repo"})
        assert response.status_code == 504

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_compat_err")
    @patch("shutil.rmtree")
    def test_500_generic_internal_error(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Generic internal errors return 500 (Req 9.3)."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        mock_orch = MagicMock()

        async def mock_run_pipeline():
            raise RuntimeError("Unexpected internal error")

        mock_orch.run_all = mock_run_pipeline
        mock_create_orch.return_value = mock_orch

        response = client.post("/analyze", json={"repo_url": "https://github.com/user/repo"})
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# 4. AnalyzeRequest validation test (Req 9.4)
# ---------------------------------------------------------------------------


class TestAnalyzeRequestValidation:
    """Verify AnalyzeRequest Pydantic model accepts existing format and rejects invalid inputs."""

    def test_accepts_valid_https_url(self):
        """Accepts standard https GitHub URL (Req 9.4)."""
        req = AnalyzeRequest(repo_url="https://github.com/user/repo")
        assert req.repo_url == "https://github.com/user/repo"

    def test_accepts_valid_http_url(self):
        """Accepts http URL (Req 9.4)."""
        req = AnalyzeRequest(repo_url="http://github.com/user/repo")
        assert req.repo_url == "http://github.com/user/repo"

    def test_accepts_url_with_trailing_spaces(self):
        """Strips whitespace from URL (Req 9.4)."""
        req = AnalyzeRequest(repo_url="  https://github.com/user/repo  ")
        assert req.repo_url == "https://github.com/user/repo"

    def test_accepts_gitlab_url(self):
        """Accepts non-GitHub URLs like GitLab (Req 9.4)."""
        req = AnalyzeRequest(repo_url="https://gitlab.com/group/project")
        assert req.repo_url == "https://gitlab.com/group/project"

    def test_rejects_empty_url(self):
        """Rejects empty string (Req 9.4)."""
        with pytest.raises(Exception):
            AnalyzeRequest(repo_url="")

    def test_rejects_whitespace_only_url(self):
        """Rejects whitespace-only string (Req 9.4)."""
        with pytest.raises(Exception):
            AnalyzeRequest(repo_url="   ")

    def test_rejects_non_http_protocol(self):
        """Rejects non-http/https URLs like git:// or ssh:// (Req 9.4)."""
        with pytest.raises(Exception):
            AnalyzeRequest(repo_url="git@github.com:user/repo.git")

    def test_rejects_ftp_protocol(self):
        """Rejects ftp:// URLs (Req 9.4)."""
        with pytest.raises(Exception):
            AnalyzeRequest(repo_url="ftp://example.com/repo")

    def test_accepts_url_with_dot_git_suffix(self):
        """Accepts URLs ending in .git (Req 9.4)."""
        req = AnalyzeRequest(repo_url="https://github.com/user/repo.git")
        assert req.repo_url == "https://github.com/user/repo.git"

    def test_endpoint_rejects_missing_repo_url(self, client):
        """Endpoint returns 422 when repo_url is missing from request body (Req 9.4)."""
        response = client.post("/analyze", json={})
        assert response.status_code == 422

    def test_endpoint_rejects_invalid_url_format(self, client):
        """Endpoint returns 422 when repo_url has invalid format (Req 9.4)."""
        response = client.post("/analyze", json={"repo_url": "not-a-url"})
        assert response.status_code == 422
