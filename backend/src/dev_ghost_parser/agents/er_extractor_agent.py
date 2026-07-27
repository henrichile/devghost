"""ERExtractorAgent — wraps the existing ER_Extractor as an async agent.

Emits progress events during extraction phases and returns a structured
AgentResult with the ER model data (entities, relations, errors).

Satisfies Requirements: 1.2, 2.2, 2.3, 2.4
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Any

from dev_ghost_parser.agent_models import AgentResult
from dev_ghost_parser.base_agent import AgentContext, BaseAgent
from dev_ghost_parser.er_extractor import ER_Extractor

logger = logging.getLogger(__name__)


class ERExtractorAgent(BaseAgent):
    """Extracts entity-relationship models from ORM definitions and SQL schemas.

    Wraps the existing ER_Extractor synchronous logic, running it in a
    thread to avoid blocking the asyncio event loop. Emits progress events at
    each major extraction phase.
    """

    name = "er_extractor"
    description = "Extracts entity-relationship models from ORM definitions and SQL schemas"

    @property
    def timeout_seconds(self) -> float:
        """ER extraction timeout: 60 seconds."""
        return 60.0

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute ER extraction on the repository.

        Parameters
        ----------
        context:
            Shared agent context containing repo_path, llm_client, and event_queue.

        Returns
        -------
        AgentResult
            Success result with ER model data, or failure result with error message.
        """
        try:
            await self.emit_progress("Buscando definiciones de modelos ORM...")

            extractor = ER_Extractor()

            await self.emit_progress("Analizando atributos y relaciones...")

            # ER_Extractor.extract() is synchronous — run in a thread
            # to avoid blocking the event loop.
            result = await asyncio.to_thread(extractor.extract, context.repo_path)

            await self.emit_progress("Construyendo diagrama ER...")

            # Convert ERResult to the same format as Output_Serializer
            # Frontend expects "from"/"to" (not "from_entity"/"to_entity"), "primaryKey" etc.
            result_dict: dict[str, Any] = {
                "entities": [
                    {
                        "name": entity.name,
                        "attributes": [{"name": a.name, "type": a.type} for a in entity.attributes],
                        "primaryKey": entity.primaryKey,
                    }
                    for entity in result.entities
                ],
                "relations": [
                    {
                        "from": rel.from_entity,
                        "to": rel.to_entity,
                        "type": rel.type,
                        "foreignKey": rel.foreignKey,
                        **({"rawDeclaration": rel.rawDeclaration} if rel.rawDeclaration else {}),
                    }
                    for rel in result.relations
                ],
                "errors": [asdict(err) for err in result.errors],
            }

            return AgentResult(
                agent_name="er_extractor",
                success=True,
                data=result_dict,
            )

        except Exception as e:
            logger.exception("ERExtractorAgent failed: %s", e)
            return AgentResult(
                agent_name="er_extractor",
                success=False,
                error_message=str(e),
            )
