# Feature: llm-integration-and-hero-redesign, Property 2: Description Prompt Completeness
"""
Property 2: Description Prompt Completeness

Validates: Requirements 2.1, 2.2

For any Node with a label, type, and method_names list, when the LLM_Client is available,
the prompt sent to the LLM SHALL contain the node's label, the node's type, and all method
names (up to 10), AND SHALL include the instruction for a Spanish description with a maximum
of 90 characters.
"""

from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.description_generator import Description_Generator
from dev_ghost_parser.models import FileContext, Node

VALID_TYPES = ["Controller", "Service", "Route", "Middleware", "Repository", "Utility", "Config"]

# --- Strategies ---

node_strategy = st.builds(
    Node,
    id=st.text(min_size=1, max_size=40),
    label=st.text(min_size=1, max_size=100, alphabet=st.characters(blacklist_categories=("Cs",))),
    type=st.sampled_from(VALID_TYPES),
    description=st.just(""),
    method_names=st.lists(
        st.text(min_size=1, max_size=50, alphabet=st.characters(blacklist_categories=("Cs",))),
        min_size=0,
        max_size=15,
    ),
)

file_context_strategy = st.builds(
    FileContext,
    imports=st.lists(st.text(min_size=0, max_size=80), max_size=10),
    class_name=st.one_of(st.none(), st.text(min_size=1, max_size=60)),
    method_names=st.lists(st.text(min_size=0, max_size=50), max_size=10),
)


@given(node=node_strategy, file_context=st.one_of(st.none(), file_context_strategy))
@settings(max_examples=100)
def test_property_2_description_prompt_completeness(node, file_context):
    """
    **Validates: Requirements 2.1, 2.2**

    For any Node with a label, type, and method_names list, when the LLM_Client is
    available, the prompt sent to the LLM SHALL contain the node's label, the node's
    type, and all method names (up to 10), AND SHALL include the instruction for a
    Spanish description with a maximum of 90 characters.
    """
    # Create a mock LLM client that captures prompts
    mock_llm_client = MagicMock()
    mock_llm_client.available = True
    # Return a valid description so the LLM path is exercised
    mock_llm_client.complete.return_value = "Descripción generada por LLM válida"

    generator = Description_Generator(llm_client=mock_llm_client)
    generator.generate(node, file_context)

    # The mock should have been called exactly once
    assert mock_llm_client.complete.called, "LLM complete() should be called when available"

    call_args = mock_llm_client.complete.call_args
    system_prompt = call_args[0][0]
    user_prompt = call_args[0][1]

    # Requirement 2.1: user_prompt SHALL contain the node's label
    assert node.label in user_prompt, (
        f"User prompt must contain node label {node.label!r}. "
        f"Got user_prompt: {user_prompt!r}"
    )

    # Requirement 2.1: user_prompt SHALL contain the node's type
    assert node.type in user_prompt, (
        f"User prompt must contain node type {node.type!r}. "
        f"Got user_prompt: {user_prompt!r}"
    )

    # Requirement 2.1: user_prompt SHALL contain all method names (up to first 10)
    # Method names come from file_context if available, else from node
    expected_methods: list[str] = []
    if file_context and file_context.method_names:
        expected_methods = file_context.method_names[:10]
    elif node.method_names:
        expected_methods = node.method_names[:10]

    for method_name in expected_methods:
        assert method_name in user_prompt, (
            f"User prompt must contain method name {method_name!r}. "
            f"Got user_prompt: {user_prompt!r}"
        )

    # Requirement 2.2: system_prompt SHALL include instruction for max 90 characters
    assert "90" in system_prompt, (
        f"System prompt must contain '90' (character limit instruction). "
        f"Got system_prompt: {system_prompt!r}"
    )

    # Requirement 2.2: system_prompt SHALL reference Spanish language
    spanish_ref = "español" in system_prompt.lower() or "spanish" in system_prompt.lower()
    assert spanish_ref, (
        f"System prompt must reference Spanish language ('español' or 'Spanish'). "
        f"Got system_prompt: {system_prompt!r}"
    )
