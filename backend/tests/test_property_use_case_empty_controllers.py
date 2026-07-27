"""
Property 2: Controllers without methods are excluded from prompt

For any CodeFlowResult containing a mix of Controller/Route nodes where some
have empty method_names lists, the generated user_prompt string SHALL NOT
contain the labels of controllers that have zero methods.

**Validates: Requirements 1.5**
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from dev_ghost_parser.models import CodeFlowResult, Edge, Node


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Strategy for generating unique labels (prefixed to ensure uniqueness tracking)
_label_alphabet = st.characters(whitelist_categories=("L", "N"), min_codepoint=65, max_codepoint=122)


@st.composite
def st_controller_node(draw, *, has_methods: bool, prefix: str = "Ctrl") -> Node:
    """Generate a Controller or Route node with or without methods."""
    node_type = draw(st.sampled_from(["Controller", "Route"]))
    # Use a unique suffix to guarantee distinguishable labels
    unique_id = draw(st.text(alphabet=_label_alphabet, min_size=3, max_size=10))
    label = f"{prefix}_{unique_id}"
    node_id = f"id_{label}"

    if has_methods:
        methods = draw(
            st.lists(
                st.text(alphabet=_label_alphabet, min_size=2, max_size=12),
                min_size=1,
                max_size=5,
            )
        )
    else:
        methods = []

    return Node(
        id=node_id,
        label=label,
        type=node_type,
        description=f"Description for {label}",
        method_names=methods,
    )


@st.composite
def st_mixed_controllers(draw) -> tuple[list[Node], list[Node]]:
    """Generate a mix of controllers: some with methods, some without.

    Returns (all_controllers, empty_controllers) where empty_controllers
    is the subset with no methods.
    """
    # Ensure at least one with methods and at least one without
    num_with_methods = draw(st.integers(min_value=1, max_value=4))
    num_without_methods = draw(st.integers(min_value=1, max_value=4))

    with_methods = [
        draw(st_controller_node(has_methods=True, prefix="WithMethods"))
        for _ in range(num_with_methods)
    ]
    without_methods = [
        draw(st_controller_node(has_methods=False, prefix="Empty"))
        for _ in range(num_without_methods)
    ]

    all_controllers = with_methods + without_methods
    return all_controllers, without_methods


# ---------------------------------------------------------------------------
# Property Test: Empty controllers excluded from prompt
# ---------------------------------------------------------------------------


class TestProperty2EmptyControllersExcluded:
    """Feature: use-case-generation, Property 2: Empty controllers excluded"""

    @settings(max_examples=100)
    @given(data=st_mixed_controllers())
    def test_empty_controller_labels_not_in_prompt(self, data):
        """Controllers with empty method_names SHALL NOT have their labels
        appear in the generated user_prompt.

        **Validates: Requirements 1.5**
        """
        from dev_ghost_parser.artifacts_generator import Artifacts_Generator

        all_controllers, empty_controllers = data

        # Build a CodeFlowResult with all controllers
        code_flow = CodeFlowResult(nodes=all_controllers, edges=[], errors=[])

        # Instantiate generator (no LLM needed for prompt building)
        generator = Artifacts_Generator(llm_client=None)

        # Call the private method to build the user prompt
        prompt = generator._build_use_case_prompt(code_flow, all_controllers)

        # Verify: labels of empty controllers do NOT appear in the prompt
        for empty_ctrl in empty_controllers:
            assert empty_ctrl.label not in prompt, (
                f"Empty controller label '{empty_ctrl.label}' should NOT appear "
                f"in the prompt, but it was found. Controller has methods: "
                f"{empty_ctrl.method_names!r}. Prompt excerpt: {prompt[:500]}"
            )

    @settings(max_examples=100)
    @given(data=st_mixed_controllers())
    def test_non_empty_controller_labels_present_in_prompt(self, data):
        """Controllers WITH methods SHALL have their labels appear in the
        generated user_prompt (complementary check).

        **Validates: Requirements 1.5**
        """
        from dev_ghost_parser.artifacts_generator import Artifacts_Generator

        all_controllers, empty_controllers = data

        # Identify controllers with methods
        non_empty = [c for c in all_controllers if c not in empty_controllers]

        # Build a CodeFlowResult with all controllers
        code_flow = CodeFlowResult(nodes=all_controllers, edges=[], errors=[])

        # Instantiate generator
        generator = Artifacts_Generator(llm_client=None)

        # Call the private method to build the user prompt
        prompt = generator._build_use_case_prompt(code_flow, all_controllers)

        # Verify: labels of non-empty controllers DO appear in the prompt
        for ctrl in non_empty:
            assert ctrl.label in prompt, (
                f"Non-empty controller label '{ctrl.label}' should appear "
                f"in the prompt but was not found. Methods: {ctrl.method_names!r}. "
                f"Prompt: {prompt[:500]}"
            )
