"""
SSE (Server-Sent Events) serialization utilities.

Provides functions to serialize AgentEvent objects into the SSE wire format
defined by the agent-streaming-reporting spec.

SSE Wire Format:
    data: {json}\n\n

Each event is a single `data: ` line followed by the JSON payload,
terminated by two newline characters.

Satisfies Requirements: 2.8
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from dev_ghost_parser.agent_models import AgentEvent


def _serialize_event_dict(event_dict: dict[str, Any]) -> str:
    """Serialize an event dictionary to JSON, omitting None values."""
    # Filter out None values to keep the payload clean
    filtered = {k: v for k, v in event_dict.items() if v is not None}
    return json.dumps(filtered, ensure_ascii=False)


def serialize_event_to_sse(event: AgentEvent) -> str:
    """Serialize an AgentEvent to the SSE wire format.

    Format: `data: {json}\n\n`
      - Starts with `data: ` (note the space after colon)
      - Followed by a valid JSON string (parseable by json.loads)
      - Ends with `\\n\\n` (two newlines)

    Args:
        event: A valid AgentEvent instance.

    Returns:
        A string in SSE format ready to be sent over the wire.

    Satisfies Requirements: 2.8
    """
    event_dict = asdict(event)
    json_payload = _serialize_event_dict(event_dict)
    return f"data: {json_payload}\n\n"
