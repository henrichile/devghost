"""
Feature: agent-streaming-reporting, Property 5: SSE format serialization

For any valid AgentEvent object, its SSE serialization SHALL start with `data: `,
followed by a valid JSON string (parseable by json.loads), followed by `\\n\\n`.

**Validates: Requirements 2.8**
"""

from hypothesis import given, settings, strategies as st
import json

from dev_ghost_parser.agent_models import AgentEvent, AgentEventType, AgentIdentifier
from dev_ghost_parser.sse_utils import serialize_event_to_sse


# ---------------------------------------------------------------------------
# Hypothesis strategies for generating valid AgentEvent objects
# ---------------------------------------------------------------------------

AGENT_EVENT_TYPES: list[AgentEventType] = [
    "agent_start",
    "agent_progress",
    "agent_complete",
    "analysis_complete",
    "agent_error",
    "analysis_error",
]

AGENT_IDENTIFIERS: list[AgentIdentifier] = [
    "ast_analyzer",
    "er_extractor",
    "code_auditor",
    "doc_generator",
    "system_reporter",
]

# Strategy for valid message (1-2048 chars, printable text)
message_strategy = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "S", "Z")),
    min_size=1,
    max_size=200,
)

# Strategy for valid ISO 8601 timestamps with millisecond precision
timestamp_strategy = st.from_regex(
    r"20[0-9]{2}-[01][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]\.[0-9]{3}Z",
    fullmatch=True,
)

# Strategy for valid duration_ms (non-negative integer)
duration_ms_strategy = st.integers(min_value=0, max_value=600_000)

# Strategy for valid error messages (1-1024 chars)
error_strategy = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "S", "Z")),
    min_size=1,
    max_size=100,
)

# Strategy for result dicts (simple JSON-serializable dicts)
result_strategy = st.dictionaries(
    keys=st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L",))),
    values=st.one_of(
        st.text(min_size=0, max_size=50),
        st.integers(min_value=-1000, max_value=1000),
        st.booleans(),
        st.none(),
    ),
    max_size=5,
)


@st.composite
def agent_event_strategy(draw: st.DrawFn) -> AgentEvent:
    """Generate a valid AgentEvent with appropriate optional fields based on type."""
    event_type = draw(st.sampled_from(AGENT_EVENT_TYPES))
    agent = draw(st.sampled_from(AGENT_IDENTIFIERS))
    message = draw(message_strategy)
    timestamp = draw(timestamp_strategy)

    # Set optional fields based on event type
    duration_ms = None
    result = None
    error = None

    if event_type == "agent_complete":
        duration_ms = draw(duration_ms_strategy)
    elif event_type == "analysis_complete":
        result = draw(result_strategy)
    elif event_type == "agent_error":
        error = draw(error_strategy)

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
# Property test
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(event=agent_event_strategy())
def test_property_5_sse_format_serialization(event: AgentEvent):
    """Feature: agent-streaming-reporting, Property 5: SSE format serialization

    **Validates: Requirements 2.8**

    For any valid AgentEvent, the SSE serialization must:
    1. Start with `data: ` (data colon space)
    2. Contain a valid JSON string (parseable by json.loads)
    3. End with `\\n\\n` (two newline characters)
    """
    serialized = serialize_event_to_sse(event)

    # 1. Must start with "data: "
    assert serialized.startswith("data: "), (
        f"SSE output must start with 'data: ', got: {serialized[:20]!r}"
    )

    # 2. Must end with "\n\n"
    assert serialized.endswith("\n\n"), (
        f"SSE output must end with '\\n\\n', got ending: {serialized[-10:]!r}"
    )

    # 3. The content between "data: " and "\n\n" must be valid JSON
    json_content = serialized[len("data: "):-len("\n\n")]
    try:
        parsed = json.loads(json_content)
    except json.JSONDecodeError as e:
        raise AssertionError(
            f"SSE payload is not valid JSON: {e}\nPayload: {json_content!r}"
        )

    # 4. The parsed JSON should contain the core event fields
    assert "type" in parsed, "Parsed JSON must contain 'type' field"
    assert "agent" in parsed, "Parsed JSON must contain 'agent' field"
    assert "message" in parsed, "Parsed JSON must contain 'message' field"
    assert "timestamp" in parsed, "Parsed JSON must contain 'timestamp' field"

    # 5. Verify field values match the original event
    assert parsed["type"] == event.type
    assert parsed["agent"] == event.agent
    assert parsed["message"] == event.message
    assert parsed["timestamp"] == event.timestamp
