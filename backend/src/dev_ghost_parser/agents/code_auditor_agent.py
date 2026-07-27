"""CodeAuditorAgent — wraps node inspection logic as an async agent.

Scans source files from the repository, extracts method implementations,
and optionally generates LLM-based method descriptions and code audits.
Emits progress events per node inspected.

Satisfies Requirements: 1.2, 2.2, 2.3, 2.4
"""

from __future__ import annotations

import asyncio
import glob
import hashlib
import logging
import os
from typing import Any, Optional

from dev_ghost_parser.agent_models import AgentResult
from dev_ghost_parser.base_agent import AgentContext, BaseAgent
from dev_ghost_parser.retry_policy import RetryPolicy
from dev_ghost_parser.work_partitioner import WorkPartitioner

logger = logging.getLogger(__name__)

# File extensions to scan for source code
_SOURCE_PATTERNS = (
    "**/*.ts",
    "**/*.js",
    "**/*.py",
    "**/*.php",
    "**/*.java",
    "**/*.go",
    "**/*.rb",
    "**/*.rs",
    "**/*.cs",
)

# Directories to skip during scanning
_SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build"}

# Maximum number of nodes to run LLM analysis on
_MAX_LLM_NODES = 10

# Maximum concurrent LLM calls
_LLM_CONCURRENCY = 5


