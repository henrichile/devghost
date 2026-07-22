"""
Output_Serializer — composes and serializes the final JSON output.

Composes the structured JSON response from subsystem results and serializes
it as UTF-8 bytes without BOM, conforming to RFC 8259.

Satisfies Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 6.2, 6.3
"""

from __future__ import annotations

import json

from .models import (
    Attribute,
    CodeFlowResult,
    ERResult,
    SubsystemError,
)


def _attribute_to_dict(attr: Attribute) -> dict:
    return {"name": attr.name, "type": attr.type}


def _code_flow_to_dict(code_flow: CodeFlowResult) -> dict:
    """Convert a CodeFlowResult to a serializable dict."""
    return {
        "nodes": [
            {"id": node.id, "label": node.label, "type": node.type}
            for node in code_flow.nodes
        ],
        "edges": [
            {"source": edge.source, "target": edge.target, "relation": edge.relation}
            for edge in code_flow.edges
        ],
    }


def _er_result_to_dict(er_result: ERResult) -> dict:
    """Convert an ERResult to a serializable dict."""
    entities = []
    for entity in er_result.entities:
        entity_dict: dict = {
            "name": entity.name,
            "attributes": [_attribute_to_dict(a) for a in entity.attributes],
            "primaryKey": entity.primaryKey,
        }
        entities.append(entity_dict)

    relations = []
    for rel in er_result.relations:
        rel_dict: dict = {
            "from": rel.from_entity,
            "to": rel.to_entity,
            "type": rel.type,
            "foreignKey": rel.foreignKey,
        }
        if rel.rawDeclaration is not None:
            rel_dict["rawDeclaration"] = rel.rawDeclaration
        relations.append(rel_dict)

    return {"entities": entities, "relations": relations}


class Output_Serializer:
    """Composes the final JSON output from subsystem results.

    Produces a single valid JSON object (RFC 8259) as UTF-8 bytes without BOM.
    When all subsystems succeed, the output contains exactly three top-level
    keys: ``codeFlow``, ``erModel``, and ``summary`` — with no ``errors`` key.

    Satisfies Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 6.2, 6.3
    """

    def serialize(
        self,
        code_flow: CodeFlowResult | None,
        er_result: ERResult | None,
        summary: str | None,
        subsystem_errors: list[SubsystemError],
    ) -> bytes:
        """Serialize analysis results to UTF-8 JSON bytes without BOM.

        Composition rules (Req 4.2, 4.7):
        - Success case: emit {"codeFlow": {...}, "erModel": {...}, "summary": "..."}
          with NO "errors" key (only when ALL subsystems succeed with zero file errors).
        - Failure case: set failed subsystem keys to null and add "errors" array.
        - Non-fatal file errors from successful subsystems are also included in the
          "errors" array (e.g., unparseable files in Code_Flow_Analyzer or ER_Extractor).

        Serialization (Req 4.1, 4.6, 6.2, 6.3):
        - Uses json.dumps with ensure_ascii=False for proper Unicode output.
        - Falls back to ensure_ascii=True if UTF-8 encoding fails (e.g., surrogates).
        - Control characters U+0000–U+001F are always escaped by json.dumps per RFC 8259.
        - Output bytes never start with BOM (\\xef\\xbb\\xbf).

        Parameters
        ----------
        code_flow:
            Result from Code_Flow_Analyzer, or None if that subsystem failed.
        er_result:
            Result from ER_Extractor, or None if that subsystem failed.
        summary:
            Result from Summary_Generator, or None if that subsystem failed.
        subsystem_errors:
            List of fatal errors from failed subsystems.

        Returns
        -------
        bytes
            UTF-8 encoded JSON object without BOM. Conforms to RFC 8259.
        """
        # Compose the output object (Req 4.2, 4.3, 4.4, 4.5)
        obj: dict = {
            "codeFlow": _code_flow_to_dict(code_flow) if code_flow is not None else None,
            "erModel": _er_result_to_dict(er_result) if er_result is not None else None,
            "summary": summary,
        }

        # Collect all errors: fatal subsystem errors + non-fatal file errors (Req 4.7)
        all_errors: list[dict] = []

        # Fatal subsystem errors
        for e in subsystem_errors:
            all_errors.append({"subsystem": e.subsystem, "message": e.message})

        # Non-fatal file errors from successful subsystems
        if code_flow is not None and code_flow.errors:
            for file_err in code_flow.errors:
                all_errors.append({
                    "subsystem": "Code_Flow_Analyzer",
                    "message": f"File '{file_err.path}': {file_err.reason}",
                })

        if er_result is not None and er_result.errors:
            for file_err in er_result.errors:
                all_errors.append({
                    "subsystem": "ER_Extractor",
                    "message": f"File '{file_err.path}': {file_err.reason}",
                })

        # Add errors key only when there are errors (Req 4.7)
        # When all subsystems succeed and there are no file errors, "errors" is omitted.
        if all_errors:
            obj["errors"] = all_errors

        # Serialize to UTF-8 bytes without BOM (Req 4.1, 6.2, 6.3)
        # json.dumps automatically escapes control chars U+0000–U+001F per RFC 8259.
        # Use ensure_ascii=False for proper Unicode; fall back to ensure_ascii=True
        # if encoding fails (e.g., surrogate characters in string values).
        try:
            json_str = json.dumps(obj, ensure_ascii=False)
            output = json_str.encode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            # Safety fallback: ensure_ascii=True escapes all non-ASCII as \uXXXX,
            # guaranteeing the result is pure ASCII and always valid UTF-8.
            json_str = json.dumps(obj, ensure_ascii=True)
            output = json_str.encode("utf-8")

        return output
