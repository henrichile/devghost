# Feature: llm-integration-and-hero-redesign, Property 5: Summary Prompt Completeness
"""
Property 5: Summary Prompt Completeness

Validates: Requirements 3.1, 3.2

For any CodeFlowResult containing controller nodes and any ERResult containing entities,
when the LLM_Client is available, the prompt sent to the LLM SHALL contain the controller
names and entity names, AND SHALL include the instruction for a 3-4 sentence Spanish
narrative with a maximum of 450 characters.
"""

from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.models import CodeFlowResult, Entity, ERResult, Node

VALID_TYPES = ["Controller", "Service", "Route", "Middleware", "Repository", "Utility", "Config"]

# --- Strategies ---

# Generate random controller names (non-empty strings without surrogates)
controller_label_strategy = st.text(
    min_size=1,
    max_size=60,
    alphabet=st.characters(blacklist_categories=("Cs",)),
)

# Generate random entity names (non-empty strings without surrogates)
entity_name_strategy = st.text(
    min_size=1,
    max_size=60,
    alphabet=st.characters(blacklist_categories=("Cs",)),
)

# Generate a list of controller nodes (at least 1)
controller_nodes_strategy = st.lists(
    st.builds(
        Node,
        id=st.text(min_size=1, max_size=40),
        label=controller_label_strategy,
        type=st.just("Controller"),
        description=st.just(""),
        method_names=st.lists(st.text(min_size=1, max_size=30), max_size=5),
    ),
    min_size=1,
    max_size=15,
)

# Generate optional non-controller nodes to mix in
other_nodes_strategy = st.lists(
    st.builds(
        Node,
        id=st.text(min_size=1, max_size=40),
        label=st.text(min_size=1, max_size=60, alphabet=st.characters(blacklist_categories=("Cs",))),
        type=st.sampled_from(["Service", "Route", "Middleware", "Repository", "Utility"]),
        description=st.just(""),
        method_names=st.lists(st.text(min_size=1, max_size=30), max_size=5),
    ),
    min_size=0,
    max_size=5,
)

# Generate a list of entities (at least 1)
entities_strategy = st.lists(
    st.builds(
        Entity,
        name=entity_name_strategy,
        attributes=st.just([]),
    ),
    min_size=1,
    max_size=15,
)


@given(
    controller_nodes=controller_nodes_strategy,
    other_nodes=other_nodes_strategy,
    entities=entities_strategy,
)
@settings(max_examples=100)
def test_property_5_summary_prompt_completeness(controller_nodes, other_nodes, entities):
    """
    **Validates: Requirements 3.1, 3.2**

    For any CodeFlowResult containing controller nodes and any ERResult containing
    entities, when the LLM_Client is available, the prompt sent to the LLM SHALL
    contain the controller names and entity names, AND SHALL include the instruction
    for a 3-4 sentence Spanish narrative with a maximum of 450 characters.
    """
    from dev_ghost_parser.summary_generator import Summary_Generator

    # Build CodeFlowResult with controller + other nodes
    all_nodes = controller_nodes + other_nodes
    code_flow = CodeFlowResult(nodes=all_nodes, edges=[])

    # Build ERResult with entities
    er_result = ERResult(entities=entities, relations=[])

    # Create a mock LLM client that captures prompts
    mock_llm_client = MagicMock()
    mock_llm_client.available = True
    # Return a valid summary (contains period, >= 10 chars)
    mock_llm_client.complete.return_value = (
        "El sistema gestiona datos importantes. Incluye controladores."
    )

    generator = Summary_Generator(llm_client=mock_llm_client)
    generator.generate(code_flow, er_result, "/tmp")

    # The mock should have been called exactly once
    assert mock_llm_client.complete.called, "LLM complete() should be called when available"

    call_args = mock_llm_client.complete.call_args
    system_prompt = call_args[0][0]
    user_prompt = call_args[0][1]

    # --- Requirement 3.2: system_prompt SHALL contain "450" (character limit) ---
    assert "450" in system_prompt, (
        f"System prompt must contain '450' (character limit instruction). "
        f"Got system_prompt: {system_prompt!r}"
    )

    # --- Requirement 3.2: system_prompt SHALL reference Spanish or sentences ---
    spanish_ref = (
        "español" in system_prompt.lower()
        or "spanish" in system_prompt.lower()
        or "oraciones" in system_prompt.lower()
    )
    assert spanish_ref, (
        f"System prompt must reference Spanish language or sentences "
        f"('español', 'Spanish', or 'oraciones'). "
        f"Got system_prompt: {system_prompt!r}"
    )

    # --- Requirement 3.1: user_prompt SHALL contain controller names (up to 10) ---
    expected_controllers = [n.label for n in controller_nodes][:10]
    for ctrl_name in expected_controllers:
        assert ctrl_name in user_prompt, (
            f"User prompt must contain controller name {ctrl_name!r}. "
            f"Got user_prompt: {user_prompt!r}"
        )

    # --- Requirement 3.1: user_prompt SHALL contain entity names (up to 10) ---
    expected_entities = [e.name for e in entities][:10]
    for entity_name in expected_entities:
        assert entity_name in user_prompt, (
            f"User prompt must contain entity name {entity_name!r}. "
            f"Got user_prompt: {user_prompt!r}"
        )
