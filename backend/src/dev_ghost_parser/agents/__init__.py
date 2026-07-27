"""Specialized agents for the multi-agent analysis architecture.

Provides all 5 specialized agents and convenience functions for
agent registration with the orchestrator.

Satisfies Requirements: 1.2
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .ast_analyzer_agent import ASTAnalyzerAgent
from .code_auditor_agent import CodeAuditorAgent
from .doc_generator_agent import DocGeneratorAgent
from .er_extractor_agent import ERExtractorAgent
from .system_reporter_agent import SystemReporterAgent

if TYPE_CHECKING:
    from dev_ghost_parser.llm_client import LLM_Client
    from dev_ghost_parser.agent_models import AgentEvent
    from dev_ghost_parser.orchestrator import AgentOrchestrator

__all__ = [
    "ASTAnalyzerAgent",
    "ERExtractorAgent",
    "CodeAuditorAgent",
    "DocGeneratorAgent",
    "SystemReporterAgent",
    "get_all_agents",
    "create_orchestrator_with_all_agents",
]


def get_all_agents() -> list:
    """Instantiate and return all 5 specialized agents."""
    return [
        ASTAnalyzerAgent(),
        ERExtractorAgent(),
        CodeAuditorAgent(),
        DocGeneratorAgent(),
        SystemReporterAgent(),
    ]


def create_orchestrator_with_all_agents(
    repo_path: str,
    llm_client: "LLM_Client",
    event_queue: "asyncio.Queue[AgentEvent]",
    **kwargs,
) -> "AgentOrchestrator":
    """Create an orchestrator with all 5 agents pre-registered.

    Args:
        repo_path: Path to the cloned repository.
        llm_client: LLM client for agents that need language model access.
        event_queue: Async queue for streaming agent events.
        **kwargs: Additional keyword arguments passed to AgentOrchestrator
                  (e.g., max_concurrency, timeout_seconds).

    Returns:
        A fully configured AgentOrchestrator with all agents registered.
    """
    from dev_ghost_parser.orchestrator import AgentOrchestrator

    orch = AgentOrchestrator(
        repo_path=repo_path,
        llm_client=llm_client,
        event_queue=event_queue,
        **kwargs,
    )
    for agent in get_all_agents():
        orch.register_agent(agent)
    return orch
