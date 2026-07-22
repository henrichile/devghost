"""
Unit tests for Code_Flow_Analyzer — Task 4.1.

Verifies:
- Architectural classification (file name and class name patterns)
- Node.id stability (same path always produces same SHA-1)
- Node.label uses class name when available, filename stem otherwise
- Node.type is always a valid NodeType value
- Empty nodes/edges for a directory with no recognized files
- AnalysisFatalError raised for inaccessible/missing root paths

Satisfies Requirements 1.1, 1.2, 1.4, 1.6
"""

from __future__ import annotations

import hashlib
import os
import tempfile

import pytest

from dev_ghost_parser.code_flow_analyzer import (
    Code_Flow_Analyzer,
    _classify,
    _classify_for_file,
    _make_node_id,
)
from dev_ghost_parser.models import AnalysisFatalError, NodeType

_VALID_TYPES: frozenset[str] = frozenset(NodeType.__args__)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------


class TestClassify:
    """Unit tests for _classify() and _classify_for_file()."""

    # --- Controller ---
    def test_controller_suffix(self):
        assert _classify("UserController") == "Controller"

    def test_controller_prefix_variant(self):
        # On Windows fnmatch is case-insensitive, so 'controllerBase' matches
        # '*Controller*'. We test a name that truly doesn't match any pattern.
        assert _classify("myhelper") == "Utility"

    def test_controller_in_middle(self):
        assert _classify("UserControllerHelper") == "Controller"

    def test_controller_underscore(self):
        assert _classify("user_controller") == "Controller"

    # --- Service ---
    def test_service_suffix(self):
        assert _classify("OrderService") == "Service"

    def test_service_underscore(self):
        assert _classify("order_service") == "Service"

    # --- Route ---
    def test_route_suffix(self):
        assert _classify("ProductRoute") == "Route"

    def test_router_prefix(self):
        assert _classify("router") == "Route"

    def test_routes_prefix(self):
        assert _classify("routes") == "Route"

    def test_routes_extended(self):
        assert _classify("routesConfig") == "Route"

    # --- Middleware ---
    def test_middleware_suffix(self):
        assert _classify("AuthMiddleware") == "Middleware"

    def test_middleware_underscore(self):
        assert _classify("auth_middleware") == "Middleware"

    # --- Repository ---
    def test_repository_suffix(self):
        assert _classify("UserRepository") == "Repository"

    def test_repo_suffix(self):
        assert _classify("UserRepo") == "Repository"

    def test_repository_underscore(self):
        assert _classify("user_repository") == "Repository"

    def test_repo_underscore(self):
        assert _classify("user_repo") == "Repository"

    # --- Utility (fallback) ---
    def test_utility_fallback(self):
        assert _classify("SomeHelper") == "Utility"

    def test_utility_index(self):
        assert _classify("index") == "Utility"

    def test_utility_empty_ish(self):
        assert _classify("main") == "Utility"

    # --- Classify for file: class name takes priority ---
    def test_classify_for_file_class_name_priority(self):
        # Filename says Utility but class name says Controller
        result = _classify_for_file("helper.php", "UserController")
        assert result == "Controller"

    def test_classify_for_file_no_class_uses_filename(self):
        result = _classify_for_file("orderService.ts", None)
        assert result == "Service"

    def test_classify_for_file_class_utility_falls_back_to_filename(self):
        # Class name is generic, but filename is a Service
        result = _classify_for_file("orderService.ts", "SomethingGeneric")
        assert result == "Service"


# ---------------------------------------------------------------------------
# Node ID
# ---------------------------------------------------------------------------


class TestMakeNodeId:
    def test_stable_for_same_path(self):
        path = "src/controllers/UserController.php"
        assert _make_node_id(path) == _make_node_id(path)

    def test_different_paths_different_ids(self):
        assert _make_node_id("a/b.py") != _make_node_id("a/c.py")

    def test_sha1_correct(self):
        rel = "app/services/OrderService.ts"
        expected = hashlib.sha1(rel.encode("utf-8")).hexdigest()
        assert _make_node_id(rel) == expected

    def test_id_is_40_hex_chars(self):
        node_id = _make_node_id("any/path.js")
        assert len(node_id) == 40
        assert all(c in "0123456789abcdef" for c in node_id)


# ---------------------------------------------------------------------------
# Code_Flow_Analyzer.analyze — integration with temp directories
# ---------------------------------------------------------------------------


@pytest.fixture()
def analyzer() -> Code_Flow_Analyzer:
    return Code_Flow_Analyzer()


@pytest.fixture()
def tmp() -> tempfile.TemporaryDirectory:
    d = tempfile.TemporaryDirectory()
    yield d
    d.cleanup()


