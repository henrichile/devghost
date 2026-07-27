# Feature: llm-integration-and-hero-redesign, Property 3: Description LLM Response Handling
"""
Property test for description LLM response handling.

**Validates: Requirements 2.3, 2.4, 2.6**

For any LLM response string of 5 or more characters, the Description_Generator SHALL
use it as the description. For any such string exceeding 90 characters, the output SHALL
be exactly 87 characters followed by "..." (total 90). For any response of fewer than 5
characters, empty, or None, the Description_Generator SHALL fall back to heuristic logic.
"""

from unittest.mock import MagicMock, patch

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from dev_ghost_parser.description_generator import Description_Generator
from dev_ghost_parser.models import Node, FileContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_node() -> Node:
    """Create a Node with known properties for deterministic heuristic output."""
    return Node(
        id="abc123",
        label="UserService",
        type="Service",
        method_names=["getUser", "createUser"],
    )


def _make_file_context() -> FileContext:
    """Create a FileContext with known properties for deterministic heuristic output."""
    return FileContext(
        imports=["auth", "database"],
        class_name="UserService",
        method_names=["getUser", "createUser"],
    )


def _make_mock_llm(response: str | None) -> MagicMock:
    """Create a mock LLM_Client that returns the given response."""
    mock = MagicMock()
    mock.available = True
    mock.complete = MagicMock(return_value=response)
    return mock


# Strategy for non-whitespace-only strings of length >= 5 and <= 90
_valid_short_strings = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=5,
    max_size=90,
).filter(lambda s: len(s.strip()) >= 5)

# Strategy for strings > 90 characters
_long_strings = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=91,
    max_size=300,
).filter(lambda s: len(s.strip()) >= 5)

# Strategy for strings < 5 characters (including empty)
_short_invalid_strings = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=0,
    max_size=4,
)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(response=_valid_short_strings)
def test_valid_response_used_as_description(response: str) -> None:
    """Strings of 5-90 chars (after strip) should be used as-is (stripped)."""
    mock_llm = _make_mock_llm(response)
    gen = Description_Generator(llm_client=mock_llm)
    node = _make_node()
    file_context = _make_file_context()

    result = gen.generate(node, file_context)

    expected = response.strip()
    assert result == expected, (
        f"Expected LLM response to be used directly (stripped).\n"
        f"  Response: {response!r}\n"
        f"  Expected: {expected!r}\n"
        f"  Got: {result!r}"
    )


@settings(max_examples=100)
@given(response=_long_strings)
def test_long_response_truncated_to_90_chars(response: str) -> None:
    """Strings > 90 chars should be truncated to first 87 chars + '...' (total 90)."""
    mock_llm = _make_mock_llm(response)
    gen = Description_Generator(llm_client=mock_llm)
    node = _make_node()
    file_context = _make_file_context()

    result = gen.generate(node, file_context)

    stripped = response.strip()
    # Since stripped is >= 5 chars (filter), LLM result will be used
    # And since stripped > 90 chars, truncation applies
    if len(stripped) > 90:
        expected = stripped[:87] + "..."
        assert result == expected, (
            f"Expected truncation to 87 + '...' (90 total).\n"
            f"  Response length: {len(stripped)}\n"
            f"  Expected: {expected!r}\n"
            f"  Got: {result!r}"
        )
        assert len(result) == 90, (
            f"Expected result length to be exactly 90, got {len(result)}"
        )
    else:
        # Edge case: stripped version is <= 90 after stripping
        assert result == stripped


@settings(max_examples=100)
@given(response=_short_invalid_strings)
def test_short_response_triggers_heuristic_fallback(response: str) -> None:
    """Strings < 5 chars (after strip) should trigger heuristic fallback."""
    mock_llm = _make_mock_llm(response)
    gen = Description_Generator(llm_client=mock_llm)
    node = _make_node()
    file_context = _make_file_context()

    result = gen.generate(node, file_context)

    # The result should NOT be the LLM response
    # It should be the heuristic result instead
    heuristic_gen = Description_Generator(llm_client=None)
    heuristic_result = heuristic_gen.generate(node, file_context)

    assert result == heuristic_result, (
        f"Expected heuristic fallback for short LLM response.\n"
        f"  LLM response: {response!r} (len={len(response)})\n"
        f"  Expected (heuristic): {heuristic_result!r}\n"
        f"  Got: {result!r}"
    )


@settings(max_examples=100)
@given(data=st.data())
def test_none_response_triggers_heuristic_fallback(data: st.DataObject) -> None:
    """None responses should trigger heuristic fallback."""
    mock_llm = _make_mock_llm(None)
    gen = Description_Generator(llm_client=mock_llm)
    node = _make_node()
    file_context = _make_file_context()

    result = gen.generate(node, file_context)

    # The result should be the heuristic result
    heuristic_gen = Description_Generator(llm_client=None)
    heuristic_result = heuristic_gen.generate(node, file_context)

    assert result == heuristic_result, (
        f"Expected heuristic fallback for None LLM response.\n"
        f"  Expected (heuristic): {heuristic_result!r}\n"
        f"  Got: {result!r}"
    )
