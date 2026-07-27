"""
Data models for the multi-agent streaming architecture.

Defines the event schema, technology stack structures, and result types
used by the Agent Orchestrator and SSE streaming endpoint.

Satisfies Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional


# ---------------------------------------------------------------------------
# Type aliases for constrained string literals
# ---------------------------------------------------------------------------

AgentEventType = Literal[
    "agent_start",
    "agent_progress",
    "agent_complete",
    "analysis_complete",
    "agent_error",
    "analysis_error",
]

AgentIdentifier = Literal[
    "ast_analyzer",
    "er_extractor",
    "code_auditor",
    "doc_generator",
    "system_reporter",
]


# ---------------------------------------------------------------------------
# AgentEvent — a single SSE event emitted during analysis streaming
# ---------------------------------------------------------------------------


@dataclass
class AgentEvent:
    """A single event emitted during analysis streaming.

    Satisfies Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 6.2, 6.4, 6.5, 9.2.

    Fields:
        type: One of the defined AgentEventType values.
        agent: One of the five agent identifiers.
        message: Human-readable description (1-2048 characters).
        timestamp: ISO 8601 string with millisecond precision.
        sequence: Monotonically increasing sequence number for event ordering.
        duration_ms: Elapsed time in ms (only for agent_complete, >= 0).
        result: Full analysis JSON (only for analysis_complete).
        error: Error description (only for agent_error, 1-1024 characters).
        progress_pct: Progress percentage (0.0 - 100.0) for progress events.
        retry_count: Number of retries attempted (for error events).
    """

    type: AgentEventType
    agent: AgentIdentifier
    message: str  # 1-2048 characters
    timestamp: str  # ISO 8601 with millisecond precision
    sequence: int = 0  # Monotonically increasing sequence number
    duration_ms: Optional[int] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    progress_pct: Optional[float] = None  # 0.0 - 100.0
    retry_count: Optional[int] = None  # Number of retries attempted

    def __post_init__(self) -> None:
        # Validate message length: 1-2048 characters
        if not self.message or len(self.message) < 1:
            raise ValueError("AgentEvent.message must be at least 1 character")
        if len(self.message) > 2048:
            raise ValueError(
                f"AgentEvent.message must be at most 2048 characters, got {len(self.message)}"
            )

        # Validate sequence: must be >= 0
        if self.sequence < 0:
            raise ValueError(
                f"AgentEvent.sequence must be >= 0, got {self.sequence}"
            )

        # Validate duration_ms when present: must be >= 0
        if self.duration_ms is not None and self.duration_ms < 0:
            raise ValueError(
                f"AgentEvent.duration_ms must be >= 0, got {self.duration_ms}"
            )

        # Validate error field when present: 1-1024 characters
        if self.error is not None:
            if len(self.error) < 1:
                raise ValueError("AgentEvent.error must be at least 1 character")
            if len(self.error) > 1024:
                raise ValueError(
                    f"AgentEvent.error must be at most 1024 characters, got {len(self.error)}"
                )

        # Validate progress_pct when present: must be 0.0 - 100.0
        if self.progress_pct is not None:
            if self.progress_pct < 0.0 or self.progress_pct > 100.0:
                raise ValueError(
                    f"AgentEvent.progress_pct must be between 0.0 and 100.0, got {self.progress_pct}"
                )

        # Validate retry_count when present: must be >= 0
        if self.retry_count is not None and self.retry_count < 0:
            raise ValueError(
                f"AgentEvent.retry_count must be >= 0, got {self.retry_count}"
            )


# ---------------------------------------------------------------------------
# TechStack — technology stack detection models
# ---------------------------------------------------------------------------


@dataclass
class TechStackEntry:
    """A single detected technology.

    Satisfies Requirements 6.1, 6.2.
    """

    name: str
    category: Literal["language", "framework", "database", "infrastructure"]
    description: str = ""


@dataclass
class TechStack:
    """Complete technology stack detection result.

    Satisfies Requirements 6.1, 6.2.
    """

    entries: list[TechStackEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SystemReportResult — output of the System Reporter agent
# ---------------------------------------------------------------------------


@dataclass
class SystemReportResult:
    """Output of the System Reporter agent.

    Satisfies Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6.

    Fields:
        tech_stack: Detected technology stack.
        setup_instructions: Markdown-formatted setup/run instructions.
        project_description: Max 500 chars, Markdown-formatted project summary.
        could_not_determine: True if no config files were found.
    """

    tech_stack: TechStack
    setup_instructions: str  # Markdown
    project_description: str  # Max 500 chars, Markdown
    could_not_determine: bool = False

    def __post_init__(self) -> None:
        # Validate project_description length: max 500 characters
        if len(self.project_description) > 500:
            raise ValueError(
                f"SystemReportResult.project_description must be at most 500 characters, "
                f"got {len(self.project_description)}"
            )


# ---------------------------------------------------------------------------
# AgentResult — generic result wrapper for any agent
# ---------------------------------------------------------------------------


@dataclass
class AgentResult:
    """Generic result wrapper for any agent.

    Satisfies Requirements 1.3, 1.4.

    Fields:
        agent_name: Identifier of the agent that produced this result.
        success: Whether the agent completed without error.
        data: Agent-specific result payload.
        error_message: Error description if success is False.
        duration_ms: Elapsed processing time in milliseconds.
    """

    agent_name: AgentIdentifier
    success: bool
    data: Any = None
    error_message: Optional[str] = None
    duration_ms: int = 0

    def __post_init__(self) -> None:
        # Validate duration_ms: must be >= 0
        if self.duration_ms < 0:
            raise ValueError(
                f"AgentResult.duration_ms must be >= 0, got {self.duration_ms}"
            )


# ---------------------------------------------------------------------------
# ExecutionMetadata — pipeline execution statistics
# ---------------------------------------------------------------------------


@dataclass
class ExecutionMetadata:
    """Pipeline execution statistics.

    Satisfies Requirements 8.5, 7.4.

    Fields:
        total_duration_ms: Total pipeline execution time in milliseconds.
        agent_durations: Per-agent execution duration in ms (agent_name -> duration_ms).
        retry_counts: Per-agent retry count (agent_name -> retries used).
        failed_agents: List of agent names that failed after all retries.
        partial_results: List of agent names that produced partial results.
    """

    total_duration_ms: int
    agent_durations: dict[str, int] = field(default_factory=dict)
    retry_counts: dict[str, int] = field(default_factory=dict)
    failed_agents: list[str] = field(default_factory=list)
    partial_results: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.total_duration_ms < 0:
            raise ValueError(
                f"ExecutionMetadata.total_duration_ms must be >= 0, got {self.total_duration_ms}"
            )


# ---------------------------------------------------------------------------
# AnalysisResult — merged result from all agents
# ---------------------------------------------------------------------------


@dataclass
class AnalysisResult:
    """Merged result from all agents.

    Satisfies Requirements 1.4, 2.6, 8.5.

    Fields:
        code_flow: AST analysis output.
        er_model: Entity-relationship extraction output.
        audit: Code audit findings.
        artifacts: Generated documentation artifacts.
        system_report: System Reporter output (tech stack, instructions, description).
        node_inspections: Node-level inspection data.
        errors: List of error dicts from failed agents.
        metadata: Pipeline execution statistics (durations, retries, failures).
    """

    code_flow: Optional[dict] = None
    er_model: Optional[dict] = None
    audit: Optional[dict] = None
    artifacts: Optional[dict] = None
    system_report: Optional[dict] = None
    node_inspections: Optional[dict] = None
    errors: list[dict] = field(default_factory=list)
    metadata: Optional[ExecutionMetadata] = None
