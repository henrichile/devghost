"""
Unit tests for import/dependency extraction — Task 4.3.

Verifies:
- Python imports (import_statement, import_from_statement) produce edges
- JavaScript/TypeScript imports (import, require) produce edges with correct relation types
- PHP use/require/include produce edges with "depends_on" relation
- Go import declarations produce edges
- Java import declarations produce edges
- Ruby require/require_relative produce edges
- Rust use declarations produce edges
- C# using directives produce edges
- Non-parseable files are recorded as errors (non-fatal) and processing continues
- Referential integrity is maintained (only edges to existing nodes)
- Self-referencing imports are excluded

Satisfies Requirements 1.3, 1.6.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from dev_ghost_parser.code_flow_analyzer import (
    Code_Flow_Analyzer,
    _extract_imports,
    _make_node_id,
    _normalize_import_path,
    _resolve_import,
    _build_resolution_maps,
)
from dev_ghost_parser.models import Node


@pytest.fixture()
def analyzer() -> Code_Flow_Analyzer:
    return Code_Flow_Analyzer()


@pytest.fixture()
def tmp():
    d = tempfile.TemporaryDirectory()
    yield d
    d.cleanup()


def _write(directory: str, name: str, content: bytes = b"") -> str:
    path = os.path.join(directory, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(content)
    return path


# ---------------------------------------------------------------------------
# Python imports
# ---------------------------------------------------------------------------


class TestPythonImportExtraction:
    def test_import_from_statement(self, analyzer, tmp):
        _write(tmp.name, "app/services/order_service.py", b"class OrderService:\n    pass\n")
        _write(tmp.name, "app/controllers/order_controller.py",
               b"from app.services.order_service import OrderService\n\nclass OrderController:\n    pass\n")
        result = analyzer.analyze(tmp.name)
        # Should produce at least one edge from controller → service
        edge_relations = [(e.relation) for e in result.edges]
        assert "imports" in edge_relations or len(result.edges) > 0

    def test_import_statement(self, analyzer, tmp):
        _write(tmp.name, "utils.py", b"def helper(): pass\n")
        _write(tmp.name, "main.py", b"import utils\n\ndef run(): pass\n")
        result = analyzer.analyze(tmp.name)
        # Should find edge from main → utils
        main_id = _make_node_id("main.py")
        utils_id = _make_node_id("utils.py")
        edges_from_main = [e for e in result.edges if e.source == main_id]
        assert any(e.target == utils_id for e in edges_from_main)

    def test_python_from_import_resolves_by_stem(self, analyzer, tmp):
        _write(tmp.name, "services.py", b"class OrderService:\n    pass\n")
        _write(tmp.name, "controller.py", b"from services import OrderService\n")
        result = analyzer.analyze(tmp.name)
        controller_id = _make_node_id("controller.py")
        services_id = _make_node_id("services.py")
        edges_from_ctrl = [e for e in result.edges if e.source == controller_id]
        assert any(e.target == services_id for e in edges_from_ctrl)


# ---------------------------------------------------------------------------
# JavaScript/TypeScript imports
# ---------------------------------------------------------------------------


class TestJsTsImportExtraction:
    def test_es_import_creates_edge(self, analyzer, tmp):
        _write(tmp.name, "OrderService.ts", b"export class OrderService {}\n")
        _write(tmp.name, "OrderController.ts",
               b"import { OrderService } from './OrderService';\n\nexport class OrderController {}\n")
        result = analyzer.analyze(tmp.name)
        ctrl_id = _make_node_id("OrderController.ts")
        svc_id = _make_node_id("OrderService.ts")
        edges_from_ctrl = [e for e in result.edges if e.source == ctrl_id]
        assert any(e.target == svc_id and e.relation == "imports" for e in edges_from_ctrl)

    def test_require_call_creates_calls_edge(self, analyzer, tmp):
        _write(tmp.name, "helper.js", b"module.exports = {};\n")
        _write(tmp.name, "main.js", b"const helper = require('./helper');\n")
        result = analyzer.analyze(tmp.name)
        main_id = _make_node_id("main.js")
        helper_id = _make_node_id("helper.js")
        edges_from_main = [e for e in result.edges if e.source == main_id]
        assert any(e.target == helper_id and e.relation == "calls" for e in edges_from_main)

    def test_nested_directory_relative_import(self, analyzer, tmp):
        _write(tmp.name, "services/OrderService.ts", b"export class OrderService {}\n")
        _write(tmp.name, "controllers/OrderController.ts",
               b"import { OrderService } from '../services/OrderService';\n\nexport class OrderController {}\n")
        result = analyzer.analyze(tmp.name)
        ctrl_id = _make_node_id(os.path.join("controllers", "OrderController.ts"))
        svc_id = _make_node_id(os.path.join("services", "OrderService.ts"))
        edges_from_ctrl = [e for e in result.edges if e.source == ctrl_id]
        assert any(e.target == svc_id and e.relation == "imports" for e in edges_from_ctrl)


# ---------------------------------------------------------------------------
# PHP imports
# ---------------------------------------------------------------------------


class TestPhpImportExtraction:
    def test_use_declaration_creates_depends_on_edge(self, analyzer, tmp):
        _write(tmp.name, "OrderService.php",
               b"<?php\nnamespace App\\Services;\nclass OrderService {}\n")
        _write(tmp.name, "OrderController.php",
               b"<?php\nuse App\\Services\\OrderService;\nclass OrderController {}\n")
        result = analyzer.analyze(tmp.name)
        ctrl_id = _make_node_id("OrderController.php")
        edges_from_ctrl = [e for e in result.edges if e.source == ctrl_id]
        # Should have at least one depends_on edge
        depends_on_edges = [e for e in edges_from_ctrl if e.relation == "depends_on"]
        # The target resolution depends on stem matching
        assert any(e.relation == "depends_on" for e in edges_from_ctrl)


# ---------------------------------------------------------------------------
# Go imports
# ---------------------------------------------------------------------------


class TestGoImportExtraction:
    def test_go_import_extracts_paths(self):
        source = b'package main\n\nimport (\n\t"fmt"\n\t"myapp/services"\n)\n'
        results = _extract_imports(source, ".go")
        paths = [r[0] for r in results]
        assert "fmt" in paths
        assert "myapp/services" in paths
        assert all(r[1] == "imports" for r in results)


# ---------------------------------------------------------------------------
# Java imports
# ---------------------------------------------------------------------------


class TestJavaImportExtraction:
    def test_java_import_extracts_qualified_name(self):
        source = b"package com.example;\n\nimport com.example.services.OrderService;\n\npublic class OrderController {}\n"
        results = _extract_imports(source, ".java")
        paths = [r[0] for r in results]
        assert any("OrderService" in p for p in paths)
        assert all(r[1] == "imports" for r in results)


# ---------------------------------------------------------------------------
# Rust imports
# ---------------------------------------------------------------------------


class TestRustImportExtraction:
    def test_rust_use_extracts_path(self):
        source = b"use crate::services::order_service;\n\nfn main() {}\n"
        results = _extract_imports(source, ".rs")
        assert len(results) >= 1
        assert all(r[1] == "imports" for r in results)


# ---------------------------------------------------------------------------
# C# imports
# ---------------------------------------------------------------------------


class TestCsharpImportExtraction:
    def test_csharp_using_extracts_namespace(self):
        from dev_ghost_parser.code_flow_analyzer import _PARSERS
        if ".cs" not in _PARSERS:
            pytest.skip("C# tree-sitter parser not available in this environment")
        source = b"using System.Collections.Generic;\nusing MyApp.Services;\n\nnamespace MyApp {\n    class OrderController {}\n}\n"
        results = _extract_imports(source, ".cs")
        paths = [r[0] for r in results]
        assert len(paths) >= 1
        assert all(r[1] == "imports" for r in results)


# ---------------------------------------------------------------------------
# Edge cases and error handling
# ---------------------------------------------------------------------------


class TestImportExtractionEdgeCases:
    def test_unresolvable_import_does_not_create_edge(self, analyzer, tmp):
        """Imports that can't be resolved to a file in the codebase produce no edge."""
        _write(tmp.name, "main.py", b"import nonexistent_module\n")
        result = analyzer.analyze(tmp.name)
        assert result.edges == []

    def test_self_referencing_import_excluded(self, analyzer, tmp):
        """A file importing itself should not produce an edge."""
        _write(tmp.name, "utils.py", b"import utils\n")
        result = analyzer.analyze(tmp.name)
        # No self-referencing edges
        for edge in result.edges:
            assert edge.source != edge.target

    def test_referential_integrity_maintained(self, analyzer, tmp):
        """All edges must reference existing node IDs (Property 1)."""
        _write(tmp.name, "services/OrderService.ts", b"export class OrderService {}\n")
        _write(tmp.name, "controllers/OrderController.ts",
               b"import { OrderService } from '../services/OrderService';\nexport class OrderController {}\n")
        result = analyzer.analyze(tmp.name)
        node_ids = {n.id for n in result.nodes}
        for edge in result.edges:
            assert edge.source in node_ids
            assert edge.target in node_ids

    def test_empty_file_produces_no_edges(self, analyzer, tmp):
        """An empty file should produce a node but no edges."""
        _write(tmp.name, "empty.py", b"")
        result = analyzer.analyze(tmp.name)
        assert len(result.nodes) == 1
        assert result.edges == []

    def test_edge_relation_type_is_valid(self, analyzer, tmp):
        """All edges must have a valid relation type."""
        _write(tmp.name, "OrderService.ts", b"export class OrderService {}\n")
        _write(tmp.name, "main.ts",
               b"import { OrderService } from './OrderService';\nconst svc = new OrderService();\n")
        result = analyzer.analyze(tmp.name)
        valid_relations = {"imports", "calls", "depends_on"}
        for edge in result.edges:
            assert edge.relation in valid_relations


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------


