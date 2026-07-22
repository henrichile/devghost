"""
Unit tests for Output_Serializer — error composition behavior (Task 8.2).

Validates Requirement 4.7:
- When a subsystem fails, its key is null and errors array is present.
- Non-fatal file errors from successful subsystems appear in the errors array.
- The errors key is completely omitted when there are no errors at all.
"""

from __future__ import annotations

import json

from dev_ghost_parser.models import (
    AnalysisError,
    CodeFlowResult,
    ERResult,
    Node,
    SubsystemError,
)
from dev_ghost_parser.output_serializer import Output_Serializer


def _make_code_flow(errors: list[AnalysisError] | None = None) -> CodeFlowResult:
    """Helper: minimal successful CodeFlowResult."""
    return CodeFlowResult(
        nodes=[Node(id="abc123", label="UserController", type="Controller")],
        edges=[],
        errors=errors or [],
    )


def _make_er_result(errors: list[AnalysisError] | None = None) -> ERResult:
    """Helper: minimal successful ERResult."""
    return ERResult(entities=[], relations=[], errors=errors or [])


class TestErrorComposition:
    """Tests for error composition in Output_Serializer (Req 4.7)."""

    def test_all_success_no_errors_key(self):
        """When all subsystems succeed with no file errors, 'errors' key is omitted."""
        serializer = Output_Serializer()
        result = serializer.serialize(
            code_flow=_make_code_flow(),
            er_result=_make_er_result(),
            summary="A summary.",
            subsystem_errors=[],
        )
        obj = json.loads(result)
        assert "errors" not in obj
        assert obj["codeFlow"] is not None
        assert obj["erModel"] is not None
        assert obj["summary"] == "A summary."

    def test_code_flow_fails_key_is_null(self):
        """When Code_Flow_Analyzer fails, codeFlow is null."""
        serializer = Output_Serializer()
        result = serializer.serialize(
            code_flow=None,
            er_result=_make_er_result(),
            summary="A summary.",
            subsystem_errors=[
                SubsystemError(subsystem="Code_Flow_Analyzer", message="Fatal error")
            ],
        )
        obj = json.loads(result)
        assert obj["codeFlow"] is None
        assert obj["erModel"] is not None
        assert "errors" in obj
        assert any(e["subsystem"] == "Code_Flow_Analyzer" for e in obj["errors"])

    def test_er_extractor_fails_key_is_null(self):
        """When ER_Extractor fails, erModel is null."""
        serializer = Output_Serializer()
        result = serializer.serialize(
            code_flow=_make_code_flow(),
            er_result=None,
            summary="A summary.",
            subsystem_errors=[
                SubsystemError(subsystem="ER_Extractor", message="Fatal error")
            ],
        )
        obj = json.loads(result)
        assert obj["erModel"] is None
        assert obj["codeFlow"] is not None
        assert "errors" in obj
        assert any(e["subsystem"] == "ER_Extractor" for e in obj["errors"])

    def test_summary_fails_key_is_null(self):
        """When Summary_Generator fails, summary is null."""
        serializer = Output_Serializer()
        result = serializer.serialize(
            code_flow=_make_code_flow(),
            er_result=_make_er_result(),
            summary=None,
            subsystem_errors=[
                SubsystemError(subsystem="Summary_Generator", message="Fatal error")
            ],
        )
        obj = json.loads(result)
        assert obj["summary"] is None
        assert "errors" in obj
        assert any(e["subsystem"] == "Summary_Generator" for e in obj["errors"])

    def test_nonfatal_file_errors_from_code_flow(self):
        """Non-fatal file errors from Code_Flow_Analyzer appear in the errors array."""
        serializer = Output_Serializer()
        code_flow = _make_code_flow(errors=[
            AnalysisError(path="broken.php", reason="Syntax error on line 5"),
        ])
        result = serializer.serialize(
            code_flow=code_flow,
            er_result=_make_er_result(),
            summary="A summary.",
            subsystem_errors=[],
        )
        obj = json.loads(result)
        assert "errors" in obj
        assert len(obj["errors"]) == 1
        assert obj["errors"][0]["subsystem"] == "Code_Flow_Analyzer"
        assert "broken.php" in obj["errors"][0]["message"]
        assert "Syntax error on line 5" in obj["errors"][0]["message"]
        # codeFlow is still present (subsystem succeeded)
        assert obj["codeFlow"] is not None

    def test_nonfatal_file_errors_from_er_extractor(self):
        """Non-fatal file errors from ER_Extractor appear in the errors array."""
        serializer = Output_Serializer()
        er_result = _make_er_result(errors=[
            AnalysisError(path="bad_schema.prisma", reason="Unexpected token"),
        ])
        result = serializer.serialize(
            code_flow=_make_code_flow(),
            er_result=er_result,
            summary="A summary.",
            subsystem_errors=[],
        )
        obj = json.loads(result)
        assert "errors" in obj
        assert len(obj["errors"]) == 1
        assert obj["errors"][0]["subsystem"] == "ER_Extractor"
        assert "bad_schema.prisma" in obj["errors"][0]["message"]
        assert "Unexpected token" in obj["errors"][0]["message"]
        # erModel is still present (subsystem succeeded)
        assert obj["erModel"] is not None

    def test_combined_fatal_and_nonfatal_errors(self):
        """Fatal subsystem errors and non-fatal file errors coexist in errors array."""
        serializer = Output_Serializer()
        code_flow = _make_code_flow(errors=[
            AnalysisError(path="broken.ts", reason="Parse failure"),
        ])
        result = serializer.serialize(
            code_flow=code_flow,
            er_result=None,
            summary="A summary.",
            subsystem_errors=[
                SubsystemError(subsystem="ER_Extractor", message="Cannot access root")
            ],
        )
        obj = json.loads(result)
        assert obj["erModel"] is None
        assert obj["codeFlow"] is not None
        assert "errors" in obj
        # Should have 2 errors: 1 fatal + 1 non-fatal
        assert len(obj["errors"]) == 2
        subsystems = [e["subsystem"] for e in obj["errors"]]
        assert "ER_Extractor" in subsystems
        assert "Code_Flow_Analyzer" in subsystems

    def test_no_nonfatal_errors_when_subsystem_is_none(self):
        """When a subsystem is None (failed fatally), its .errors are NOT collected."""
        serializer = Output_Serializer()
        # code_flow is None — we should NOT try to read code_flow.errors
        result = serializer.serialize(
            code_flow=None,
            er_result=_make_er_result(),
            summary="A summary.",
            subsystem_errors=[
                SubsystemError(subsystem="Code_Flow_Analyzer", message="Fatal")
            ],
        )
        obj = json.loads(result)
        assert "errors" in obj
        # Only the fatal error, no non-fatal since code_flow is None
        assert len(obj["errors"]) == 1
        assert obj["errors"][0]["subsystem"] == "Code_Flow_Analyzer"

    def test_errors_omitted_when_empty(self):
        """The errors key must NOT appear as an empty array — it's omitted entirely."""
        serializer = Output_Serializer()
        result = serializer.serialize(
            code_flow=_make_code_flow(),
            er_result=_make_er_result(),
            summary="All good.",
            subsystem_errors=[],
        )
        obj = json.loads(result)
        assert "errors" not in obj
        # Verify exactly 3 top-level keys
        assert set(obj.keys()) == {"codeFlow", "erModel", "summary"}