class CodeAuditorAgent(BaseAgent):
    """Audits code quality, generates method descriptions, and extracts source code.

    Scans source files from the repository, extracts method implementations
    using heuristic brace/indentation counting, and optionally runs parallel
    LLM calls to generate descriptions and audit reports for top nodes.

    Integrates WorkPartitioner to split large file sets (>50 files) into
    parallel batches for faster processing.
    """

    name = "code_auditor"
    description = "Audits code quality, generates method descriptions, and extracts source code"

    def __init__(self) -> None:
        super().__init__()
        self._partitioner = WorkPartitioner(batch_size=20, file_threshold=50, max_batch_concurrency=5)

    @property
    def timeout_seconds(self) -> float:
        """Code auditor timeout: 180 seconds (audits multiple components via LLM)."""
        return 180.0

    @property
    def retry_policy(self) -> RetryPolicy:
        """Code auditor retry policy: 2 retries, 1.5s base delay, 2x multiplier."""
        return RetryPolicy(max_retries=2, base_delay_seconds=1.5, multiplier=2.0)

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute code auditing on the repository.

        When the number of source files exceeds the partitioning threshold (50),
        uses WorkPartitioner to split processing into parallel batches for
        faster execution.

        Parameters
        ----------
        context:
            Shared agent context containing repo_path, llm_client, and event_queue.

        Returns
        -------
        AgentResult
            Success result with node_inspections dict, or failure result with error.
        """
        try:
            await self.emit_progress("Reading source files...")

            # Read all source files from the repository
            source_files = await asyncio.to_thread(
                self._scan_source_files, context.repo_path
            )

            await self.emit_progress(
                f"Found {len(source_files)} source files to analyze"
            )

            await self.emit_progress("Extracting method implementations...")

            # Use WorkPartitioner for large repositories
            if self._partitioner.should_partition(len(source_files)):
                all_method_sources = await self._extract_methods_partitioned(
                    source_files
                )
            else:
                # Extract method code for all files directly
                all_method_sources = await asyncio.to_thread(
                    self._extract_all_methods, source_files
                )

            await self.emit_progress(
                f"Extracted methods from {len(all_method_sources)} components"
            )

            # Build node_inspections with source code data
            # The frontend looks up inspections by node ID (SHA-1 of relative path),
            # so we use the same hashing that code_flow_analyzer uses for node IDs.
            node_inspections: dict[str, dict[str, Any]] = {}
            for component_id, sources in all_method_sources.items():
                # component_id is the relative path (e.g., "src/repos/UserRepo.ts")
                # Convert to the SHA-1 node ID that the frontend expects
                node_id = hashlib.sha1(component_id.encode("utf-8")).hexdigest()
                node_inspections[node_id] = {
                    "descriptions": {},
                    "audit": None,
                    "methodSources": sources,
                }

            # If LLM is available, run audits on the top components
            if context.llm_client.available and all_method_sources:
                # Sort by number of methods (most methods first)
                sorted_components = sorted(
                    all_method_sources.items(),
                    key=lambda x: len(x[1]),
                    reverse=True,
                )
                nodes_to_audit = sorted_components[:_MAX_LLM_NODES]

                semaphore = asyncio.Semaphore(_LLM_CONCURRENCY)

                async def audit_component(
                    component_id: str, methods: dict[str, str]
                ) -> tuple[str, dict[str, str], Optional[str]]:
                    """Run LLM-based description + audit for a single component."""
                    async with semaphore:
                        method_names = list(methods.keys())[:20]
                        methods_str = ", ".join(method_names)

                        # Include source code snippets for better context
                        source_snippets = ""
                        for m_name, m_source in list(methods.items())[:5]:
                            # Include first 8 lines of each method for context
                            snippet = "\n".join(m_source.split("\n")[:8])
                            source_snippets += f"\n--- {m_name} ---\n{snippet}\n"

                        desc_system = (
                            "Eres un analista de código experto. Para cada método/función listado, "
                            "genera una descripción PRECISA y TÉCNICA en español (max 20 palabras) "
                            "explicando QUÉ hace específicamente, basándote en el código fuente proporcionado.\n\n"
                            "REGLAS:\n"
                            "- Describe la LÓGICA REAL del método, no solo lo que sugiere su nombre\n"
                            "- Menciona qué datos recibe, qué retorna, o qué efecto secundario produce\n"
                            "- Si manipula base de datos, di qué tabla/entidad y qué operación\n"
                            "- Si valida datos, especifica qué valida\n"
                            "- Si llama a servicios externos, nómbralos\n\n"
                            "Responde SOLO en formato: nombre_metodo: descripcion\n"
                            "Un método por línea. Sin numeración, sin bullets."
                        )
                        desc_user = (
                            f"Componente: {component_id}\n"
                            f"Métodos: {methods_str}\n\n"
                            f"Código fuente (primeras líneas de cada método):{source_snippets}"
                        )

                        audit_system = (
                            "Eres un auditor de código senior con experiencia en arquitectura de software, "
                            "seguridad y patrones de diseño. Realiza un análisis PROFUNDO y DETALLADO "
                            "del componente basándote en su código fuente real.\n\n"
                            "REGLAS DE FORMATO:\n"
                            "- Responde en español con Markdown para headings/texto\n"
                            "- Para TODAS las tablas usa HTML: <table><thead>...</thead><tbody>...</tbody></table>\n"
                            "- NUNCA uses tablas markdown (| col |). SIEMPRE HTML tables.\n\n"
                            "ESTRUCTURA OBLIGATORIA:\n\n"
                            "## Calidad General\n"
                            "Puntuación X/10 con JUSTIFICACIÓN detallada (menciona principios SOLID, "
                            "cohesión, acoplamiento, complejidad ciclomática estimada).\n\n"
                            "## Responsabilidades del Componente\n"
                            "Lista las responsabilidades reales que tiene este componente. "
                            "Evalúa si viola el Principio de Responsabilidad Única (SRP).\n\n"
                            "## Buenas Prácticas Detectadas\n"
                            "Identifica patrones positivos ESPECÍFICOS con referencia a los métodos.\n\n"
                            "## Problemas Detectados\n"
                            "Tabla HTML con columnas: Severidad (🔴Alta/🟡Media/🟢Baja), Problema, "
                            "Método Afectado, Impacto, Solución Propuesta.\n\n"
                            "## Riesgos de Seguridad\n"
                            "Identifica vulnerabilidades específicas (SQL injection, XSS, auth bypass, "
                            "secrets hardcodeados, race conditions, etc). Si no hay, explica por qué.\n\n"
                            "## Deuda Técnica\n"
                            "Identifica código que necesita refactorización con prioridad y esfuerzo estimado.\n\n"
                            "## Recomendaciones Prioritarias\n"
                            "Top 3 acciones concretas ordenadas por impacto/esfuerzo.\n\n"
                            "SÉ ESPECÍFICO. Referencia nombres de métodos reales. No uses frases genéricas."
                        )
                        audit_user = (
                            f"Componente: {component_id}\n"
                            f"Métodos ({len(method_names)}): {methods_str}\n\n"
                            f"Código fuente:{source_snippets}"
                        )

                        # Run both LLM calls in parallel
                        desc_result, audit_result = await asyncio.gather(
                            context.llm_client.complete_async(desc_system, desc_user),
                            context.llm_client.complete_async(audit_system, audit_user),
                        )

                        # Parse descriptions
                        descriptions: dict[str, str] = {}
                        if desc_result:
                            for line in desc_result.strip().split("\n"):
                                if ":" in line:
                                    parts = line.split(":", 1)
                                    descriptions[parts[0].strip()] = parts[1].strip()

                        # Ensure all methods have an entry
                        for m in method_names:
                            if m not in descriptions:
                                descriptions[m] = ""

                        return component_id, descriptions, audit_result

                # Run LLM audits in parallel for top components
                tasks = []
                for component_id, methods in nodes_to_audit:
                    await self.emit_progress(
                        f"Auditing code quality for {component_id}..."
                    )
                    tasks.append(audit_component(component_id, methods))

                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, tuple):
                        comp_id, descriptions, audit_text = result
                        node_id = hashlib.sha1(comp_id.encode("utf-8")).hexdigest()
                        if node_id in node_inspections:
                            node_inspections[node_id]["descriptions"] = descriptions
                            node_inspections[node_id]["audit"] = audit_text
                        else:
                            node_inspections[node_id] = {
                                "descriptions": descriptions,
                                "audit": audit_text,
                                "methodSources": all_method_sources.get(comp_id, {}),
                            }
                    elif isinstance(result, Exception):
                        logger.warning("LLM audit failed for a component: %s", result)

            return AgentResult(
                agent_name="code_auditor",
                success=True,
                data=node_inspections,
            )

        except Exception as e:
            logger.exception("CodeAuditorAgent failed: %s", e)
            return AgentResult(
                agent_name="code_auditor",
                success=False,
                error_message=str(e),
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _extract_methods_partitioned(
        self, source_files: dict[str, str]
    ) -> dict[str, dict[str, str]]:
        """Extract methods using WorkPartitioner for large file sets.

        Splits the file list into batches and processes each batch concurrently,
        emitting progress events per batch completion.

        Parameters
        ----------
        source_files:
            Mapping of relative file paths to their text content.

        Returns
        -------
        dict mapping component identifiers to dicts of method_name → source_code.
        """
        file_list = list(source_files.keys())
        batches = self._partitioner.create_batches(file_list)

        await self.emit_progress(
            f"Partitioning {len(file_list)} files into {len(batches)} batches"
        )

        async def process_batch(batch_files: list[str]) -> dict[str, dict[str, str]]:
            """Process a single batch of files."""
            batch_sources = {f: source_files[f] for f in batch_files}
            return await asyncio.to_thread(
                self._extract_all_methods, batch_sources
            )

        async def progress_callback(completed: int, total: int) -> None:
            """Report batch completion progress."""
            pct = (completed / total) * 100.0 if total > 0 else 100.0
            await self.emit_progress(
                f"Processing batch {completed}/{total}", progress_pct=pct
            )

        batch_results = await self._partitioner.process_batches(
            batches, process_batch, progress_callback
        )

        # Merge results from all successful batches
        all_methods: dict[str, dict[str, str]] = {}
        for result in batch_results:
            if result.success and result.data:
                all_methods.update(result.data)

        return all_methods

    def _scan_source_files(self, repo_path: str) -> dict[str, str]:
        """Scan the repository for source files and read their contents.

        Parameters
        ----------
        repo_path:
            Absolute path to the cloned repository root.

        Returns
        -------
        dict mapping relative file paths to their text content.
        """
        source_files: dict[str, str] = {}

        for pattern in _SOURCE_PATTERNS:
            for filepath in glob.glob(
                os.path.join(repo_path, pattern), recursive=True
            ):
                # Skip excluded directories
                if any(skip in filepath.split(os.sep) for skip in _SKIP_DIRS):
                    continue

                rel_path = os.path.relpath(filepath, repo_path)
                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        source_files[rel_path] = f.read()
                except Exception:
                    pass

        return source_files

    def _extract_all_methods(
        self, source_files: dict[str, str]
    ) -> dict[str, dict[str, str]]:
        """Extract method implementations from all source files.

        Groups methods by their containing file/component and returns
        extracted source code for each method found.

        Parameters
        ----------
        source_files:
            Mapping of relative paths to file contents.

        Returns
        -------
        dict mapping component identifiers to dicts of method_name → source_code.
        """
        all_methods: dict[str, dict[str, str]] = {}

        for rel_path, content in source_files.items():
            methods = self._extract_methods_from_file(rel_path, content)
            if methods:
                # Use the relative path as the component identifier
                component_id = rel_path.replace("\\", "/")
                all_methods[component_id] = methods

        return all_methods

    def _extract_methods_from_file(
        self, rel_path: str, content: str
    ) -> dict[str, str]:
        """Extract individual method/function definitions from a single file.

        Uses heuristic detection based on common patterns for function
        definitions in various languages (brace-based and indentation-based).

        Parameters
        ----------
        rel_path:
            Relative path of the file (used for extension detection).
        content:
            Full text content of the file.

        Returns
        -------
        dict mapping method names to their extracted source code.
        """
        methods: dict[str, str] = {}
        lines = content.split("\n")
        is_python = rel_path.endswith(".py")

        i = 0
        while i < len(lines):
            line = lines[i]
            method_name = self._detect_method_name(line, is_python)

            if method_name and method_name not in methods:
                # Extract method body
                code = self._extract_method_body(lines, i, is_python)
                if code:
                    methods[method_name] = code

            i += 1

        return methods

    def _detect_method_name(self, line: str, is_python: bool) -> Optional[str]:
        """Detect a method/function name from a line of code.

        Parameters
        ----------
        line:
            A single line of source code.
        is_python:
            Whether the file is a Python file.

        Returns
        -------
        The detected method name, or None if the line doesn't define a method.
        """
        stripped = line.strip()

        if is_python:
            # Python: def method_name(...) or async def method_name(...)
            if stripped.startswith("def ") or stripped.startswith("async def "):
                prefix = "async def " if stripped.startswith("async def ") else "def "
                rest = stripped[len(prefix):]
                paren_idx = rest.find("(")
                if paren_idx > 0:
                    name = rest[:paren_idx].strip()
                    # Skip dunder methods and private helpers for brevity
                    if not name.startswith("__"):
                        return name
        else:
            # JS/TS/Java/Go/etc: look for function-like patterns
            # Pattern: function name(
            if "function " in stripped and "(" in stripped:
                idx = stripped.find("function ") + len("function ")
                rest = stripped[idx:]
                # Handle function* for generators
                if rest.startswith("*"):
                    rest = rest[1:]
                paren_idx = rest.find("(")
                if paren_idx > 0:
                    name = rest[:paren_idx].strip()
                    if name and name.isidentifier():
                        return name

            # Pattern: name( for method definitions (class methods, arrow functions)
            # e.g., "  methodName(" or "const name = ("
            if "(" in stripped and not stripped.startswith("//") and not stripped.startswith("/*"):
                # Arrow function: const/let/var name = (...) =>
                for keyword in ("const ", "let ", "var "):
                    if stripped.startswith(keyword):
                        rest = stripped[len(keyword):]
                        eq_idx = rest.find("=")
                        if eq_idx > 0:
                            name = rest[:eq_idx].strip()
                            if name and name.isidentifier():
                                return name
                        break

                # Class method: name(...) { or async name(...) {
                if stripped.startswith("async "):
                    rest = stripped[len("async "):]
                else:
                    rest = stripped

                paren_idx = rest.find("(")
                if paren_idx > 0 and not any(
                    rest.startswith(kw)
                    for kw in ("if", "for", "while", "switch", "catch", "return", "import", "export")
                ):
                    name = rest[:paren_idx].strip()
                    if name and name.isidentifier() and len(name) > 1:
                        return name

        return None

    def _extract_method_body(
        self, lines: list[str], start_idx: int, is_python: bool
    ) -> str:
        """Extract the full body of a method starting at the given line index.

        Uses brace counting for C-style languages and indentation for Python.

        Parameters
        ----------
        lines:
            All lines in the file.
        start_idx:
            The line index where the method definition starts.
        is_python:
            Whether the file is a Python file.

        Returns
        -------
        The extracted method source code, or empty string if extraction failed.
        """
        if is_python:
            return self._extract_python_method(lines, start_idx)
        else:
            return self._extract_brace_method(lines, start_idx)

    def _extract_python_method(self, lines: list[str], start_idx: int) -> str:
        """Extract a Python function body using indentation."""
        start_line = lines[start_idx]
        base_indent = len(start_line) - len(start_line.lstrip())
        end_idx = start_idx + 1

        for j in range(start_idx + 1, min(start_idx + 50, len(lines))):
            line = lines[j]
            if line.strip() and (len(line) - len(line.lstrip())) <= base_indent:
                end_idx = j
                break
            end_idx = j + 1

        return "\n".join(lines[start_idx:end_idx])

    def _extract_brace_method(self, lines: list[str], start_idx: int) -> str:
        """Extract a method body using brace counting for C-style languages."""
        brace_count = 0
        found_open = False
        end_idx = min(start_idx + 50, len(lines))

        for j in range(start_idx, min(start_idx + 100, len(lines))):
            brace_count += lines[j].count("{") - lines[j].count("}")
            if "{" in lines[j]:
                found_open = True
            if found_open and brace_count <= 0 and j > start_idx:
                end_idx = j + 1
                break

        # Fallback: if no braces found, take up to 50 lines
        if not found_open:
            end_idx = min(start_idx + 50, len(lines))

        return "\n".join(lines[start_idx:end_idx])
