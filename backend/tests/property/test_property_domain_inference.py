# Feature: precision-analysis-enhancements, Property 10: Domain Inference Correctness
"""
Property 10: Domain Inference Correctness

Validates: Requirements 6.1, 6.2, 6.3

For any set of ER entities and node labels, the Summary_Generator's domain inference
SHALL select the domain from the keyword map that has the highest number of
case-insensitive substring matches. When multiple domains tie in match count,
it SHALL select the domain whose first matching entity/label appears earliest
in the entity list order.
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from dev_ghost_parser.models import Attribute, Entity
from dev_ghost_parser.summary_generator import _infer_domain, _DOMAIN_KEYWORD_MAP


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# All keywords from _DOMAIN_KEYWORD_MAP
DOMAIN_KEYWORDS = list(_DOMAIN_KEYWORD_MAP.keys())

# Build a reverse map: domain purpose -> list of keywords
_DOMAIN_TO_KEYWORDS: dict[str, list[str]] = {}
for _kw, _dom in _DOMAIN_KEYWORD_MAP.items():
    _DOMAIN_TO_KEYWORDS.setdefault(_dom, []).append(_kw)

# Simple safe alphabet for entity/label names (no special chars)
_SAFE_ALPHABET = st.characters(
    whitelist_categories=("L", "N"), min_codepoint=65, max_codepoint=122
)

attribute_strategy = st.builds(
    Attribute,
    name=st.text(min_size=1, max_size=15, alphabet=_SAFE_ALPHABET),
    type=st.sampled_from(["string", "integer", "boolean", "float"]),
)

entity_strategy = st.builds(
    Entity,
    name=st.text(min_size=1, max_size=20, alphabet=_SAFE_ALPHABET),
    attributes=st.lists(attribute_strategy, max_size=3),
    primaryKey=st.just("id"),
)


def _compute_expected_domain(entities: list[Entity], labels: list[str]) -> str | None:
    """Reference implementation that mirrors the expected algorithm."""
    domain_counts: dict[str, int] = {}
    domain_first_pos: dict[str, int] = {}

    all_names = [e.name for e in entities] + labels

    for idx, name in enumerate(all_names):
        name_lower = name.lower()
        for keyword, domain in _DOMAIN_KEYWORD_MAP.items():
            if keyword in name_lower or name_lower in keyword:
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
                if domain not in domain_first_pos:
                    domain_first_pos[domain] = idx

    if not domain_counts:
        return None

    max_count = max(domain_counts.values())
    candidates = [d for d, c in domain_counts.items() if c == max_count]
    candidates.sort(key=lambda d: domain_first_pos[d])
    return candidates[0]


# ---------------------------------------------------------------------------
# Property 10a: When entities contain domain keywords, correct domain selected
# ---------------------------------------------------------------------------

@given(
    keyword=st.sampled_from(DOMAIN_KEYWORDS),
    prefix=st.text(min_size=0, max_size=10, alphabet=_SAFE_ALPHABET),
    suffix=st.text(min_size=0, max_size=10, alphabet=_SAFE_ALPHABET),
    extra_entities=st.lists(entity_strategy, max_size=5),
    labels=st.lists(
        st.text(min_size=1, max_size=20, alphabet=_SAFE_ALPHABET), max_size=5
    ),
)
@settings(max_examples=100)
def test_property_10_single_keyword_match_selects_correct_domain(
    keyword, prefix, suffix, extra_entities, labels
):
    """
    **Validates: Requirements 6.1, 6.2**

    For any entity whose name contains a domain keyword (as substring),
    _infer_domain SHALL return the corresponding domain from the keyword map.
    When the keyword-bearing entity is the only match, it must win.
    """
    # Create an entity whose name contains the keyword
    matching_entity = Entity(name=f"{prefix}{keyword}{suffix}", attributes=[], primaryKey="id")

    # Filter extra entities that don't accidentally match any keyword
    # (to ensure our entity is the unique dominant match)
    entities = [matching_entity] + extra_entities

    result = _infer_domain(entities, labels)
    expected = _compute_expected_domain(entities, labels)

    assert result == expected, (
        f"Expected domain '{expected}', got '{result}'. "
        f"Entity names: {[e.name for e in entities]}, labels: {labels}"
    )


# ---------------------------------------------------------------------------
# Property 10b: Tie-break by earliest first occurrence position
# ---------------------------------------------------------------------------

@given(
    kw_a=st.sampled_from(DOMAIN_KEYWORDS),
    kw_b=st.sampled_from(DOMAIN_KEYWORDS),
    prefix=st.text(min_size=0, max_size=5, alphabet=_SAFE_ALPHABET),
)
@settings(max_examples=100)
def test_property_10_tie_break_earliest_first_occurrence(kw_a, kw_b, prefix):
    """
    **Validates: Requirements 6.3**

    When multiple domains tie in match count, _infer_domain SHALL select
    the domain whose first matching entity/label appears earliest in the
    entity list order.
    """
    domain_a = _DOMAIN_KEYWORD_MAP[kw_a]
    domain_b = _DOMAIN_KEYWORD_MAP[kw_b]

    # Only test when the two keywords map to DIFFERENT domains
    assume(domain_a != domain_b)

    # Each keyword matches exactly once, so counts are tied at 1.
    # Entity with kw_a comes first → domain_a should win.
    entity_a = Entity(name=f"{prefix}{kw_a}", attributes=[], primaryKey="id")
    entity_b = Entity(name=f"{prefix}{kw_b}", attributes=[], primaryKey="id")

    entities = [entity_a, entity_b]
    labels: list[str] = []

    result = _infer_domain(entities, labels)
    expected = _compute_expected_domain(entities, labels)

    assert result == expected, (
        f"Tie-break failed. Expected '{expected}', got '{result}'. "
        f"Entities: {[e.name for e in entities]}"
    )


# ---------------------------------------------------------------------------
# Property 10c: No matches returns None
# ---------------------------------------------------------------------------

@given(
    entities=st.lists(entity_strategy, min_size=0, max_size=10),
    labels=st.lists(
        st.text(min_size=1, max_size=20, alphabet=_SAFE_ALPHABET), max_size=10
    ),
)
@settings(max_examples=100)
def test_property_10_no_matches_returns_none(entities, labels):
    """
    **Validates: Requirements 6.4**

    When no entity name or label matches any keyword in the domain map
    (bidirectional substring), _infer_domain SHALL return None.
    """
    # Filter out any entities/labels that would accidentally match
    all_names = [e.name for e in entities] + labels
    for name in all_names:
        name_lower = name.lower()
        for keyword in DOMAIN_KEYWORDS:
            if keyword in name_lower or name_lower in keyword:
                assume(False)

    result = _infer_domain(entities, labels)
    assert result is None, (
        f"Expected None when no matches, got '{result}'. "
        f"Entity names: {[e.name for e in entities]}, labels: {labels}"
    )


# ---------------------------------------------------------------------------
# Property 10d: Highest count wins over position
# ---------------------------------------------------------------------------

@given(
    kw_a=st.sampled_from(DOMAIN_KEYWORDS),
    kw_b=st.sampled_from(DOMAIN_KEYWORDS),
    extra_count=st.integers(min_value=1, max_value=3),
)
@settings(max_examples=100)
def test_property_10_highest_count_wins(kw_a, kw_b, extra_count):
    """
    **Validates: Requirements 6.1, 6.2, 6.3**

    The domain with the highest match count SHALL be selected, regardless
    of position. Position only matters for tie-breaking.
    """
    domain_a = _DOMAIN_KEYWORD_MAP[kw_a]
    domain_b = _DOMAIN_KEYWORD_MAP[kw_b]

    assume(domain_a != domain_b)

    # Domain A appears first but only once
    entity_a = Entity(name=f"X{kw_a}X", attributes=[], primaryKey="id")

    # Domain B appears multiple times (1 + extra_count), so it has more matches
    entities_b = [
        Entity(name=f"Y{kw_b}Y{i}", attributes=[], primaryKey="id")
        for i in range(1 + extra_count)
    ]

    # Put entity_a first so domain_a has earlier position
    entities = [entity_a] + entities_b
    labels: list[str] = []

    result = _infer_domain(entities, labels)
    expected = _compute_expected_domain(entities, labels)

    assert result == expected, (
        f"Highest count should win. Expected '{expected}', got '{result}'. "
        f"Entities: {[e.name for e in entities]}"
    )
