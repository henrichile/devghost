"""Unit tests for agent_models.py validation constraints."""

import pytest

from dev_ghost_parser.agent_models import (
    AgentEvent,
    AgentResult,
    AnalysisResult,
    SystemReportResult,
    TechStack,
    TechStackEntry,
)


class TestAgentEventValidation:
    """Tests for AgentEvent field validation."""

    def test_valid_agent_event_minimal(self):
        """A valid AgentEvent with only required fields."""
        event = AgentEvent(
            type="agent_start",
            agent="ast_analyzer",
            message="Starting analysis",
            timestamp="2024-01-15T10:30:00.123Z",
        )
        assert event.type == "agent_start"
        assert event.agent == "ast_analyzer"
        assert event.message == "Starting analysis"

    def test_valid_agent_event_with_duration(self):
        """A valid agent_complete event with duration_ms."""
        event = AgentEvent(
            type="agent_complete",
            agent="er_extractor",
            message="Analysis complete",
            timestamp="2024-01-15T10:30:05.456Z",
            duration_ms=5333,
        )
        assert event.duration_ms == 5333

    def test_valid_agent_event_with_zero_duration(self):
        """duration_ms=0 is valid."""
        event = AgentEvent(
            type="agent_complete",
            agent="code_auditor",
            message="Done",
            timestamp="2024-01-15T10:30:00.000Z",
            duration_ms=0,
        )
        assert event.duration_ms == 0

    def test_valid_agent_event_with_error(self):
        """A valid agent_error event with error field."""
        event = AgentEvent(
            type="agent_error",
            agent="doc_generator",
            message="Agent failed",
            timestamp="2024-01-15T10:30:00.123Z",
            error="Connection timeout to LLM service",
        )
        assert event.error == "Connection timeout to LLM service"

    def test_message_empty_raises(self):
        """Empty message should raise ValueError."""
        with pytest.raises(ValueError, match="at least 1 character"):
            AgentEvent(
                type="agent_start",
                agent="ast_analyzer",
                message="",
                timestamp="2024-01-15T10:30:00.123Z",
            )

    def test_message_too_long_raises(self):
        """Message over 2048 chars should raise ValueError."""
        with pytest.raises(ValueError, match="at most 2048 characters"):
            AgentEvent(
                type="agent_progress",
                agent="ast_analyzer",
                message="x" * 2049,
                timestamp="2024-01-15T10:30:00.123Z",
            )

    def test_message_at_max_length(self):
        """Message exactly 2048 chars is valid."""
        event = AgentEvent(
            type="agent_progress",
            agent="ast_analyzer",
            message="x" * 2048,
            timestamp="2024-01-15T10:30:00.123Z",
        )
        assert len(event.message) == 2048

    def test_negative_duration_raises(self):
        """Negative duration_ms should raise ValueError."""
        with pytest.raises(ValueError, match="must be >= 0"):
            AgentEvent(
                type="agent_complete",
                agent="ast_analyzer",
                message="Done",
                timestamp="2024-01-15T10:30:00.123Z",
                duration_ms=-1,
            )

    def test_error_empty_raises(self):
        """Empty error string should raise ValueError."""
        with pytest.raises(ValueError, match="at least 1 character"):
            AgentEvent(
                type="agent_error",
                agent="ast_analyzer",
                message="Failed",
                timestamp="2024-01-15T10:30:00.123Z",
                error="",
            )

    def test_error_too_long_raises(self):
        """Error over 1024 chars should raise ValueError."""
        with pytest.raises(ValueError, match="at most 1024 characters"):
            AgentEvent(
                type="agent_error",
                agent="ast_analyzer",
                message="Failed",
                timestamp="2024-01-15T10:30:00.123Z",
                error="e" * 1025,
            )

    def test_error_at_max_length(self):
        """Error exactly 1024 chars is valid."""
        event = AgentEvent(
            type="agent_error",
            agent="ast_analyzer",
            message="Failed",
            timestamp="2024-01-15T10:30:00.123Z",
            error="e" * 1024,
        )
        assert len(event.error) == 1024


