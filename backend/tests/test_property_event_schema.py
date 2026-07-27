"""
Property 6: Event schema validity

For any emitted AgentEvent, it SHALL contain non-null, non-empty `type`, `agent`,
`message`, and `timestamp` fields where: `type` is one of the defined event types,
`agent` is one of the 5 valid identifiers, `message` is 1-2048 characters,
`timestamp` is valid ISO 8601 with millisecond precision; additionally,
"agent_complete" events SHALL have integer `duration_ms` >= 0, and "agent_error"
events SHALL have string `error` of 1-1024 characters.

Validates: Requirements 3.1, 3.2, 3.3, 3.5, 3.6
"""

from datetime import datetime, timezone

import pytest
from hypothesis import given, settings, strategies as st

from dev_ghost_parser.agent_models import AgentEvent


# ---------------------------------------------------------------------------
# Strategies for generating valid AgentEvent components
# ---------------------------------------------------------------------------

VALID_EVENT_TYPES = [
    "agent_start",
    "agent_progress",
    "agent_complete",
    "analysis_complete",
    "agent_error",
    "analysis_error",
]

VALID_AGENT_IDENTIFIERS = [
    "ast_analyzer",
    "er_extractor",
    "code_auditor",
    "doc_generator",
    "system_reporter",
]

event_type_strategy = st.sampled_from(VALID_EVENT_TYPES)
agent_identifier_strategy = st.sampled_from(VALID_AGENT_IDENTIFIERS)

# Message: 1-2048 characters (printable text)
message_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z")),
    min_size=1,
    max_size=2048,
)

# Timestamp: valid ISO 8601 with millisecond precision
timestamp_strategy = st.builds(
    lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z",
    st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2030, 12, 31),
        timezones=st.just(timezone.utc),
    ),
)

# duration_ms: non-negative integer
duration_ms_strategy = st.integers(min_value=0, max_value=10_000_000)

# error: 1-1024 characters
error_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z")),
    min_size=1,
    max_size=1024,
)


# ---------------------------------------------------------------------------
# Composite strategy for generating valid AgentEvent instances
# ---------------------------------------------------------------------------

@st.composite
def valid_agent_event_strategy(draw):
    """Generate a valid AgentEvent with all constraints satisfied."""
    event_type = draw(event_type_strategy)
    agent = draw(agent_identifier_strategy)
    message = draw(message_strategy)
    timestamp = draw(timestamp_strategy)

    duration_ms = None
    error = None
    result = None

    if event_type == "agent_complete":
        duration_ms = draw(duration_ms_strategy)
    elif event_type == "agent_error":
        error = draw(error_strategy)
    elif event_type == "analysis_complete":
        result = {"code_flow": None, "er_model": None}

    return AgentEvent(
        type=event_type,
        agent=agent,
        message=message,
        timestamp=timestamp,
        duration_ms=duration_ms,
        result=result,
        error=error,
    )


# ---------------------------------------------------------------------------
# Property Test: Valid AgentEvent instances satisfy all schema constraints
# ---------------------------------------------------------------------------


