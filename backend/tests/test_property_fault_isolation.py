"""
Property 2: Fault isolation preserves successful results

For any subset S of agents that raise exceptions, all agents NOT in S SHALL
complete successfully and their results SHALL be present in the merged output,
alongside error entries for each agent in S.

**Validates: Requirements 1.3**
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, strategies as st

from dev_ghost_parser.agent_models import AgentEvent, AgentResult, AnalysisResult
from dev_ghost_parser.base_agent import AgentContext, BaseAgent
from dev_ghost_parser.orchestrator import AgentOrchestrator, _AGENT_RESULT_FIELD_MAP


# ---------------------------------------------------------------------------
# Valid agent identifiers
# ---------------------------------------------------------------------------

VALID_AGENT_IDENTIFIERS = list(_AGENT_RESULT_FIELD_MAP.keys())


# ---------------------------------------------------------------------------
# Test agent implementations
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


class FailingAgent(BaseAgent):
    """An agent that emits progress then raises an exception."""

    def __init__(self, name: str, error_msg: str = "Simulated failure") -> None:
        super().__init__()
        self.name = name
        self.description = f"Failing {name} agent"
        self._error_msg = error_msg

    async def execute(self, context: AgentContext) -> AgentResult:
        await self.emit_progress(f"{self.name} starting work...")
        raise RuntimeError(self._error_msg)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Strategy for generating agent data dictionaries
agent_data_strategy = st.dictionaries(
    keys=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=15,
    ),
    values=st.one_of(
        st.text(min_size=1, max_size=30),
        st.integers(min_value=-100, max_value=100),
        st.booleans(),
    ),
    min_size=1,
    max_size=3,
)


@st.composite
def fault_isolation_scenario(draw):
    """Generate a scenario with 2-5 agents where a random subset fails.

    Returns a list of dicts with:
    - name: agent identifier
    - should_fail: whether this agent should raise an exception
    - data: the data dict for successful agents (None for failing)
    - error_msg: error message for failing agents
    """
    num_agents = draw(st.integers(min_value=2, max_value=5))

    # Pick unique identifiers
    identifiers = draw(
        st.lists(
            st.sampled_from(VALID_AGENT_IDENTIFIERS),
            min_size=num_agents,
            max_size=num_agents,
            unique=True,
        )
    )

    # Generate failure mask — at least one succeeds and at least one fails
    # to make the property meaningful
    failure_mask = draw(
        st.lists(
            st.booleans(),
            min_size=num_agents,
            max_size=num_agents,
        ).filter(
            lambda mask: any(mask) and not all(mask)
        )
    )

    configs = []
    for idx, agent_id in enumerate(identifiers):
        should_fail = failure_mask[idx]
        data = None if should_fail else draw(agent_data_strategy)
        error_msg = f"Error in {agent_id}" if should_fail else None

        configs.append({
            "name": agent_id,
            "should_fail": should_fail,
            "data": data,
            "error_msg": error_msg,
        })

    return configs


# ---------------------------------------------------------------------------
# Property Test: Fault isolation preserves successful results
# ---------------------------------------------------------------------------


class TestProperty2FaultIsolation:
    """Feature: agent-streaming-reporting, Property 2: Fault isolation preserves successful results"""

    @settings(max_examples=100)
    @given(scenario=fault_isolation_scenario())
    def test_property_2_successful_agents_results_preserved(self, scenario):
        """For any subset S of agents that raise exceptions, all agents NOT in S
        SHALL complete successfully and their results SHALL be present in the
        merged output.

        **Validates: Requirements 1.3**
        """

        async def _run():
            event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
            mock_llm = MagicMock()

            orch = AgentOrchestrator(
                repo_path="/tmp/test_repo",
                llm_client=mock_llm,
                event_queue=event_queue,
                max_concurrency=5,
                timeout_seconds=30.0,
            )

            for config in scenario:
                if config["should_fail"]:
                    orch.register_agent(
                        FailingAgent(
                            name=config["name"],
                            error_msg=config["error_msg"],
                        )
                    )
                else:
                    orch.register_agent(
                        FakeAgent(
                            name=config["name"],
                            data=config["data"],
                        )
                    )

            return await orch.run_all()

        result = asyncio.run(_run())

        # Verify: all successful agents' data is in the merged result
        successful_agents = [c for c in scenario if not c["should_fail"]]
        for config in successful_agents:
            field_name = _AGENT_RESULT_FIELD_MAP[config["name"]]
            actual_value = getattr(result, field_name)
            assert actual_value == config["data"], (
                f"Successful agent '{config['name']}' data not found in "
                f"field '{field_name}'. Expected {config['data']!r}, "
                f"got {actual_value!r}"
            )

    @settings(max_examples=100)
    @given(scenario=fault_isolation_scenario())
    def test_property_2_failed_agents_produce_error_entries(self, scenario):
        """For any subset S of agents that raise exceptions, the merged output
        SHALL contain error entries for each agent in S.

        **Validates: Requirements 1.3**
        """

        async def _run():
            event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
            mock_llm = MagicMock()

            orch = AgentOrchestrator(
                repo_path="/tmp/test_repo",
                llm_client=mock_llm,
                event_queue=event_queue,
                max_concurrency=5,
                timeout_seconds=30.0,
            )

            for config in scenario:
                if config["should_fail"]:
                    orch.register_agent(
                        FailingAgent(
                            name=config["name"],
                            error_msg=config["error_msg"],
                        )
                    )
                else:
                    orch.register_agent(
                        FakeAgent(
                            name=config["name"],
                            data=config["data"],
                        )
                    )

            return await orch.run_all()

        result = asyncio.run(_run())

        # Verify: each failed agent has an error entry in result.errors
        failed_agents = [c for c in scenario if c["should_fail"]]
        error_agent_names = {err["agent"] for err in result.errors}

        for config in failed_agents:
            assert config["name"] in error_agent_names, (
                f"Failed agent '{config['name']}' does not have an error "
                f"entry in result.errors. Errors: {result.errors}"
            )

        # Verify: error count matches failed agent count
        assert len(result.errors) == len(failed_agents), (
            f"Expected {len(failed_agents)} error entries, "
            f"got {len(result.errors)}: {result.errors}"
        )

    @settings(max_examples=100)
    @given(scenario=fault_isolation_scenario())
    def test_property_2_error_entries_contain_agent_name_and_message(self, scenario):
        """Each error entry SHALL contain the agent name and a non-empty error
        message describing the failure.

        **Validates: Requirements 1.3**
        """

        async def _run():
            event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
            mock_llm = MagicMock()

            orch = AgentOrchestrator(
                repo_path="/tmp/test_repo",
                llm_client=mock_llm,
                event_queue=event_queue,
                max_concurrency=5,
                timeout_seconds=30.0,
            )

            for config in scenario:
                if config["should_fail"]:
                    orch.register_agent(
                        FailingAgent(
                            name=config["name"],
                            error_msg=config["error_msg"],
                        )
                    )
                else:
                    orch.register_agent(
                        FakeAgent(
                            name=config["name"],
                            data=config["data"],
                        )
                    )

            return await orch.run_all()

        result = asyncio.run(_run())

        # Verify: each error entry has required fields
        for error_entry in result.errors:
            assert "agent" in error_entry, (
                f"Error entry missing 'agent' field: {error_entry}"
            )
            assert "error" in error_entry, (
                f"Error entry missing 'error' field: {error_entry}"
            )
            assert isinstance(error_entry["agent"], str) and error_entry["agent"], (
                f"Error entry 'agent' should be a non-empty string: {error_entry}"
            )
            assert isinstance(error_entry["error"], str) and error_entry["error"], (
                f"Error entry 'error' should be a non-empty string: {error_entry}"
            )
