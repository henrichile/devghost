# Feature: llm-integration-and-hero-redesign, Property 4: Description Fallback on LLM Error
"""
Property 4: Description Fallback on LLM Error

Validates: Requirements 2.5, 2.6, 2.7

For any error condition from the LLM_Client (timeout, network error, HTTP error,
empty/whitespace response), the Description_Generator SHALL produce a non-empty
description using the existing heuristic logic, identical to what would be produced
without LLM integration.
"""

from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.description_generator import Description_Generator
from dev_ghost_parser.models import FileContext, Node, NodeType

VALID_TYPES: list[NodeType] = [
    "Controller", "Service", "Route", "Middleware", "Repository", "Utility", "Config"
]

# --- Strategies ---

node_strategy = st.builds(
    Node,
    id=st.text(min_size=1, max_size=40),
    label=st.text(min_size=1, max_size=100),
    type=st.sampled_from(VALID_TYPES),
    description=st.just(""),
    method_names=st.lists(st.text(min_size=1, max_size=50), max_size=10),
)

file_context_strategy = st.builds(
    FileContext,
    imports=st.lists(st.text(min_size=1, max_size=80), max_size=10),
    class_name=st.one_of(st.none(), st.text(min_size=1, max_size=60)),
    method_names=st.lists(st.text(min_size=1, max_size=50), max_size=10),
)

optional_file_context_strategy = st.one_of(st.none(), file_context_strategy)


def _make_error_llm_client(complete_return_value=None):
    """Create a mock LLM_Client that is available but returns error (None)."""
    mock_client = MagicMock()
    mock_client.available = True
    mock_client.complete.return_value = complete_return_value
    return mock_client


def _make_unavailable_llm_client():
    """Create a mock LLM_Client that has available=False."""
    mock_client = MagicMock()
    mock_client.available = False
    return mock_client


@given(
    node=node_strategy,
    file_context=optional_file_context_strategy,
)
@settings(max_examples=100)
def test_property_4_fallback_on_llm_returning_none(node, file_context):
    """
    **Validates: Requirements 2.5, 2.6, 2.7**

    When LLM_Client.complete() returns None (simulating timeout, network error,
    HTTP error), the Description_Generator produces output identical to heuristic-only mode.
    """
    # Generator with LLM that returns None (error simulation)
    error_client = _make_error_llm_client(complete_return_value=None)
    gen_with_error_llm = Description_Generator(llm_client=error_client)

    # Generator with no LLM (heuristic-only)
    gen_heuristic_only = Description_Generator(llm_client=None)

    result_with_error = gen_with_error_llm.generate(node, file_context)
    result_heuristic = gen_heuristic_only.generate(node, file_context)

    assert result_with_error == result_heuristic, (
        f"Fallback output differs from heuristic-only.\n"
        f"With error LLM: {result_with_error!r}\n"
        f"Heuristic only: {result_heuristic!r}\n"
        f"Node: label={node.label!r}, type={node.type!r}, methods={node.method_names!r}\n"
        f"FileContext: {file_context!r}"
    )
    assert len(result_with_error) > 0, "Description must be non-empty"


@given(
    node=node_strategy,
    file_context=optional_file_context_strategy,
)
@settings(max_examples=100)
def test_property_4_fallback_on_llm_unavailable(node, file_context):
    """
    **Validates: Requirements 2.5, 2.6, 2.7**

    When LLM_Client.available is False, the Description_Generator produces output
    identical to heuristic-only mode (no LLM client at all).
    """
    # Generator with unavailable LLM
    unavailable_client = _make_unavailable_llm_client()
    gen_with_unavailable = Description_Generator(llm_client=unavailable_client)

    # Generator with no LLM (heuristic-only)
    gen_heuristic_only = Description_Generator(llm_client=None)

    result_unavailable = gen_with_unavailable.generate(node, file_context)
    result_heuristic = gen_heuristic_only.generate(node, file_context)

    assert result_unavailable == result_heuristic, (
        f"Unavailable LLM output differs from heuristic-only.\n"
        f"With unavailable LLM: {result_unavailable!r}\n"
        f"Heuristic only: {result_heuristic!r}\n"
        f"Node: label={node.label!r}, type={node.type!r}, methods={node.method_names!r}\n"
        f"FileContext: {file_context!r}"
    )
    assert len(result_unavailable) > 0, "Description must be non-empty"


@given(
    node=node_strategy,
    file_context=optional_file_context_strategy,
    whitespace=st.sampled_from(["", " ", "  ", "\t", "\n", "  \n\t  "]),
)
@settings(max_examples=100)
def test_property_4_fallback_on_empty_or_whitespace_response(node, file_context, whitespace):
    """
    **Validates: Requirements 2.5, 2.6, 2.7**

    When LLM_Client.complete() returns an empty string or whitespace-only string,
    the Description_Generator produces output identical to heuristic-only mode.
    """
    # Generator with LLM that returns empty/whitespace
    error_client = _make_error_llm_client(complete_return_value=whitespace)
    gen_with_error_llm = Description_Generator(llm_client=error_client)

    # Generator with no LLM (heuristic-only)
    gen_heuristic_only = Description_Generator(llm_client=None)

    result_with_error = gen_with_error_llm.generate(node, file_context)
    result_heuristic = gen_heuristic_only.generate(node, file_context)

    assert result_with_error == result_heuristic, (
        f"Empty/whitespace LLM response output differs from heuristic-only.\n"
        f"LLM returned: {whitespace!r}\n"
        f"With error LLM: {result_with_error!r}\n"
        f"Heuristic only: {result_heuristic!r}\n"
        f"Node: label={node.label!r}, type={node.type!r}, methods={node.method_names!r}\n"
        f"FileContext: {file_context!r}"
    )
    assert len(result_with_error) > 0, "Description must be non-empty"
