"""
Property 3: Result merging completeness

For any set of agent results (each containing distinct data fields), the merged
AnalysisResult SHALL contain all fields from all successful agents with no data
loss or field collision.

Validates: Requirements 1.4
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from hypothesis import given, settings, strategies as st

from dev_ghost_parser.agent_models import AgentResult, AnalysisResult
from dev_ghost_parser.base_agent import AgentContext, BaseAgent
from dev_ghost_parser.orchestrator import AgentOrchestrator, _AGENT_RESULT_FIELD_MAP


# ---------------------------------------------------------------------------
# Valid agent identifiers and their corresponding AnalysisResult fields
# ---------------------------------------------------------------------------

AGENT_NAMES = list(_AGENT_RESULT_FIELD_MAP.keys())
RESULT_FIELDS = list(_AGENT_RESULT_FIELD_MAP.values())


# ---------------------------------------------------------------------------
# FakeAgent for property-based testing
# ---------------------------------------------------------------------------


class FakeAgent(BaseAgent):
    """A configurable agent that succeeds with the given data."""

    def __init__(self, name: str, data: dict) -> None:
        super().__init__()
        self.name = name
        self.description = f"Fake {name} agent"
        self._data = data

    async def execute(self, context: AgentContext) -> AgentResult:
        await self.emit_progress(f"{self.name} processing...")
        return AgentResult(
            agent_name=self.name,
            success=True,
            data=self._data,
        )


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Strategy for generating agent data dictionaries with random content
agent_data_strategy = st.dictionaries(
    keys=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=20,
    ),
    values=st.one_of(
        st.text(min_size=0, max_size=50),
        st.integers(min_value=-1000, max_value=1000),
        st.floats(allow_nan=False, allow_infinity=False),
        st.booleans(),
        st.lists(st.integers(min_value=0, max_value=100), max_size=5),
    ),
    min_size=1,
    max_size=5,
)


@st.composite
def agent_configs_strategy(draw):
    """Generate 1-5 agent configurations, each with a unique agent name and random data.

    Returns a list of (agent_name, data_dict) tuples.
    """
    # Draw a subset of agent names (1 to 5)
    num_agents = draw(st.integers(min_value=1, max_value=5))
    selected_agents = draw(
        st.lists(
            st.sampled_from(AGENT_NAMES),
            min_size=num_agents,
            max_size=num_agents,
            unique=True,
        )
    )

    configs = []
    for agent_name in selected_agents:
        data = draw(agent_data_strategy)
        configs.append((agent_name, data))

    return configs


# ---------------------------------------------------------------------------
# Property Test: Result merging completeness
# ---------------------------------------------------------------------------


class TestProperty3ResultMergingCompleteness:
    """Feature: agent-streaming-reporting, Property 3: Result merging completeness"""

    @settings(max_examples=100)
    @given(agent_configs=agent_configs_strategy())
    def test_property_3_merged_output_contains_all_fields(
        self,
        agent_configs: list[tuple[str, dict]],
    ):
        """For any set of successful agents, the merged AnalysisResult contains
        all fields from all agents with no data loss.

        **Validates: Requirements 1.4**
        """

        async def _run():
            event_queue: asyncio.Queue = asyncio.Queue()
            mock_llm = MagicMock()

            orch = AgentOrchestrator(
                repo_path="/tmp/test_repo",
                llm_client=mock_llm,
                event_queue=event_queue,
                max_concurrency=5,
                timeout_seconds=30.0,
            )

            # Register all agents with their generated data
            for agent_name, data in agent_configs:
                orch.register_agent(FakeAgent(name=agent_name, data=data))

            # Run orchestrator
            result = await orch.run_all()
            return result

        result = asyncio.run(_run())

        # Verify: no errors since all agents succeed
        assert result.errors == [], f"Expected no errors but got: {result.errors}"

        # Verify: each agent's data maps to the correct AnalysisResult field
        for agent_name, data in agent_configs:
            expected_field = _AGENT_RESULT_FIELD_MAP[agent_name]
            actual_value = getattr(result, expected_field)
            assert actual_value == data, (
                f"Agent '{agent_name}' data not found in field '{expected_field}'. "
                f"Expected {data!r}, got {actual_value!r}"
            )

    @settings(max_examples=100)
    @given(agent_configs=agent_configs_strategy())
    def test_property_3_no_field_collision(
        self,
        agent_configs: list[tuple[str, dict]],
    ):
        """Each agent's data maps to a distinct field — no data overwrites another
        agent's result.

        **Validates: Requirements 1.4**
        """

        async def _run():
            event_queue: asyncio.Queue = asyncio.Queue()
            mock_llm = MagicMock()

            orch = AgentOrchestrator(
                repo_path="/tmp/test_repo",
                llm_client=mock_llm,
                event_queue=event_queue,
                max_concurrency=5,
                timeout_seconds=30.0,
            )

            for agent_name, data in agent_configs:
                orch.register_agent(FakeAgent(name=agent_name, data=data))

            result = await orch.run_all()
            return result

        result = asyncio.run(_run())

        # Verify: fields not corresponding to any registered agent remain None
        registered_fields = {
            _AGENT_RESULT_FIELD_MAP[name] for name, _ in agent_configs
        }
        all_fields = set(RESULT_FIELDS)
        unset_fields = all_fields - registered_fields

        for field_name in unset_fields:
            assert getattr(result, field_name) is None, (
                f"Field '{field_name}' should be None (no agent produced it) "
                f"but got {getattr(result, field_name)!r}"
            )

    @settings(max_examples=100)
    @given(agent_configs=agent_configs_strategy())
    def test_property_3_result_type_is_analysis_result(
        self,
        agent_configs: list[tuple[str, dict]],
    ):
        """The merged output is always an AnalysisResult instance regardless of
        agent count or data content.

        **Validates: Requirements 1.4**
        """

        async def _run():
            event_queue: asyncio.Queue = asyncio.Queue()
            mock_llm = MagicMock()

            orch = AgentOrchestrator(
                repo_path="/tmp/test_repo",
                llm_client=mock_llm,
                event_queue=event_queue,
                max_concurrency=5,
                timeout_seconds=30.0,
            )

            for agent_name, data in agent_configs:
                orch.register_agent(FakeAgent(name=agent_name, data=data))

            return await orch.run_all()

        result = asyncio.run(_run())
        assert isinstance(result, AnalysisResult)
