"""
Unit tests for DevGhost_Parser — validation and orchestration.

Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
"""

from __future__ import annotations

import json
import os
import platform
import sys
import tempfile

import pytest

from dev_ghost_parser import DevGhost_Parser


@pytest.fixture
def parser() -> DevGhost_Parser:
    """Provide a fresh parser instance for each test."""
    return DevGhost_Parser()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _parse(result: bytes) -> dict:
    """Parse bytes result to dict, asserting it's valid UTF-8 JSON."""
    assert isinstance(result, bytes), "analyze() must return bytes"
    return json.loads(result.decode("utf-8"))


# ===========================================================================
# Check 1 — missing/empty path (Requirement 5.1)
# ===========================================================================


class TestCheck1MissingOrEmptyPath:
    """Req 5.1: empty or missing path returns a specific error."""

    def test_empty_string(self, parser: DevGhost_Parser) -> None:
        result = _parse(parser.analyze(""))
        assert result == {"errors": [{"message": "A Target_Codebase path is required."}]}

    def test_none_value(self, parser: DevGhost_Parser) -> None:
        # The signature is `path: str` but `if not path` handles None gracefully.
        result = _parse(parser.analyze(None))  # type: ignore[arg-type]
        assert result == {"errors": [{"message": "A Target_Codebase path is required."}]}


# ===========================================================================
# Check 2 — path not found (Requirement 5.2)
# ===========================================================================


class TestCheck2PathNotFound:
    """Req 5.2: non-existent path returns an error including the path."""

    def test_nonexistent_path(self, parser: DevGhost_Parser) -> None:
        bad_path = "/nonexistent/path/xyz123"
        result = _parse(parser.analyze(bad_path))
        assert result == {
            "errors": [{"message": f"Path '{bad_path}' was not found."}]
        }

    def test_error_message_includes_path(self, parser: DevGhost_Parser) -> None:
        bad_path = "/some/other/missing/dir"
        result = _parse(parser.analyze(bad_path))
        assert bad_path in result["errors"][0]["message"]


# ===========================================================================
# Check 3 — permission denied (Requirement 5.3)
# ===========================================================================


@pytest.mark.skipif(
    platform.system() == "Windows",
    reason="Permission removal via chmod is unreliable on Windows",
)
class TestCheck3PermissionDenied:
    """Req 5.3: inaccessible path returns a permission error."""

    def test_no_read_permission(self, parser: DevGhost_Parser) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chmod(tmpdir, 0o000)
            try:
                result = _parse(parser.analyze(tmpdir))
                assert result == {
                    "errors": [
                        {"message": f"Permission denied accessing '{tmpdir}'."}
                    ]
                }
            finally:
                # Restore permissions so cleanup can proceed.
                os.chmod(tmpdir, 0o700)


# ===========================================================================
# Check 4 — not a directory (Requirement 5.4)
# ===========================================================================


class TestCheck4NotADirectory:
    """Req 5.4: path to a file (not directory) returns an appropriate error."""

    def test_path_is_file(self, parser: DevGhost_Parser) -> None:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            filepath = f.name
        try:
            result = _parse(parser.analyze(filepath))
            assert result == {
                "errors": [{"message": f"Path '{filepath}' is not a directory."}]
            }
        finally:
            os.unlink(filepath)


# ===========================================================================
# Validation passes → subsystems invoked (Requirement 5.6)
# ===========================================================================


