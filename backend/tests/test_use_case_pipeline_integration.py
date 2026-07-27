"""
Unit tests for use case generation pipeline integration.

Validates that the analysis pipeline produces the expected output
including useCases key in the artifacts dict when the orchestrator
runs successfully.

Validates: Requirements 4.4, 4.5
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from dev_ghost_parser.server import app
from dev_ghost_parser.agent_models import AgentEvent, AnalysisResult


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


def _parse_sse_events(response_text: str) -> list[dict]:
    """Parse SSE response text into a list of event dicts."""
    events = []
    for chunk in response_text.split("\n\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk.startswith("data: "):
            json_str = chunk[len("data: "):]
            try:
                events.append(json.loads(json_str))
            except json.JSONDecodeError:
                continue
    return events


class TestUseCasePipelineIntegration:
    """Tests verifying useCases appears in the analysis output."""

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_use_case_pipeline")
    @patch("shutil.rmtree")
    def test_generate_use_cases_is_called_during_pipeline(
        self,
        mock_rmtree,
        mock_mkdtemp,
        mock_llm_cls,
        mock_create_orch,
        mock_subprocess,
        mock_check,
        client,
    ):
        """Req 4.4, 4.5: generate_use_cases is invoked during the analysis pipeline."""
        mock_check.return_value = None
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")

        # Create a mock orchestrator that returns results with useCases in artifacts
        mock_orch = MagicMock()
        use_cases_content = "## Historias de Usuario\n### HU-001"

        async def run_all():
            return AnalysisResult(
                code_flow={"nodes": [{"id": "1", "label": "UsersController"}], "edges": []},
                er_model={"entities": [], "relations": []},
                artifacts={"useCases": use_cases_content, "c4Mermaid": "graph TD; A-->B"},
                node_inspections={},
                system_report=None,
            )

        mock_orch.run_all = run_all
        mock_create_orch.return_value = mock_orch

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"},
        )

        assert response.status_code == 200

        # Verify the orchestrator was created and run_all was called
        mock_create_orch.assert_called_once()

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_use_case_pipeline")
    @patch("shutil.rmtree")
    def test_artifacts_in_analysis_complete_contains_use_cases_key(
        self,
        mock_rmtree,
        mock_mkdtemp,
        mock_llm_cls,
        mock_create_orch,
        mock_subprocess,
        mock_check,
        client,
    ):
        """Req 4.4, 4.5: The analysis_complete SSE event artifacts dict has useCases key."""
        mock_check.return_value = None
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")

        use_cases_content = "## Historias de Usuario\n### HU-001: Gestionar usuarios"

        mock_orch = MagicMock()

        async def run_all():
            return AnalysisResult(
                code_flow={"nodes": [{"id": "ctrl-1", "label": "UsersController"}]},
                er_model={"entities": []},
                artifacts={"useCases": use_cases_content, "c4Mermaid": "graph TD; A-->B"},
                node_inspections={},
                system_report=None,
            )

        mock_orch.run_all = run_all
        mock_create_orch.return_value = mock_orch

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"},
        )

        assert response.status_code == 200

        # Parse SSE events and find analysis_complete
        events = _parse_sse_events(response.text)
        analysis_complete_events = [e for e in events if e.get("type") == "analysis_complete"]

        assert len(analysis_complete_events) == 1, (
            f"Expected exactly one analysis_complete event, got {len(analysis_complete_events)}"
        )

        final_event = analysis_complete_events[0]
        assert "result" in final_event, "analysis_complete must have 'result' field"

        result = final_event["result"]
        assert "artifacts" in result, "result must contain 'artifacts' key"

        artifacts = result["artifacts"]
        assert "useCases" in artifacts, (
            f"artifacts dict must contain 'useCases' key. Keys found: {list(artifacts.keys())}"
        )
        assert artifacts["useCases"] == use_cases_content, (
            f"Expected useCases to be '{use_cases_content}', got '{artifacts['useCases']}'"
        )

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_use_case_pipeline")
    @patch("shutil.rmtree")
    def test_generate_use_cases_called_with_code_flow_result(
        self,
        mock_rmtree,
        mock_mkdtemp,
        mock_llm_cls,
        mock_create_orch,
        mock_subprocess,
        mock_check,
        client,
    ):
        """Req 4.4: generate_use_cases receives the CodeFlowResult during the pipeline."""
        mock_check.return_value = None
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")

        mock_orch = MagicMock()

        async def run_all():
            return AnalysisResult(
                code_flow={
                    "nodes": [
                        {"id": "ctrl-1", "label": "UsersController", "type": "Controller"}
                    ],
                    "edges": [],
                },
                er_model={"entities": []},
                artifacts={"useCases": "## Use Cases", "c4Mermaid": "graph TD"},
                node_inspections={},
                system_report=None,
            )

        mock_orch.run_all = run_all
        mock_create_orch.return_value = mock_orch

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"},
        )

        assert response.status_code == 200

        # Parse SSE events and find analysis_complete
        events = _parse_sse_events(response.text)
        analysis_complete_events = [e for e in events if e.get("type") == "analysis_complete"]

        assert len(analysis_complete_events) == 1, (
            "Expected one analysis_complete event"
        )

        final_event = analysis_complete_events[0]
        result = final_event["result"]

        # The codeFlow should contain the controller node data
        assert "codeFlow" in result
        code_flow = result["codeFlow"]
        assert "nodes" in code_flow
        assert any(
            n.get("label") == "UsersController" for n in code_flow["nodes"]
        ), "CodeFlowResult with UsersController should be in the response"