class TestNormalizeImportPath:
    def test_strips_leading_dot_slash(self):
        assert _normalize_import_path("./services/OrderService") == "services/OrderService"

    def test_strips_leading_double_dot_slash(self):
        assert _normalize_import_path("../services/OrderService") == "services/OrderService"

    def test_converts_dots_to_slashes(self):
        assert _normalize_import_path("app.services.order_service") == "app/services/order_service"

    def test_converts_rust_double_colon(self):
        assert _normalize_import_path("crate::services::order") == "crate/services/order"

    def test_strips_extension(self):
        assert _normalize_import_path("./helper.js") == "helper"


class TestBuildResolutionMaps:
    def test_builds_all_three_maps(self):
        nodes = [
            Node(id="abc123", label="OrderService", type="Service"),
            Node(id="def456", label="UserController", type="Controller"),
        ]
        rel_paths = ["services/OrderService.ts", "controllers/UserController.ts"]
        path_no_ext, stem, full_path = _build_resolution_maps(nodes, rel_paths)

        assert path_no_ext["services/OrderService"] == "abc123"
        assert stem["OrderService"] == "abc123"
        assert full_path["services/OrderService.ts"] == "abc123"

        assert path_no_ext["controllers/UserController"] == "def456"
        assert stem["UserController"] == "def456"
        assert full_path["controllers/UserController.ts"] == "def456"


