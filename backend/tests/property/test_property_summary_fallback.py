# Feature: llm-integration-and-hero-redesign, Property 7: Summary Fallback on LLM Error
"""
Property 7: Summary Fallback on LLM Error

Validates: Requirements 3.5, 3.6, 3.7

For any error condition from the LLM_Client (timeout, network error, HTTP error,
empty/whitespace response, or response without a period), the Summary_Generator
SHALL produce a summary using the existing heuristic logic, maintaining the existing
invariants (≤500 code points, ≤4 sentences, no prohibited characters).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.models import (
    Attribute,
    CodeFlowResult,
    Entity,
    ERResult,
    Node,
)
from dev_ghost_parser.summary_generator import Summary_Generator, _PROHIBITED_CHARS


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

VALID_TYPES = ["Controller", "Service", "Route", "Middleware", "Repository", "Utility", "Config"]

_SAFE_ALPHABET = st.characters(
    whitelist_categories=("L", "N"), min_codepoint=65, max_codepoint=122
)

attribute_strategy = st.builds(
    Attribute,
    name=st.text(min_size=1, max_size=20, alphabet=_SAFE_ALPHABET),
    type=st.sampled_from(["string", "integer", "boolean", "float", "DateTime"]),
)

entity_strategy = st.builds(
    Entity,
    name=st.text(min_size=1, max_size=30, alphabet=_SAFE_ALPHABET),
    attributes=st.lists(attribute_strategy, max_size=5),
    primaryKey=st.just("id"),
)

node_strategy = st.builds(
    Node,
    id=st.text(min_size=1, max_size=40, alphabet=_SAFE_ALPHABET),
    label=st.text(min_size=1, max_size=30, alphabet=_SAFE_ALPHABET),
    type=st.sampled_from(VALID_TYPES),
    description=st.text(min_size=0, max_size=120),
    method_names=st.lists(
        st.text(min_size=1, max_size=20, alphabet=_SAFE_ALPHABET), max_size=5
    ),
)

code_flow_strategy = st.builds(
    CodeFlowResult,
    nodes=st.lists(node_strategy, min_size=1, max_size=15),
)

er_result_strategy = st.builds(
    ERResult,
    entities=st.lists(entity_strategy, min_size=1, max_size=10),
)


def _make_error_llm_client() -> MagicMock:
    """Create a mock LLM_Client that reports available=True but complete() returns None.

    This simulates any error condition (timeout, network error, HTTP error,
    empty/whitespace response) since LLM_Client.complete() returns None for all errors.
    """
    mock_client = MagicMock()
    mock_client.available = True
    mock_client.complete.return_value = None
    return mock_client


def _make_no_period_llm_client() -> MagicMock:
    """Create a mock LLM_Client that returns a response without any period.

    The Summary_Generator should reject this and fall back to heuristics.
    """
    mock_client = MagicMock()
    mock_client.available = True
    mock_client.complete.return_value = "Esta respuesta no tiene ningun punto final"
    return mock_client


def count_sentences(text: str) -> int:
    """Count sentences by splitting on '. ' and counting non-empty parts."""
    parts = text.split(". ")
    count = 0
    for part in parts:
        stripped = part.strip()
        if stripped:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Property 7a: LLM error (returns None) produces output identical to heuristic
# ---------------------------------------------------------------------------

@given(
    nodes=st.lists(node_strategy, min_size=1, max_size=15),
    entities=st.lists(entity_strategy, min_size=1, max_size=10),
)
@settings(max_examples=100)
def test_property_7_summary_fallback_llm_error_matches_heuristic(nodes, entities):
    """
    **Validates: Requirements 3.5, 3.6, 3.7**

    When the LLM_Client returns None (simulating timeout, network error, HTTP error,
    or empty response), the Summary_Generator SHALL produce output identical to the
    heuristic-only generator.
    """
    code_flow = CodeFlowResult(nodes=nodes)
    er_result = ERResult(entities=entities)

    # Generator with mock LLM that returns None (error simulation)
    error_client = _make_error_llm_client()
    sg_with_error_llm = Summary_Generator(llm_client=error_client)

    # Generator with no LLM (heuristic-only)
    sg_heuristic_only = Summary_Generator(llm_client=None)

    result_error = sg_with_error_llm.generate(code_flow, er_result, "/test/path")
    result_heuristic = sg_heuristic_only.generate(code_flow, er_result, "/test/path")

    # Outputs must be identical
    assert result_error == result_heuristic, (
        f"LLM error fallback produced different output than heuristic.\n"
        f"Error fallback: {result_error!r}\n"
        f"Heuristic only: {result_heuristic!r}"
    )


# ---------------------------------------------------------------------------
# Property 7b: LLM response without a period produces output identical to heuristic
# ---------------------------------------------------------------------------

@given(
    nodes=st.lists(node_strategy, min_size=1, max_size=15),
    entities=st.lists(entity_strategy, min_size=1, max_size=10),
)
@settings(max_examples=100)
def test_property_7_summary_fallback_no_period_matches_heuristic(nodes, entities):
    """
    **Validates: Requirements 3.5, 3.6, 3.7**

    When the LLM_Client returns a response without a period (invalid sentence),
    the Summary_Generator SHALL discard it and produce output identical to the
    heuristic-only generator.
    """
    code_flow = CodeFlowResult(nodes=nodes)
    er_result = ERResult(entities=entities)

    # Generator with mock LLM that returns text without a period
    no_period_client = _make_no_period_llm_client()
    sg_with_no_period = Summary_Generator(llm_client=no_period_client)

    # Generator with no LLM (heuristic-only)
    sg_heuristic_only = Summary_Generator(llm_client=None)

    result_no_period = sg_with_no_period.generate(code_flow, er_result, "/test/path")
    result_heuristic = sg_heuristic_only.generate(code_flow, er_result, "/test/path")

    # Outputs must be identical
    assert result_no_period == result_heuristic, (
        f"LLM no-period fallback produced different output than heuristic.\n"
        f"No-period fallback: {result_no_period!r}\n"
        f"Heuristic only: {result_heuristic!r}"
    )


# ---------------------------------------------------------------------------
# Property 7c: Fallback output maintains invariants (≤500 cp, ≤4 sentences,
#              no prohibited characters)
# ---------------------------------------------------------------------------

@given(
    nodes=st.lists(node_strategy, min_size=0, max_size=20),
    entities=st.lists(entity_strategy, min_size=0, max_size=15),
    code_flow_none=st.booleans(),
    er_none=st.booleans(),
)
@settings(max_examples=100)
def test_property_7_summary_fallback_maintains_invariants(
    nodes, entities, code_flow_none, er_none
):
    """
    **Validates: Requirements 3.5, 3.6, 3.7**

    For any error condition from the LLM_Client, the Summary_Generator SHALL
    produce a summary maintaining the existing invariants:
    - ≤500 code points
    - ≤4 sentences
    - No prohibited characters (* # ` _ ~ > <)
    """
    code_flow = None if code_flow_none else CodeFlowResult(nodes=nodes)
    er_result = None if er_none else ERResult(entities=entities)

    # Generator with mock LLM that returns None (error)
    error_client = _make_error_llm_client()
    sg = Summary_Generator(llm_client=error_client)

    result = sg.generate(code_flow, er_result, "/test/path")

    # Invariant 1: ≤500 code points
    assert len(result) <= 500, (
        f"Summary length {len(result)} exceeds 500 code points. "
        f"Summary: {result!r}"
    )

    # Invariant 2: ≤4 sentences
    sentence_count = count_sentences(result)
    assert sentence_count <= 4, (
        f"Summary has {sentence_count} sentences, exceeds max 4. "
        f"Summary: {result!r}"
    )

    # Invariant 3: No prohibited characters
    found_prohibited = set(result) & _PROHIBITED_CHARS
    assert not found_prohibited, (
        f"Summary contains prohibited characters: {found_prohibited}. "
        f"Summary: {result!r}"
    )
