"""
Summary_Generator — produces a plain-text executive summary of a codebase.

The summary is 3 to 4 sentences, free of markdown formatting characters,
camelCase/snake_case identifiers, and Unicode control characters.

Satisfies Requirements 3.1, 3.2, 3.3, 3.4, 3.5.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .llm_client import LLM_Client

from .models import CodeFlowResult, Entity, ERResult

# Fixed string returned when no analyzable source files are present (Req 3.3).
_NO_FILES_MESSAGE = (
    "No se encontraron archivos de codigo fuente analizables en la base de codigo proporcionada."
)

# Sentence appended when one or more subsystems failed (Req 3.5).
_INCOMPLETE_WARNING = (
    "Este resumen puede estar incompleto debido a errores en el analisis."
)

# Characters explicitly prohibited in the summary (Req 3.2).
_PROHIBITED_CHARS = set("*#`_~><")

# Regex for camelCase identifiers (starts lowercase, has uppercase in middle).
# e.g., orderService, getUserName
_RE_CAMEL_CASE = re.compile(r"\b[a-z]+[A-Z][a-zA-Z0-9]*\b")

# Regex for PascalCase identifiers (starts uppercase, then lowercase + uppercase).
# e.g., OrderService, UserController
_RE_PASCAL_CASE = re.compile(r"\b[A-Z][a-z]+[A-Z][a-zA-Z0-9]*\b")

# Regex for snake_case identifiers (lowercase with underscores).
# e.g., order_service, user_name, get_user_by_id
_RE_SNAKE_CASE = re.compile(r"\b[a-z]+(_[a-z0-9]+)+\b")

# Maximum summary length in Unicode code points (Req 3.4).
_MAX_CODE_POINTS = 500

# Maximum number of sentences in the summary (Req 3.1).
_MAX_SENTENCES = 4

# Domain keyword map: maps common entity/label keywords (lowercase) to
# business purposes in Spanish.  Used by _infer_domain() for summary
# domain inference (Requirement 6.5).
_DOMAIN_KEYWORD_MAP: dict[str, str] = {
    "asistencia": "control de asistencia",
    "producto": "gestión de inventario",
    "factura": "facturación",
    "usuario": "gestión de usuarios",
    "orden": "gestión de pedidos",
    "paciente": "gestión hospitalaria",
    "alumno": "gestión educativa",
    "empleado": "gestión de recursos humanos",
    "vehiculo": "gestión de flota vehicular",
    "reserva": "gestión de reservas",
    "pago": "procesamiento de pagos",
    "cuenta": "gestión financiera",
    "inventario": "control de inventario",
    "ticket": "gestión de soporte",
    "proyecto": "gestión de proyectos",
    "cliente": "gestión de clientes",
    "venta": "gestión de ventas",
    "compra": "gestión de compras",
    "envio": "logística de envíos",
    "curso": "gestión educativa",
}

def _infer_domain(entities: list[Entity], labels: list[str]) -> str | None:
    """Infer business domain by comparing ER entities/labels against keyword map.

    Performs bidirectional case-insensitive substring matching:
    - keyword in entity/label name OR entity/label name in keyword.

    Selects the domain with the highest match count.
    Tie-break: the domain whose first match appears earliest in the combined
    entity+label list wins.

    Returns None when no keyword matches any entity or label.

    Satisfies Requirements 6.1, 6.2, 6.3, 6.4.
    """
    domain_counts: dict[str, int] = {}
    domain_first_pos: dict[str, int] = {}

    all_names = [e.name for e in entities] + labels

    for idx, name in enumerate(all_names):
        name_lower = name.lower()
        for keyword, domain in _DOMAIN_KEYWORD_MAP.items():
            if keyword in name_lower or name_lower in keyword:
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
                if domain not in domain_first_pos:
                    domain_first_pos[domain] = idx

    if not domain_counts:
        return None

    # Select domain with highest count; tie-break by earliest first occurrence
    max_count = max(domain_counts.values())
    candidates = [d for d, c in domain_counts.items() if c == max_count]
    candidates.sort(key=lambda d: domain_first_pos[d])
    return candidates[0]


# Spanish type name mapping: NodeType → (singular, plural)
_SPANISH_TYPE_NAMES: dict[str, tuple[str, str]] = {
    "Controller": ("controlador", "controladores"),
    "Service": ("servicio", "servicios"),
    "Route": ("ruta", "rutas"),
    "Middleware": ("middleware", "middleware"),
    "Repository": ("repositorio", "repositorios"),
    "Utility": ("utilidad", "utilidades"),
}


def _get_spanish_type_name(node_type: str, count: int) -> str:
    """Return the Spanish name for a node type, singular or plural based on count."""
    singular, plural = _SPANISH_TYPE_NAMES.get(node_type, (node_type.lower(), node_type.lower()))
    return singular if count == 1 else plural


def _infer_purpose(code_flow: CodeFlowResult) -> str | None:
    """Infer a general purpose for the system based on node types and labels.

    Returns a short Spanish phrase describing the system purpose, or None
    if no meaningful inference can be made.
    """
    counts: Counter[str] = Counter(node.type for node in code_flow.nodes)

    # Infer purpose based on dominant patterns
    if counts.get("Controller", 0) > 0 and counts.get("Repository", 0) > 0:
        return "la gestion de datos"
    if counts.get("Controller", 0) > 0 and counts.get("Service", 0) > 0:
        return "la gestion de operaciones"
    if counts.get("Route", 0) > 0 and counts.get("Service", 0) > 0:
        return "una arquitectura de microservicios"
    if counts.get("Route", 0) >= 2:
        return "el enrutamiento de solicitudes"
    if counts.get("Service", 0) >= 2:
        return "el procesamiento de servicios"
    if counts.get("Controller", 0) > 0:
        return "el control de flujo de la aplicacion"
    if counts.get("Middleware", 0) > 0:
        return "el procesamiento intermedio"
    if counts.get("Repository", 0) > 0:
        return "el acceso a datos"

    return None


def _sanitize(text: str) -> str:
    """Sanitize a generated summary string.

    Performs the following transformations in order:
    1. Remove all Unicode control characters U+0000–U+001F.
    2. Remove prohibited markdown/formatting characters: * # ` _ ~ > <
    3. Remove camelCase identifiers (e.g., orderService).
    4. Remove PascalCase identifiers (e.g., OrderService).
    5. Remove snake_case identifiers (e.g., order_service).
    6. Collapse multiple spaces into one and strip leading/trailing whitespace.

    Satisfies Requirements 3.2, 3.4.
    """
    # Step 1: Remove Unicode control characters U+0000–U+001F
    text = re.sub(r"[\u0000-\u001f]", "", text)

    # Step 2: Remove prohibited characters
    text = "".join(ch for ch in text if ch not in _PROHIBITED_CHARS)

    # Step 3: Remove camelCase identifiers
    text = _RE_CAMEL_CASE.sub("", text)

    # Step 4: Remove PascalCase identifiers
    text = _RE_PASCAL_CASE.sub("", text)

    # Step 5: Remove snake_case identifiers
    text = _RE_SNAKE_CASE.sub("", text)

    # Step 6: Collapse multiple spaces and strip
    text = re.sub(r" {2,}", " ", text)
    text = text.strip()

    # Step 7: Truncate to max code points (Req 3.4)
    if len(text) > _MAX_CODE_POINTS:
        text = text[:_MAX_CODE_POINTS]

    return text


def _sanitize_llm(text: str) -> str:
    """Light sanitization for LLM-generated text.

    Only removes control characters and markdown formatting, but preserves
    identifiers (camelCase, PascalCase, snake_case) since the LLM uses them
    intentionally as component/entity names in the narrative.
    """
    # Remove Unicode control characters U+0000–U+001F
    text = re.sub(r"[\u0000-\u001f]", "", text)

    # Remove prohibited markdown characters
    text = "".join(ch for ch in text if ch not in _PROHIBITED_CHARS)

    # Collapse multiple spaces and strip
    text = re.sub(r" {2,}", " ", text)
    text = text.strip()

    return text


def _infer_pattern(code_flow: CodeFlowResult) -> str:
    """Infer the dominant architectural pattern from node type counts.

    Rules (evaluated in priority order):
    - Controllers present              → "model-view-controller"
    - Services dominant                → "orientado a servicios"
    - Routes dominant                  → "basado en rutas"
    - Anything else                    → "basado en utilidades"

    Parameters
    ----------
    code_flow:
        The result produced by Code_Flow_Analyzer.

    Returns
    -------
    str
        A plain-text label for the dominant pattern.
    """
    counts: Counter[str] = Counter(node.type for node in code_flow.nodes)

    if counts.get("Controller", 0) > 0:
        return "model-view-controller"

    total = sum(counts.values())
    if total == 0:
        return "basado en utilidades"

    # "Dominant" means the highest count; if Services > others → service-oriented
    most_common_type, most_common_count = counts.most_common(1)[0]

    if most_common_type == "Service":
        return "orientado a servicios"

    if most_common_type == "Route":
        return "basado en rutas"

    return "basado en utilidades"


class Summary_Generator:
    """Generates a concise plain-text summary of a codebase analysis result.

    The output:
    - Is 3 to 4 sentences (Req 3.1).
    - Contains no markdown characters, camelCase/snake_case identifiers,
      or Unicode control characters (Req 3.2 — full sanitization in Task 7.2).
    - Returns a fixed message when no files are analyzable (Req 3.3).
    - Uses Spanish architectural type names (Req 3.3).
    - Appends an incompleteness warning when a subsystem failed (Req 3.5).
    - Never raises exceptions.
    """

    def __init__(self, llm_client: LLM_Client | None = None) -> None:
        """Initialize Summary_Generator with an optional LLM client.

        Parameters
        ----------
        llm_client:
            An instance of LLM_Client. When provided and available, the
            generator will attempt LLM-based summary generation before
            falling back to heuristic logic. Default None for backward
            compatibility.
        """
        self._llm_client = llm_client

    def generate(
        self,
        code_flow: CodeFlowResult | None,
        er_result: ERResult | None,
        root_path: str,
    ) -> str:
        """Generate a plain-text summary from partial or complete analysis results.

        Parameters
        ----------
        code_flow:
            Result from Code_Flow_Analyzer, or None if that subsystem failed.
        er_result:
            Result from ER_Extractor, or None if that subsystem failed.
        root_path:
            The filesystem path of the analyzed codebase (currently unused in
            templates but retained for future extension).

        Returns
        -------
        str
            A plain-text summary string, 3 to 4 sentences.
            Never raises; errors produce the fixed no-files message.
        """
        try:
            # Try LLM first if available
            if self._llm_client and self._llm_client.available:
                llm_summary = self._from_llm(code_flow, er_result)
                if llm_summary:
                    return llm_summary[:_MAX_CODE_POINTS]

            # Fallback to heuristics (existing logic)
            result = self._build_summary(code_flow, er_result)
            # Only sanitize dynamically generated summaries; the fixed
            # no-files message is returned as-is (it already conforms).
            if result == _NO_FILES_MESSAGE:
                return result
            return _sanitize(result)
        except Exception:
            # Safety net — must never propagate exceptions (design contract).
            return _NO_FILES_MESSAGE

    def _from_llm(
        self,
        code_flow: CodeFlowResult | None,
        er_result: ERResult | None,
    ) -> str | None:
        """Attempt to generate summary using the LLM client.

        Extracts controller names, service names from code_flow and entity names
        from er_result, sends them to the LLM with a structured 3-part narrative
        prompt (max 550 chars).

        Returns the sanitized summary string, or None if the LLM result is
        unusable (empty, no period, post-sanitization too short).
        """
        controllers = (
            [n.label for n in code_flow.nodes if n.type == "Controller"]
            if code_flow
            else []
        )
        services = (
            [n.label for n in code_flow.nodes if n.type == "Service"]
            if code_flow
            else []
        )
        entities = (
            [e.name for e in er_result.entities] if er_result else []
        )

        if not controllers and not entities:
            return None

        # Build clean lists — include all names (even if they have control chars)
        ctrl_str = ', '.join(controllers[:10]) or 'no identificados'
        svc_str = ', '.join(services[:10]) or 'no identificados'
        ent_str = ', '.join(entities[:10]) or 'no identificadas'

        user_prompt = (
            f"Controladores: {ctrl_str}\n"
            f"Servicios: {svc_str}\n"
            f"Entidades de base de datos: {ent_str}"
        )
        system_prompt = (
            "Eres un narrador tecnico. A partir de los componentes listados, genera un "
            "parrafo narrativo fluido y natural en español de máximo 450 caracteres que describa la arquitectura "
            "del sistema. Incluye:\n"
            "- El proposito del sistema (infierelo de los nombres de controladores y entidades)\n"
            "- Que datos maneja (menciona las entidades por nombre)\n"
            "- Como fluye la logica (controladores → servicios → base de datos)\n\n"
            "Reglas:\n"
            "- Escribe en tercera persona, tono profesional pero accesible\n"
            "- Menciona los nombres reales de controladores, servicios y entidades tal como aparecen\n"
            "- NO uses plantillas rigidas ni frases predefinidas\n"
            "- Termina con punto final\n"
            "- Solo responde con el parrafo, sin comillas ni explicaciones"
        )

        result = self._llm_client.complete(system_prompt, user_prompt)
        if not result:
            return None

        # Truncate to 450 chars (447 + '...') before sanitization (Req 3.4)
        if len(result) > 450:
            result = result[:447] + "..."

        # Validate: at least one sentence ending in period
        if "." not in result:
            return None

        # Apply full sanitization (remove control chars, markdown, identifiers, truncate to 500)
        sanitized = _sanitize(result)

        # Verify post-sanitization length
        if len(sanitized) < 10:
            return None

        return sanitized

    def _build_summary(
        self,
        code_flow: CodeFlowResult | None,
        er_result: ERResult | None,
    ) -> str:
        """Core summary construction logic (may not raise)."""

        subsystem_failed = (code_flow is None) or (er_result is None)

        # ------------------------------------------------------------------ #
        # Empty-codebase check                                                #
        # Req 3.3: both subsystems returned nothing useful                    #
        # ------------------------------------------------------------------ #
        has_nodes = code_flow is not None and len(code_flow.nodes) > 0
        has_entities = er_result is not None and len(er_result.entities) > 0

        if not has_nodes and not has_entities:
            # If both subsystems were present but empty → no analyzable files.
            # If either subsystem failed → we still have no real data; return
            # the fixed message (partial results = nothing useful available).
            return _NO_FILES_MESSAGE

        sentences: list[str] = []

        # ------------------------------------------------------------------ #
        # Sentence 1 — architecture pattern + component count (Req 3.1)      #
        # ------------------------------------------------------------------ #
        if has_nodes:
            assert code_flow is not None  # type-narrowing
            pattern = _infer_pattern(code_flow)
            n_components = len(code_flow.nodes)
            sentences.append(
                f"La base de codigo sigue un patron {pattern}"
                f" con {n_components} componente"
                f"{'s' if n_components != 1 else ''} identificado"
                f"{'s' if n_components != 1 else ''}."
            )

        # ------------------------------------------------------------------ #
        # Sentence 2 — data entities (Req 3.1, 3.4)                          #
        # Omitted when there are no entities.                                 #
        # ------------------------------------------------------------------ #
        if has_entities:
            assert er_result is not None  # type-narrowing
            all_names = [e.name for e in er_result.entities]
            n_entities = len(all_names)
            # List up to 3 entity names; use plain comma separation.
            sample = all_names[:3]
            names_str = ", ".join(sample)
            sentences.append(
                f"El modelo de datos incluye {n_entities}"
                f" {'entidad' if n_entities == 1 else 'entidades'}"
                f" como {names_str}."
            )

        # ------------------------------------------------------------------ #
        # Sentence 3 — component type breakdown with Spanish names (Req 3.3) #
        # Lists counts per type using Spanish terminology.                    #
        # ------------------------------------------------------------------ #
        if has_nodes:
            assert code_flow is not None  # type-narrowing
            type_counts: Counter[str] = Counter(
                node.type for node in code_flow.nodes
            )
            # Build type breakdown parts; only include types with count > 0
            breakdown_parts: list[str] = []
            for node_type in [
                "Controller", "Service", "Route",
                "Middleware", "Repository", "Utility",
            ]:
                count = type_counts.get(node_type, 0)
                if count > 0:
                    spanish_name = _get_spanish_type_name(node_type, count)
                    breakdown_parts.append(f"{count} {spanish_name}")

            if breakdown_parts:
                if len(breakdown_parts) == 1:
                    parts_str = breakdown_parts[0]
                elif len(breakdown_parts) == 2:
                    parts_str = f"{breakdown_parts[0]} y {breakdown_parts[1]}"
                else:
                    parts_str = (
                        ", ".join(breakdown_parts[:-1])
                        + ", y "
                        + breakdown_parts[-1]
                    )
                sentences.append(
                    f"Los componentes incluyen {parts_str}."
                )

        # ------------------------------------------------------------------ #
        # Sentence 4 — domain/purpose inference (optional, Req 3.1, 6.2, 6.6)#
        # Try domain inference first; fall back to generic purpose.          #
        # Omitted if it would push total over 500 code points or 4 sentences.#
        # ------------------------------------------------------------------ #
        if len(sentences) < _MAX_SENTENCES:
            # Try domain inference from ER entities + node labels
            entities = er_result.entities if er_result is not None else []
            labels = [node.label for node in code_flow.nodes] if code_flow is not None else []
            domain = _infer_domain(entities, labels)

            if domain is not None:
                sentence_4 = f"El sistema esta diseñado para {domain}."
            elif has_nodes:
                assert code_flow is not None  # type-narrowing
                purpose = _infer_purpose(code_flow)
                if purpose is not None:
                    sentence_4 = f"El sistema parece orientado a {purpose}."
                else:
                    sentence_4 = None
            else:
                sentence_4 = None

            if sentence_4 is not None:
                candidate = " ".join(sentences + [sentence_4])
                if len(candidate) <= _MAX_CODE_POINTS:
                    sentences.append(sentence_4)

        # ------------------------------------------------------------------ #
        # Incompleteness warning (Req 3.5)                                   #
        # Replaces sentence 4 or is appended when a subsystem failed.        #
        # ------------------------------------------------------------------ #
        if subsystem_failed:
            sentences.append(_INCOMPLETE_WARNING)

        return " ".join(sentences)
