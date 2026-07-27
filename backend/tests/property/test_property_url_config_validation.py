# Feature: llm-integration-and-hero-redesign, Property 1: URL Configuration Validation
"""
Property test for URL configuration validation.

**Validates: Requirements 1.3, 1.9**

For any string value set as LLM_BASE_URL:
- If it starts with "http://" or "https://", the LLM_Client SHALL set available=True
  (given a valid API key).
- If it does NOT start with "http://" or "https://", the LLM_Client SHALL set
  available=False regardless of other configuration.
"""

import os
from unittest.mock import patch, MagicMock

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from dev_ghost_parser.llm_client import LLM_Client

# Strategy that generates strings valid as environment variable values (no null bytes)
_env_safe_text = st.text(
    alphabet=st.characters(blacklist_characters="\x00"),
)


@settings(max_examples=100)
@given(url=_env_safe_text)
def test_url_starting_with_http_or_https_activates_available(url: str) -> None:
    """Only URLs starting with http:// or https:// should result in available=True."""
    env = {
        "LLM_API_KEY": "test-key-123",
        "LLM_BASE_URL": url,
    }

    with patch.dict(os.environ, env, clear=False):
        with patch("openai.OpenAI") as mock_openai:
            mock_openai.return_value = MagicMock()
            client = LLM_Client()

    stripped = url.strip()
    if stripped.startswith(("http://", "https://")):
        assert client.available is True, (
            f"Expected available=True for URL starting with http(s)://, got False. "
            f"URL (stripped): {stripped!r}"
        )
    else:
        assert client.available is False, (
            f"Expected available=False for URL not starting with http(s)://, got True. "
            f"URL (stripped): {stripped!r}"
        )
