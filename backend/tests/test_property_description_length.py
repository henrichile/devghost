"""
Property 13: Project description length constraint

For any repository analysis that produces a project description,
the description length SHALL be at most 500 characters.

**Validates: Requirements 6.4**
"""

import pytest
from hypothesis import given, settings, strategies as st

from dev_ghost_parser.agent_models import (
    SystemReportResult,
    TechStack,
    TechStackEntry,
)
from dev_ghost_parser.agents.system_reporter_agent import SystemReporterAgent


# ---------------------------------------------------------------------------
# Strategies for generating TechStack entries
# ---------------------------------------------------------------------------

CATEGORIES = ["language", "framework", "database", "infrastructure"]

SAMPLE_LANGUAGES = [
    "Python", "JavaScript", "TypeScript", "Rust", "Go", "Java",
    "PHP", "Ruby", "Kotlin", "C#", "C++", "Swift", "Dart",
]

SAMPLE_FRAMEWORKS = [
    "FastAPI", "Django", "Flask", "React", "Next.js", "Express",
    "Vue.js", "Angular", "NestJS", "Ruby on Rails", "Laravel",
    "Spring Boot", "Svelte", "Nuxt.js",
]

SAMPLE_DATABASES = [
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "SQLite",
    "Cassandra", "DynamoDB", "Neo4j",
]

SAMPLE_INFRASTRUCTURE = [
    "Docker", "Kubernetes", "Make", "Terraform", "Ansible",
    "Nginx", "AWS Lambda", "GitHub Actions",
]


@st.composite
def tech_stack_entry_strategy(draw):
    """Generate a random TechStackEntry with valid category and name."""
    category = draw(st.sampled_from(CATEGORIES))

    if category == "language":
        name = draw(st.sampled_from(SAMPLE_LANGUAGES))
    elif category == "framework":
        name = draw(st.sampled_from(SAMPLE_FRAMEWORKS))
    elif category == "database":
        name = draw(st.sampled_from(SAMPLE_DATABASES))
    else:
        name = draw(st.sampled_from(SAMPLE_INFRASTRUCTURE))

    description = draw(st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z")),
        min_size=0,
        max_size=100,
    ))

    return TechStackEntry(name=name, category=category, description=description)


@st.composite
def tech_stack_strategy(draw):
    """Generate a TechStack with 0-10 random entries."""
    entries = draw(st.lists(tech_stack_entry_strategy(), min_size=0, max_size=10))
    return TechStack(entries=entries)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestProperty13DescriptionLengthConstraint:
    """Feature: agent-streaming-reporting, Property 13: Project description length constraint"""

    @settings(max_examples=100)
    @given(tech_stack=tech_stack_strategy())
    def test_heuristic_description_never_exceeds_500_chars(self, tech_stack: TechStack):
        """The heuristic description SHALL never exceed 500 characters.

        **Validates: Requirements 6.4**
        """
        agent = SystemReporterAgent.__new__(SystemReporterAgent)
        description = agent._heuristic_description(tech_stack)

        assert len(description) <= 500, (
            f"Heuristic description exceeds 500 chars: got {len(description)} chars. "
            f"Description: {description!r}"
        )

    @settings(max_examples=100)
    @given(tech_stack=tech_stack_strategy())
    def test_heuristic_description_is_non_empty(self, tech_stack: TechStack):
        """The heuristic description SHALL always produce a non-empty string.

        **Validates: Requirements 6.4**
        """
        agent = SystemReporterAgent.__new__(SystemReporterAgent)
        description = agent._heuristic_description(tech_stack)

        assert len(description) > 0, "Heuristic description should not be empty"

    @settings(max_examples=100)
    @given(
        description=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z")),
            min_size=0,
            max_size=500,
        )
    )
    def test_system_report_result_accepts_descriptions_up_to_500_chars(
        self, description: str
    ):
        """SystemReportResult SHALL accept descriptions of 0-500 characters.

        **Validates: Requirements 6.4**
        """
        result = SystemReportResult(
            tech_stack=TechStack(entries=[]),
            setup_instructions="## Setup\nRun it.",
            project_description=description,
        )
        assert len(result.project_description) <= 500

    @settings(max_examples=100)
    @given(
        extra_length=st.integers(min_value=1, max_value=1000)
    )
    def test_system_report_result_rejects_descriptions_over_500_chars(
        self, extra_length: int
    ):
        """SystemReportResult SHALL raise ValueError for descriptions > 500 chars.

        **Validates: Requirements 6.4**
        """
        description = "x" * (500 + extra_length)
        with pytest.raises(ValueError, match="at most 500 characters"):
            SystemReportResult(
                tech_stack=TechStack(entries=[]),
                setup_instructions="## Setup\nRun it.",
                project_description=description,
            )

    @settings(max_examples=100)
    @given(
        length=st.sampled_from([499, 500, 501])
    )
    def test_system_report_result_boundary_values(self, length: int):
        """SystemReportResult boundary: 499 and 500 OK, 501 raises ValueError.

        **Validates: Requirements 6.4**
        """
        description = "a" * length

        if length <= 500:
            result = SystemReportResult(
                tech_stack=TechStack(entries=[]),
                setup_instructions="## Setup\nRun it.",
                project_description=description,
            )
            assert len(result.project_description) == length
        else:
            with pytest.raises(ValueError, match="at most 500 characters"):
                SystemReportResult(
                    tech_stack=TechStack(entries=[]),
                    setup_instructions="## Setup\nRun it.",
                    project_description=description,
                )
