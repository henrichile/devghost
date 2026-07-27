"""
Property 4: Agent event lifecycle ordering

For any agent that executes, the sequence of emitted events SHALL follow the order:
exactly one "agent_start", then one or more "agent_progress", then exactly one of
"agent_complete" or "agent_error" — with no events from that agent appearing out
of this order.

Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.10
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, strategies as st

from dev_ghost_parser.agent_models import AgentEvent, AgentResult
from dev_ghost_parser.base_agent import AgentContext, BaseAgent
from dev_ghost_parser.orchestrator import AgentOrchestrator


# ---------------------------------------------------------------------------
# Valid agent identifiers (we pick from these to generate scenarios)
# ---------------------------------------------------------------------------

VALID_AGENT_IDENTIFIERS = [
    "ast_analyzer",
    "er_extractor",
    "code_auditor",
    "doc_generator",
    "system_reporter",
]


# ---------------------------------------------------------------------------
# Test agent implementations with configurable behavior
# ---------------------------------------------------------------------------


class FakeAgent(BaseAgent):
    """A configurable agent that succeeds after emitting progress events."""

    def __init__(
        self,
        name: str,
        description: str,
        delay: float = 0.0,
        progress_count: int = 1,
    ):
        super().__init__()
        self.name = name
        self.description = description
        self._delay = delay
        self._progress_count = progress_count

    async def execute(self, context: AgentContext) -> AgentResult:
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        for i in range(self._progress_count):
            await self.emit_progress(f"{self.name} step {i + 1}/{self._progress_count}")
        return AgentResult(
            agent_name=self.name,
            success=True,
            data={"agent": self.name, "status": "done"},
        )


class FailingAgent(BaseAgent):
    """An agent that emits progress then raises an exception."""

    def __init__(
        self,
        name: str,
        description: str,
        delay: float = 0.0,
        progress_count: int = 1,
        error_msg: str = "Agent failure",
    ):
        super().__init__()
        self.name = name
        self.description = description
        self._delay = delay
        self._progress_count = progress_count
        self._error_msg = error_msg

    async def execute(self, context: AgentContext) -> AgentResult:
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        for i in range(self._progress_count):
            await self.emit_progress(f"{self.name} progress {i + 1}/{self._progress_count}")
        raise RuntimeError(self._error_msg)


# ---------------------------------------------------------------------------
# Hypothesis strategy for generating agent execution scenarios
# ---------------------------------------------------------------------------


@st.composite
def agent_scenario_strategy(draw):
    """Generate a randomized agent execution scenario.

    Produces 1-5 agents, each with:
    - A unique agent identifier
    - A random delay (0 to 0.05s for test speed)
    - A random failure state (True/False)
    - A random number of progress emissions (1-5)
    """
    num_agents = draw(st.integers(min_value=1, max_value=5))

    # Pick unique identifiers for each agent
    identifiers = draw(
        st.lists(
            st.sampled_from(VALID_AGENT_IDENTIFIERS),
            min_size=num_agents,
            max_size=num_agents,
            unique=True,
        )
    )

    agents_config = []
    for agent_id in identifiers:
        delay = draw(st.floats(min_value=0.0, max_value=0.05))
        should_fail = draw(st.booleans())
        progress_count = draw(st.integers(min_value=1, max_value=5))

        agents_config.append({
            "name": agent_id,
            "delay": delay,
            "should_fail": should_fail,
            "progress_count": progress_count,
        })

    return agents_config


# ---------------------------------------------------------------------------
# Helper: collect all events from queue
# ---------------------------------------------------------------------------


async def collect_events(queue: asyncio.Queue) -> list[AgentEvent]:
    """Drain all events from the queue."""
    events = []
    while not queue.empty():
        events.append(await queue.get())
    return events


# ---------------------------------------------------------------------------
# Helper: verify lifecycle ordering for a single agent's events
# ---------------------------------------------------------------------------


def verify_agent_lifecycle(agent_name: str, events: list[AgentEvent]) -> None:
    """Verify the event lifecycle ordering for a single agent.

    Asserts:
    1. Exactly one "agent_start" event
    2. One or more "agent_progress" events
    3. Exactly one of "agent_complete" or "agent_error"
    4. Ordering: start first, then all progress, then complete/error last
    """
    # Filter events for this agent
    agent_events = [e for e in events if e.agent == agent_name]

    # Must have at least 3 events: start + progress + (complete|error)
    assert len(agent_events) >= 3, (
        f"Agent '{agent_name}' has fewer than 3 events: "
        f"{[e.type for e in agent_events]}"
    )

    # Count event types
    start_events = [e for e in agent_events if e.type == "agent_start"]
    progress_events = [e for e in agent_events if e.type == "agent_progress"]
    complete_events = [e for e in agent_events if e.type == "agent_complete"]
    error_events = [e for e in agent_events if e.type == "agent_error"]

    # 1. Exactly one agent_start
    assert len(start_events) == 1, (
        f"Agent '{agent_name}' expected exactly 1 agent_start, "
        f"got {len(start_events)}"
    )

    # 2. One or more agent_progress
    assert len(progress_events) >= 1, (
        f"Agent '{agent_name}' expected >= 1 agent_progress, "
        f"got {len(progress_events)}"
    )

    # 3. Exactly one of agent_complete or agent_error (not both)
    terminal_count = len(complete_events) + len(error_events)
    assert terminal_count == 1, (
        f"Agent '{agent_name}' expected exactly 1 terminal event "
        f"(complete or error), got {len(complete_events)} complete + "
        f"{len(error_events)} error"
    )

    # 4. Ordering: start must be first, terminal must be last
    event_types = [e.type for e in agent_events]

    # Start must be at index 0
    assert event_types[0] == "agent_start", (
        f"Agent '{agent_name}' first event should be agent_start, "
        f"got: {event_types}"
    )

    # Terminal (complete or error) must be the last event
    assert event_types[-1] in ("agent_complete", "agent_error"), (
        f"Agent '{agent_name}' last event should be agent_complete or "
        f"agent_error, got: {event_types}"
    )

    # All middle events must be agent_progress
    middle_events = event_types[1:-1]
    assert all(t == "agent_progress" for t in middle_events), (
        f"Agent '{agent_name}' middle events should all be agent_progress, "
        f"got: {event_types}"
    )


# ---------------------------------------------------------------------------
# Property Test: Event lifecycle ordering
# ---------------------------------------------------------------------------


class TestProperty4EventLifecycleOrdering:
    """Feature: agent-streaming-reporting, Property 4: Agent event lifecycle ordering"""

    @settings(max_examples=100)
    @given(scenario=agent_scenario_strategy())
    @pytest.mark.asyncio
    async def test_property_4_event_lifecycle_ordering(self, scenario):
        """For any agent that executes, the event sequence SHALL follow:
        exactly one agent_start → one or more agent_progress →
        exactly one agent_complete or agent_error.

        **Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.10**
        """
        event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        mock_llm = MagicMock()

        orchestrator = AgentOrchestrator(
            repo_path="/tmp/test_repo",
            llm_client=mock_llm,
            event_queue=event_queue,
            max_concurrency=5,
            timeout_seconds=30.0,
        )

        # Register agents based on scenario
        for agent_config in scenario:
            if agent_config["should_fail"]:
                agent = FailingAgent(
                    name=agent_config["name"],
                    description=f"Test agent {agent_config['name']}",
                    delay=agent_config["delay"],
                    progress_count=agent_config["progress_count"],
                    error_msg=f"Simulated failure in {agent_config['name']}",
                )
            else:
                agent = FakeAgent(
                    name=agent_config["name"],
                    description=f"Test agent {agent_config['name']}",
                    delay=agent_config["delay"],
                    progress_count=agent_config["progress_count"],
                )

            orchestrator.register_agent(agent)

        # Run the orchestrator
        await orchestrator.run_all()

        # Collect all emitted events
        events = await collect_events(event_queue)

        # Verify lifecycle ordering for each agent in the scenario
        for agent_config in scenario:
            verify_agent_lifecycle(agent_config["name"], events)

    @settings(max_examples=100)
    @given(scenario=agent_scenario_strategy())
    @pytest.mark.asyncio
    async def test_property_4_no_events_out_of_order(self, scenario):
        """No events from an agent appear outside the start → progress+ →
        terminal ordering.

        **Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.10**
        """
        event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        mock_llm = MagicMock()

        orchestrator = AgentOrchestrator(
            repo_path="/tmp/test_repo",
            llm_client=mock_llm,
            event_queue=event_queue,
            max_concurrency=5,
            timeout_seconds=30.0,
        )

        for agent_config in scenario:
            if agent_config["should_fail"]:
                agent = FailingAgent(
                    name=agent_config["name"],
                    description=f"Test agent {agent_config['name']}",
                    delay=agent_config["delay"],
                    progress_count=agent_config["progress_count"],
                    error_msg=f"Simulated failure in {agent_config['name']}",
                )
            else:
                agent = FakeAgent(
                    name=agent_config["name"],
                    description=f"Test agent {agent_config['name']}",
                    delay=agent_config["delay"],
                    progress_count=agent_config["progress_count"],
                )

            orchestrator.register_agent(agent)

        await orchestrator.run_all()

        events = await collect_events(event_queue)

        # For each agent, verify state machine transitions are valid
        for agent_config in scenario:
            agent_name = agent_config["name"]
            agent_events = [e for e in events if e.agent == agent_name]

            # State machine: expecting_start → expecting_progress → expecting_terminal → done
            state = "expecting_start"

            for event in agent_events:
                if state == "expecting_start":
                    assert event.type == "agent_start", (
                        f"Agent '{agent_name}': expected agent_start in state "
                        f"'{state}', got '{event.type}'"
                    )
                    state = "expecting_progress"

                elif state == "expecting_progress":
                    if event.type == "agent_progress":
                        # Stay in expecting_progress (can have multiple)
                        pass
                    elif event.type in ("agent_complete", "agent_error"):
                        # Transition to done — but we already saw at least one progress
                        state = "done"
                    else:
                        pytest.fail(
                            f"Agent '{agent_name}': unexpected event type "
                            f"'{event.type}' in state '{state}'"
                        )

                elif state == "done":
                    pytest.fail(
                        f"Agent '{agent_name}': received event '{event.type}' "
                        f"after terminal event"
                    )

            # Verify we reached terminal state
            assert state == "done", (
                f"Agent '{agent_name}': lifecycle did not reach terminal state, "
                f"ended in '{state}'"
            )