class TestValidationPassesSubsystemsInvoked:
    """Req 5.6: when validation succeeds, all three subsystems are invoked."""

    def test_empty_directory_produces_valid_structure(
        self, parser: DevGhost_Parser
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _parse(parser.analyze(tmpdir))
            # Must have codeFlow, erModel, summary — no errors key for empty dir
            assert "codeFlow" in result
            assert "erModel" in result
            assert "summary" in result
            assert "errors" not in result

    def test_empty_directory_summary_is_fixed_message(
        self, parser: DevGhost_Parser
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _parse(parser.analyze(tmpdir))
            assert (
                result["summary"]
                == "No analyzable source files were found in the provided codebase."
            )

    def test_codeflow_has_nodes_and_edges(self, parser: DevGhost_Parser) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _parse(parser.analyze(tmpdir))
            assert "nodes" in result["codeFlow"]
            assert "edges" in result["codeFlow"]

    def test_ermodel_has_entities_and_relations(
        self, parser: DevGhost_Parser
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _parse(parser.analyze(tmpdir))
            assert "entities" in result["erModel"]
            assert "relations" in result["erModel"]


# ===========================================================================
# Error response structure (Requirements 5.1–5.4)
# ===========================================================================


class TestErrorResponseStructure:
    """Validation errors must have ONLY the `errors` key."""

    def test_error_response_has_only_errors_key(
        self, parser: DevGhost_Parser
    ) -> None:
        result = _parse(parser.analyze(""))
        assert list(result.keys()) == ["errors"]

    def test_no_codeflow_key_in_error_response(
        self, parser: DevGhost_Parser
    ) -> None:
        result = _parse(parser.analyze("/nonexistent/xyz"))
        assert "codeFlow" not in result
        assert "erModel" not in result
        assert "summary" not in result

    def test_result_is_bytes(self, parser: DevGhost_Parser) -> None:
        raw = parser.analyze("")
        assert isinstance(raw, bytes)

    def test_no_bom_prefix(self, parser: DevGhost_Parser) -> None:
        raw = parser.analyze("")
        assert not raw.startswith(b"\xef\xbb\xbf")


# ===========================================================================
# Never raises exceptions (Requirement 4.7 + implicit contract)
# ===========================================================================


class TestNeverRaisesExceptions:
    """DevGhost_Parser.analyze() must never raise for any error condition."""

    def test_empty_path_no_exception(self, parser: DevGhost_Parser) -> None:
        parser.analyze("")  # Should not raise

    def test_none_path_no_exception(self, parser: DevGhost_Parser) -> None:
        parser.analyze(None)  # type: ignore[arg-type]

    def test_nonexistent_path_no_exception(self, parser: DevGhost_Parser) -> None:
        parser.analyze("/nonexistent/xyz123/abc")  # Should not raise

    def test_file_path_no_exception(self, parser: DevGhost_Parser) -> None:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            filepath = f.name
        try:
            parser.analyze(filepath)  # Should not raise
        finally:
            os.unlink(filepath)


# ===========================================================================
# Full orchestration with a real codebase (Requirement 5.6)
# ===========================================================================


class TestFullOrchestrationWithRealCodebase:
    """Verify that a directory with source files produces populated output."""

    def test_python_file_produces_nonempty_nodes(
        self, parser: DevGhost_Parser
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a simple Python file
            py_path = os.path.join(tmpdir, "user_service.py")
            with open(py_path, "w", encoding="utf-8") as f:
                f.write(
                    "class UserService:\n"
                    "    def get_user(self, user_id: int):\n"
                    "        pass\n"
                )

            result = _parse(parser.analyze(tmpdir))

            assert "codeFlow" in result
            assert len(result["codeFlow"]["nodes"]) > 0, (
                "A Python source file should produce at least one node"
            )

    def test_python_file_node_has_correct_structure(
        self, parser: DevGhost_Parser
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            py_path = os.path.join(tmpdir, "order_controller.py")
            with open(py_path, "w", encoding="utf-8") as f:
                f.write(
                    "class OrderController:\n"
                    "    def index(self):\n"
                    "        pass\n"
                )

            result = _parse(parser.analyze(tmpdir))
            nodes = result["codeFlow"]["nodes"]
            assert len(nodes) >= 1

            node = nodes[0]
            assert "id" in node
            assert "label" in node
            assert "type" in node
            # A file named 'order_controller.py' should be classified as Controller
            assert node["type"] == "Controller"
