"""SystemReporterAgent — detects technology stack, generates setup instructions and project description.

Scans repository configuration files to identify languages, frameworks,
databases, and infrastructure tools. Generates setup/run instructions and
a concise project description using the LLM client with heuristic fallback.

Satisfies Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from typing import Any, Optional

from dev_ghost_parser.agent_models import (
    AgentResult,
    SystemReportResult,
    TechStack,
    TechStackEntry,
)
from dev_ghost_parser.base_agent import AgentContext, BaseAgent
from dev_ghost_parser.retry_policy import RetryPolicy

logger = logging.getLogger(__name__)


@dataclass
class ConfigFileInfo:
    """Information about a detected configuration file."""

    filename: str
    path: str
    content: Optional[str] = None


class SystemReporterAgent(BaseAgent):
    """Detects technology stack, generates setup instructions and project description.

    Scans the repository root and first-level subdirectories for known
    configuration files, extracts technology stack metadata, and uses the
    LLM (with heuristic fallback) to produce setup instructions and a
    project description.
    """

    name = "system_reporter"
    description = "Detects technology stack, generates setup instructions and project description"

    @property
    def timeout_seconds(self) -> float:
        """System reporter timeout: 30 seconds."""
        return 30.0

    @property
    def retry_policy(self) -> RetryPolicy:
        """System reporter retry policy: 1 retry, 0.5s base delay, 2x multiplier."""
        return RetryPolicy(max_retries=1, base_delay_seconds=0.5, multiplier=2.0)

    CONFIG_FILES = [
        "package.json",
        "pyproject.toml",
        "Dockerfile",
        "Makefile",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "requirements.txt",
        "composer.json",
        "Gemfile",
        "build.gradle",
    ]

    # Mapping of known dependency names to database entries
    _DB_KEYWORDS: dict[str, str] = {
        "postgres": "PostgreSQL",
        "pg": "PostgreSQL",
        "psycopg": "PostgreSQL",
        "psycopg2": "PostgreSQL",
        "asyncpg": "PostgreSQL",
        "mysql": "MySQL",
        "pymysql": "MySQL",
        "mysql2": "MySQL",
        "redis": "Redis",
        "ioredis": "Redis",
        "mongodb": "MongoDB",
        "mongoose": "MongoDB",
        "pymongo": "MongoDB",
        "mongo": "MongoDB",
        "sqlite": "SQLite",
        "sqlite3": "SQLite",
        "better-sqlite3": "SQLite",
    }

    # Mapping of known dependency names to framework entries
    _FRAMEWORK_KEYWORDS: dict[str, str] = {
        # JavaScript/TypeScript frameworks
        "react": "React",
        "next": "Next.js",
        "express": "Express",
        "fastify": "Fastify",
        "vue": "Vue.js",
        "nuxt": "Nuxt.js",
        "angular": "Angular",
        "svelte": "Svelte",
        "nest": "NestJS",
        "@nestjs/core": "NestJS",
        # Python frameworks
        "fastapi": "FastAPI",
        "django": "Django",
        "flask": "Flask",
        "starlette": "Starlette",
        "tornado": "Tornado",
        "aiohttp": "aiohttp",
        # Ruby frameworks
        "rails": "Ruby on Rails",
        # PHP frameworks
        "laravel": "Laravel",
        "symfony": "Symfony",
    }

    async def execute(self, context: AgentContext) -> AgentResult:
        """Scan repo, detect stack, generate instructions and description.

        Parameters
        ----------
        context:
            Shared agent context containing repo_path, llm_client, and event_queue.

        Returns
        -------
        AgentResult
            Success result with SystemReportResult data, or failure result with error message.
        """
        try:
            await self.emit_progress("Buscando archivos de configuración...")

            configs = self._scan_config_files(context.repo_path)

            # Handle case where no config files found
            if not configs:
                report = SystemReportResult(
                    tech_stack=TechStack(entries=[]),
                    setup_instructions="",
                    project_description="Technology stack could not be determined.",
                    could_not_determine=True,
                )
                return AgentResult(
                    agent_name="system_reporter",
                    success=True,
                    data=asdict(report),
                )

            await self.emit_progress("Detectando stack tecnológico...")

            tech_stack = self._extract_tech_stack(configs)

            await self.emit_progress("Generando instrucciones de instalación...")

            instructions = await self._generate_instructions(
                tech_stack, configs, context
            )

            await self.emit_progress("Generando descripción del proyecto...")

            description = await self._generate_description(
                tech_stack, context.repo_path, context
            )

            report = SystemReportResult(
                tech_stack=tech_stack,
                setup_instructions=instructions,
                project_description=description,
                could_not_determine=False,
            )

            return AgentResult(
                agent_name="system_reporter",
                success=True,
                data=asdict(report),
            )

        except Exception as e:
            logger.exception("SystemReporterAgent failed: %s", e)
            return AgentResult(
                agent_name="system_reporter",
                success=False,
                error_message=str(e),
            )

    def _scan_config_files(self, repo_path: str) -> list[ConfigFileInfo]:
        """Find config files in root and first-level subdirectories.

        Walks the repository root directory and its immediate subdirectories
        looking for known configuration files. For each match, reads the file
        content (silently skipping files that cannot be read).

        Parameters
        ----------
        repo_path:
            Path to the repository root.

        Returns
        -------
        list[ConfigFileInfo]
            List of detected configuration files with their content.
        """
        found: list[ConfigFileInfo] = []

        # Collect directories to scan: root + first-level subdirectories
        dirs_to_scan = [repo_path]
        try:
            for entry in os.listdir(repo_path):
                entry_path = os.path.join(repo_path, entry)
                if os.path.isdir(entry_path) and not entry.startswith("."):
                    dirs_to_scan.append(entry_path)
        except OSError:
            pass

        for dir_path in dirs_to_scan:
            for config_name in self.CONFIG_FILES:
                file_path = os.path.join(dir_path, config_name)
                if os.path.isfile(file_path):
                    content = None
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                    except OSError:
                        pass
                    found.append(
                        ConfigFileInfo(
                            filename=config_name,
                            path=file_path,
                            content=content,
                        )
                    )

        return found

    def _extract_tech_stack(self, configs: list[ConfigFileInfo]) -> TechStack:
        """Parse config files to extract languages, frameworks, infra tools.

        Analyzes the detected configuration files to determine the project's
        technology stack including programming languages, frameworks, databases,
        and infrastructure tools.

        Parameters
        ----------
        configs:
            List of detected configuration files with their content.

        Returns
        -------
        TechStack
            Detected technology stack entries.
        """
        entries: list[TechStackEntry] = []
        languages_added: set[str] = set()
        frameworks_added: set[str] = set()
        databases_added: set[str] = set()
        infra_added: set[str] = set()

        for config in configs:
            # --- Language detection ---
            if config.filename == "package.json":
                lang = self._detect_js_language(config.content)
                if lang not in languages_added:
                    languages_added.add(lang)
                    entries.append(
                        TechStackEntry(name=lang, category="language")
                    )
                # Extract frameworks and databases from package.json
                self._parse_package_json_deps(
                    config.content, entries, frameworks_added, databases_added
                )

            elif config.filename in ("pyproject.toml", "requirements.txt"):
                if "Python" not in languages_added:
                    languages_added.add("Python")
                    entries.append(
                        TechStackEntry(name="Python", category="language")
                    )
                # Extract frameworks and databases
                self._parse_python_deps(
                    config, entries, frameworks_added, databases_added
                )

            elif config.filename == "Cargo.toml":
                if "Rust" not in languages_added:
                    languages_added.add("Rust")
                    entries.append(
                        TechStackEntry(name="Rust", category="language")
                    )

            elif config.filename == "go.mod":
                if "Go" not in languages_added:
                    languages_added.add("Go")
                    entries.append(
                        TechStackEntry(name="Go", category="language")
                    )

            elif config.filename == "pom.xml":
                if "Java" not in languages_added:
                    languages_added.add("Java")
                    entries.append(
                        TechStackEntry(name="Java", category="language")
                    )

            elif config.filename == "composer.json":
                if "PHP" not in languages_added:
                    languages_added.add("PHP")
                    entries.append(
                        TechStackEntry(name="PHP", category="language")
                    )
                self._parse_composer_deps(
                    config.content, entries, frameworks_added, databases_added
                )

            elif config.filename == "Gemfile":
                if "Ruby" not in languages_added:
                    languages_added.add("Ruby")
                    entries.append(
                        TechStackEntry(name="Ruby", category="language")
                    )
                self._parse_gemfile_deps(
                    config.content, entries, frameworks_added, databases_added
                )

            elif config.filename == "build.gradle":
                # Could be Java or Kotlin
                lang = self._detect_gradle_language(config.content)
                if lang not in languages_added:
                    languages_added.add(lang)
                    entries.append(
                        TechStackEntry(name=lang, category="language")
                    )

            # --- Infrastructure detection ---
            if config.filename == "Dockerfile":
                if "Docker" not in infra_added:
                    infra_added.add("Docker")
                    entries.append(
                        TechStackEntry(name="Docker", category="infrastructure")
                    )

            elif config.filename == "Makefile":
                if "Make" not in infra_added:
                    infra_added.add("Make")
                    entries.append(
                        TechStackEntry(name="Make", category="infrastructure")
                    )

        return TechStack(entries=entries)

    async def _generate_instructions(
        self,
        tech_stack: TechStack,
        configs: list[ConfigFileInfo],
        context: AgentContext,
    ) -> str:
        """Generate setup/run instructions using LLM or heuristic fallback.

        If the LLM client is available, sends the tech stack and config file
        contents to generate natural-language setup instructions. Otherwise,
        falls back to heuristic-based instructions.

        Parameters
        ----------
        tech_stack:
            Detected technology stack.
        configs:
            List of detected configuration files.
        context:
            Agent context with LLM client.

        Returns
        -------
        str
            Markdown-formatted setup and run instructions.
        """
        if context.llm_client.available:
            result = await self._llm_generate_instructions(
                tech_stack, configs, context
            )
            if result:
                return result

        # Heuristic fallback
        return self._heuristic_instructions(tech_stack, configs)

    async def _generate_description(
        self,
        tech_stack: TechStack,
        repo_path: str,
        context: AgentContext,
    ) -> str:
        """Generate project description (max 500 chars) using LLM or heuristic.

        If the LLM client is available, generates a concise project description.
        Otherwise, produces a heuristic description based on the tech stack.

        Parameters
        ----------
        tech_stack:
            Detected technology stack.
        repo_path:
            Path to the repository root.
        context:
            Agent context with LLM client.

        Returns
        -------
        str
            Project description, at most 500 characters.
        """
        if context.llm_client.available:
            result = await self._llm_generate_description(
                tech_stack, repo_path, context
            )
            if result:
                # Enforce 500-char limit
                return result[:500]

        # Heuristic fallback
        return self._heuristic_description(tech_stack)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _detect_js_language(self, content: Optional[str]) -> str:
        """Detect whether a package.json project uses TypeScript or JavaScript."""
        if not content:
            return "JavaScript"
        try:
            data = json.loads(content)
            all_deps = {}
            all_deps.update(data.get("dependencies", {}))
            all_deps.update(data.get("devDependencies", {}))
            if "typescript" in all_deps:
                return "TypeScript"
        except (json.JSONDecodeError, TypeError):
            pass
        return "JavaScript"

    def _detect_gradle_language(self, content: Optional[str]) -> str:
        """Detect whether a build.gradle uses Kotlin or Java."""
        if content and ("kotlin" in content.lower() or "org.jetbrains.kotlin" in content):
            return "Kotlin"
        return "Java"

    def _parse_package_json_deps(
        self,
        content: Optional[str],
        entries: list[TechStackEntry],
        frameworks_added: set[str],
        databases_added: set[str],
    ) -> None:
        """Extract framework and database entries from package.json dependencies."""
        if not content:
            return
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return

        all_deps: dict[str, Any] = {}
        all_deps.update(data.get("dependencies", {}))
        all_deps.update(data.get("devDependencies", {}))

        for dep_name in all_deps:
            dep_lower = dep_name.lower()

            # Check frameworks
            for keyword, framework_name in self._FRAMEWORK_KEYWORDS.items():
                if dep_lower == keyword or dep_lower.startswith(f"@{keyword}/"):
                    if framework_name not in frameworks_added:
                        frameworks_added.add(framework_name)
                        entries.append(
                            TechStackEntry(name=framework_name, category="framework")
                        )

            # Check databases
            for keyword, db_name in self._DB_KEYWORDS.items():
                if keyword in dep_lower:
                    if db_name not in databases_added:
                        databases_added.add(db_name)
                        entries.append(
                            TechStackEntry(name=db_name, category="database")
                        )

    def _parse_python_deps(
        self,
        config: ConfigFileInfo,
        entries: list[TechStackEntry],
        frameworks_added: set[str],
        databases_added: set[str],
    ) -> None:
        """Extract framework and database entries from Python config files."""
        if not config.content:
            return

        # Normalize content to lowercase for keyword matching
        content_lower = config.content.lower()

        # Check frameworks
        for keyword, framework_name in self._FRAMEWORK_KEYWORDS.items():
            if keyword in content_lower:
                if framework_name not in frameworks_added:
                    frameworks_added.add(framework_name)
                    entries.append(
                        TechStackEntry(name=framework_name, category="framework")
                    )

        # Check databases
        for keyword, db_name in self._DB_KEYWORDS.items():
            if keyword in content_lower:
                if db_name not in databases_added:
                    databases_added.add(db_name)
                    entries.append(
                        TechStackEntry(name=db_name, category="database")
                    )

    def _parse_composer_deps(
        self,
        content: Optional[str],
        entries: list[TechStackEntry],
        frameworks_added: set[str],
        databases_added: set[str],
    ) -> None:
        """Extract framework and database entries from composer.json."""
        if not content:
            return
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return

        all_deps: dict[str, Any] = {}
        all_deps.update(data.get("require", {}))
        all_deps.update(data.get("require-dev", {}))

        for dep_name in all_deps:
            dep_lower = dep_name.lower()
            for keyword, framework_name in self._FRAMEWORK_KEYWORDS.items():
                if keyword in dep_lower:
                    if framework_name not in frameworks_added:
                        frameworks_added.add(framework_name)
                        entries.append(
                            TechStackEntry(name=framework_name, category="framework")
                        )
            for keyword, db_name in self._DB_KEYWORDS.items():
                if keyword in dep_lower:
                    if db_name not in databases_added:
                        databases_added.add(db_name)
                        entries.append(
                            TechStackEntry(name=db_name, category="database")
                        )

    def _parse_gemfile_deps(
        self,
        content: Optional[str],
        entries: list[TechStackEntry],
        frameworks_added: set[str],
        databases_added: set[str],
    ) -> None:
        """Extract framework and database entries from Gemfile."""
        if not content:
            return

        content_lower = content.lower()

        # Check for Rails
        if "rails" in content_lower:
            if "Ruby on Rails" not in frameworks_added:
                frameworks_added.add("Ruby on Rails")
                entries.append(
                    TechStackEntry(name="Ruby on Rails", category="framework")
                )

        # Check databases
        for keyword, db_name in self._DB_KEYWORDS.items():
            if keyword in content_lower:
                if db_name not in databases_added:
                    databases_added.add(db_name)
                    entries.append(
                        TechStackEntry(name=db_name, category="database")
                    )

    async def _llm_generate_instructions(
        self,
        tech_stack: TechStack,
        configs: list[ConfigFileInfo],
        context: AgentContext,
    ) -> Optional[str]:
        """Use LLM to generate setup instructions."""
        stack_summary = ", ".join(e.name for e in tech_stack.entries)
        config_summaries = []
        for cfg in configs[:5]:  # Limit to first 5 config files for prompt size
            snippet = cfg.content[:2000] if cfg.content else "(empty)"
            config_summaries.append(f"### {cfg.filename}\n```\n{snippet}\n```")

        config_text = "\n\n".join(config_summaries)

        system_prompt = (
            "Eres un asistente de documentación técnica. Genera instrucciones claras y concisas "
            "de instalación y ejecución en formato Markdown para un proyecto de software. "
            "Incluye: prerrequisitos, pasos de instalación, y el comando para iniciar el proyecto localmente. "
            "Sé práctico y específico basándote en los archivos de configuración.\n\n"
            "REGLAS:\n"
            "- Responde SIEMPRE en español\n"
            "- Los nombres de comandos, paquetes y tecnologías se dejan en su idioma original (ej: npm, pip, docker)\n"
            "- Los títulos, descripciones y explicaciones deben ser en español\n"
            "- Usa bloques de código para los comandos"
        )
        user_prompt = (
            f"Stack tecnológico: {stack_summary}\n\n"
            f"Archivos de configuración:\n\n{config_text}\n\n"
            "Genera instrucciones de instalación y ejecución en Markdown, en español."
        )

        try:
            result = await context.llm_client.complete_async(system_prompt, user_prompt)
            return result
        except Exception as e:
            logger.warning("LLM instructions generation failed: %s", e)
            return None

    async def _llm_generate_description(
        self,
        tech_stack: TechStack,
        repo_path: str,
        context: AgentContext,
    ) -> Optional[str]:
        """Use LLM to generate a project description."""
        stack_summary = ", ".join(e.name for e in tech_stack.entries)
        repo_name = os.path.basename(repo_path)

        # Try to read README for better context about the project's purpose
        readme_content = ""
        for readme_name in ["README.md", "readme.md", "README.txt", "README"]:
            readme_path = os.path.join(repo_path, readme_name)
            if os.path.isfile(readme_path):
                try:
                    with open(readme_path, "r", encoding="utf-8", errors="ignore") as f:
                        readme_content = f.read()[:3000]  # First 3000 chars
                except Exception:
                    pass
                break

        # Try to read package.json description or pyproject.toml description
        project_desc_hint = ""
        pkg_path = os.path.join(repo_path, "package.json")
        if os.path.isfile(pkg_path):
            try:
                with open(pkg_path, "r", encoding="utf-8") as f:
                    pkg = json.loads(f.read())
                    project_desc_hint = pkg.get("description", "")
            except Exception:
                pass

        system_prompt = (
            "Eres un asistente de documentación técnica. Genera una descripción concisa del proyecto "
            "en 500 caracteres o menos. Resume el PROPÓSITO REAL del proyecto y su patrón arquitectónico "
            "dominante basándote en el contenido del README y los archivos del repositorio.\n\n"
            "REGLAS ESTRICTAS:\n"
            "- Responde SIEMPRE en español\n"
            "- Los nombres de tecnologías se dejan en su idioma original\n"
            "- NO inventes funcionalidades que no están evidenciadas en los archivos\n"
            "- Basa tu descripción en lo que REALMENTE hace el proyecto según el README y la estructura\n"
            "- Si no hay README claro, describe basándote en la estructura de archivos y dependencias\n"
            "- Devuelve SOLO el texto de la descripción, sin comillas ni explicaciones adicionales"
        )

        user_prompt = f"Nombre del repositorio: {repo_name}\nStack tecnológico: {stack_summary}\n"
        if readme_content:
            user_prompt += f"\nContenido del README:\n{readme_content}\n"
        if project_desc_hint:
            user_prompt += f"\nDescripción del package.json: {project_desc_hint}\n"
        user_prompt += "\nGenera una descripción concisa y precisa del proyecto (máximo 500 caracteres), en español."

        try:
            result = await context.llm_client.complete_async(system_prompt, user_prompt)
            return result
        except Exception as e:
            logger.warning("LLM description generation failed: %s", e)
            return None

    def _heuristic_instructions(
        self, tech_stack: TechStack, configs: list[ConfigFileInfo]
    ) -> str:
        """Generate heuristic-based setup instructions when LLM is unavailable."""
        languages = [e.name for e in tech_stack.entries if e.category == "language"]
        frameworks = [e.name for e in tech_stack.entries if e.category == "framework"]
        config_names = {cfg.filename for cfg in configs}

        sections: list[str] = []
        sections.append("## Prerequisites\n")

        prereqs: list[str] = []
        install_steps: list[str] = []
        run_cmds: list[str] = []

        if "package.json" in config_names:
            prereqs.append("- Node.js (LTS version recommended)")
            prereqs.append("- npm or yarn")
            install_steps.append("```bash\nnpm install\n```")
            if "Next.js" in frameworks:
                run_cmds.append("```bash\nnpm run dev\n```")
            else:
                run_cmds.append("```bash\nnpm start\n```")

        if "pyproject.toml" in config_names or "requirements.txt" in config_names:
            prereqs.append("- Python 3.8+")
            prereqs.append("- pip or uv")
            if "pyproject.toml" in config_names:
                install_steps.append("```bash\npip install -e .\n```")
            else:
                install_steps.append("```bash\npip install -r requirements.txt\n```")
            if "FastAPI" in frameworks:
                run_cmds.append("```bash\nuvicorn main:app --reload\n```")
            elif "Django" in frameworks:
                run_cmds.append("```bash\npython manage.py runserver\n```")
            elif "Flask" in frameworks:
                run_cmds.append("```bash\nflask run\n```")
            else:
                run_cmds.append("```bash\npython main.py\n```")

        if "Cargo.toml" in config_names:
            prereqs.append("- Rust (latest stable)")
            prereqs.append("- Cargo")
            install_steps.append("```bash\ncargo build\n```")
            run_cmds.append("```bash\ncargo run\n```")

        if "go.mod" in config_names:
            prereqs.append("- Go 1.21+")
            install_steps.append("```bash\ngo mod download\n```")
            run_cmds.append("```bash\ngo run .\n```")

        if "pom.xml" in config_names:
            prereqs.append("- Java 17+")
            prereqs.append("- Maven")
            install_steps.append("```bash\nmvn install\n```")
            run_cmds.append("```bash\nmvn spring-boot:run\n```")

        if "build.gradle" in config_names:
            prereqs.append("- Java 17+")
            prereqs.append("- Gradle")
            install_steps.append("```bash\ngradle build\n```")
            run_cmds.append("```bash\ngradle run\n```")

        if "composer.json" in config_names:
            prereqs.append("- PHP 8.0+")
            prereqs.append("- Composer")
            install_steps.append("```bash\ncomposer install\n```")
            run_cmds.append("```bash\nphp artisan serve\n```")

        if "Gemfile" in config_names:
            prereqs.append("- Ruby 3.0+")
            prereqs.append("- Bundler")
            install_steps.append("```bash\nbundle install\n```")
            if "Ruby on Rails" in frameworks:
                run_cmds.append("```bash\nrails server\n```")
            else:
                run_cmds.append("```bash\nruby main.rb\n```")

        if "Dockerfile" in config_names:
            prereqs.append("- Docker")
            install_steps.append("```bash\ndocker build -t project .\n```")
            run_cmds.append("```bash\ndocker run -p 8080:8080 project\n```")

        # Deduplicate prereqs
        seen: set[str] = set()
        unique_prereqs: list[str] = []
        for p in prereqs:
            if p not in seen:
                seen.add(p)
                unique_prereqs.append(p)

        sections.append("\n".join(unique_prereqs) if unique_prereqs else "- See project documentation")
        sections.append("\n\n## Installation\n")
        sections.append("\n".join(install_steps) if install_steps else "See project documentation.")
        sections.append("\n\n## Run\n")
        sections.append("\n".join(run_cmds) if run_cmds else "See project documentation.")

        return "".join(sections)

    def _heuristic_description(self, tech_stack: TechStack) -> str:
        """Generate a heuristic project description when LLM is unavailable."""
        languages = [e.name for e in tech_stack.entries if e.category == "language"]
        frameworks = [e.name for e in tech_stack.entries if e.category == "framework"]

        if frameworks:
            desc = f"A {', '.join(languages)} application using {', '.join(frameworks)}."
        elif languages:
            desc = f"A {', '.join(languages)} application."
        else:
            desc = "A software project."

        # Ensure max 500 chars
        return desc[:500]