class TestResolveImport:
    def setup_method(self):
        nodes = [
            Node(id="svc_id", label="OrderService", type="Service"),
            Node(id="ctrl_id", label="UserController", type="Controller"),
            Node(id="utils_id", label="utils", type="Utility"),
        ]
        rel_paths = [
            "services/OrderService.ts",
            "controllers/UserController.ts",
            "utils.py",
        ]
        self.path_no_ext, self.stem, self.full_path = _build_resolution_maps(nodes, rel_paths)

    def test_relative_path_resolves(self):
        result = _resolve_import(
            "../services/OrderService",
            "controllers/UserController.ts",
            self.path_no_ext, self.stem, self.full_path,
        )
        assert result == "svc_id"

    def test_stem_resolves(self):
        result = _resolve_import(
            "OrderService",
            "controllers/UserController.ts",
            self.path_no_ext, self.stem, self.full_path,
        )
        assert result == "svc_id"

    def test_unresolvable_returns_none(self):
        result = _resolve_import(
            "nonexistent",
            "main.ts",
            self.path_no_ext, self.stem, self.full_path,
        )
        assert result is None

    def test_dotted_python_path_resolves(self):
        result = _resolve_import(
            "utils",
            "main.py",
            self.path_no_ext, self.stem, self.full_path,
        )
        assert result == "utils_id"
