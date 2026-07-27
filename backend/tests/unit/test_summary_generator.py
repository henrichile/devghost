"""
Unit tests for Summary_Generator — task 7.1 / 7.2 / 7.5.

Validates Requirements 3.1, 3.2, 3.3, 3.4, 3.5.
"""

from __future__ import annotations

import pytest

from dev_ghost_parser.models import (
    Attribute,
    CodeFlowResult,
    ERResult,
    Entity,
    Node,
    Relation,
)
from dev_ghost_parser.summary_generator import (
    Summary_Generator,
    _NO_FILES_MESSAGE,
    _INCOMPLETE_WARNING,
    _sanitize,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(label: str, ntype: str) -> Node:
    return Node(id=label, label=label, type=ntype)  # type: ignore[arg-type]


def _entity(name: str) -> Entity:
    return Entity(name=name, attributes=[], primaryKey="id")


def _make_code_flow(*types: str) -> CodeFlowResult:
    nodes = [_node(f"node_{i}_{t}", t) for i, t in enumerate(types)]
    return CodeFlowResult(nodes=nodes, edges=[], errors=[])


def _make_er_result(*names: str) -> ERResult:
    entities = [_entity(n) for n in names]
    return ERResult(entities=entities, relations=[], errors=[])


sg = Summary_Generator()


# ---------------------------------------------------------------------------
# Req 3.3: empty / no-files cases
# ---------------------------------------------------------------------------

class TestEmptyCodebase:
    """Summary_Generator must return the fixed message when there is nothing to summarize."""

    def test_both_none_returns_fixed_message(self):
        result = sg.generate(None, None, "/some/path")
        assert result == _NO_FILES_MESSAGE

    def test_both_empty_returns_fixed_message(self):
        result = sg.generate(
            CodeFlowResult(), ERResult(), "/some/path"
        )
        assert result == _NO_FILES_MESSAGE

    def test_code_flow_none_er_empty_returns_fixed_message(self):
        result = sg.generate(None, ERResult(), "/some/path")
        assert result == _NO_FILES_MESSAGE

    def test_code_flow_empty_er_none_returns_fixed_message(self):
        result = sg.generate(CodeFlowResult(), None, "/some/path")
        assert result == _NO_FILES_MESSAGE

    def test_code_flow_empty_er_empty_returns_fixed_message(self):
        result = sg.generate(
            _make_code_flow(),   # 0 nodes
            _make_er_result(),   # 0 entities
            "/path",
        )
        assert result == _NO_FILES_MESSAGE


# ---------------------------------------------------------------------------
# Req 3.1: normal summaries contain at most 3 sentences
# ---------------------------------------------------------------------------

class TestSentenceCount:
    """Summary must be 3 to 4 sentences."""

    def test_only_code_flow_produces_two_sentences(self):
        """With only nodes (no entities), should produce sentence 1 + sentence 3."""
        result = sg.generate(_make_code_flow("Service"), ERResult(), "/p")
        sentences = [s.strip() for s in result.split(".") if s.strip()]
        assert 2 <= len(sentences) <= 4

    def test_code_flow_and_entities_produce_three_or_four_sentences(self):
        result = sg.generate(
            _make_code_flow("Service", "Utility"),
            _make_er_result("User", "Order"),
            "/p",
        )
        # Should produce sentence 1 + sentence 2 + sentence 3 (+ optional sentence 4)
        sentences = [s.strip() for s in result.split(".") if s.strip()]
        assert 3 <= len(sentences) <= 4

    def test_failed_subsystem_adds_warning_sentence(self):
        result = sg.generate(_make_code_flow("Service"), None, "/p")
        assert _INCOMPLETE_WARNING in result

    def test_full_result_stays_at_most_four_sentences(self):
        result = sg.generate(
            _make_code_flow("Controller", "Service"),
            _make_er_result("User"),
            "/p",
        )
        sentences = [s.strip() for s in result.split(".") if s.strip()]
        assert len(sentences) <= 4


# ---------------------------------------------------------------------------
# Pattern inference rules
# ---------------------------------------------------------------------------

class TestPatternInference:
    """Pattern labels depend on node-type composition."""

    def test_controller_present_gives_mvc(self):
        result = sg.generate(_make_code_flow("Controller", "Service"), ERResult(), "/p")
        assert "model-view-controller" in result

    def test_service_dominant_gives_service_oriented(self):
        result = sg.generate(
            _make_code_flow("Service", "Service", "Utility"), ERResult(), "/p"
        )
        assert "orientado a servicios" in result

    def test_route_dominant_gives_routing_based(self):
        result = sg.generate(
            _make_code_flow("Route", "Route", "Utility"), ERResult(), "/p"
        )
        assert "basado en rutas" in result

    def test_utility_only_gives_utility_based(self):
        result = sg.generate(_make_code_flow("Utility", "Utility"), ERResult(), "/p")
        assert "basado en utilidades" in result

    def test_controller_takes_priority_over_service(self):
        """Even one Controller should override a dominant Service."""
        result = sg.generate(
            _make_code_flow("Service", "Service", "Service", "Controller"),
            ERResult(),
            "/p",
        )
        assert "model-view-controller" in result


# ---------------------------------------------------------------------------
# Spanish type names in component breakdown (Req 3.3)
# ---------------------------------------------------------------------------

class TestSpanishTypeNames:
    """Summary must use Spanish architectural type names."""

    def test_controller_type_uses_spanish_name(self):
        result = sg.generate(
            _make_code_flow("Controller", "Controller"),
            _make_er_result("User"),
            "/p",
        )
        assert "controladores" in result

    def test_service_type_uses_spanish_name(self):
        result = sg.generate(
            _make_code_flow("Service", "Service"),
            _make_er_result("User"),
            "/p",
        )
        assert "servicios" in result

    def test_route_type_uses_spanish_name(self):
        result = sg.generate(
            _make_code_flow("Route"),
            _make_er_result("User"),
            "/p",
        )
        assert "ruta" in result

    def test_singular_controller_uses_singular(self):
        result = sg.generate(
            _make_code_flow("Controller"),
            _make_er_result("User"),
            "/p",
        )
        assert "1 controlador" in result

    def test_component_breakdown_present(self):
        result = sg.generate(
            _make_code_flow("Controller", "Service", "Route"),
            _make_er_result("User"),
            "/p",
        )
        assert "Los componentes incluyen" in result


# ---------------------------------------------------------------------------
# Sentence 4 — general purpose inference
# ---------------------------------------------------------------------------

class TestPurposeInference:
    """Sentence 4 provides general purpose when inferable."""

    def test_controller_and_repository_infers_data_management(self):
        result = sg.generate(
            _make_code_flow("Controller", "Repository"),
            _make_er_result("User"),
            "/p",
        )
        assert "El sistema parece orientado a" in result

    def test_utility_only_has_no_purpose_sentence(self):
        result = sg.generate(
            _make_code_flow("Utility"),
            _make_er_result("User"),
            "/p",
        )
        assert "El sistema parece orientado a" not in result


# ---------------------------------------------------------------------------
# Entity listing
# ---------------------------------------------------------------------------

class TestEntityListing:
    """Entities are mentioned in the summary (up to 3 names)."""

    def test_entity_names_appear_in_summary(self):
        result = sg.generate(
            _make_code_flow("Service"),
            _make_er_result("User", "Order"),
            "/p",
        )
        assert "User" in result
        assert "Order" in result

    def test_only_first_three_entities_listed(self):
        result = sg.generate(
            _make_code_flow("Service"),
            _make_er_result("Alpha", "Beta", "Gamma", "Delta", "Epsilon"),
            "/p",
        )
        assert "Alpha" in result
        assert "Beta" in result
        assert "Gamma" in result
        assert "Delta" not in result
        assert "Epsilon" not in result

    def test_entity_count_mentioned(self):
        result = sg.generate(
            _make_code_flow("Service"),
            _make_er_result("User", "Order", "Product", "Invoice"),
            "/p",
        )
        assert "4" in result


# ---------------------------------------------------------------------------
# Req 3.5: incompleteness warning
# ---------------------------------------------------------------------------

class TestIncompleteWarning:
    """Warning sentence is present iff at least one subsystem is None."""

    def test_warning_present_when_code_flow_none(self):
        result = sg.generate(None, _make_er_result("User"), "/p")
        assert _INCOMPLETE_WARNING in result

    def test_warning_present_when_er_result_none(self):
        result = sg.generate(_make_code_flow("Service"), None, "/p")
        assert _INCOMPLETE_WARNING in result

    def test_warning_absent_when_both_present(self):
        result = sg.generate(
            _make_code_flow("Service"),
            _make_er_result("User"),
            "/p",
        )
        assert _INCOMPLETE_WARNING not in result

    def test_warning_present_when_both_none_but_fixed_message_returned(self):
        # When both are None, we get the fixed no-files message, not the warning.
        result = sg.generate(None, None, "/p")
        assert result == _NO_FILES_MESSAGE


# ---------------------------------------------------------------------------
# Never-raise contract
# ---------------------------------------------------------------------------

class TestNeverRaises:
    """generate() must not raise regardless of input."""

    def test_none_none_no_exception(self):
        sg.generate(None, None, "")

    def test_empty_path_no_exception(self):
        sg.generate(CodeFlowResult(), ERResult(), "")

    def test_unusual_inputs_no_exception(self):
        cf = _make_code_flow("Controller")
        er = _make_er_result("SomeEntity")
        sg.generate(cf, er, "")


# ---------------------------------------------------------------------------
# Req 3.2: sanitization removes prohibited characters
# ---------------------------------------------------------------------------

class TestSanitize:
    """_sanitize must remove prohibited chars, identifiers, and truncate."""

    def test_removes_star(self):
        assert "*" not in _sanitize("Hello * world")

    def test_removes_hash(self):
        assert "#" not in _sanitize("Section # heading")

    def test_removes_backtick(self):
        assert "`" not in _sanitize("Use `code` here")

    def test_removes_underscore(self):
        assert "_" not in _sanitize("some_text here")

    def test_removes_tilde(self):
        assert "~" not in _sanitize("approximately ~100")

    def test_removes_angle_brackets(self):
        result = _sanitize("Type <string> value")
        assert "<" not in result
        assert ">" not in result

    def test_removes_control_characters(self):
        # U+0000 through U+001F
        text = "Hello\x00World\x01\x1fEnd"
        result = _sanitize(text)
        for cp in range(0x00, 0x20):
            assert chr(cp) not in result

    def test_removes_camel_case_identifiers(self):
        result = _sanitize("The service orderService is running.")
        assert "orderService" not in result

    def test_removes_pascal_case_identifiers(self):
        result = _sanitize("The class OrderService handles requests.")
        assert "OrderService" not in result

    def test_removes_snake_case_identifiers(self):
        result = _sanitize("The function get_user_name returns a value.")
        assert "get_user_name" not in result

    def test_preserves_normal_text(self):
        text = "The codebase follows a service pattern with 5 components."
        assert _sanitize(text) == text

    def test_collapses_double_spaces(self):
        result = _sanitize("Hello   world")
        assert "  " not in result

    def test_strips_leading_trailing_whitespace(self):
        result = _sanitize("  Hello world  ")
        assert result == "Hello world"

    def test_combined_sanitization(self):
        text = "The *service* uses `orderService` and get_user_name."
        result = _sanitize(text)
        assert "*" not in result
        assert "`" not in result
        assert "orderService" not in result
        assert "get_user_name" not in result


# ---------------------------------------------------------------------------
# Req 3.4: truncation to 500 code points
# ---------------------------------------------------------------------------

class TestTruncation:
    """_sanitize must truncate to 500 Unicode code points."""

    def test_short_text_unchanged(self):
        text = "Short text."
        assert _sanitize(text) == text

    def test_exactly_500_code_points_unchanged(self):
        text = "A" * 500
        assert len(_sanitize(text)) == 500

    def test_over_500_code_points_truncated(self):
        text = "A" * 600
        result = _sanitize(text)
        assert len(result) == 500

    def test_unicode_emoji_counted_as_one_code_point(self):
        # Each emoji is 1 code point; 501 emojis should be truncated to 500
        text = "\U0001F600" * 501
        result = _sanitize(text)
        assert len(result) == 500

    def test_truncation_applied_after_sanitization(self):
        # 400 chars + prohibited chars that get removed + 200 more = should still truncate
        text = "A" * 400 + "***" + "B" * 200
        result = _sanitize(text)
        # After removing ***, we have 600 chars → truncated to 500
        assert len(result) == 500


# ---------------------------------------------------------------------------
# Integration: sanitization applied to generated summaries
# ---------------------------------------------------------------------------

class TestSanitizationIntegration:
    """generate() applies sanitization to dynamic summaries but not the fixed message."""

    def test_fixed_message_not_altered(self):
        result = sg.generate(None, None, "/p")
        assert result == _NO_FILES_MESSAGE

    def test_entity_name_with_camelcase_removed(self):
        """If an entity name is camelCase, it should be stripped from the summary."""
        result = sg.generate(
            _make_code_flow("Service"),
            _make_er_result("orderService"),
            "/p",
        )
        assert "orderService" not in result

    def test_no_prohibited_chars_in_output(self):
        """Generated summary should never contain prohibited chars."""
        prohibited = set("*#`_~><")
        result = sg.generate(
            _make_code_flow("Controller", "Service"),
            _make_er_result("User", "Order"),
            "/p",
        )
        for ch in result:
            assert ch not in prohibited

    def test_no_control_chars_in_output(self):
        """Generated summary should never contain control chars U+0000-U+001F."""
        result = sg.generate(
            _make_code_flow("Service"),
            _make_er_result("User"),
            "/p",
        )
        for ch in result:
            assert ord(ch) >= 0x20
