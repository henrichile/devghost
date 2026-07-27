"""
Artifacts Generator — generates architecture documentation using LLM.

Produces:
1. C4 Diagram (Mermaid.js code)
2. Database Dictionary (Markdown table)
3. Architecture Decision Record (ADR)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .llm_client import LLM_Client
    from .models import CodeFlowResult, ERResult, Node

logger = logging.getLogger(__name__)


class Artifacts_Generator:
    """Generates architecture documentation artifacts using LLM."""

    def __init__(self, llm_client: "LLM_Client | None" = None) -> None:
        self._llm_client = llm_client

    def generate_c4_diagram(
        self, code_flow: "CodeFlowResult | None", er_result: "ERResult | None"
    ) -> str | None:
        """Generate a C4 Component diagram in Mermaid.js syntax."""
        if not self._llm_client or not self._llm_client.available:
            return None

        components = self._extract_components(code_flow)
        entities = self._extract_entities(er_result)

        if not components and not entities:
            return None

        user_prompt = (
            f"Componentes del sistema:\n{components}\n\n"
            f"Entidades de base de datos:\n{entities}"
        )
        system_prompt = (
            "Genera un diagrama de arquitectura usando sintaxis Mermaid valida (flowchart TD). "
            "Reglas ESTRICTAS de sintaxis Mermaid que DEBES seguir:\n"
            "- Solo usa '-->' para conexiones\n"
            "- Los nombres de subgraph NO deben tener parentesis ni caracteres especiales. "
            "Usa nombres simples como: subgraph Controladores, subgraph Servicios, subgraph BD\n"
            "- Los IDs de nodos deben ser alfanumericos sin espacios (ej: authCtrl, userSvc)\n"
            "- Las etiquetas van entre corchetes: authCtrl[AuthController]\n"
            "- Para base de datos usa la forma cilindro: db[(BaseDatos)]\n"
            "- NO uses <|-- ni --|> ni --- ni ningun operador que no sea -->\n"
            "- NO pongas parentesis () en nombres de subgraph\n"
            "- Para labels en conexiones usa pipes: A -->|label| B (NUNCA A --> [label] B)\n"
            "- NUNCA pongas corchetes [] despues de --> en una conexion\n\n"
            "Estructura:\n"
            "subgraph Controladores\n"
            "subgraph Servicios\n"
            "subgraph Repositorios\n"
            "subgraph BaseDatos\n"
            "Flechas: Controlador --> Servicio --> Repositorio --> BD\n\n"
            "Responde UNICAMENTE con el codigo Mermaid. "
            "Empieza directamente con 'flowchart TD' sin bloques ```."
        )

        result = self._llm_client.complete(system_prompt, user_prompt)
        if result:
            result = self._sanitize_mermaid(result)
        return result

    @staticmethod
    def _sanitize_mermaid(code: str) -> str:
        """Clean common LLM Mermaid syntax errors."""
        import re
        # Remove markdown code fences if present
        code = re.sub(r'^```\w*\n?', '', code)
        code = re.sub(r'\n?```$', '', code)
        # Fix subgraph names with parentheses: "subgraph Base de datos (entidades)" -> "subgraph BaseDatos"
        code = re.sub(r'subgraph\s+(.+?)\s*\(.*?\)', lambda m: f'subgraph {m.group(1).replace(" ", "")}', code)
        # Remove <|-- patterns
        code = code.replace('<|--', '-->')
        code = code.replace('--|>', '-->')
        # Fix brackets in connection labels: A --> [text] B → A --> |text| B
        code = re.sub(r'(-->|---)\s*\[([^\]]*)\]', r'\1|\2|', code)
        # Fix standalone brackets as node IDs in connections (e.g. "A --> [Bad Node]")
        # Replace square brackets in node references with round parens
        lines = code.split('\n')
        fixed_lines = []
        for line in lines:
            # Skip subgraph/end lines and node definitions (id[label])
            stripped = line.strip()
            if stripped.startswith('subgraph') or stripped == 'end' or stripped.startswith('flowchart') or stripped.startswith('graph'):
                fixed_lines.append(line)
                continue
            # For connection lines, replace unmatched [ ] that aren't node definitions
            # Pattern: word[text] is valid, but --> [text] or bare [text] on connections is not
            if '-->' in line or '---' in line:
                # Replace [text] that appears right after --> with |text|
                line = re.sub(r'-->\s*\[([^\]]*)\]\s*$', r'--> |\1|', line)
                line = re.sub(r'-->\s*\[([^\]]*)\]\s*(-->)', r'--> |\1| \2', line)
            fixed_lines.append(line)
        code = '\n'.join(fixed_lines)
        # Remove any remaining problematic characters in node IDs
        # Replace special chars in IDs (keep only alphanumeric, underscore, dash)
        return code.strip()

    def generate_db_dictionary(
        self, er_result: "ERResult | None"
    ) -> str | None:
        """Generate a database dictionary as a Markdown table."""
        if not self._llm_client or not self._llm_client.available:
            return None
        if not er_result or not er_result.entities:
            return None

        entities_detail = []
        for entity in er_result.entities:
            attrs = ", ".join(f"{a.name} ({a.type})" for a in entity.attributes) or "sin atributos"
            pk = getattr(entity, "primaryKey", "id") or "id"
            entities_detail.append(f"- {entity.name}: PK={pk}, Atributos: {attrs}")

        relations_detail = []
        if hasattr(er_result, "relations") and er_result.relations:
            for rel in er_result.relations:
                fk = getattr(rel, "foreignKey", "") or ""
                relations_detail.append(
                    f"- {getattr(rel, 'from_entity', '?')} → {getattr(rel, 'to_entity', '?')} "
                    f"({getattr(rel, 'type', 'unknown')}, FK: {fk})"
                )

        user_prompt = (
            f"Entidades:\n" + "\n".join(entities_detail) + "\n\n"
            f"Relaciones:\n" + ("\n".join(relations_detail) if relations_detail else "No detectadas")
        )
        system_prompt = (
            "Genera un Diccionario de Base de Datos completo. "
            "Usa Markdown para headings y texto, pero para TODAS las tablas usa HTML puro "
            "(<table>, <thead>, <tbody>, <tr>, <th>, <td>). "
            "Incluye una tabla HTML por cada entidad con columnas: Campo, Tipo, PK/FK, Descripcion. "
            "Al final incluye una seccion de Relaciones explicando las foreign keys. "
            "Responde sin bloques de codigo."
        )

        return self._llm_client.complete(system_prompt, user_prompt)

    def generate_adr(
        self, code_flow: "CodeFlowResult | None", er_result: "ERResult | None"
    ) -> str | None:
        """Generate an Architecture Decision Record (ADR)."""
        if not self._llm_client or not self._llm_client.available:
            return None

        components = self._extract_components(code_flow)
        entities = self._extract_entities(er_result)

        if not components:
            return None

        user_prompt = (
            f"Componentes:\n{components}\n\n"
            f"Entidades:\n{entities}"
        )
        system_prompt = (
            "Genera un Architecture Decision Record (ADR) en formato Markdown analizando "
            "el patron de arquitectura de este sistema. El ADR debe incluir:\n"
            "## Titulo\n## Contexto\n## Decision\n## Patron Identificado\n"
            "## Componentes Clave\n## Consecuencias\n\n"
            "Identifica si es MVC, Layered, Hexagonal, etc. basandote en los controladores, "
            "servicios y repositorios presentes. "
            "Responde SOLO con el Markdown del ADR, sin explicaciones adicionales."
        )

        return self._llm_client.complete(system_prompt, user_prompt)

    def _extract_components(self, code_flow: "CodeFlowResult | None") -> str:
        """Extract component summary from code flow."""
        if not code_flow or not code_flow.nodes:
            return "Sin componentes detectados"

        lines = []
        by_type: dict[str, list[str]] = {}
        for node in code_flow.nodes:
            by_type.setdefault(node.type, []).append(node.label)

        for ntype, labels in by_type.items():
            lines.append(f"- {ntype}: {', '.join(labels[:10])}")

        return "\n".join(lines)

    def _extract_entities(self, er_result: "ERResult | None") -> str:
        """Extract entity summary from ER result."""
        if not er_result or not er_result.entities:
            return "Sin entidades detectadas"

        return ", ".join(e.name for e in er_result.entities[:15])

    def generate_rbac_matrix(
        self, code_flow: "CodeFlowResult | None"
    ) -> str | None:
        """Generate a Security & Permissions Matrix (RBAC) in Markdown."""
        if not self._llm_client or not self._llm_client.available:
            return None
        if not code_flow or not code_flow.nodes:
            return None

        # Extract controllers, routes, and middleware
        controllers = [n.label for n in code_flow.nodes if n.type == "Controller"]
        routes = [n.label for n in code_flow.nodes if n.type == "Route"]
        middleware = [n.label for n in code_flow.nodes if n.type == "Middleware"]
        methods_by_ctrl: dict[str, list[str]] = {}
        for node in code_flow.nodes:
            if node.type == "Controller" and node.method_names:
                methods_by_ctrl[node.label] = node.method_names[:10]

        if not controllers and not routes:
            return None

        user_prompt = (
            f"Controladores: {', '.join(controllers[:10])}\n"
            f"Rutas: {', '.join(routes[:10]) or 'no detectadas'}\n"
            f"Middleware: {', '.join(middleware[:10]) or 'ninguno detectado'}\n"
            f"Metodos por controlador:\n" +
            "\n".join(f"  {ctrl}: {', '.join(methods)}" for ctrl, methods in methods_by_ctrl.items())
        )
        system_prompt = (
            "Genera una Matriz de Seguridad y Permisos (RBAC).\n\n"
            "FORMATO: Usa Markdown para texto y headings, pero para TODAS las tablas usa HTML puro.\n\n"
            "Ejemplo de tabla HTML que debes usar:\n"
            "<table>\n"
            "<thead><tr><th>Columna1</th><th>Columna2</th></tr></thead>\n"
            "<tbody>\n"
            "<tr><td>valor1</td><td>valor2</td></tr>\n"
            "</tbody>\n"
            "</table>\n\n"
            "Estructura del documento:\n\n"
            "## Matriz RBAC\n\n"
            "Una tabla HTML con columnas: Ruta/Endpoint, Metodo, Autenticacion, Rol Requerido, Descripcion\n\n"
            "## Middleware de Seguridad Detectado\n\n"
            "Una tabla HTML con columnas: Nombre, Descripcion, Tipo, Alcance\n\n"
            "## Resumen de Roles\n\n"
            "Una tabla HTML con columnas: Rol, Permisos, Endpoints Accesibles\n\n"
            "IMPORTANTE: Usa <table>, <thead>, <tbody>, <tr>, <th>, <td> para TODAS las tablas.\n"
            "El resto del contenido (titulos, parrafos, listas) puede ser Markdown normal.\n"
            "Responde sin bloques de codigo."
        )

        return self._llm_client.complete(system_prompt, user_prompt)

    def generate_test_plan(
        self, code_flow: "CodeFlowResult | None", repo_path: str | None = None
    ) -> str | None:
        """Generate a Testing Guide that detects existing tests and suggests improvements."""
        if not self._llm_client or not self._llm_client.available:
            return None
        if not code_flow or not code_flow.nodes:
            return None

        # Collect key methods from services, controllers, and repositories
        key_methods: list[str] = []
        for node in code_flow.nodes:
            if node.type in ("Service", "Controller", "Repository") and node.method_names:
                for method in node.method_names[:5]:
                    key_methods.append(f"{node.label}.{method}")

        if not key_methods:
            return None

        # Detect existing tests in the repository
        existing_tests = self._detect_existing_tests(repo_path) if repo_path else ""

        if existing_tests:
            user_prompt = (
                f"Funciones clave del sistema:\n" +
                "\n".join(f"- {m}" for m in key_methods[:25]) +
                f"\n\nArchivos de test existentes encontrados:\n{existing_tests}"
            )
            system_prompt = (
                "Analiza los tests existentes del repositorio y genera un reporte en Markdown:\n\n"
                "## Estado Actual de Testing\n"
                "- Indica que tests existen y que cubren\n"
                "- Evalua la cobertura: que funciones tienen tests y cuales no\n\n"
                "## Oportunidades de Mejora\n"
                "- Identifica funciones sin tests\n"
                "- Sugiere tests que faltan (edge cases, error handling, integracion)\n"
                "- Indica si los tests existentes siguen buenas practicas\n\n"
                "## Tests Sugeridos\n"
                "Para cada funcion sin cobertura, genera un stub de test con:\n"
                "- Nombre descriptivo\n"
                "- Que valida\n"
                "- Codigo plantilla\n\n"
                "Responde SOLO con el Markdown."
            )
        else:
            user_prompt = (
                f"Funciones clave detectadas:\n" +
                "\n".join(f"- {m}" for m in key_methods[:25])
            )
            system_prompt = (
                "Este repositorio NO tiene tests. Genera una Guia de Testing completa en Markdown:\n\n"
                "## Estado: Sin Tests Detectados\n"
                "Indica que no se encontraron archivos de test.\n\n"
                "## Plan de Testing Sugerido\n"
                "### Tests Unitarios Prioritarios\n"
                "Para cada funcion clave, genera:\n"
                "- Nombre del test\n"
                "- Que valida\n"
                "- Stub de codigo del test\n\n"
                "### Tests de Integracion\n"
                "Sugiere tests de integracion entre componentes.\n\n"
                "### Configuracion Recomendada\n"
                "Sugiere framework de testing segun el lenguaje detectado.\n\n"
                "Responde SOLO con el Markdown."
            )

        return self._llm_client.complete(system_prompt, user_prompt)

    def generate_use_cases(self, code_flow: "CodeFlowResult | None") -> str | None:
        """Generate User Stories and Use Cases from Controller/Route methods."""
        if not self._llm_client or not self._llm_client.available:
            return None
        if not code_flow or not code_flow.nodes:
            return None

        # Filtrar nodos relevantes
        controllers = [n for n in code_flow.nodes if n.type in ("Controller", "Route")]
        if not controllers:
            return None

        # Extraer contexto (middleware, services) via edges
        user_prompt = self._build_use_case_prompt(code_flow, controllers)
        system_prompt = self._build_use_case_system_prompt()

        result = self._llm_client.complete(system_prompt, user_prompt)
        return result if result and result.strip() else None

    def _build_use_case_prompt(
        self, code_flow: "CodeFlowResult", controllers: list["Node"]
    ) -> str:
        """Build the user prompt with controller info, services, and middleware."""
        # Mapear edges para encontrar dependencias
        node_map = {n.id: n for n in code_flow.nodes}
        edges_from: dict[str, list] = {}
        for edge in code_flow.edges:
            edges_from.setdefault(edge.source, []).append(edge)

        lines: list[str] = []
        for ctrl in controllers:
            methods = ctrl.method_names[:15] if ctrl.method_names else []
            # Sanitize method names: filter out injected prompts/long strings
            safe_methods = [
                m[:40] for m in methods
                if len(m) <= 60 and '\n' not in m and not any(c in m for c in '{}[]<>()\"\'')
            ]
            if not safe_methods:
                continue
            lines.append(f"\n### {ctrl.label} (tipo: {ctrl.type})")
            lines.append(f"Descripción: {ctrl.description[:120] if ctrl.description else ''}")
            lines.append(f"Métodos: {', '.join(safe_methods)}")

            # Servicios y middleware relacionados
            related = edges_from.get(ctrl.id, [])
            services = [node_map[e.target].label for e in related
                        if e.target in node_map and node_map[e.target].type == "Service"]
            middleware = [node_map[e.target].label for e in related
                         if e.target in node_map and node_map[e.target].type == "Middleware"]

            if services:
                lines.append(f"Servicios invocados: {', '.join(services)}")
            if middleware:
                lines.append(f"Middleware asociado: {', '.join(middleware)}")

        return "\n".join(lines)

    @staticmethod
    def _detect_existing_tests(repo_path: str | None) -> str:
        """Scan the repository for existing test files and return a summary."""
        import os
        import glob

        if not repo_path or not os.path.isdir(repo_path):
            return ""

        test_patterns = [
            "**/*test*", "**/*spec*", "**/__tests__/**",
            "**/tests/**", "**/test/**",
        ]

        test_files: list[str] = []
        for pattern in test_patterns:
            found = glob.glob(os.path.join(repo_path, pattern), recursive=True)
            for f in found:
                if os.path.isfile(f) and not "node_modules" in f:
                    rel_path = os.path.relpath(f, repo_path)
                    test_files.append(rel_path)

        test_files = sorted(set(test_files))[:20]  # Limit to 20 files

        if not test_files:
            return ""

        # Read first few lines of each test file to understand what they test
        summaries: list[str] = []
        for tf in test_files[:10]:
            full_path = os.path.join(repo_path, tf)
            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as fh:
                    lines = fh.readlines()[:30]
                    content_preview = "".join(lines)
                    summaries.append(f"### {tf}\n```\n{content_preview}\n```\n")
            except Exception:
                summaries.append(f"- {tf} (no se pudo leer)")

        return (
            f"Se encontraron {len(test_files)} archivos de test:\n" +
            "\n".join(f"- {f}" for f in test_files) +
            "\n\nContenido parcial de los tests:\n" +
            "\n".join(summaries)
        )

    def _build_use_case_system_prompt(self) -> str:
        """Return the system prompt for use case and user story generation in UML format."""
        return (
            "Eres un analista de software UML experto. A partir de los controladores y métodos "
            "proporcionados, genera un documento Markdown con formato UML estándar.\n\n"
            "REGLAS DE FORMATO OBLIGATORIAS:\n"
            "- Responde en español\n"
            "- Para TODAS las tablas usa HTML: <table><thead><tr><th>...</th></tr></thead><tbody><tr><td>...</td></tr></tbody></table>\n"
            "- NUNCA uses tablas Markdown (| col |). SIEMPRE tablas HTML.\n"
            "- Para diagramas usa bloques ```mermaid\n"
            "- Responde SOLO con el contenido, sin bloques de código envolventes\n\n"
            "---\n\n"
            "## Diagrama de Casos de Uso\n\n"
            "Genera un diagrama Mermaid de casos de uso:\n"
            "```mermaid\n"
            "flowchart LR\n"
            "  subgraph Actores\n"
            "    A1[Usuario Final]\n"
            "    A2[Administrador]\n"
            "  end\n"
            "  subgraph Sistema\n"
            "    UC1([CU-001: Nombre])\n"
            "    UC2([CU-002: Nombre])\n"
            "  end\n"
            "  A1 --> UC1\n"
            "  A2 --> UC2\n"
            "```\n\n"
            "---\n\n"
            "## Historias de Usuario\n\n"
            "Para cada método público, genera una historia de usuario con tabla HTML:\n\n"
            "### HU-XXX: [título]\n\n"
            "<table>\n"
            "<thead><tr><th>Campo</th><th>Detalle</th></tr></thead>\n"
            "<tbody>\n"
            "<tr><td><strong>ID</strong></td><td>HU-XXX</td></tr>\n"
            "<tr><td><strong>Rol</strong></td><td>Como [actor]</td></tr>\n"
            "<tr><td><strong>Acción</strong></td><td>Quiero [acción específica]</td></tr>\n"
            "<tr><td><strong>Beneficio</strong></td><td>Para [valor de negocio]</td></tr>\n"
            "<tr><td><strong>Prioridad</strong></td><td>Alta/Media/Baja</td></tr>\n"
            "<tr><td><strong>Criterios de Aceptación</strong></td><td>1. [criterio verificable]<br/>2. [criterio]</td></tr>\n"
            "</tbody>\n"
            "</table>\n\n"
            "---\n\n"
            "## Especificación de Casos de Uso (UML)\n\n"
            "Para cada caso de uso, usa este formato con tablas HTML:\n\n"
            "### CU-XXX: [Nombre]\n\n"
            "<table>\n"
            "<thead><tr><th>Campo</th><th>Detalle</th></tr></thead>\n"
            "<tbody>\n"
            "<tr><td><strong>ID</strong></td><td>CU-XXX</td></tr>\n"
            "<tr><td><strong>Nombre</strong></td><td>[nombre descriptivo]</td></tr>\n"
            "<tr><td><strong>Actores</strong></td><td>Principal: xxx / Secundario: yyy</td></tr>\n"
            "<tr><td><strong>Descripción</strong></td><td>[resumen]</td></tr>\n"
            "<tr><td><strong>Trigger</strong></td><td>[evento disparador]</td></tr>\n"
            "<tr><td><strong>HU Relacionadas</strong></td><td>HU-XXX, HU-YYY</td></tr>\n"
            "</tbody>\n"
            "</table>\n\n"
            "**Precondiciones:**\n"
            "- [precondición 1]\n"
            "- [precondición 2]\n\n"
            "**Postcondiciones:**\n"
            "- [postcondición 1]\n\n"
            "**Flujo Principal:**\n\n"
            "<table>\n"
            "<thead><tr><th>Paso</th><th>Actor</th><th>Sistema</th></tr></thead>\n"
            "<tbody>\n"
            "<tr><td>1</td><td>[acción del actor]</td><td></td></tr>\n"
            "<tr><td>2</td><td></td><td>[respuesta del sistema]</td></tr>\n"
            "</tbody>\n"
            "</table>\n\n"
            "**Flujos Alternativos:**\n"
            "- **FA1 - [Nombre]:** En paso X, si [condición], entonces [acción].\n\n"
            "**Excepciones:**\n"
            "- **EX1 - [Nombre]:** Si [error], el sistema [manejo].\n\n"
            "---\n\n"
            "## Matriz de Trazabilidad\n\n"
            "<table>\n"
            "<thead><tr><th>Caso de Uso</th><th>Historias</th><th>Actor</th><th>Controlador</th><th>Servicios</th></tr></thead>\n"
            "<tbody>\n"
            "<tr><td>CU-001</td><td>HU-001, HU-002</td><td>[actor]</td><td>[ctrl]</td><td>[services]</td></tr>\n"
            "</tbody>\n"
            "</table>\n\n"
            "---\n\n"
            "REGLAS:\n"
            "- Los roles deben derivarse del contexto (auth → administrador, public → usuario)\n"
            "- Incluir middleware como precondiciones\n"
            "- Incluir servicios como pasos del sistema en el flujo\n"
            "- Criterios de aceptación deben ser verificables\n"
            "- Cada CU tiene 4-8 pasos en el flujo principal\n"
        )