class TestSystemReportResultValidation:
    """Tests for SystemReportResult.project_description constraint."""

    def test_valid_system_report(self):
        """A valid SystemReportResult."""
        result = SystemReportResult(
            tech_stack=TechStack(entries=[
                TechStackEntry(name="Python", category="language", description="Main language"),
            ]),
            setup_instructions="## Setup\n\n```bash\npip install -e .\n```",
            project_description="A web application for code analysis.",
        )
        assert result.project_description == "A web application for code analysis."
        assert not result.could_not_determine

    def test_project_description_at_max(self):
        """project_description exactly 500 chars is valid."""
        result = SystemReportResult(
            tech_stack=TechStack(),
            setup_instructions="",
            project_description="d" * 500,
        )
        assert len(result.project_description) == 500

    def test_project_description_too_long_raises(self):
        """project_description over 500 chars should raise ValueError."""
        with pytest.raises(ValueError, match="at most 500 characters"):
            SystemReportResult(
                tech_stack=TechStack(),
                setup_instructions="",
                project_description="d" * 501,
            )

    def test_could_not_determine_flag(self):
        """SystemReportResult with could_not_determine=True."""
        result = SystemReportResult(
            tech_stack=TechStack(),
            setup_instructions="",
            project_description="",
            could_not_determine=True,
        )
        assert result.could_not_determine is True


class TestAgentResultValidation:
    """Tests for AgentResult.duration_ms constraint."""

    def test_valid_agent_result(self):
        """A valid AgentResult."""
        result = AgentResult(
            agent_name="ast_analyzer",
            success=True,
            data={"nodes": [], "edges": []},
            duration_ms=1234,
        )
        assert result.success is True
        assert result.duration_ms == 1234

    def test_duration_zero_valid(self):
        """duration_ms=0 is valid."""
        result = AgentResult(agent_name="er_extractor", success=True, duration_ms=0)
        assert result.duration_ms == 0

    def test_negative_duration_raises(self):
        """Negative duration_ms should raise ValueError."""
        with pytest.raises(ValueError, match="must be >= 0"):
            AgentResult(agent_name="code_auditor", success=False, duration_ms=-5)


class TestTechStackModels:
    """Tests for TechStack and TechStackEntry."""

    def test_tech_stack_entry(self):
        """Basic TechStackEntry creation."""
        entry = TechStackEntry(
            name="FastAPI", category="framework", description="Python web framework"
        )
        assert entry.name == "FastAPI"
        assert entry.category == "framework"

    def test_tech_stack_default_entries(self):
        """TechStack defaults to empty entries list."""
        stack = TechStack()
        assert stack.entries == []

    def test_tech_stack_with_entries(self):
        """TechStack with multiple entries."""
        stack = TechStack(entries=[
            TechStackEntry(name="Python", category="language"),
            TechStackEntry(name="PostgreSQL", category="database"),
        ])
        assert len(stack.entries) == 2


class TestAnalysisResult:
    """Tests for AnalysisResult."""

    def test_defaults(self):
        """AnalysisResult defaults to None fields and empty errors."""
        result = AnalysisResult()
        assert result.code_flow is None
        assert result.er_model is None
        assert result.audit is None
        assert result.artifacts is None
        assert result.system_report is None
        assert result.node_inspections is None
        assert result.errors == []

    def test_with_data(self):
        """AnalysisResult with populated fields."""
        result = AnalysisResult(
            code_flow={"nodes": [], "edges": []},
            system_report={"tech_stack": {"entries": []}},
            errors=[{"agent": "code_auditor", "message": "timeout"}],
        )
        assert result.code_flow is not None
        assert result.system_report is not None
        assert len(result.errors) == 1
