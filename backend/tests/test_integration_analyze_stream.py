"""
Integration tests for POST /analyze-stream end-to-end with mock LLM.

Tests the full SSE flow by mocking the orchestrator to emit pre-defined
events, then verifying event ordering, schema, and final analysis_complete
payload.

Validates: Requirements 2.1, 2.6, 2.8
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
            events.append(json.loads(json_str))
    return events


def _make_mock_orchestrator_factory(events_to_emit: list[AgentEvent], result: AnalysisResult):
    """Create a factory that returns a mock orchestrator emitting predefined events.

    The mock orchestrator puts all events on the queue, then the sentinel (None),
    and returns the given AnalysisResult.
    """

    def factory(repo_path, llm_client, event_queue, **kwargs):
        mock_orch = MagicMock()

        async def run_all():
            for event in events_to_emit:
                await event_queue.put(event)
            await event_queue.put(None)  # sentinel
            return result

        mock_orch.run_all = run_all
        return mock_orch

    return factory


# ---------------------------------------------------------------------------
# Pre-defined event sequences for testing
# ---------------------------------------------------------------------------

SAMPLE_EVENTS = [
    AgentEvent(
        type="agent_start",
        agent="ast_analyzer",
        message="Analyzing AST structure and code flow",
        timestamp="2024-01-15T10:30:00.100Z",
    ),
    AgentEvent(
        type="agent_progress",
        agent="ast_analyzer",
        message="Scanning Python files",
        timestamp="2024-01-15T10:30:00.200Z",
    ),
    AgentEvent(
        type="agent_complete",
        agent="ast_analyzer",
        message="Completed ast_analyzer",
        timestamp="2024-01-15T10:30:01.500Z",
        duration_ms=1400,
    ),
    AgentEvent(
        type="agent_start",
        agent="er_extractor",
        message="Extracting entity-relationship model",
        timestamp="2024-01-15T10:30:00.110Z",
    ),
    AgentEvent(
        type="agent_progress",
        agent="er_extractor",
        message="Parsing ORM models",
        timestamp="2024-01-15T10:30:00.300Z",
    ),
    AgentEvent(
        type="agent_complete",
        agent="er_extractor",
        message="Completed er_extractor",
        timestamp="2024-01-15T10:30:02.000Z",
        duration_ms=1890,
    ),
    AgentEvent(
        type="agent_start",
        agent="code_auditor",
        message="Auditing code quality",
        timestamp="2024-01-15T10:30:00.120Z",
    ),
    AgentEvent(
        type="agent_error",
        agent="code_auditor",
        message="Agent code_auditor failed: LLM unavailable",
        timestamp="2024-01-15T10:30:01.800Z",
        error="LLM unavailable",
    ),
    AgentEvent(
        type="agent_start",
        agent="doc_generator",
        message="Generating documentation artifacts",
        timestamp="2024-01-15T10:30:00.130Z",
    ),
    AgentEvent(
        type="agent_progress",
        agent="doc_generator",
        message="Generating C4 diagram",
        timestamp="2024-01-15T10:30:00.500Z",
    ),
    AgentEvent(
        type="agent_complete",
        agent="doc_generator",
        message="Completed doc_generator",
        timestamp="2024-01-15T10:30:03.000Z",
        duration_ms=2870,
    ),
    AgentEvent(
        type="agent_start",
        agent="system_reporter",
        message="Detecting technology stack and generating report",
        timestamp="2024-01-15T10:30:00.140Z",
    ),
    AgentEvent(
        type="agent_progress",
        agent="system_reporter",
        message="Scanning config files",
        timestamp="2024-01-15T10:30:00.400Z",
    ),
    AgentEvent(
        type="agent_progress",
        agent="system_reporter",
        message="Generating setup instructions",
        timestamp="2024-01-15T10:30:01.000Z",
    ),
    AgentEvent(
        type="agent_complete",
        agent="system_reporter",
        message="Completed system_reporter",
        timestamp="2024-01-15T10:30:02.500Z",
        duration_ms=2360,
    ),
]

SAMPLE_RESULT = AnalysisResult(
    code_flow={"nodes": [{"id": "1", "label": "AppService", "type": "Service"}]},
    er_model={"entities": [{"name": "User", "attributes": []}], "relations": []},
    audit=None,
    artifacts={"c4Mermaid": "graph TD; A-->B"},
    system_report={
        "tech_stack": [{"name": "Python", "category": "language"}],
        "setup_instructions": "# Setup\n```bash\npip install -r requirements.txt\n```",
        "project_description": "A sample project.",
    },
    errors=[{"agent": "code_auditor", "error": "LLM unavailable", "duration_ms": 1680}],
)


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestAnalyzeStreamEndToEnd:
    """Integration tests for /analyze-stream full SSE flow with mock orchestrator."""

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_integration_stream")
    @patch("shutil.rmtree")
    def test_response_status_200(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Req 2.1: Endpoint returns 200 for valid request."""
        mock_check.return_value = None
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_create_orch.side_effect = _make_mock_orchestrator_factory(
            SAMPLE_EVENTS, SAMPLE_RESULT
        )

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"},
        )

        assert response.status_code == 200

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_integration_stream")
    @patch("shutil.rmtree")
    def test_content_type_is_event_stream(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Req 2.1: Content-Type should be text/event-stream."""
        mock_check.return_value = None
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_create_orch.side_effect = _make_mock_orchestrator_factory(
            SAMPLE_EVENTS, SAMPLE_RESULT
        )

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"},
        )

        assert "text/event-stream" in response.headers.get("content-type", "")

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_integration_stream")
    @patch("shutil.rmtree")
    def test_all_events_are_valid_sse_format(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Req 2.8: Each event starts with 'data: ', contains valid JSON, ends with '\\n\\n'."""
        mock_check.return_value = None
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_create_orch.side_effect = _make_mock_orchestrator_factory(
            SAMPLE_EVENTS, SAMPLE_RESULT
        )

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"},
        )

        # Split by double newline to get individual SSE frames
        raw = response.text
        frames = [f for f in raw.split("\n\n") if f.strip()]

        assert len(frames) >= 1, "Expected at least one SSE frame"

        for frame in frames:
            assert frame.startswith("data: "), (
                f"SSE frame must start with 'data: ', got: {frame[:50]}"
            )
            json_str = frame[len("data: "):]
            # Must be valid JSON
            parsed = json.loads(json_str)
            assert isinstance(parsed, dict)

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_integration_stream")
    @patch("shutil.rmtree")
    def test_all_events_have_required_fields(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Req 2.8: All events must have type, agent, message, timestamp fields."""
        mock_check.return_value = None
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_create_orch.side_effect = _make_mock_orchestrator_factory(
            SAMPLE_EVENTS, SAMPLE_RESULT
        )

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"},
        )

        events = _parse_sse_events(response.text)
        assert len(events) >= 1

        for event in events:
            assert "type" in event, f"Missing 'type' in event: {event}"
            assert "agent" in event, f"Missing 'agent' in event: {event}"
            assert "message" in event, f"Missing 'message' in event: {event}"
            assert "timestamp" in event, f"Missing 'timestamp' in event: {event}"
            # Non-empty values
            assert event["type"], "type must not be empty"
            assert event["agent"], "agent must not be empty"
            assert event["message"], "message must not be empty"
            assert event["timestamp"], "timestamp must not be empty"

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_integration_stream")
    @patch("shutil.rmtree")
    def test_event_ordering_per_agent(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Req 2.8: Events follow chronological ordering per agent:
        start -> progress+ -> complete|error."""
        mock_check.return_value = None
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_create_orch.side_effect = _make_mock_orchestrator_factory(
            SAMPLE_EVENTS, SAMPLE_RESULT
        )

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"},
        )

        events = _parse_sse_events(response.text)

        # Group events by agent (exclude analysis_complete which is a global event)
        agent_events: dict[str, list[dict]] = {}
        for event in events:
            if event["type"] == "analysis_complete":
                continue
            agent = event["agent"]
            agent_events.setdefault(agent, []).append(event)

        # Verify ordering for each agent
        for agent, agent_evts in agent_events.items():
            types = [e["type"] for e in agent_evts]

            # First event must be agent_start
            assert types[0] == "agent_start", (
                f"Agent {agent}: first event must be 'agent_start', got '{types[0]}'"
            )

            # Last event must be agent_complete or agent_error
            assert types[-1] in ("agent_complete", "agent_error"), (
                f"Agent {agent}: last event must be 'agent_complete' or "
                f"'agent_error', got '{types[-1]}'"
            )

            # Middle events (if any) must be agent_progress
            for t in types[1:-1]:
                assert t == "agent_progress", (
                    f"Agent {agent}: middle events must be 'agent_progress', "
                    f"got '{t}'"
                )

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_integration_stream")
    @patch("shutil.rmtree")
    def test_final_event_is_analysis_complete(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Req 2.6: Last event is analysis_complete with result object."""
        mock_check.return_value = None
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_create_orch.side_effect = _make_mock_orchestrator_factory(
            SAMPLE_EVENTS, SAMPLE_RESULT
        )

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"},
        )

        events = _parse_sse_events(response.text)
        assert len(events) >= 2, "Expected at least agent events + analysis_complete"

        # Final event must be analysis_complete
        final_event = events[-1]
        assert final_event["type"] == "analysis_complete", (
            f"Final event must be 'analysis_complete', got '{final_event['type']}'"
        )

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_integration_stream")
    @patch("shutil.rmtree")
    def test_analysis_complete_has_result_payload(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Req 2.6: analysis_complete event contains the full merged result."""
        mock_check.return_value = None
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_create_orch.side_effect = _make_mock_orchestrator_factory(
            SAMPLE_EVENTS, SAMPLE_RESULT
        )

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"},
        )

        events = _parse_sse_events(response.text)
        final_event = events[-1]

        assert final_event["type"] == "analysis_complete"
        assert "result" in final_event, "analysis_complete must contain 'result' field"

        result = final_event["result"]
        assert isinstance(result, dict)

        # Result should contain the merged analysis fields (camelCase for backward compat)
        assert "codeFlow" in result
        assert "erModel" in result
        # Check actual data present from our mock
        assert result["codeFlow"]["nodes"][0]["label"] == "AppService"
        assert result["erModel"]["entities"][0]["name"] == "User"

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_integration_stream")
    @patch("shutil.rmtree")
    def test_agent_complete_has_duration_ms(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Req 2.8: agent_complete events must have duration_ms >= 0."""
        mock_check.return_value = None
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_create_orch.side_effect = _make_mock_orchestrator_factory(
            SAMPLE_EVENTS, SAMPLE_RESULT
        )

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"},
        )

        events = _parse_sse_events(response.text)
        complete_events = [e for e in events if e["type"] == "agent_complete"]

        assert len(complete_events) >= 1, "Expected at least one agent_complete event"
        for event in complete_events:
            assert "duration_ms" in event, (
                f"agent_complete must have 'duration_ms': {event}"
            )
            assert isinstance(event["duration_ms"], int)
            assert event["duration_ms"] >= 0

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_integration_stream")
    @patch("shutil.rmtree")
    def test_agent_error_has_error_field(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Req 2.8: agent_error events must have non-empty error field."""
        mock_check.return_value = None
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_create_orch.side_effect = _make_mock_orchestrator_factory(
            SAMPLE_EVENTS, SAMPLE_RESULT
        )

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"},
        )

        events = _parse_sse_events(response.text)
        error_events = [e for e in events if e["type"] == "agent_error"]

        assert len(error_events) >= 1, "Expected at least one agent_error event"
        for event in error_events:
            assert "error" in event, f"agent_error must have 'error': {event}"
            assert event["error"], "error field must not be empty"

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_integration_stream")
    @patch("shutil.rmtree")
    def test_event_count_matches_expected(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Verify all emitted events plus analysis_complete are received."""
        mock_check.return_value = None
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_create_orch.side_effect = _make_mock_orchestrator_factory(
            SAMPLE_EVENTS, SAMPLE_RESULT
        )

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"},
        )

        events = _parse_sse_events(response.text)
        # Should have all SAMPLE_EVENTS + 1 analysis_complete
        expected_count = len(SAMPLE_EVENTS) + 1
        assert len(events) == expected_count, (
            f"Expected {expected_count} events, got {len(events)}"
        )

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_integration_stream")
    @patch("shutil.rmtree")
    def test_agent_identifiers_are_valid(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Req 2.8: All agent identifiers must be from the valid set."""
        mock_check.return_value = None
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_create_orch.side_effect = _make_mock_orchestrator_factory(
            SAMPLE_EVENTS, SAMPLE_RESULT
        )

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"},
        )

        valid_agents = {
            "ast_analyzer", "er_extractor", "code_auditor",
            "doc_generator", "system_reporter",
        }
        events = _parse_sse_events(response.text)

        for event in events:
            assert event["agent"] in valid_agents, (
                f"Invalid agent identifier: '{event['agent']}'"
            )

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_integration_stream")
    @patch("shutil.rmtree")
    def test_event_types_are_valid(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Req 2.8: All event types must be from the valid set."""
        mock_check.return_value = None
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_create_orch.side_effect = _make_mock_orchestrator_factory(
            SAMPLE_EVENTS, SAMPLE_RESULT
        )

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"},
        )

        valid_types = {
            "agent_start", "agent_progress", "agent_complete",
            "analysis_complete", "agent_error", "analysis_error",
        }
        events = _parse_sse_events(response.text)

        for event in events:
            assert event["type"] in valid_types, (
                f"Invalid event type: '{event['type']}'"
            )


class TestAnalyzeStreamEdgeCases:
    """Integration tests for edge cases of the /analyze-stream endpoint."""

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_integration_stream")
    @patch("shutil.rmtree")
    def test_empty_orchestrator_produces_analysis_complete(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """When orchestrator emits no agent events, analysis_complete is still sent."""
        mock_check.return_value = None
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
        mock_create_orch.side_effect = _make_mock_orchestrator_factory(
            [], AnalysisResult()  # No events, empty result
        )

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        assert len(events) >= 1
        assert events[-1]["type"] == "analysis_complete"
        assert "result" in events[-1]

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_integration_stream")
    @patch("shutil.rmtree")
    def test_all_agents_fail_still_produces_analysis_complete(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """When all agents fail, analysis_complete still contains errors."""
        mock_check.return_value = None
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")

        error_events = [
            AgentEvent(
                type="agent_start",
                agent="ast_analyzer",
                message="Starting AST analysis",
                timestamp="2024-01-15T10:30:00.100Z",
            ),
            AgentEvent(
                type="agent_error",
                agent="ast_analyzer",
                message="Agent ast_analyzer failed: timeout",
                timestamp="2024-01-15T10:30:01.000Z",
                error="timeout",
            ),
        ]
        error_result = AnalysisResult(
            errors=[{"agent": "ast_analyzer", "error": "timeout", "duration_ms": 900}]
        )
        mock_create_orch.side_effect = _make_mock_orchestrator_factory(
            error_events, error_result
        )

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"},
        )

        assert response.status_code == 200
        events = _parse_sse_events(response.text)

        # Final event is analysis_complete even when all agents fail
        final = events[-1]
        assert final["type"] == "analysis_complete"
        assert final["result"]["errors"][0]["agent"] == "ast_analyzer"

    @patch("dev_ghost_parser.server._check_repo_accessibility")
    @patch("subprocess.run")
    @patch("dev_ghost_parser.server.create_orchestrator_with_all_agents")
    @patch("dev_ghost_parser.server.LLM_Client")
    @patch("tempfile.mkdtemp", return_value="/tmp/test_integration_stream")
    @patch("shutil.rmtree")
    def test_analysis_complete_result_excludes_none_fields(
        self, mock_rmtree, mock_mkdtemp, mock_llm, mock_create_orch,
        mock_subprocess, mock_check, client
    ):
        """Req 2.6: None fields are omitted from the result payload."""
        mock_check.return_value = None
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")

        # Result with only code_flow set
        partial_result = AnalysisResult(
            code_flow={"nodes": []},
        )
        mock_create_orch.side_effect = _make_mock_orchestrator_factory(
            [], partial_result
        )

        response = client.post(
            "/analyze-stream",
            json={"repo_url": "https://github.com/test/repo"},
        )

        events = _parse_sse_events(response.text)
        final = events[-1]
        result = final["result"]

        # codeFlow should be present (camelCase for backward compat)
        assert "codeFlow" in result
        # None fields should be omitted or empty
        assert result.get("artifacts") == {}
        assert result.get("nodeInspections") == {}