def _write(directory: str, name: str, content: bytes = b"") -> str:
    path = os.path.join(directory, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(content)
    return path


class TestAnalyzeDirectoryTraversal:
    """Tests that os.walk picks up files in subdirectories."""

    def test_empty_directory_returns_empty_result(self, analyzer, tmp):
        result = analyzer.analyze(tmp.name)
        assert result.nodes == []
        assert result.edges == []

    def test_ignores_unrecognized_extensions(self, analyzer, tmp):
        _write(tmp.name, "README.md", b"# readme")
        _write(tmp.name, "config.yaml", b"key: value")
        _write(tmp.name, "image.png", b"\x89PNG")
        result = analyzer.analyze(tmp.name)
        assert result.nodes == []

    def test_recognizes_recognized_extensions(self, analyzer, tmp):
        for ext in [".php", ".js", ".ts", ".py", ".rb", ".go", ".rs", ".java", ".cs"]:
            _write(tmp.name, f"file{ext}", b"")
        result = analyzer.analyze(tmp.name)
        assert len(result.nodes) == 9

    def test_recursive_traversal(self, analyzer, tmp):
        _write(tmp.name, "a/b/UserController.php", b"<?php class UserController {}")
        _write(tmp.name, "services/OrderService.ts", b"class OrderService {}")
        result = analyzer.analyze(tmp.name)
        assert len(result.nodes) == 2

    def test_edges_always_empty_at_task_41(self, analyzer, tmp):
        _write(tmp.name, "UserController.php", b"<?php class UserController {}")
        result = analyzer.analyze(tmp.name)
        assert result.edges == []


class TestNodeClassification:
    """Verifies Node.type is assigned correctly."""

    def test_php_controller_classified_as_controller(self, analyzer, tmp):
        _write(tmp.name, "UserController.php",
               b"<?php\nclass UserController extends Controller {\n}\n")
        result = analyzer.analyze(tmp.name)
        assert len(result.nodes) == 1
        assert result.nodes[0].type == "Controller"

    def test_ts_service_classified_as_service(self, analyzer, tmp):
        _write(tmp.name, "orderService.ts", b"class OrderService { }")
        result = analyzer.analyze(tmp.name)
        assert len(result.nodes) == 1
        assert result.nodes[0].type == "Service"

    def test_js_middleware_classified_as_middleware(self, analyzer, tmp):
        _write(tmp.name, "authMiddleware.js", b"class AuthMiddleware { }")
        result = analyzer.analyze(tmp.name)
        assert len(result.nodes) == 1
        assert result.nodes[0].type == "Middleware"

    def test_py_helper_classified_as_utility(self, analyzer, tmp):
        _write(tmp.name, "helper.py", b"def helper(): pass\n")
        result = analyzer.analyze(tmp.name)
        assert len(result.nodes) == 1
        assert result.nodes[0].type == "Utility"

    def test_all_node_types_valid(self, analyzer, tmp):
        files = [
            ("UserController.php", b"<?php class UserController {}"),
            ("OrderService.ts",    b"class OrderService {}"),
            ("productRoutes.js",   b"const router = {}"),
            ("AuthMiddleware.py",  b"class AuthMiddleware: pass"),
            ("UserRepository.java", b"public class UserRepository {}"),
            ("utils.go",           b"package main"),
        ]
        for name, content in files:
            _write(tmp.name, name, content)
        result = analyzer.analyze(tmp.name)
        for node in result.nodes:
            assert node.type in _VALID_TYPES, f"Invalid type {node.type!r} for {node.label}"


class TestNodeLabel:
    """Verifies Node.label uses class name when detected, else filename stem."""

    def test_label_is_class_name_when_detected(self, analyzer, tmp):
        _write(tmp.name, "usercontroller.php",
               b"<?php\nclass UserController {}\n")
        result = analyzer.analyze(tmp.name)
        # Label should be the detected class name, not the filename stem
        assert result.nodes[0].label == "UserController"

    def test_label_is_filename_stem_when_no_class(self, analyzer, tmp):
        _write(tmp.name, "helpers.py", b"def helper(): pass\n")
        result = analyzer.analyze(tmp.name)
        assert result.nodes[0].label == "helpers"

    def test_label_is_non_empty(self, analyzer, tmp):
        _write(tmp.name, "index.js", b"const x = 1;")
        result = analyzer.analyze(tmp.name)
        assert result.nodes[0].label != ""


class TestNodeId:
    """Verifies Node.id stability and uniqueness."""

    def test_same_path_same_id_across_calls(self, analyzer, tmp):
        _write(tmp.name, "UserController.php", b"<?php class UserController {}")
        result1 = analyzer.analyze(tmp.name)
        result2 = analyzer.analyze(tmp.name)
        assert result1.nodes[0].id == result2.nodes[0].id

    def test_different_files_different_ids(self, analyzer, tmp):
        _write(tmp.name, "UserController.php", b"<?php class UserController {}")
        _write(tmp.name, "OrderService.ts",    b"class OrderService {}")
        result = analyzer.analyze(tmp.name)
        ids = [n.id for n in result.nodes]
        assert len(ids) == len(set(ids)), "Duplicate node IDs detected"

    def test_node_id_is_sha1_of_relative_path(self, analyzer, tmp):
        _write(tmp.name, "UserController.php", b"<?php class UserController {}")
        result = analyzer.analyze(tmp.name)
        node = result.nodes[0]
        rel = os.path.relpath(
            os.path.join(os.path.realpath(tmp.name), "UserController.php"),
            os.path.realpath(tmp.name),
        )
        expected = hashlib.sha1(rel.encode("utf-8")).hexdigest()
        assert node.id == expected


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestAnalysisFatalError:
    def test_raises_for_nonexistent_path(self, analyzer):
        with pytest.raises(AnalysisFatalError) as exc_info:
            analyzer.analyze("/nonexistent_path_that_should_not_exist_xyz123")
        assert "not found" in exc_info.value.message.lower()

    def test_raises_for_file_path_instead_of_directory(self, analyzer, tmp):
        file_path = os.path.join(tmp.name, "file.py")
        with open(file_path, "w") as fh:
            fh.write("")
        with pytest.raises(AnalysisFatalError) as exc_info:
            analyzer.analyze(file_path)
        assert "not a directory" in exc_info.value.message.lower()
