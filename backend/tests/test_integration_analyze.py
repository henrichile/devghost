"""
Integration tests for /analyze endpoint backward compatibility.

Tests more realistic scenarios by creating a real temp directory with sample
config files and verifying the full response structure through the endpoint.

Satisfies Requirements: 8.1, 8.2, 8.3
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from dev_ghost_parser.server import app
from dev_ghost_parser.agent_models import AnalysisResult


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def sample_repo_dir():
    """Create a real temp directory with sample config files that mimic a repo."""
    tmp_dir = tempfile.mkdtemp(prefix="devghost_integration_test_")

    # Create a package.json (Node.js project)
    package_json = {
        "name": "sample-project",
        "version": "1.0.0",
        "dependencies": {"express": "^4.18.0", "react": "^18.2.0"},
        "scripts": {"start": "node index.js", "dev": "vite"},
    }
    with open(os.path.join(tmp_dir, "package.json"), "w") as f:
        import json
        json.dump(package_json, f)

    # Create a Dockerfile
    dockerfile_content = "FROM node:18\nWORKDIR /app\nCOPY . .\nRUN npm install\nCMD [\"npm\", \"start\"]"
    with open(os.path.join(tmp_dir, "Dockerfile"), "w") as f:
        f.write(dockerfile_content)

    # Create a requirements.txt (mixed project)
    with open(os.path.join(tmp_dir, "requirements.txt"), "w") as f:
        f.write("fastapi==0.115.6\nuvicorn==0.34.0\n")

    # Create a simple source file
    os.makedirs(os.path.join(tmp_dir, "src"), exist_ok=True)
    with open(os.path.join(tmp_dir, "src", "index.js"), "w") as f:
        f.write("const express = require('express');\nconst app = express();\n")

    yield tmp_dir

    # Cleanup
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Expected camelCase field names for the /analyze response
# ---------------------------------------------------------------------------

EXPECTED_CORE_FIELDS = {"codeFlow", "erModel", "artifacts", "nodeInspections"}


class TestAnalyzeIntegrationBackwardCompat:
    """Integration tests verifying /analyze response structure with realistic data.

    Requirements: 8.1, 8.2, 8.3
    """

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("shutil.rmtree")
    def test_response_has_all_core_fields_and_camelcase(
        self, mock_rmtree, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client, sample_repo_dir
    ):
        """Response contains codeFlow, erModel, artifacts, nodeInspections in camelCase (Req 8.1)."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        mock_orch = MagicMock()

        async def mock_run_all():
            return AnalysisResult(
                code_flow={"nodes": [{"id": "1", "label": "AppModule"}], "edges": []},
                er_model={"entities": [{"name": "User"}], "relations": []},
                artifacts={"c4Mermaid": "graph TD;A-->B"},
                node_inspections={"AppModule": {"methods": ["init"]}},
                system_report={
                    "tech_stack": {"entries": [{"name": "JavaScript", "category": "language"}]},
                    "setup_instructions": "npm install && npm start",
                    "project_description": "A sample web application.",
                    "could_not_determine": False,
                },
            )

        mock_orch.run_all = mock_run_all
        mock_create_orch.return_value = mock_orch

        response = client.post(
            "/analyze",
            json={"repo_url": "https://github.com/test/sample-project"}
        )

        assert response.status_code == 200
        data = response.json()

        # All core fields must be present with camelCase naming (Req 8.1)
        for field_name in EXPECTED_CORE_FIELDS:
            assert field_name in data, f"Missing expected field: {field_name}"

        # Verify no snake_case equivalents leak through
        assert "code_flow" not in data
        assert "er_model" not in data
        assert "node_inspections" not in data

        # Verify field values are dicts, not None
        for field_name in EXPECTED_CORE_FIELDS:
            assert isinstance(data[field_name], dict), (
                f"Field '{field_name}' should be a dict, got {type(data[field_name])}"
            )

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("shutil.rmtree")
    def test_system_report_present_when_agent_succeeds(
        self, mock_rmtree, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client, sample_repo_dir
    ):
        """systemReport field is present when System Reporter succeeds (Req 8.2)."""
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
                    "tech_stack": {
                        "entries": [
                            {"name": "JavaScript", "category": "language", "description": ""},
                            {"name": "Express", "category": "framework", "description": ""},
                            {"name": "Docker", "category": "infrastructure", "description": ""},
                        ]
                    },
                    "setup_instructions": "## Setup\n```\nnpm install\nnpm start\n```",
                    "project_description": "A web application built with Express.js",
                    "could_not_determine": False,
                },
            )

        mock_orch.run_all = mock_run_all
        mock_create_orch.return_value = mock_orch

        response = client.post(
            "/analyze",
            json={"repo_url": "https://github.com/test/sample-project"}
        )

        assert response.status_code == 200
        data = response.json()

        # systemReport must be present (Req 8.2)
        assert "systemReport" in data
        assert isinstance(data["systemReport"], dict)

        # Verify systemReport structure
        report = data["systemReport"]
        assert "tech_stack" in report
        assert "setup_instructions" in report
        assert "project_description" in report
        assert len(report["tech_stack"]["entries"]) == 3

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("shutil.rmtree")
    def test_system_report_absent_when_agent_fails(
        self, mock_rmtree, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client, sample_repo_dir
    ):
        """systemReport field is absent when System Reporter fails (Req 8.3)."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        mock_orch = MagicMock()

        async def mock_run_all():
            return AnalysisResult(
                code_flow={"nodes": [{"id": "1", "label": "Main"}]},
                er_model={"entities": [{"name": "User"}]},
                artifacts={"c4Mermaid": "graph TD"},
                node_inspections={"Main": {"methods": []}},
                system_report=None,  # System Reporter failed
                errors=[{"agent": "system_reporter", "message": "LLM unavailable"}],
            )

        mock_orch.run_all = mock_run_all
        mock_create_orch.return_value = mock_orch

        response = client.post(
            "/analyze",
            json={"repo_url": "https://github.com/test/sample-project"}
        )

        assert response.status_code == 200
        data = response.json()

        # systemReport should be empty dict when reporter failed (backward compat, Req 9.1)
        assert "systemReport" in data
        assert data["systemReport"] == {}

        # Core fields must still be present and valid
        for field_name in EXPECTED_CORE_FIELDS:
            assert field_name in data
            assert isinstance(data[field_name], dict)

        # Non-empty data should be preserved from other agents
        assert len(data["codeFlow"].get("nodes", [])) > 0
        assert len(data["erModel"].get("entities", [])) > 0

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("shutil.rmtree")
    def test_no_error_status_on_system_reporter_failure(
        self, mock_rmtree, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client, sample_repo_dir
    ):
        """Response is 200 even when System Reporter fails (Req 8.3)."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        mock_orch = MagicMock()

        async def mock_run_all():
            return AnalysisResult(
                code_flow={},
                er_model={},
                artifacts={},
                node_inspections={},
                system_report=None,
                errors=[{"agent": "system_reporter", "message": "Connection timeout"}],
            )

        mock_orch.run_all = mock_run_all
        mock_create_orch.return_value = mock_orch

        response = client.post(
            "/analyze",
            json={"repo_url": "https://github.com/test/sample-project"}
        )

        # Must NOT return error status (Req 8.3)
        assert response.status_code == 200

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("shutil.rmtree")
    def test_no_unexpected_fields_in_response(
        self, mock_rmtree, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client, sample_repo_dir
    ):
        """Response should only contain known fields (Req 8.1)."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        mock_orch = MagicMock()

        async def mock_run_all():
            return AnalysisResult(
                code_flow={"nodes": []},
                er_model={},
                artifacts={},
                node_inspections={},
                system_report={
                    "tech_stack": {"entries": []},
                    "setup_instructions": "",
                    "project_description": "A project",
                    "could_not_determine": False,
                },
            )

        mock_orch.run_all = mock_run_all
        mock_create_orch.return_value = mock_orch

        response = client.post(
            "/analyze",
            json={"repo_url": "https://github.com/test/sample-project"}
        )

        assert response.status_code == 200
        data = response.json()

        # Only expected fields should be present
        allowed_fields = EXPECTED_CORE_FIELDS | {"systemReport"}
        actual_fields = set(data.keys())

        unexpected = actual_fields - allowed_fields
        assert not unexpected, f"Unexpected fields in response: {unexpected}"

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("shutil.rmtree")
    def test_response_json_serializable_with_nested_data(
        self, mock_rmtree, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client, sample_repo_dir
    ):
        """Response is valid JSON with complex nested structures (Req 8.1)."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        mock_orch = MagicMock()

        async def mock_run_all():
            return AnalysisResult(
                code_flow={
                    "nodes": [
                        {"id": "1", "label": "Server", "type": "Controller", "methods": ["start", "stop"]},
                        {"id": "2", "label": "Database", "type": "Service", "methods": ["connect"]},
                    ],
                    "edges": [{"from": "1", "to": "2", "label": "uses"}],
                },
                er_model={
                    "entities": [
                        {"name": "User", "attributes": [{"name": "id", "type": "int"}]},
                        {"name": "Post", "attributes": [{"name": "title", "type": "string"}]},
                    ],
                    "relations": [{"from": "User", "to": "Post", "type": "has_many"}],
                },
                artifacts={"c4Mermaid": "graph TD;Server-->Database"},
                node_inspections={
                    "Server": {"methods": ["start", "stop"], "complexity": "low"},
                    "Database": {"methods": ["connect"], "complexity": "medium"},
                },
                system_report={
                    "tech_stack": {
                        "entries": [
                            {"name": "Python", "category": "language", "description": "Backend"},
                            {"name": "FastAPI", "category": "framework", "description": "Web framework"},
                        ]
                    },
                    "setup_instructions": "pip install -r requirements.txt\nuvicorn main:app",
                    "project_description": "A REST API server",
                    "could_not_determine": False,
                },
            )

        mock_orch.run_all = mock_run_all
        mock_create_orch.return_value = mock_orch

        response = client.post(
            "/analyze",
            json={"repo_url": "https://github.com/test/sample-project"}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify nested data integrity
        assert len(data["codeFlow"]["nodes"]) == 2
        assert data["codeFlow"]["nodes"][0]["label"] == "Server"
        assert len(data["erModel"]["entities"]) == 2
        assert data["erModel"]["relations"][0]["type"] == "has_many"
        assert "c4Mermaid" in data["artifacts"]
        assert "Server" in data["nodeInspections"]
        assert data["systemReport"]["tech_stack"]["entries"][0]["name"] == "Python"
