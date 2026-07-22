"""
DevGhost-Parser — static architecture analysis system.

Public API
----------
    from dev_ghost_parser import DevGhost_Parser

    parser = DevGhost_Parser()
    result: bytes = parser.analyze("/path/to/codebase")
    # result is UTF-8 encoded JSON (no BOM), RFC 8259 compliant.
"""

from __future__ import annotations

import json
import os

from .code_flow_analyzer import Code_Flow_Analyzer
from .er_extractor import ER_Extractor
from .models import CodeFlowResult, ERResult, SubsystemError
from .output_serializer import Output_Serializer
from .summary_generator import Summary_Generator


def _error_response(message: str) -> bytes:
    """Serialize a single-entry validation error response as UTF-8 JSON bytes (no BOM).

    Parameters
    ----------
    message:
        The human-readable error description to include in the response.

    Returns
    -------
    bytes
        ``{"errors": [{"message": "..."}]}`` encoded as UTF-8 without BOM.

    Notes
    -----
    ``ensure_ascii=True`` is used intentionally: if the path contains surrogate
    code points (U+D800 through U+DFFF) that are not valid UTF-8 scalar
    values, ``ensure_ascii=False`` would raise ``UnicodeEncodeError`` when
    calling ``.encode("utf-8")``.  With ``ensure_ascii=True`` those characters
    are rendered as JSON escape sequences, producing valid RFC 8259 JSON
    and valid UTF-8 bytes in all cases (Req 4.1, 6.2, 6.3).
    """
    return json.dumps(
        {"errors": [{"message": message}]},
        ensure_ascii=True,
    ).encode("utf-8")


class DevGhost_Parser:
    """Top-level orchestrator for static codebase analysis.

    Responsibilities:
    - Validate the input path (4 checks in mandatory order).
    - Invoke Code_Flow_Analyzer, ER_Extractor, and Summary_Generator.
    - Pass results to Output_Serializer.
    - Never raise exceptions — all errors are encoded in the returned JSON.

    Returns
    -------
    bytes
        UTF-8 encoded JSON object without BOM, conforming to RFC 8259.
    """

    def analyze(self, path: str) -> bytes:
        """Analyze a codebase directory and return a structured JSON result.

        Validation is performed in mandatory order before any subsystem is
        invoked:

        1. Missing / empty path  — Requirement 5.1
        2. Path not found        — Requirement 5.2
        3. Permission denied     — Requirement 5.3
        4. Not a directory       — Requirement 5.4

        The first failing check causes an immediate return with a JSON error
        object; no subsequent checks or subsystems are evaluated (Req 5.5).

        When all validation checks pass, the subsystems are invoked
        independently (Req 5.6). Fatal errors from any subsystem are captured
        and encoded in the output JSON rather than propagated as exceptions
        (Req 4.7). This method never raises exceptions.

        Parameters
        ----------
        path:
            Filesystem path to the root directory of the target codebase.

        Returns
        -------
        bytes
            UTF-8 JSON bytes (no BOM). On validation failure or subsystem
            error the JSON will contain an ``errors`` key.
        """
        # --- Check 1: missing / empty path (Requirement 5.1) ---
        if not path:
            return _error_response("A Target_Codebase path is required.")

        # --- Check 2: path does not exist (Requirement 5.2) ---
        if not os.path.exists(path):
            return _error_response(f"Path '{path}' was not found.")

        # --- Check 3: no read permission (Requirement 5.3) ---
        if not os.access(path, os.R_OK):
            return _error_response(f"Permission denied accessing '{path}'.")

        # --- Check 4: not a directory (Requirement 5.4) ---
        if not os.path.isdir(path):
            return _error_response(f"Path '{path}' is not a directory.")

        # All validation checks passed — subsystem orchestration (Req 5.6)
        # Each subsystem runs independently; failures are captured and encoded
        # in the JSON output rather than raised (Req 4.7).
        try:
            return self._orchestrate(path)
        except Exception as exc:
            # Top-level safety net: guarantee no exception ever escapes analyze().
            # This branch should never be reached under normal conditions.
            fallback_error = SubsystemError(
                subsystem="DevGhost_Parser",
                message=f"Unexpected orchestration error: {exc}",
            )
            try:
                return Output_Serializer().serialize(
                    code_flow=None,
                    er_result=None,
                    summary=None,
                    subsystem_errors=[fallback_error],
                )
            except Exception:
                # Absolute last resort — return a minimal error JSON manually.
                # ensure_ascii=True to avoid UnicodeEncodeError with surrogate chars.
                return json.dumps(
                    {"errors": [{"subsystem": "DevGhost_Parser", "message": str(exc)}]},
                    ensure_ascii=True,
                ).encode("utf-8")

    def _orchestrate(self, path: str) -> bytes:
        """Run all subsystems and compose the output via Output_Serializer.

        Called only after all four validation checks pass.

        Parameters
        ----------
        path:
            Validated, existing, readable directory path.

        Returns
        -------
        bytes
            UTF-8 JSON bytes produced by Output_Serializer.
        """
        subsystem_errors: list[SubsystemError] = []

        # --- Code_Flow_Analyzer (Req 5.6) ---
        code_flow_result: CodeFlowResult | None = None
        try:
            code_flow_result = Code_Flow_Analyzer().analyze(path)
        except Exception as exc:
            subsystem_errors.append(
                SubsystemError(subsystem="Code_Flow_Analyzer", message=str(exc))
            )

        # --- ER_Extractor (Req 5.6) ---
        er_result: ERResult | None = None
        try:
            er_result = ER_Extractor().extract(path)
        except Exception as exc:
            subsystem_errors.append(
                SubsystemError(subsystem="ER_Extractor", message=str(exc))
            )

        # --- Summary_Generator (Req 5.6) ---
        # Summary_Generator.generate() is specified to never raise, but we
        # wrap it defensively to honour the "never propagate exceptions" contract.
        summary: str | None = None
        try:
            summary = Summary_Generator().generate(code_flow_result, er_result, path)
        except Exception as exc:
            subsystem_errors.append(
                SubsystemError(subsystem="Summary_Generator", message=str(exc))
            )

        # --- Output_Serializer ---
        return Output_Serializer().serialize(
            code_flow=code_flow_result,
            er_result=er_result,
            summary=summary,
            subsystem_errors=subsystem_errors,
        )


__all__ = ["DevGhost_Parser"]
