"""
Summary_Generator — produces a plain-text executive summary of a codebase.

The summary is at most 3 sentences, free of markdown formatting characters,
camelCase/snake_case identifiers, and Unicode control characters.

Satisfies Requirements 3.1, 3.2, 3.3, 3.4, 3.5.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING

from .models import CodeFlowResult, ERResult

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


def _sanitize(text: str) -> str:
    """Sanitize a generated summary string.

    Performs the following transformations in order:
    1. Remove all Unicode control characters U+0000–U+001F.
    2. Remove prohibited markdown/formatting characters: * # ` _ ~ > <
    3. Remove camelCase identifiers (e.g., orderService).
    4. Remove PascalCase identifiers (e.g., OrderService).
    5. Remove snake_case identifiers (e.g., order_service).
    6. Collapse multiple spaces into one and strip leading/trailing whitespace.
    7. Truncate to 500 Unicode code points.

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

    # Step 7: Truncate to 500 Unicode code points
    text = text[:_MAX_CODE_POINTS]

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
    - Is at most 3 sentences (Req 3.1).
    - Contains no markdown characters, camelCase/snake_case identifiers,
      or Unicode control characters (Req 3.2 — full sanitization in Task 7.2).
    - Returns a fixed message when no files are analyzable (Req 3.3).
    - Appends an incompleteness warning when a subsystem failed (Req 3.5).
    - Never raises exceptions.
    """

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
            A plain-text summary string, at most 3 sentences.
            Never raises; errors produce the fixed no-files message.
        """
        try:
            result = self._build_summary(code_flow, er_result)
            # Only sanitize dynamically generated summaries; the fixed
            # no-files message is returned as-is (it already conforms).
            if result == _NO_FILES_MESSAGE:
                return result
            return _sanitize(result)
        except Exception:
            # Safety net — must never propagate exceptions (design contract).
            return _NO_FILES_MESSAGE

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
        # Sentence 1 — architecture (Req 3.1)                                #
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
        # Sentence 2 — data entities (Req 3.1)                               #
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
        # Sentence 3 — incompleteness warning (Req 3.5)                      #
        # ------------------------------------------------------------------ #
        if subsystem_failed:
            sentences.append(_INCOMPLETE_WARNING)

        return " ".join(sentences)
