# Feature: llm-integration-and-hero-redesign, Property 9: Heuristic Equivalence When LLM Unavailable
"""
Property 9: Heuristic Equivalence When LLM Unavailable

Validates: Requirements 4.5

For any valid CodeFlowResult and ERResult combination, when the LLM_Client has
available == False, the system SHALL produce output identical to the output
produced by the current heuristic-only implementation (Description_Generator
and Summary_Generator without LLM).
"""

from __future__ import annotations

from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.description_generator import Description_Generator
from dev_ghost_parser.llm_client import LLM_Client
from dev_ghost_parser.models import (
    CodeFlowResult,
    Entity,
    ERResult,
    FileContext,
    Node,
)
from dev_ghost_parser.summary_generator import Summary_Generator

# ---------------------------------------------------------------------------
# Valid node types
# ---------------------------------------------------------------------------

VALID_NODE_TYPES = [
    "Controller",
    "Service",
    "Route",
    "Middleware",
    "Repository",
    "Utility",
    "Config",
]

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

method_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "Nd", "Pc")),
    min_size=1,
    max_size=30,
)

label_strategy = st.text(min_size=1, max_size=60)

node_strategy = st.builds(
    Node,
    id=st.text(min_size=1, max_size=40),
    label=label_strategy,
    type=st.sampled_from(VALID_NODE_TYPES),
    description=st.just(""),
    method_names=st.lists(method_name_strategy, max_size=10),
)

file_context_strategy = st.builds(
    FileContext,
    imports=st.lists(st.text(min_size=1, max_size=60), max_size=10),
    class_name=st.one_of(st.none(), st.text(min_size=1, max_size=40)),
    method_names=st.lists(method_name_strategy, max_size=10),
)

optional_file_context_strategy = st.one_of(st.none(), file_context_strategy)

entity_strategy = st.builds(
    Entity,
    name=st.text(min_size=1, max_size=40),
    attributes=st.just([]),
)

code_flow_result_strategy = st.builds(
    CodeFlowResult,
    nodes=st.lists(node_strategy, min_size=0, max_size=8),
    edges=st.just([]),
    errors=st.just([]),
)

er_result_strategy = st.builds(
    ERResult,
    entities=st.lists(entity_strategy, min_size=0, max_size=8),
    relations=st.just([]),
    errors=st.just([]),
)


# ---------------------------------------------------------------------------
# Helper: create an unavailable LLM_Client (without needing env vars)
# ---------------------------------------------------------------------------


def _make_unavailable_llm_client() -> LLM_Client:
    """Create an LLM_Client instance that has available == False."""
    with patch.dict("os.environ", {"LLM_API_KEY": ""}, clear=False):
        client = LLM_Client()
    assert not client.available
    return client


# ---------------------------------------------------------------------------
# Property Test: Description_Generator heuristic equivalence
# ---------------------------------------------------------------------------


@given(
    node=node_strategy,
    file_context=optional_file_context_strategy,
)
@settings(max_examples=100)
def test_property_9_description_heuristic_equivalence(node, file_context):
    """
    **Validates: Requirements 4.5**

    For any valid Node and FileContext, when the LLM_Client has available == False,
    Description_Generator SHALL produce output identical to Description_Generator
    with llm_client=None (pure heuristic).
    """
    unavailable_client = _make_unavailable_llm_client()

    # Generator with unavailable LLM client
    gen_with_unavailable = Description_Generator(llm_client=unavailable_client)
    result_unavailable = gen_with_unavailable.generate(node, file_context)

    # Generator with no LLM client (pure heuristic)
    gen_heuristic_only = Description_Generator(llm_client=None)
    result_heuristic = gen_heuristic_only.generate(node, file_context)

    assert result_unavailable == result_heuristic, (
        f"Description mismatch when LLM unavailable.\n"
        f"With unavailable client: {result_unavailable!r}\n"
        f"With no client (heuristic): {result_heuristic!r}\n"
        f"Node: label={node.label!r}, type={node.type!r}, methods={node.method_names!r}\n"
        f"FileContext: {file_context!r}"
    )


# ---------------------------------------------------------------------------
# Property Test: Summary_Generator heuristic equivalence
# ---------------------------------------------------------------------------


@given(
    code_flow=code_flow_result_strategy,
    er_result=er_result_strategy,
)
@settings(max_examples=100)
def test_property_9_summary_heuristic_equivalence(code_flow, er_result):
    """
    **Validates: Requirements 4.5**

    For any valid CodeFlowResult and ERResult, when the LLM_Client has
    available == False, Summary_Generator SHALL produce output identical to
    Summary_Generator with llm_client=None (pure heuristic).
    """
    unavailable_client = _make_unavailable_llm_client()

    root_path = "/tmp/test_project"

    # Generator with unavailable LLM client
    gen_with_unavailable = Summary_Generator(llm_client=unavailable_client)
    result_unavailable = gen_with_unavailable.generate(code_flow, er_result, root_path)

    # Generator with no LLM client (pure heuristic)
    gen_heuristic_only = Summary_Generator(llm_client=None)
    result_heuristic = gen_heuristic_only.generate(code_flow, er_result, root_path)

    assert result_unavailable == result_heuristic, (
        f"Summary mismatch when LLM unavailable.\n"
        f"With unavailable client: {result_unavailable!r}\n"
        f"With no client (heuristic): {result_heuristic!r}\n"
        f"CodeFlow nodes: {len(code_flow.nodes)}, "
        f"ER entities: {len(er_result.entities)}"
    )
