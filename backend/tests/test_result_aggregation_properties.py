# Feature: sub-agent-parallel-analysis, Property 12: Result Merge Preserves All Successful Agent Data
# Feature: sub-agent-parallel-analysis, Property 13: Priority-Based Conflict Resolution
"""
Property-based tests for result aggregation in DependencyGraphOrchestrator.

Tests result merging behavior using randomly generated agent results:
- Property 12: Merging successful AgentResults preserves all data without loss
- Property 13: When two agents produce data for the same field, higher priority wins

Validates: Requirements 8.1, 8.3, 8.4
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from dev_ghost_parser.agent_models import AgentEvent, AgentResult, AnalysisResult
from dev_ghost_parser.base_agent import AgentContext, BaseAgent
from dev_ghost_parser.graph_orchestrator import (
    AGENT_FIELD_MAP,
    AGENT_PRIORITY,
    DependencyGraphOrchestrator,
)
from dev_ghost_parser.retry_policy import RetryPolicy


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KNOWN_AGENTS = list(AGENT_FIELD_MAP.keys())


# ---------------------------------------------------------------------------
# Mock Agent for registering in orchestrator
# ---------------------------------------------------------------------------


class MockRegisteredAgent(BaseAgent):
    """Mock agent that can be registered in the orchestrator for metadata lookup."""

    description = "Mock agent for aggregation tests"

    def __init__(self, agent_name: str) -> None:
        super().__init__()
        self.name = agent_name

    @property
    def timeout_seconds(self) -> float:
        return 60.0

    @property
    def retry_policy(self) -> RetryPolicy:
        return RetryPolicy(max_retries=2, base_delay_seconds=0.01, multiplier=2.0)

    async def execute(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            success=True,
            data={},
            duration_ms=10,
        )


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for generating random dict data for an agent result
agent_data = st.dictionaries(
    keys=st.text(min_size=1, max_size=15, alphabet=st.characters(categories=("L", "N"))),
    values=st.one_of(
        st.integers(min_value=-1000, max_value=1000),
        st.text(min_size=0, max_size=50),
        st.booleans(),
        st.lists(st.integers(min_value=0, max_value=100), max_size=5),
    ),
    min_size=1,
    max_size=8,
)

# Strategy for selecting a non-empty subset of known agents
agent_subset = st.lists(
    st.sampled_from(KNOWN_AGENTS),
    min_size=1,
    max_size=len(KNOWN_AGENTS),
    unique=True,
)

# Strategy for duration values
duration_ms = st.integers(min_value=0, max_value=10000)

# Strategy for total pipeline duration
total_duration = st.integers(min_value=100, max_value=60000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_orchestrator_with_agents(agent_names: list[str]) -> DependencyGraphOrchestrator:
    """Create an orchestrator with mock agents registered for the given names."""
    event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
    mock_llm = MagicMock()

    orchestrator = DependencyGraphOrchestrator(
        repo_path="/tmp/test_repo",
        llm_client=mock_llm,
        event_queue=event_queue,
        max_concurrency=5,
        global_timeout_seconds=30.0,
    )

    for name in agent_names:
        agent = MockRegisteredAgent(agent_name=name)
        orchestrator.register_agent(agent)

    return orchestrator


def _get_field_value(result: AnalysisResult, field_name: str) -> Any:
    """Get the value of a named field from an AnalysisResult."""
    return getattr(result, field_name)


# ---------------------------------------------------------------------------
# Property 12: Result Merge Preserves All Successful Agent Data
# ---------------------------------------------------------------------------


@given(
    agents=agent_subset,
    data_list=st.data(),
    total_dur=total_duration,
)
@settings(max_examples=100, deadline=None)
def test_property_12_result_merge_preserves_all_successful_agent_data(
    agents: list[str],
    data_list: st.DataObject,
    total_dur: int,
):
    """
    **Validates: Requirements 8.1, 8.3**

    For any set of AgentResult objects where success=True, merging them into
    an AnalysisResult SHALL produce an output where every data field from each
    successful agent is present and unmodified in the corresponding
    AnalysisResult field.
    """
    # Generate random data for each agent in the subset
    agent_data_map: dict[str, dict] = {}
    for agent_name in agents:
        agent_data_map[agent_name] = data_list.draw(agent_data, label=f"data_{agent_name}")

    # Create AgentResult objects with success=True
    results: list[AgentResult] = []
    for agent_name, data in agent_data_map.items():
        results.append(
            AgentResult(
                agent_name=agent_name,
                success=True,
                data=data,
                duration_ms=data_list.draw(duration_ms, label=f"dur_{agent_name}"),
            )
        )

    # Create orchestrator with registered agents (needed for retry_policy lookup)
    orchestrator = _create_orchestrator_with_agents(agents)

    # Call _aggregate_results
    analysis_result = orchestrator._aggregate_results(results, total_dur)

    # Verify: each agent's data appears in the correct AnalysisResult field
    for agent_name, expected_data in agent_data_map.items():
        target_field = AGENT_FIELD_MAP[agent_name]
        actual_value = _get_field_value(analysis_result, target_field)

        assert actual_value is not None, (
            f"Agent '{agent_name}' data should be in AnalysisResult.{target_field} "
            f"but got None"
        )
        assert actual_value == expected_data, (
            f"Agent '{agent_name}' data in AnalysisResult.{target_field} was modified.\n"
            f"  Expected: {expected_data}\n"
            f"  Got: {actual_value}"
        )

    # Verify metadata is populated
    assert analysis_result.metadata is not None
    assert analysis_result.metadata.total_duration_ms == total_dur
    assert analysis_result.metadata.failed_agents == []


# ---------------------------------------------------------------------------
# Property 13: Priority-Based Conflict Resolution
# ---------------------------------------------------------------------------

# Strategy for picking two different agents
two_different_agents = st.tuples(
    st.sampled_from(KNOWN_AGENTS),
    st.sampled_from(KNOWN_AGENTS),
).filter(lambda pair: pair[0] != pair[1])


@given(
    agent_pair=two_different_agents,
    high_data=agent_data,
    low_data=agent_data,
    total_dur=total_duration,
)
@settings(max_examples=100, deadline=None)
def test_property_13_priority_based_conflict_resolution(
    agent_pair: tuple[str, str],
    high_data: dict,
    low_data: dict,
    total_dur: int,
):
    """
    **Validates: Requirements 8.4**

    For any two agents producing data for the same field with different
    priorities, the merged AnalysisResult SHALL contain the data from the
    higher-priority agent.
    """
    agent_a, agent_b = agent_pair

    # Determine which has higher priority
    priority_a = AGENT_PRIORITY.get(agent_a, 0)
    priority_b = AGENT_PRIORITY.get(agent_b, 0)

    if priority_a == priority_b:
        # Skip equal priorities (shouldn't happen with known agents, but be safe)
        return

    if priority_a > priority_b:
        high_agent = agent_a
        low_agent = agent_b
    else:
        high_agent = agent_b
        low_agent = agent_a
        # Swap data to match
        high_data, low_data = low_data, high_data

    # Pick a target field — use the field of the higher-priority agent
    # We need both agents to claim the SAME field for a conflict to occur.
    # To do this, we make both agents map to the same field by creating
    # AgentResult objects that target the same AGENT_FIELD_MAP entry.
    # Since the orchestrator uses AGENT_FIELD_MAP[agent_name] to determine
    # the target field, a conflict only happens if two agents map to the same field.
    # In the default map, each agent maps to a unique field, so normally no conflict.
    # The conflict resolution is tested by having both results target the same field name.
    #
    # The implementation resolves conflicts via _resolve_field_conflict which
    # compares AGENT_PRIORITY of the agent_name. So we test by forcing both
    # AgentResults to target the same field (the high-priority agent's field).

    target_field = AGENT_FIELD_MAP[high_agent]

    # Create results — the low_agent's result is created with the high_agent's
    # field name by temporarily adjusting the AGENT_FIELD_MAP is not possible.
    # Instead, we create both results as if they both map to the same field.
    # The _aggregate_results method uses AGENT_FIELD_MAP.get(agent_name) so
    # both agents will write to different fields by default.
    #
    # To trigger a real conflict, we need both AgentResults to map to the
    # same field. Let's test by creating two results with the SAME agent_name
    # but different data — no, that doesn't test priority.
    #
    # The proper way: create two AgentResult objects where both agent names
    # map to the same field. In current AGENT_FIELD_MAP, each maps to unique.
    # So we test by providing both results sequentially and checking priority
    # resolution. We can monkey-patch or test the _resolve_field_conflict method.
    #
    # Actually, looking at _aggregate_results more carefully:
    # It iterates results and for each, gets target_field = AGENT_FIELD_MAP.get(agent_name).
    # Conflict only occurs if two different agent_names map to the same field.
    # Since the default map has unique mappings, we need to temporarily adjust
    # AGENT_FIELD_MAP for this test to create a conflict scenario.

    # Create orchestrator with both agents registered
    all_agents = list(set(KNOWN_AGENTS))
    orchestrator = _create_orchestrator_with_agents(all_agents)

    # Temporarily patch AGENT_FIELD_MAP so both agents target the same field
    import dev_ghost_parser.graph_orchestrator as go_module

    original_map = go_module.AGENT_FIELD_MAP.copy()
    try:
        # Make both agents target the same field
        go_module.AGENT_FIELD_MAP[low_agent] = target_field

        # Create results — low priority first, high priority second
        # (to also test that order doesn't matter, only priority)
        results: list[AgentResult] = [
            AgentResult(
                agent_name=low_agent,
                success=True,
                data=low_data,
                duration_ms=50,
            ),
            AgentResult(
                agent_name=high_agent,
                success=True,
                data=high_data,
                duration_ms=100,
            ),
        ]

        # Call _aggregate_results
        analysis_result = orchestrator._aggregate_results(results, total_dur)

        # Verify: higher-priority agent's data wins
        actual_value = _get_field_value(analysis_result, target_field)
        assert actual_value == high_data, (
            f"Expected higher-priority agent '{high_agent}' (priority "
            f"{AGENT_PRIORITY[high_agent]}) data to win over '{low_agent}' "
            f"(priority {AGENT_PRIORITY[low_agent]}) for field '{target_field}'.\n"
            f"  Expected: {high_data}\n"
            f"  Got: {actual_value}"
        )

        # Also test reverse order: high priority first, low priority second
        results_reversed: list[AgentResult] = [
            AgentResult(
                agent_name=high_agent,
                success=True,
                data=high_data,
                duration_ms=100,
            ),
            AgentResult(
                agent_name=low_agent,
                success=True,
                data=low_data,
                duration_ms=50,
            ),
        ]

        analysis_result_reversed = orchestrator._aggregate_results(results_reversed, total_dur)

        # Verify: higher-priority agent's data still wins regardless of order
        actual_value_reversed = _get_field_value(analysis_result_reversed, target_field)
        assert actual_value_reversed == high_data, (
            f"With reversed input order, expected higher-priority agent '{high_agent}' "
            f"(priority {AGENT_PRIORITY[high_agent]}) data to still win over "
            f"'{low_agent}' (priority {AGENT_PRIORITY[low_agent]}) for field "
            f"'{target_field}'.\n"
            f"  Expected: {high_data}\n"
            f"  Got: {actual_value_reversed}"
        )

    finally:
        # Restore original AGENT_FIELD_MAP
        go_module.AGENT_FIELD_MAP.clear()
        go_module.AGENT_FIELD_MAP.update(original_map)
