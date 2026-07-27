# Feature: llm-integration-and-hero-redesign, Property 6: Summary LLM Response Pipeline
"""
Property test for summary LLM response pipeline.

**Validates: Requirements 3.3, 3.4, 3.8, 3.9**

For any LLM response string that is 1-450 characters and contains at least one period,
the Summary_Generator SHALL accept it. For any response exceeding 450 characters, it
SHALL be truncated to 447 + "...". The accepted/truncated text SHALL then be sanitized
(removal of control characters, prohibited markdown chars, and code identifiers). For any
post-sanitization result shorter than 10 characters, the Summary_Generator SHALL discard
the LLM result and fall back to heuristic logic.
"""

from unittest.mock import MagicMock

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from dev_ghost_parser.summary_generator import Summary_Generator, _sanitize
from dev_ghost_parser.models import (
    CodeFlowResult,
    ERResult,
    Entity,
    Node,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_code_flow() -> CodeFlowResult:
    """Create a CodeFlowResult with at least one Controller node."""
    return CodeFlowResult(
        nodes=[Node(id="1", label="UserController", type="Controller")],
        edges=[],
    )


def _make_er_result() -> ERResult:
    """Create an ERResult with at least one entity."""
    return ERResult(
        entities=[Entity(name="User", attributes=[])],
        relations=[],
    )


def _make_mock_llm(response: str | None) -> MagicMock:
    """Create a mock LLM_Client that returns the given response."""
    mock = MagicMock()
    mock.available = True
    mock.complete = MagicMock(return_value=response)
    return mock


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Characters that survive sanitization: printable ASCII letters, digits, spaces,
# and safe punctuation (excluding prohibited chars *#`_~>< and control chars).
# This avoids identifiers by using spaces between words.
_safe_printable = st.sampled_from(
    list("abcdefghijklmnopqrstuvwxyz0123456789 ,;:()!?-")
)

# Strategy: valid responses 1-450 chars that contain at least one period
# and where post-sanitization produces >= 10 chars.
# Built by combining safe text with a guaranteed period.
_valid_responses = st.builds(
    lambda prefix, suffix: prefix + "." + suffix,
    prefix=st.text(alphabet=_safe_printable, min_size=10, max_size=200),
    suffix=st.text(alphabet=_safe_printable, min_size=0, max_size=200),
).filter(lambda s: len(s) <= 450 and len(_sanitize(s)) >= 10)

# Strategy: responses > 450 chars (will be truncated to 447 + "...")
# Build long text with a period guaranteed somewhere in the first 447 chars.
_long_responses = st.builds(
    lambda prefix, suffix: prefix + "." + suffix,
    prefix=st.text(alphabet=_safe_printable, min_size=100, max_size=300),
    suffix=st.text(alphabet=_safe_printable, min_size=200, max_size=500),
).filter(lambda s: len(s) > 450)

# Strategy: responses without any period (should be rejected)
_no_period_responses = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),
        blacklist_characters=".",
    ),
    min_size=1,
    max_size=450,
).filter(lambda s: len(s.strip()) > 0)

# Strategy: responses where post-sanitization produces < 10 chars
# Use strings composed mostly of prohibited chars and identifiers
_sanitized_too_short = st.text(
    alphabet=st.sampled_from(list("*#`_~><")),
    min_size=1,
    max_size=100,
).map(lambda s: s + ".").filter(lambda s: len(_sanitize(s)) < 10)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(response=_valid_responses)
def test_valid_response_accepted_and_sanitized(response: str) -> None:
    """Valid responses (1-450 chars, has period, post-sanitize >= 10) use LLM result."""
    mock_llm = _make_mock_llm(response)
    gen = Summary_Generator(llm_client=mock_llm)
    code_flow = _make_code_flow()
    er_result = _make_er_result()

    result = gen.generate(code_flow, er_result, "/test")

    # The result should be the sanitized version of the response
    expected = _sanitize(response)
    assert result == expected, (
        f"Expected sanitized LLM response to be used.\n"
        f"  Response: {response!r}\n"
        f"  Expected (sanitized): {expected!r}\n"
        f"  Got: {result!r}"
    )


@settings(max_examples=100)
@given(response=_long_responses)
def test_long_response_truncated_before_sanitization(response: str) -> None:
    """Responses > 450 chars are truncated to 447 + '...' before sanitization."""
    mock_llm = _make_mock_llm(response)
    gen = Summary_Generator(llm_client=mock_llm)
    code_flow = _make_code_flow()
    er_result = _make_er_result()

    result = gen.generate(code_flow, er_result, "/test")

    # The response should be truncated to 447 + "..." = 450 chars
    truncated = response[:447] + "..."
    sanitized_truncated = _sanitize(truncated)

    if len(sanitized_truncated) >= 10:
        # LLM result is used (sanitized version of truncated text)
        assert result == sanitized_truncated, (
            f"Expected sanitized truncated LLM response.\n"
            f"  Original length: {len(response)}\n"
            f"  Truncated: {truncated!r}\n"
            f"  Expected (sanitized truncated): {sanitized_truncated!r}\n"
            f"  Got: {result!r}"
        )
    else:
        # Post-sanitization too short -> heuristic fallback
        heuristic_gen = Summary_Generator(llm_client=None)
        heuristic_result = heuristic_gen.generate(code_flow, er_result, "/test")
        assert result == heuristic_result, (
            f"Expected heuristic fallback when post-sanitization < 10 chars.\n"
            f"  Sanitized length: {len(sanitized_truncated)}\n"
            f"  Expected (heuristic): {heuristic_result!r}\n"
            f"  Got: {result!r}"
        )


@settings(max_examples=100)
@given(response=_no_period_responses)
def test_no_period_response_triggers_heuristic_fallback(response: str) -> None:
    """Responses without a period are rejected, heuristic fallback is used."""
    assume("." not in response)

    mock_llm = _make_mock_llm(response)
    gen = Summary_Generator(llm_client=mock_llm)
    code_flow = _make_code_flow()
    er_result = _make_er_result()

    result = gen.generate(code_flow, er_result, "/test")

    # Should fall back to heuristic
    heuristic_gen = Summary_Generator(llm_client=None)
    heuristic_result = heuristic_gen.generate(code_flow, er_result, "/test")

    assert result == heuristic_result, (
        f"Expected heuristic fallback for response without period.\n"
        f"  LLM response: {response!r}\n"
        f"  Expected (heuristic): {heuristic_result!r}\n"
        f"  Got: {result!r}"
    )


@settings(max_examples=100)
@given(response=_sanitized_too_short)
def test_post_sanitization_too_short_triggers_fallback(response: str) -> None:
    """Responses where post-sanitization produces < 10 chars trigger heuristic fallback."""
    # Confirm our strategy produces the right precondition
    assume(len(_sanitize(response)) < 10)
    assume("." in response)

    mock_llm = _make_mock_llm(response)
    gen = Summary_Generator(llm_client=mock_llm)
    code_flow = _make_code_flow()
    er_result = _make_er_result()

    result = gen.generate(code_flow, er_result, "/test")

    # Should fall back to heuristic
    heuristic_gen = Summary_Generator(llm_client=None)
    heuristic_result = heuristic_gen.generate(code_flow, er_result, "/test")

    assert result == heuristic_result, (
        f"Expected heuristic fallback when post-sanitization < 10 chars.\n"
        f"  LLM response: {response!r}\n"
        f"  Sanitized: {_sanitize(response)!r} (len={len(_sanitize(response))})\n"
        f"  Expected (heuristic): {heuristic_result!r}\n"
        f"  Got: {result!r}"
    )