class TestOutputFormat:
    """Tests for output format: bytes, no BOM, valid JSON (Reqs 4.1, 4.2, 4.6)."""

    def test_output_is_bytes_not_str(self):
        """The serialize() method must return bytes, not a string."""
        serializer = Output_Serializer()
        result = serializer.serialize(
            code_flow=_make_code_flow(),
            er_result=_make_er_result(),
            summary="A summary.",
            subsystem_errors=[],
        )
        assert isinstance(result, bytes), f"Expected bytes, got {type(result).__name__}"
        assert not isinstance(result, str)

    def test_output_does_not_start_with_bom(self):
        """The output bytes must not begin with the UTF-8 BOM (EF BB BF)."""
        serializer = Output_Serializer()
        result = serializer.serialize(
            code_flow=_make_code_flow(),
            er_result=_make_er_result(),
            summary="A summary.",
            subsystem_errors=[],
        )
        bom = b"\xef\xbb\xbf"
        assert not result.startswith(bom), "Output starts with UTF-8 BOM"

    def test_output_no_bom_when_errors_present(self):
        """No BOM even when the output includes error entries."""
        serializer = Output_Serializer()
        result = serializer.serialize(
            code_flow=None,
            er_result=_make_er_result(),
            summary="A summary.",
            subsystem_errors=[
                SubsystemError(subsystem="Code_Flow_Analyzer", message="Fatal")
            ],
        )
        bom = b"\xef\xbb\xbf"
        assert isinstance(result, bytes)
        assert not result.startswith(bom), "Output starts with UTF-8 BOM"

    def test_output_is_valid_utf8_json(self):
        """The bytes must be decodable as UTF-8 and parseable as valid JSON."""
        serializer = Output_Serializer()
        result = serializer.serialize(
            code_flow=_make_code_flow(),
            er_result=_make_er_result(),
            summary="Résumé with ñ and 中文.",
            subsystem_errors=[],
        )
        # Must decode as valid UTF-8
        text = result.decode("utf-8")
        # Must parse as valid JSON
        obj = json.loads(text)
        assert isinstance(obj, dict)
        assert obj["summary"] == "Résumé with ñ and 中文."
