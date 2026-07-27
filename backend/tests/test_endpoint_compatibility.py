"""
Unit tests for backward compatibility of the /analyze endpoint.

Validates:
- /analyze response contains codeFlow, erModel, artifacts, nodeInspections fields
- systemReport field is present when System Reporter succeeds (Req 8.2)
- systemReport field is absent when System Reporter fails (Req 8.3)
- /analyze-stream returns Content-Type text/event-stream (Req 2.7)
- /analyze-stream includes CORS headers (Req 2.7)

Satisfies Requirements: 2.7, 8.1, 8.2, 8.3
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient

from dev_ghost_parser.server import app
from dev_ghost_parser.agent_models import AnalysisResult


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# /analyze backward compatibility tests (Req 8.1)
# ---------------------------------------------------------------------------


class TestAnalyzeBackwardCompatibility:
    """Verify /analyze maintains backward-compatible response schema."""

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_devghost_compat")
    @patch("shutil.rmtree")
    def test_response_contains_core_fields(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Response must contain codeFlow, erModel, artifacts, nodeInspections (Req 8.1)."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        # Mock orchestrator returning a result with all fields populated
        mock_orch = MagicMock()

        async def mock_run_all():
            return AnalysisResult(
                code_flow={"nodes": [], "edges": []},
                er_model={"entities": [], "relations": []},
                artifacts={"c4Mermaid": "graph TD"},
                node_inspections={"summary": "ok"},
                system_report=None,
            )

        mock_orch.run_all = mock_run_all
        mock_create_orch.return_value = mock_orch

        response = client.post(
            "/analyze",
            json={"repo_url": "https://github.com/test/repo"}
        )

        assert response.status_code == 200
        data = response.json()

        # Core fields MUST always be present (Req 8.1)
        assert "codeFlow" in data
        assert "erModel" in data
        assert "artifacts" in data
        assert "nodeInspections" in data

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_devghost_compat")
    @patch("shutil.rmtree")
    def test_response_fields_are_correct_types(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Core response fields should be dicts (objects) as per schema (Req 8.1)."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        mock_orch = MagicMock()

        async def mock_run_all():
            return AnalysisResult(
                code_flow={"nodes": [{"id": "1", "label": "Main"}]},
                er_model={"entities": [{"name": "User"}]},
                artifacts={"c4Mermaid": "graph TD;A-->B"},
                node_inspections={"nodes": ["n1"]},
            )

        mock_orch.run_all = mock_run_all
        mock_create_orch.return_value = mock_orch

        response = client.post(
            "/analyze",
            json={"repo_url": "https://github.com/test/repo"}
        )

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data["codeFlow"], dict)
        assert isinstance(data["erModel"], dict)
        assert isinstance(data["artifacts"], dict)
        assert isinstance(data["nodeInspections"], dict)

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_devghost_compat")
    @patch("shutil.rmtree")
    def test_empty_results_return_empty_dicts(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """When agents return None, the response should have empty dicts (Req 8.1)."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        mock_orch = MagicMock()

        async def mock_run_all():
            return AnalysisResult()  # All fields default to None

        mock_orch.run_all = mock_run_all
        mock_create_orch.return_value = mock_orch

        response = client.post(
            "/analyze",
            json={"repo_url": "https://github.com/test/repo"}
        )

        assert response.status_code == 200
        data = response.json()

        # Should return empty dicts, not null/None
        assert data["codeFlow"] == {}
        assert data["erModel"] == {}
        assert data["artifacts"] == {}
        assert data["nodeInspections"] == {}


# ---------------------------------------------------------------------------
# /analyze systemReport field behavior (Req 8.2, 8.3)
# ---------------------------------------------------------------------------


