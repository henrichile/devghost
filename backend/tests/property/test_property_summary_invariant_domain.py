# Feature: precision-analysis-enhancements, Property 11: Summary Invariant With Domain Inference
"""
Property 11: Summary Invariant With Domain Inference

Validates: Requirements 6.6

For any combination of CodeFlowResult and ERResult (including cases where
domain inference produces a match), the generated summary SHALL never exceed
500 Unicode code points and SHALL contain at most 4 sentences.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.models import (
    Attribute,
    CodeFlowResult,
    Entity,
    ERResult,
    Node,
)
from dev_ghost_parser.summary_generator import (
    Summary_Generator,
    _DOMAIN_KEYWORD_MAP,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

VALID_TYPES = ["Controller", "Service", "Route", "Middleware", "Repository", "Utility", "Config"]

DOMAIN_KEYWORDS = list(_DOMAIN_KEYWORD_MAP.keys())

_SAFE_ALPHABET = st.characters(
    whitelist_categories=("L", "N"), min_codepoint=65, max_codepoint=122
)

attribute_strategy = st.builds(
    Attribute,
    name=st.text(min_size=1, max_size=20, alphabet=_SAFE_ALPHABET),
    type=st.sampled_from(["string", "integer", "boolean", "float", "DateTime"]),
)

# Entity names that INCLUDE domain keywords (to trigger domain inference)
domain_entity_strategy = st.builds(
    Entity,
    name=st.sampled_from(DOMAIN_KEYWORDS).map(lambda kw: kw.capitalize()),
    attributes=st.lists(attribute_strategy, max_size=5),
    primaryKey=st.just("id"),
)

# Entity names that are generic (no domain keyword match)
generic_entity_strategy = st.builds(
    Entity,
    name=st.sampled_from([
        "Data", "Item", "Record", "Entry", "Model",
        "Element", "Object", "Thing", "Stuff", "Block",
    ]),
    attributes=st.lists(attribute_strategy, max_size=5),
    primaryKey=st.just("id"),
)

# Mix of domain-matching and generic entities
mixed_entity_strategy = st.one_of(domain_entity_strategy, generic_entity_strategy)

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

# Nodes whose labels contain domain keywords (to trigger domain inference via labels)
domain_node_strategy = st.builds(
    Node,
    id=st.text(min_size=1, max_size=40, alphabet=_SAFE_ALPHABET),
    label=st.sampled_from(DOMAIN_KEYWORDS).map(lambda kw: kw.capitalize() + "Manager"),
    type=st.sampled_from(VALID_TYPES),
    description=st.text(min_size=0, max_size=120),
    method_names=st.lists(
        st.text(min_size=1, max_size=20, alphabet=_SAFE_ALPHABET), max_size=5
    ),
)


def count_sentences(text: str) -> int:
    """Count sentences by splitting on '. ' and counting non-empty parts ending with '.'"""
    # Split by ". " to separate sentences, then check the last part
    parts = text.split(". ")
    # Each part except possibly the last should be a sentence
    count = 0
    for part in parts:
        stripped = part.strip()
        if stripped:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Property 11a: Summary with domain-matching entities respects limits
# ---------------------------------------------------------------------------

@given(
    nodes=st.lists(node_strategy, min_size=1, max_size=20),
    entities=st.lists(mixed_entity_strategy, min_size=1, max_size=15),
    code_flow_none=st.booleans(),
    er_none=st.booleans(),
)
@settings(max_examples=100)
def test_property_11_summary_invariant_with_domain(
    nodes, entities, code_flow_none, er_none
):
    """
    **Validates: Requirements 6.6**

    For any combination of CodeFlowResult and ERResult (including None cases
    and cases where domain inference produces a match), the generated summary
    SHALL never exceed 500 Unicode code points and SHALL contain at most 4 sentences.
    """
    code_flow = None if code_flow_none else CodeFlowResult(nodes=nodes)
    er_result = None if er_none else ERResult(entities=entities)

    sg = Summary_Generator()
    result = sg.generate(code_flow, er_result, "/test/path")

    # Check code point limit
    assert len(result) <= 500, (
        f"Summary length {len(result)} exceeds 500 code points. "
        f"Summary: {result!r}"
    )

    # Check sentence count limit
    sentence_count = count_sentences(result)
    assert sentence_count <= 4, (
        f"Summary has {sentence_count} sentences, exceeds max 4. "
        f"Summary: {result!r}"
    )


# ---------------------------------------------------------------------------
# Property 11b: Summary with domain-bearing labels and entities
# ---------------------------------------------------------------------------

@given(
    domain_nodes=st.lists(domain_node_strategy, min_size=1, max_size=10),
    extra_nodes=st.lists(node_strategy, min_size=0, max_size=10),
    domain_entities=st.lists(domain_entity_strategy, min_size=1, max_size=10),
    extra_entities=st.lists(generic_entity_strategy, min_size=0, max_size=5),
)
@settings(max_examples=100)
def test_property_11_summary_invariant_domain_inference_active(
    domain_nodes, extra_nodes, domain_entities, extra_entities
):
    """
    **Validates: Requirements 6.6**

    When domain inference IS active (entities/labels match domain keywords),
    the summary must still respect ≤500 code points and ≤4 sentences.
    """
    all_nodes = domain_nodes + extra_nodes
    all_entities = domain_entities + extra_entities

    code_flow = CodeFlowResult(nodes=all_nodes)
    er_result = ERResult(entities=all_entities)

    sg = Summary_Generator()
    result = sg.generate(code_flow, er_result, "/test/path")

    # Check code point limit
    assert len(result) <= 500, (
        f"Summary length {len(result)} exceeds 500 code points with domain inference. "
        f"Summary: {result!r}"
    )

    # Check sentence count limit
    sentence_count = count_sentences(result)
    assert sentence_count <= 4, (
        f"Summary has {sentence_count} sentences with domain inference, exceeds max 4. "
        f"Summary: {result!r}"
    )


# ---------------------------------------------------------------------------
# Property 11c: Edge case - many entities with long keyword-matching names
# ---------------------------------------------------------------------------

@given(
    nodes=st.lists(
        st.builds(
            Node,
            id=st.text(min_size=1, max_size=40, alphabet=_SAFE_ALPHABET),
            label=st.sampled_from(DOMAIN_KEYWORDS).map(
                lambda kw: kw.capitalize() + "Service"
            ),
            type=st.sampled_from(VALID_TYPES),
            description=st.text(min_size=0, max_size=120),
            method_names=st.just([]),
        ),
        min_size=5,
        max_size=30,
    ),
    entities=st.lists(
        st.builds(
            Entity,
            name=st.sampled_from(DOMAIN_KEYWORDS).map(
                lambda kw: "Sistema" + kw.capitalize() + "Principal"
            ),
            attributes=st.lists(attribute_strategy, max_size=5),
            primaryKey=st.just("id"),
        ),
        min_size=5,
        max_size=20,
    ),
)
@settings(max_examples=100)
def test_property_11_summary_invariant_many_domain_matches(nodes, entities):
    """
    **Validates: Requirements 6.6**

    Edge case: Many nodes and entities whose names match domain keywords,
    potentially triggering a long domain inference sentence. The summary
    must still respect ≤500 code points and ≤4 sentences.
    """
    code_flow = CodeFlowResult(nodes=nodes)
    er_result = ERResult(entities=entities)

    sg = Summary_Generator()
    result = sg.generate(code_flow, er_result, "/test/path")

    # Check code point limit
    assert len(result) <= 500, (
        f"Summary length {len(result)} exceeds 500 code points with many domain matches. "
        f"Summary: {result!r}"
    )

    # Check sentence count limit
    sentence_count = count_sentences(result)
    assert sentence_count <= 4, (
        f"Summary has {sentence_count} sentences with many domain matches, exceeds max 4. "
        f"Summary: {result!r}"
    )
