"""
Unit tests for the POST /analyze-stream endpoint.

Validates:
- Correct content-type (text/event-stream)
- CORS headers present
- Request validation returns HTTP errors before stream
- SSE format compliance

Satisfies Requirements: 2.1, 2.7, 2.8, 2.9
"""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from dev_ghost_parser.server import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class TestAnalyzeStreamValidation:
    """Test request validation — errors returned before stream begins (Req 2.9)."""

    def test_missing_repo_url_returns_422(self, client):
        """Empty body should return 422 Unprocessable Entity."""
        response = client.post("/analyze-stream", json={})
        assert response.status_code == 422

    def test_empty_repo_url_returns_422(self, client):
        """Empty string repo_url should return 422."""
        response = client.post("/analyze-stream", json={"repo_url": ""})
        assert response.status_code == 422

    def test_invalid_scheme_returns_422(self, client):
        """Non-http(s) URL should return 422."""
        response = client.post("/analyze-stream", json={"repo_url": "ftp://example.com/repo"})
        assert response.status_code == 422

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    def test_inaccessible_repo_returns_http_error(self, mock_check, client):
        """Inaccessible repo should return HTTP error, not a stream."""
        from fastapi import HTTPException
        mock_check.side_effect = HTTPException(status_code=404, detail="Not found")
        
        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/nonexistent/repo"}
        )
        assert response.status_code == 404


class TestAnalyzeStreamResponse:
    """Test response format and headers (Req 2.7)."""

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_devghost_stream_xxx")
    @patch("shutil.rmtree")
    def test_response_content_type_is_event_stream(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch, 
        mock_subprocess, mock_check, client
    ):
        """Response should have content-type text/event-stream (Req 2.7)."""
        import asyncio
        from dev_ghost_parser.agent_models import AnalysisResult

        # Mock successful git clone
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        # Mock orchestrator that completes immediately
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
        assert "text/event-stream" in response.headers.get("content-type", "")

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_devghost_stream_xxx")
    @patch("shutil.rmtree")
    def test_response_has_cors_headers(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Response should include CORS headers (Req 2.7)."""
        import asyncio
        from dev_ghost_parser.agent_models import AnalysisResult

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
        # CORS headers come from middleware + explicit response headers
        assert "access-control-allow-origin" in response.headers or \
               "Access-Control-Allow-Origin" in response.headers.get("access-control-allow-origin", "*")


class TestAnalyzeStreamSSEFormat:
    """Test SSE event format (Req 2.8)."""

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_devghost_stream_xxx")
    @patch("shutil.rmtree")
    def test_events_are_sse_formatted(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Events should be formatted as `data: {json}\\n\\n` (Req 2.8)."""
        import asyncio
        from dev_ghost_parser.agent_models import AgentEvent, AnalysisResult

        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_check.return_value = None

        # Create mock orchestrator that emits events via the queue
        async def mock_run_all_with_events(orch):
            """Simulate orchestrator putting events on the queue."""
            queue = orch._event_queue
            event = AgentEvent(
                type="agent_start",
                agent="ast_analyzer",
                message="Starting AST analysis",
                timestamp="2024-01-15T10:30:00.123Z",
            )
            await queue.put(event)
            await queue.put(None)  # Sentinel
            return AnalysisResult()

        # We need to properly mock the orchestrator
        mock_orch_instance = MagicMock()
        mock_orch_instance._event_queue = None  # Will be set by endpoint

        def create_orch_side_effect(repo_path, llm_client, event_queue, **kwargs):
            """Capture the event queue and return mock orchestrator."""
            from unittest.mock import AsyncMock
            
            mock_inst = MagicMock()
            mock_inst._event_queue = event_queue
            
            async def run_all():
                await event_queue.put(AgentEvent(
                    type="agent_start",
                    agent="ast_analyzer",
                    message="Starting AST analysis",
                    timestamp="2024-01-15T10:30:00.123Z",
                ))
                await event_queue.put(None)
                return AnalysisResult()
            
            mock_inst.run_all = run_all
            return mock_inst

        mock_create_orch.side_effect = create_orch_side_effect

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"}
        )

        assert response.status_code == 200
        content = response.text

        # Each event should be prefixed with "data: " and end with "\n\n"
        events = [e for e in content.split("\n\n") if e.strip()]
        assert len(events) >= 1  # At least one event

        for event_text in events:
            assert event_text.startswith("data: "), f"Event not prefixed with 'data: ': {event_text}"
            json_str = event_text[len("data: "):]
            parsed = json.loads(json_str)
            # Verify required fields
            assert "type" in parsed
            assert "agent" in parsed
            assert "message" in parsed
            assert "timestamp" in parsed