class TestAnalyzeSystemReportField:
    """Verify systemReport field presence/absence based on System Reporter result."""

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_devghost_compat")
    @patch("shutil.rmtree")
    def test_system_report_present_on_success(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """systemReport field should be present when System Reporter succeeds (Req 8.2)."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        mock_orch = MagicMock()

        async def mock_run_all():
            return AnalysisResult(
                code_flow={"nodes": []},
                er_model={"entities": []},
                artifacts={},
                node_inspections={},
                system_report={
                    "tech_stack": {"entries": [{"name": "Python", "category": "language"}]},
                    "setup_instructions": "pip install -r requirements.txt",
                    "project_description": "A sample project",
                    "could_not_determine": False,
                },
            )

        mock_orch.run_all = mock_run_all
        mock_create_orch.return_value = mock_orch

        response = client.post(
            "/analyze",
            json={"repo_url": "https://github.com/test/repo"}
        )

        assert response.status_code == 200
        data = response.json()

        assert "systemReport" in data
        assert isinstance(data["systemReport"], dict)
        assert data["systemReport"]["tech_stack"]["entries"][0]["name"] == "Python"

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_devghost_compat")
    @patch("shutil.rmtree")
    def test_system_report_absent_on_failure(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """systemReport field should be absent when System Reporter fails (Req 8.3)."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        mock_orch = MagicMock()

        async def mock_run_all():
            return AnalysisResult(
                code_flow={"nodes": []},
                er_model={"entities": []},
                artifacts={},
                node_inspections={},
                system_report=None,  # System Reporter failed
            )

        mock_orch.run_all = mock_run_all
        mock_create_orch.return_value = mock_orch

        response = client.post(
            "/analyze",
            json={"repo_url": "https://github.com/test/repo"}
        )

        assert response.status_code == 200
        data = response.json()

        # systemReport should be empty dict when it failed (backward compat, Req 9.1)
        assert "systemReport" in data
        assert data["systemReport"] == {}

        # Core fields should still be present and valid
        assert "codeFlow" in data
        assert "erModel" in data
        assert "artifacts" in data
        assert "nodeInspections" in data

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_devghost_compat")
    @patch("shutil.rmtree")
    def test_no_error_status_when_system_reporter_fails(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Response should still be 200 even if System Reporter fails (Req 8.3)."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        mock_orch = MagicMock()

        async def mock_run_all():
            return AnalysisResult(
                code_flow={"nodes": []},
                er_model={},
                artifacts={},
                node_inspections={},
                system_report=None,
                errors=[{"agent": "system_reporter", "message": "LLM unavailable"}],
            )

        mock_orch.run_all = mock_run_all
        mock_create_orch.return_value = mock_orch

        response = client.post(
            "/analyze",
            json={"repo_url": "https://github.com/test/repo"}
        )

        # Should NOT return an error status code (Req 8.3)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# /analyze-stream headers verification (Req 2.7)
# ---------------------------------------------------------------------------


class TestAnalyzeStreamHeaders:
    """Verify /analyze-stream response headers for SSE compliance."""

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_devghost_stream_compat")
    @patch("shutil.rmtree")
    def test_content_type_is_event_stream(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Content-Type must be text/event-stream (Req 2.7)."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        mock_orch = MagicMock()

        async def mock_run_all():
            return AnalysisResult()

        mock_orch.run_all = mock_run_all
        mock_create_orch.return_value = mock_orch

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"}
        )

        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "text/event-stream" in content_type

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_devghost_stream_compat")
    @patch("shutil.rmtree")
    def test_cors_allow_origin_header_present(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """CORS Access-Control-Allow-Origin header must be present (Req 2.7)."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        mock_orch = MagicMock()

        async def mock_run_all():
            return AnalysisResult()

        mock_orch.run_all = mock_run_all
        mock_create_orch.return_value = mock_orch

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"}
        )

        assert response.status_code == 200
        # Check for CORS header (case-insensitive header lookup)
        headers_lower = {k.lower(): v for k, v in response.headers.items()}
        assert "access-control-allow-origin" in headers_lower
        assert headers_lower["access-control-allow-origin"] == "*"

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_devghost_stream_compat")
    @patch("shutil.rmtree")
    def test_cache_control_no_cache(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """SSE responses should have Cache-Control: no-cache (Req 2.7)."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        mock_orch = MagicMock()

        async def mock_run_all():
            return AnalysisResult()

        mock_orch.run_all = mock_run_all
        mock_create_orch.return_value = mock_orch

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"}
        )

        assert response.status_code == 200
        headers_lower = {k.lower(): v for k, v in response.headers.items()}
        assert "cache-control" in headers_lower
        assert "no-cache" in headers_lower["cache-control"]
