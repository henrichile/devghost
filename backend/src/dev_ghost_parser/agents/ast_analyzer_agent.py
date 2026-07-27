"""ASTAnalyzerAgent — wraps the existing Code_Flow_Analyzer as an async agent.

Emits progress events during analysis phases and returns a structured
AgentResult with the code flow data (nodes, edges, errors).

Satisfies Requirements: 1.2, 2.2, 2.3, 2.4
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Any

from dev_ghost_parser.agent_models import AgentResult
from dev_ghost_parser.base_agent import AgentContext, BaseAgent
from dev_ghost_parser.code_flow_analyzer import Code_Flow_Analyzer
from dev_ghost_parser.retry_policy import RetryPolicy

logger = logging.getLogger(__name__)


class ASTAnalyzerAgent(BaseAgent):
    """Analyzes code structure, architecture classification, and dependency graph.

    Wraps the existing Code_Flow_Analyzer synchronous logic, running it in a
    thread to avoid blocking the asyncio event loop. Emits progress events at
    each major analysis phase.
    """

    name = "ast_analyzer"
    description = "Analyzes code structure, architecture classification, and dependency graph"

    @property
    def timeout_seconds(self) -> float:
        """AST analysis timeout: 90 seconds."""
        return 90.0

    @property
    def retry_policy(self) -> RetryPolicy:
        """AST analyzer retry policy: 2 retries, 1.0s base delay, 2x multiplier."""
        return RetryPolicy(max_retries=2, base_delay_seconds=1.0, multiplier=2.0)

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute AST analysis on the repository.

        Parameters
        ----------
        context:
            Shared agent context containing repo_path, llm_client, and event_queue.

        Returns
        -------
        AgentResult
            Success result with code flow data, or failure result with error message.
        """
        try:
            await self.emit_progress("Escaneando estructura de directorios...")

            analyzer = Code_Flow_Analyzer(llm_client=context.llm_client)

            await self.emit_progress("Extrayendo dependencias de imports...")

            await self.emit_progress("Clasificando patrones arquitectónicos...")

            # Code_Flow_Analyzer.analyze() is synchronous — run in a thread
            # to avoid blocking the event loop.
            result = await asyncio.to_thread(analyzer.analyze, context.repo_path)

            # Convert the CodeFlowResult to the same format as Output_Serializer
            # Frontend expects "methods" (not "method_names"), camelCase fields
            result_dict: dict[str, Any] = {
                "nodes": [
                    {
                        "id": node.id,
                        "label": node.label,
                        "type": node.type,
                        "description": node.description,
                        "methods": node.method_names,
                    }
                    for node in result.nodes
                ],
                "edges": [
                    {"source": edge.source, "target": edge.target, "relation": edge.relation}
                    for edge in result.edges
                ],
                "errors": [asdict(err) for err in result.errors],
            }

            return AgentResult(
                agent_name="ast_analyzer",
                success=True,
                data=result_dict,
            )

        except Exception as e:
            logger.exception("ASTAnalyzerAgent failed: %s", e)
            return AgentResult(
                agent_name="ast_analyzer",
                success=False,
                error_message=str(e),
            )
