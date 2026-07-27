# Feature: llm-integration-and-hero-redesign, Property 8: LLM_Client Error Containment
"""
Property 8: LLM_Client Error Containment

Validates: Requirements 4.1, 4.2, 4.3

For any exception raised by the OpenAI SDK (including APIError, APITimeoutError,
APIConnectionError, and any unexpected exception), the LLM_Client.complete() method
SHALL return None without propagating the exception. Additionally, for any such error,
a warning-level log message SHALL be emitted containing the error type.
"""

import logging
from unittest.mock import MagicMock, patch

import openai
from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.llm_client import LLM_Client


# --- Exception factory helpers ---

def _make_api_timeout_error(message: str) -> openai.APITimeoutError:
    """Create an APITimeoutError with a given message."""
    request = MagicMock()
    return openai.APITimeoutError(request=request)


def _make_api_connection_error(message: str) -> openai.APIConnectionError:
    """Create an APIConnectionError with a given message."""
    request = MagicMock()
    return openai.APIConnectionError(message=message, request=request)


def _make_api_error(message: str) -> openai.APIError:
    """Create an APIError with a given message."""
    request = MagicMock()
    return openai.APIError(message=message, request=request, body=None)


# --- Strategies ---

exception_type_strategy = st.sampled_from([
    "APITimeoutError",
    "APIConnectionError",
    "APIError",
    "RuntimeError",
    "ValueError",
    "Exception",
])

error_message_strategy = st.text(min_size=1, max_size=50)


def _build_exception(exc_type: str, message: str) -> Exception:
    """Build an exception instance from its type name and a message."""
    if exc_type == "APITimeoutError":
        return _make_api_timeout_error(message)
    elif exc_type == "APIConnectionError":
        return _make_api_connection_error(message)
    elif exc_type == "APIError":
        return _make_api_error(message)
    elif exc_type == "RuntimeError":
        return RuntimeError(message)
    elif exc_type == "ValueError":
        return ValueError(message)
    else:
        return Exception(message)


class _WarningCapture(logging.Handler):
    """Simple log handler that captures warning-level records."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@given(
    exc_type=exception_type_strategy,
    error_message=error_message_strategy,
)
@settings(max_examples=100)
def test_property_8_llm_client_error_containment(exc_type, error_message):
    """
    **Validates: Requirements 4.1, 4.2, 4.3**

    For any exception raised by the OpenAI SDK (including APIError, APITimeoutError,
    APIConnectionError, and any unexpected exception), the LLM_Client.complete() method
    SHALL return None without propagating the exception. Additionally, for any such error,
    a warning-level log message SHALL be emitted containing the error type.
    """
    exception_instance = _build_exception(exc_type, error_message)

    env_vars = {
        "LLM_API_KEY": "test-key",
        "LLM_BASE_URL": "https://example.com/v1",
    }

    with patch.dict("os.environ", env_vars, clear=False):
        with patch("openai.OpenAI") as mock_openai_constructor:
            mock_client = MagicMock()
            mock_openai_constructor.return_value = mock_client

            # Make the chat completions create method raise our exception
            mock_client.chat.completions.create.side_effect = exception_instance

            client = LLM_Client()

            # Verify client is available (properly configured)
            assert client.available is True, (
                "LLM_Client should be available with valid API key and URL"
            )

            # Set up log capture on the LLM_Client logger
            llm_logger = logging.getLogger("dev_ghost_parser.llm_client")
            handler = _WarningCapture()
            llm_logger.addHandler(handler)
            original_level = llm_logger.level
            llm_logger.setLevel(logging.WARNING)

            try:
                result = client.complete("system prompt", "user prompt")
            finally:
                llm_logger.removeHandler(handler)
                llm_logger.setLevel(original_level)

            # Property 1: complete() returns None without propagating the exception
            assert result is None, (
                f"Expected complete() to return None for {exc_type}({error_message!r}), "
                f"but got {result!r}"
            )

            # Property 2: A warning-level log was emitted
            assert len(handler.records) >= 1, (
                f"Expected at least one WARNING log for {exc_type}({error_message!r}), "
                f"but found {len(handler.records)} warning records."
            )