class TestProperty6EventSchemaValidity:
    """Feature: agent-streaming-reporting, Property 6: Event schema validity"""

    @settings(max_examples=100)
    @given(event=valid_agent_event_strategy())
    def test_property_6_event_schema_validity(self, event: AgentEvent):
        """Feature: agent-streaming-reporting, Property 6: Event schema validity

        **Validates: Requirements 3.1, 3.2, 3.3, 3.5, 3.6**
        """
        # Requirement 3.2: All four required fields are non-null, non-empty
        assert event.type is not None and event.type != ""
        assert event.agent is not None and event.agent != ""
        assert event.message is not None and event.message != ""
        assert event.timestamp is not None and event.timestamp != ""

        # Requirement 3.1: type is one of the defined event types
        assert event.type in VALID_EVENT_TYPES

        # Requirement 3.6: agent is one of the 5 valid identifiers
        assert event.agent in VALID_AGENT_IDENTIFIERS

        # Requirement 3.1: message is 1-2048 characters
        assert 1 <= len(event.message) <= 2048

        # Requirement 3.1: timestamp is valid ISO 8601 with millisecond precision
        assert event.timestamp.endswith("Z") or "+" in event.timestamp
        # Verify it can be parsed as a datetime
        ts = event.timestamp
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        parsed = datetime.fromisoformat(ts)
        assert parsed is not None

        # Requirement 3.3: agent_complete events have integer duration_ms >= 0
        if event.type == "agent_complete":
            assert event.duration_ms is not None
            assert isinstance(event.duration_ms, int)
            assert event.duration_ms >= 0

        # Requirement 3.5: agent_error events have string error of 1-1024 chars
        if event.type == "agent_error":
            assert event.error is not None
            assert isinstance(event.error, str)
            assert 1 <= len(event.error) <= 1024

    @settings(max_examples=100)
    @given(event=valid_agent_event_strategy())
    def test_property_6_timestamp_has_millisecond_precision(self, event: AgentEvent):
        """Verify timestamp includes millisecond precision.

        **Validates: Requirements 3.1**
        """
        # ISO 8601 with ms should have a dot followed by 3 digits before timezone
        ts = event.timestamp
        # Find the fractional seconds part
        dot_index = ts.rfind(".")
        assert dot_index != -1, f"Timestamp lacks millisecond fraction: {ts}"
        # After the dot, there should be exactly 3 digits before Z or timezone
        fractional_part = ts[dot_index + 1:]
        digits = ""
        for ch in fractional_part:
            if ch.isdigit():
                digits += ch
            else:
                break
        assert len(digits) >= 3, f"Timestamp has fewer than 3 ms digits: {ts}"

    # -----------------------------------------------------------------------
    # Boundary/Invalid value tests using property-based approach
    # -----------------------------------------------------------------------

    @settings(max_examples=50)
    @given(
        agent=agent_identifier_strategy,
        timestamp=timestamp_strategy,
    )
    def test_property_6_empty_message_raises_error(self, agent, timestamp):
        """Empty message must raise ValueError.

        **Validates: Requirements 3.1, 3.2**
        """
        with pytest.raises(ValueError):
            AgentEvent(
                type="agent_start",
                agent=agent,
                message="",
                timestamp=timestamp,
            )

    @settings(max_examples=50)
    @given(
        agent=agent_identifier_strategy,
        timestamp=timestamp_strategy,
    )
    def test_property_6_message_over_2048_raises_error(self, agent, timestamp):
        """Message exceeding 2048 chars must raise ValueError.

        **Validates: Requirements 3.1**
        """
        long_message = "x" * 2049
        with pytest.raises(ValueError):
            AgentEvent(
                type="agent_progress",
                agent=agent,
                message=long_message,
                timestamp=timestamp,
            )

    @settings(max_examples=50)
    @given(
        agent=agent_identifier_strategy,
        message=message_strategy,
        timestamp=timestamp_strategy,
    )
    def test_property_6_negative_duration_ms_raises_error(self, agent, message, timestamp):
        """Negative duration_ms must raise ValueError.

        **Validates: Requirements 3.3**
        """
        with pytest.raises(ValueError):
            AgentEvent(
                type="agent_complete",
                agent=agent,
                message=message,
                timestamp=timestamp,
                duration_ms=-1,
            )

    @settings(max_examples=50)
    @given(
        agent=agent_identifier_strategy,
        message=message_strategy,
        timestamp=timestamp_strategy,
    )
    def test_property_6_empty_error_raises_error(self, agent, message, timestamp):
        """Empty error field must raise ValueError.

        **Validates: Requirements 3.5**
        """
        with pytest.raises(ValueError):
            AgentEvent(
                type="agent_error",
                agent=agent,
                message=message,
                timestamp=timestamp,
                error="",
            )

    @settings(max_examples=50)
    @given(
        agent=agent_identifier_strategy,
        message=message_strategy,
        timestamp=timestamp_strategy,
    )
    def test_property_6_error_over_1024_raises_error(self, agent, message, timestamp):
        """Error field exceeding 1024 chars must raise ValueError.

        **Validates: Requirements 3.5**
        """
        long_error = "e" * 1025
        with pytest.raises(ValueError):
            AgentEvent(
                type="agent_error",
                agent=agent,
                message=message,
                timestamp=timestamp,
                error=long_error,
            )
