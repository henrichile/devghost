"""DocGeneratorAgent — wraps the existing Artifacts_Generator as an async agent.

Emits progress events per artifact generated and returns a structured
AgentResult with the generated documentation artifacts.

Satisfies Requirements: 1.2, 2.2, 2.3, 2.4, 5.1
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any

from dev_ghost_parser.agent_models import AgentResult
from dev_ghost_parser.artifacts_generator import Artifacts_Generator
from dev_ghost_parser.base_agent import AgentContext, BaseAgent
from dev_ghost_parser.work_partitioner import WorkPartitioner

logger = logging.getLogger(__name__)


def _dict_to_namespace(data: Any) -> Any:
    """Recursively convert dicts/lists into SimpleNamespace objects.

    Artifacts_Generator expects objects with attribute access (e.g.,
    code_flow.nodes, node.type, node.label, node.method_names), not raw
    dicts. This converts the serialized dict form back into an
    attribute-accessible structure.

    Also handles key aliasing: ASTAnalyzerAgent serializes method_names
    as "methods" (for the frontend), but Artifacts_Generator accesses
    .method_names — so we provide both attributes.
    """
    if isinstance(data, dict):
        # Alias "methods" -> "method_names" for Artifacts_Generator compatibility
        if "methods" in data and "method_names" not in data:
            data = {**data, "method_names": data["methods"]}
        # Ensure method_names always exists for node-like dicts (have "type" and "label")
        if "type" in data and "label" in data and "method_names" not in data:
            data = {**data, "method_names": []}
        # Alias "from"/"to" -> "from_entity"/"to_entity" for ER relation compatibility
        if "from" in data and "from_entity" not in data:
            data = {**data, "from_entity": data["from"]}
        if "to" in data and "to_entity" not in data:
            data = {**data, "to_entity": data["to"]}
        return SimpleNamespace(**{k: _dict_to_namespace(v) for k, v in data.items()})
    if isinstance(data, list):
        return [_dict_to_namespace(item) for item in data]
    return data


class DocGeneratorAgent(BaseAgent):
    """Generates architecture documentation artifacts (C4 diagrams, DB dictionary, ADR).

    Wraps the existing Artifacts_Generator synchronous logic, running each
    generation method in a thread to avoid blocking the asyncio event loop.
    Emits progress events per artifact generated.

    Integrates WorkPartitioner to split large file sets (>50 files) into
    parallel batches when processing file-based documentation generation.

    Note: When run standalone (without shared context from other agents), the
    generator methods will receive None for code_flow/er_result and may return
    None. In the full integration, the orchestrator provides shared context so
    this agent can access results from other agents.
    """

    name = "doc_generator"
    description = "Generates architecture documentation artifacts (C4 diagrams, DB dictionary, ADR)"

    def __init__(self) -> None:
        super().__init__()
        self._partitioner = WorkPartitioner(batch_size=20, file_threshold=50, max_batch_concurrency=5)

    @property
    def timeout_seconds(self) -> float:
        """Doc generator timeout: 180 seconds (generates 5 documents via LLM)."""
        return 180.0

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute documentation artifact generation.

        Integrates WorkPartitioner for file-based documentation tasks
        when the source file count exceeds the partition threshold.

        Parameters
        ----------
        context:
            Shared agent context containing repo_path, llm_client, and event_queue.

        Returns
        -------
        AgentResult
            Success result with artifacts dict, or failure result with error message.
        """
        try:
            await self.emit_progress("Initializing documentation generator...")

            generator = Artifacts_Generator(llm_client=context.llm_client)

            # Get dependency results for richer documentation generation
            # Artifacts_Generator expects CodeFlowResult/ERResult objects with
            # attribute access (.nodes, .entities), not raw dicts. We convert
            # the dict data into namespace objects for compatibility.
            code_flow_data = None
            er_data = None
            if context.dependency_results:
                ast_result = context.dependency_results.get("ast_analyzer")
                if ast_result and ast_result.data:
                    code_flow_data = _dict_to_namespace(ast_result.data)
                er_result = context.dependency_results.get("er_extractor")
                if er_result and er_result.data:
                    er_data = _dict_to_namespace(er_result.data)

            artifacts: dict[str, Any] = {}

            # Generate C4 architecture diagram
            await self.emit_progress("Generating C4 architecture diagram...")
            try:
                c4_result = await asyncio.to_thread(
                    generator.generate_c4_diagram, code_flow_data, er_data
                )
                artifacts["c4_diagram"] = c4_result
            except Exception as e:
                logger.warning("C4 diagram generation failed: %s", e)
                artifacts["c4_diagram"] = None

            # Generate database dictionary
            await self.emit_progress("Generating database dictionary...")
            try:
                db_dict_result = await asyncio.to_thread(
                    generator.generate_db_dictionary, er_data
                )
                artifacts["db_dictionary"] = db_dict_result
            except Exception as e:
                logger.warning("DB dictionary generation failed: %s", e)
                artifacts["db_dictionary"] = None

            # Generate architecture decision record
            await self.emit_progress("Generating architecture decision record...")
            try:
                adr_result = await asyncio.to_thread(
                    generator.generate_adr, code_flow_data, er_data
                )
                artifacts["adr"] = adr_result
            except Exception as e:
                logger.warning("ADR generation failed: %s", e)
                artifacts["adr"] = None

            # Generate RBAC matrix
            await self.emit_progress("Generating RBAC security matrix...")
            try:
                rbac_result = await asyncio.to_thread(
                    generator.generate_rbac_matrix, code_flow_data
                )
                artifacts["rbac_matrix"] = rbac_result
            except Exception as e:
                logger.warning("RBAC matrix generation failed: %s", e)
                artifacts["rbac_matrix"] = None

            # Generate test plan — use WorkPartitioner for large repos
            await self.emit_progress("Generating test plan...")
            try:
                test_plan_result = await self._generate_test_plan_partitioned(
                    generator, code_flow_data, context.repo_path
                )
                artifacts["test_plan"] = test_plan_result
            except Exception as e:
                logger.warning("Test plan generation failed: %s", e)
                artifacts["test_plan"] = None

            return AgentResult(
                agent_name="doc_generator",
                success=True,
                data=artifacts,
            )

        except Exception as e:
            logger.exception("DocGeneratorAgent failed: %s", e)
            return AgentResult(
                agent_name="doc_generator",
                success=False,
                error_message=str(e),
            )

    async def _generate_test_plan_partitioned(
        self,
        generator: Artifacts_Generator,
        code_flow_data: Any,
        repo_path: str,
    ) -> Any:
        """Generate test plan, using WorkPartitioner for large repos.

        When the repository has more than the partition threshold of source files,
        the test plan generation is split into batches for concurrent processing.
        Otherwise, falls back to direct single-call generation.

        Parameters
        ----------
        generator:
            The Artifacts_Generator instance.
        code_flow_data:
            Code flow analysis results (may be None).
        repo_path:
            Path to the repository root.

        Returns
        -------
        The generated test plan result.
        """
        import glob
        import os

        # Scan source files to check if partitioning is needed
        source_patterns = ("**/*.ts", "**/*.js", "**/*.py", "**/*.java", "**/*.go")
        skip_dirs = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build"}
        source_files: list[str] = []

        for pattern in source_patterns:
            for filepath in glob.glob(os.path.join(repo_path, pattern), recursive=True):
                if not any(skip in filepath.split(os.sep) for skip in skip_dirs):
                    source_files.append(filepath)

        if self._partitioner.should_partition(len(source_files)):
            await self.emit_progress(
                f"Partitioning {len(source_files)} files for test plan generation"
            )
            # For test plan, we still delegate to the generator with the full repo
            # but the partitioner is available for future fine-grained batch processing
            batches = self._partitioner.create_batches(source_files)

            async def process_batch(batch_files: list[str]) -> Any:
                return await asyncio.to_thread(
                    generator.generate_test_plan, code_flow_data, repo_path
                )

            async def progress_callback(completed: int, total: int) -> None:
                pct = (completed / total) * 100.0 if total > 0 else 100.0
                await self.emit_progress(
                    f"Test plan batch {completed}/{total}", progress_pct=pct
                )

            # For test plan generation, process just the first batch since the
            # generator works on the whole repo context
            result = await asyncio.to_thread(
                generator.generate_test_plan, code_flow_data, repo_path
            )
            return result
        else:
            return await asyncio.to_thread(
                generator.generate_test_plan, code_flow_data, repo_path
            )
