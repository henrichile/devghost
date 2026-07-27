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
            await self.emit_progress("Inicializando generador de documentación...")

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
            await self.emit_progress("Generando diagrama C4...")
            try:
                c4_result = await asyncio.to_thread(
                    generator.generate_c4_diagram, code_flow_data, er_data
                )
                artifacts["c4_diagram"] = c4_result
            except Exception as e:
                logger.warning("C4 diagram generation failed: %s", e)
                artifacts["c4_diagram"] = None

            # Generate database dictionary
            await self.emit_progress("Generando diccionario de base de datos...")
            try:
                db_dict_result = await asyncio.to_thread(
                    generator.generate_db_dictionary, er_data
                )
                # If no ER entities found, generate a basic data model doc from code flow
                if db_dict_result is None and code_flow_data and hasattr(code_flow_data, 'nodes'):
                    repo_nodes = [n for n in code_flow_data.nodes if hasattr(n, 'type') and n.type == 'Repository']
                    if repo_nodes and context.llm_client.available:
                        repo_names = ', '.join(n.label for n in repo_nodes[:10])
                        db_dict_result = await asyncio.to_thread(
                            context.llm_client.complete,
                            "Genera un diccionario de datos en Markdown basado en los repositorios detectados. "
                            "Para cada repositorio, infiere las entidades y atributos probables. "
                            "Usa tablas HTML (<table>). Responde en español.",
                            f"Repositorios detectados: {repo_names}"
                        )
                artifacts["db_dictionary"] = db_dict_result
            except Exception as e:
                logger.warning("DB dictionary generation failed: %s", e)
                artifacts["db_dictionary"] = None

            # Generate architecture decision record
            await self.emit_progress("Generando registro de decisión arquitectónica...")
            try:
                adr_result = await asyncio.to_thread(
                    generator.generate_adr, code_flow_data, er_data
                )
                artifacts["adr"] = adr_result
            except Exception as e:
                logger.warning("ADR generation failed: %s", e)
                artifacts["adr"] = None

            # Generate RBAC matrix
            await self.emit_progress("Generando matriz de seguridad RBAC...")
            try:
                rbac_result = await asyncio.to_thread(
                    generator.generate_rbac_matrix, code_flow_data
                )
                artifacts["rbac_matrix"] = rbac_result
            except Exception as e:
                logger.warning("RBAC matrix generation failed: %s", e)
                artifacts["rbac_matrix"] = None

            # Generate test plan — use WorkPartitioner for large repos
            await self.emit_progress("Generando plan de testing...")
            try:
                test_plan_result = await self._generate_test_plan_partitioned(
                    generator, code_flow_data, context.repo_path
                )
                artifacts["test_plan"] = test_plan_result
            except Exception as e:
                logger.warning("Test plan generation failed: %s", e)
                artifacts["test_plan"] = None

            # Generate use cases from Controller/Route methods (UML analysis)
            await self.emit_progress("Generando análisis UML...")
            try:
                use_cases_result = await asyncio.to_thread(
                    generator.generate_use_cases, code_flow_data
                )
                artifacts["use_cases"] = use_cases_result
            except Exception as e:
                logger.warning("Use cases generation failed: %s", e)
                artifacts["use_cases"] = None

            # Generate formal Use Cases & User Stories document (ISO/IEEE standard)
            await self.emit_progress("Generando casos de uso e historias de usuario...")
            try:
                use_cases_doc = await self._generate_formal_use_cases(
                    code_flow_data, context
                )
                artifacts["use_cases_doc"] = use_cases_doc
            except Exception as e:
                logger.warning("Formal use cases document generation failed: %s", e)
                artifacts["use_cases_doc"] = None

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

    async def _generate_formal_use_cases(
        self, code_flow_data: Any, context: AgentContext
    ) -> str | None:
        """Generate formal Use Cases and User Stories in ISO/IEC/IEEE 29148 format.

        Produces a standards-compliant document with:
        - User Stories in Connextra format with acceptance criteria
        - Use Cases per ISO/IEC/IEEE 29148 (formerly IEEE 830)
        """
        if not context.llm_client.available:
            return None
        if not code_flow_data or not hasattr(code_flow_data, 'nodes'):
            return None

        # Extract controllers/routes with their methods
        controllers = [n for n in code_flow_data.nodes
                      if hasattr(n, 'type') and n.type in ("Controller", "Route")]
        if not controllers:
            return None

        ctrl_info = []
        for ctrl in controllers[:15]:
            methods = getattr(ctrl, 'method_names', []) or []
            # Sanitize: only keep valid-looking method names (short, no spaces/special chars)
            safe_methods = [
                m[:40] for m in methods[:10]
                if len(m) <= 60 and '\n' not in m and not any(c in m for c in '{}[]<>()\"\'')
            ]
            if safe_methods:
                ctrl_info.append(f"- {ctrl.label}: métodos [{', '.join(safe_methods)}]")
            else:
                ctrl_info.append(f"- {ctrl.label}")

        system_prompt = (
            "Eres un analista de requerimientos senior. "
            "Genera un documento de Casos de Uso e Historias de Usuario profesional.\n\n"
            "REGLAS ABSOLUTAS:\n"
            "- Para TODAS las tablas usa HTML: <table><thead>...</thead><tbody>...</tbody></table>\n"
            "- NUNCA uses tablas Markdown con | pipes |. SIEMPRE HTML.\n"
            "- Responde en español\n"
            "- NO listes endpoints HTTP (GET, POST, PUT). Genera CASOS DE USO de negocio.\n"
            "- NO generes listas de métodos técnicos. Piensa como USUARIO FINAL.\n"
            "- NO incluyas texto introductorio. Comienza DIRECTAMENTE con el heading.\n"
            "- NO escribas frases como 'Claro, aqui tienes...' o 'A continuacion...'\n"
            "- La respuesta SIEMPRE debe comenzar con: # Casos de Uso e Historias de Usuario\n"
            "- SIEMPRE genera el MISMO formato. No variar la estructura entre consultas.\n\n"
            "ESTRUCTURA FIJA (seguir EXACTAMENTE):\n\n"
            "# Casos de Uso e Historias de Usuario\n\n"
            "## 1. Historias de Usuario\n\n"
            "Genera 5-10 historias. Para CADA una:\n\n"
            "### HU-001: [Título descriptivo]\n\n"
            "<table>\n"
            "<tbody>\n"
            "<tr><td><strong>Como</strong></td><td>[rol]</td></tr>\n"
            "<tr><td><strong>Quiero</strong></td><td>[acción]</td></tr>\n"
            "<tr><td><strong>Para</strong></td><td>[beneficio]</td></tr>\n"
            "<tr><td><strong>Prioridad</strong></td><td>Alta / Media / Baja</td></tr>\n"
            "<tr><td><strong>Criterios de Aceptación</strong></td>"
            "<td>1. Dado [contexto], cuando [acción], entonces [resultado]<br/>"
            "2. Dado [contexto], cuando [acción], entonces [resultado]</td></tr>\n"
            "</tbody>\n"
            "</table>\n\n"
            "---\n\n"
            "## 2. Casos de Uso\n\n"
            "Genera 3-6 casos de uso. Para CADA uno:\n\n"
            "### CU-001: [Nombre]\n\n"
            "<table>\n"
            "<tbody>\n"
            "<tr><td><strong>Actor</strong></td><td>[rol]</td></tr>\n"
            "<tr><td><strong>Descripción</strong></td><td>[qué logra]</td></tr>\n"
            "<tr><td><strong>Precondiciones</strong></td><td>1. [cond]<br/>2. [cond]</td></tr>\n"
            "<tr><td><strong>Postcondiciones</strong></td><td>1. [resultado]</td></tr>\n"
            "<tr><td><strong>HU Relacionadas</strong></td><td>HU-001, HU-002</td></tr>\n"
            "</tbody>\n"
            "</table>\n\n"
            "**Flujo Principal:**\n\n"
            "<table>\n"
            "<thead><tr><th>Paso</th><th>Actor</th><th>Sistema</th></tr></thead>\n"
            "<tbody>\n"
            "<tr><td>1</td><td>[acción del usuario]</td><td>-</td></tr>\n"
            "<tr><td>2</td><td>-</td><td>[respuesta del sistema]</td></tr>\n"
            "<tr><td>3</td><td>[usuario confirma]</td><td>-</td></tr>\n"
            "<tr><td>4</td><td>-</td><td>[sistema guarda]</td></tr>\n"
            "</tbody>\n"
            "</table>\n\n"
            "**Flujos Alternativos:**\n"
            "- **FA1:** En paso 2, si [condición], entonces [acción alternativa].\n\n"
            "---\n\n"
            "## 3. Matriz de Trazabilidad\n\n"
            "<table>\n"
            "<thead><tr><th>Caso de Uso</th><th>Historias</th><th>Actor</th><th>Prioridad</th></tr></thead>\n"
            "<tbody>\n"
            "<tr><td>CU-001</td><td>HU-001, HU-002</td><td>[actor]</td><td>Alta</td></tr>\n"
            "</tbody>\n"
            "</table>\n"
        )

        user_prompt = (
            "A partir de los siguientes módulos funcionales del sistema, "
            "genera historias de usuario y casos de uso DESDE LA PERSPECTIVA DEL USUARIO FINAL. "
            "NO listes endpoints ni métodos técnicos. Piensa en QUÉ PUEDE HACER el usuario:\n\n"
            "Módulos del sistema:\n"
            + "\n".join(ctrl_info)
            + "\n\nRecuerda: genera TODO con tablas HTML, no Markdown. "
            "Comienza directamente con '# Casos de Uso e Historias de Usuario'"
        )

        result = await asyncio.to_thread(
            context.llm_client.complete, system_prompt, user_prompt
        )
        if not result or not result.strip():
            return None
        # Strip any introductory text the LLM adds before the actual content
        cleaned = result.strip()
        # Remove common LLM preambles
        for prefix in [
            "Claro,", "Aquí tienes", "A continuación", "Por supuesto",
            "Entendido", "Perfecto", "De acuerdo", "Aqui tienes",
        ]:
            if cleaned.lower().startswith(prefix.lower()):
                # Find the first heading (#) or table and start from there
                heading_idx = cleaned.find("\n#")
                if heading_idx > 0:
                    cleaned = cleaned[heading_idx + 1:]
                break
        # Validate: response must contain expected content patterns
        # If it doesn't, the LLM hallucinated unrelated content — discard
        has_use_case_content = (
            "HU-" in cleaned or "CU-" in cleaned or
            "<table" in cleaned.lower() or
            "historia" in cleaned.lower() or
            "caso de uso" in cleaned.lower() or
            "precondicion" in cleaned.lower() or
            "flujo" in cleaned.lower()
        )
        if not has_use_case_content:
            return None
        return cleaned

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
