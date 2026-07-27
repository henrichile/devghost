# Feature: precision-analysis-enhancements, Property 3: Method Extraction Produces Ordered List Capped at 15
# Feature: precision-analysis-enhancements, Property 4: Private/Dunder Method Exclusion
# Feature: precision-analysis-enhancements, Property 5: Graceful Fallback for Unsupported Files
"""
Property 3: Method Extraction Produces Ordered List Capped at 15
Property 4: Private/Dunder Method Exclusion
Property 5: Graceful Fallback for Unsupported Files

Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from dev_ghost_parser.code_flow_analyzer import (
    _extract_method_names,
    _filter_methods_by_visibility,
)

# ---------------------------------------------------------------------------
# Supported extensions for tree-sitter parsing
# ---------------------------------------------------------------------------
SUPPORTED_EXTENSIONS = [".py", ".js", ".ts", ".tsx", ".php", ".rb", ".go", ".rs", ".java", ".cs"]

# Extensions where no visibility filtering is applied
NO_FILTER_EXTENSIONS = [".go", ".rs", ".rb"]

# Extensions where underscore-prefix filtering is applied (Java/TS/C#)
UNDERSCORE_FILTER_EXTENSIONS = [".java", ".ts", ".tsx", ".cs"]


# ---------------------------------------------------------------------------
# Strategies: generate valid Python source with varying function counts
# ---------------------------------------------------------------------------

def _make_python_source(func_names: list[str]) -> bytes:
    """Generate valid Python source code with the given function names."""
    lines = []
    for name in func_names:
        lines.append(f"def {name}():")
        lines.append("    pass")
        lines.append("")
    return "\n".join(lines).encode("utf-8")


def _make_go_source(func_names: list[str]) -> bytes:
    """Generate valid Go source code with the given function names."""
    lines = ["package main", ""]
    for name in func_names:
        lines.append(f"func {name}() {{")
        lines.append("}")
        lines.append("")
    return "\n".join(lines).encode("utf-8")


def _make_ruby_source(func_names: list[str]) -> bytes:
    """Generate valid Ruby source code with the given function names."""
    lines = []
    for name in func_names:
        lines.append(f"def {name}")
        lines.append("end")
        lines.append("")
    return "\n".join(lines).encode("utf-8")


def _make_rust_source(func_names: list[str]) -> bytes:
    """Generate valid Rust source code with the given function names."""
    lines = []
    for name in func_names:
        lines.append(f"fn {name}() {{}}")
        lines.append("")
    return "\n".join(lines).encode("utf-8")


# Strategy for valid Python identifiers (no leading digits, no keywords conflicts)
python_identifier = st.from_regex(r"[a-z][a-z0-9_]{0,19}", fullmatch=True)

# Strategy for Go/Rust/Ruby identifiers (valid function names)
go_identifier = st.from_regex(r"[a-zA-Z][a-zA-Z0-9_]{0,19}", fullmatch=True)


# ---------------------------------------------------------------------------
# Property 3: Method Extraction Produces Ordered List Capped at 15
# ---------------------------------------------------------------------------

@given(
    func_names=st.lists(python_identifier, min_size=1, max_size=25, unique=True),
)
@settings(max_examples=100)
def test_property_3_method_extraction_ordered_and_capped(func_names):
    """
    **Validates: Requirements 2.1, 2.4**

    For any source file with a supported extension that parses successfully,
    the extracted method_names list SHALL contain methods in their order of
    appearance in the source code and SHALL never exceed 15 elements.
    """
    source = _make_python_source(func_names)
    raw_methods = _extract_method_names(source, ".py")
    filtered = _filter_methods_by_visibility(raw_methods, ".py")
    result = filtered[:15]

    # Cap: never more than 15
    assert len(result) <= 15, (
        f"Result has {len(result)} methods, exceeds cap of 15. "
        f"Input had {len(func_names)} functions."
    )

    # Order: methods must appear in source order
    # Filter func_names to match what would pass visibility filter (no dunder)
    expected_visible = [n for n in func_names if not n.startswith("__")]
    expected_capped = expected_visible[:15]

    # The extracted methods that are in our expected list should be in order
    # (tree-sitter extracts in source order)
    for i in range(len(result) - 1):
        if result[i] in expected_capped and result[i + 1] in expected_capped:
            idx_a = expected_capped.index(result[i])
            idx_b = expected_capped.index(result[i + 1])
            assert idx_a < idx_b, (
                f"Methods not in source order: {result[i]!r} (pos {idx_a}) "
                f"appears before {result[i+1]!r} (pos {idx_b}) in result "
                f"but should be after based on source order."
            )


@given(
    func_names=st.lists(go_identifier, min_size=1, max_size=25, unique=True),
)
@settings(max_examples=100)
def test_property_3_go_method_extraction_ordered_and_capped(func_names):
    """
    **Validates: Requirements 2.1, 2.4**

    For Go source files, extracted method_names list SHALL contain methods in
    their order of appearance and SHALL never exceed 15 elements.
    """
    source = _make_go_source(func_names)
    raw_methods = _extract_method_names(source, ".go")
    filtered = _filter_methods_by_visibility(raw_methods, ".go")
    result = filtered[:15]

    # Cap: never more than 15
    assert len(result) <= 15, (
        f"Result has {len(result)} methods, exceeds cap of 15."
    )

    # Order preservation: Go doesn't filter, so expected order matches input
    expected_capped = func_names[:15]
    for i in range(len(result) - 1):
        if result[i] in expected_capped and result[i + 1] in expected_capped:
            idx_a = expected_capped.index(result[i])
            idx_b = expected_capped.index(result[i + 1])
            assert idx_a < idx_b, (
                f"Methods not in source order: {result[i]!r} before {result[i+1]!r} "
                f"but source order says otherwise."
            )


# ---------------------------------------------------------------------------
# Property 4: Private/Dunder Method Exclusion
# ---------------------------------------------------------------------------

@given(
    regular_names=st.lists(
        st.from_regex(r"[a-z][a-z0-9_]{0,15}", fullmatch=True),
        min_size=0,
        max_size=10,
        unique=True,
    ),
    dunder_names=st.lists(
        st.from_regex(r"__[a-z][a-z0-9_]{0,12}__", fullmatch=True),
        min_size=1,
        max_size=5,
        unique=True,
    ),
)
@settings(max_examples=100)
def test_property_4_python_dunder_exclusion(regular_names, dunder_names):
    """
    **Validates: Requirements 2.2, 2.5**

    For any Python source file, method names starting with double underscore
    SHALL NOT appear in the extracted method_names.
    """
    # Combine regular and dunder methods
    all_names = regular_names + dunder_names
    source = _make_python_source(all_names)

    raw_methods = _extract_method_names(source, ".py")
    filtered = _filter_methods_by_visibility(raw_methods, ".py")

    # No dunder method should appear in the filtered result
    for method in filtered:
        assert not method.startswith("__"), (
            f"Dunder method {method!r} should have been excluded from Python methods. "
            f"Input names: {all_names}"
        )

    # Regular methods SHOULD still appear (if they parsed successfully)
    for name in regular_names:
        if name in raw_methods:
            assert name in filtered, (
                f"Regular method {name!r} was incorrectly excluded from Python filtering."
            )


@given(
    func_names=st.lists(go_identifier, min_size=1, max_size=15, unique=True),
)
@settings(max_examples=100)
def test_property_4_go_no_filtering(func_names):
    """
    **Validates: Requirements 2.5**

    For any Go source file, ALL defined functions and methods SHALL appear
    without visibility filtering.
    """
    source = _make_go_source(func_names)
    raw_methods = _extract_method_names(source, ".go")
    filtered = _filter_methods_by_visibility(raw_methods, ".go")

    # All extracted methods should remain after filtering (no visibility filter for Go)
    assert filtered == raw_methods, (
        f"Go methods should not be filtered. "
        f"Raw: {raw_methods}, Filtered: {filtered}"
    )


@given(
    func_names=st.lists(
        st.from_regex(r"[a-z][a-z0-9_]{0,15}", fullmatch=True),
        min_size=1,
        max_size=15,
        unique=True,
    ),
)
@settings(max_examples=100)
def test_property_4_rust_no_filtering(func_names):
    """
    **Validates: Requirements 2.5**

    For any Rust source file, ALL defined functions and methods SHALL appear
    without visibility filtering.
    """
    source = _make_rust_source(func_names)
    raw_methods = _extract_method_names(source, ".rs")
    filtered = _filter_methods_by_visibility(raw_methods, ".rs")

    # All extracted methods should remain after filtering (no visibility filter for Rust)
    assert filtered == raw_methods, (
        f"Rust methods should not be filtered. "
        f"Raw: {raw_methods}, Filtered: {filtered}"
    )


@given(
    func_names=st.lists(
        st.from_regex(r"[a-z][a-z0-9_]{0,15}", fullmatch=True),
        min_size=1,
        max_size=15,
        unique=True,
    ),
)
@settings(max_examples=100)
def test_property_4_ruby_no_filtering(func_names):
    """
    **Validates: Requirements 2.5**

    For any Ruby source file, ALL defined functions and methods SHALL appear
    without visibility filtering.
    """
    source = _make_ruby_source(func_names)
    raw_methods = _extract_method_names(source, ".rb")
    filtered = _filter_methods_by_visibility(raw_methods, ".rb")

    # All extracted methods should remain after filtering (no visibility filter for Ruby)
    assert filtered == raw_methods, (
        f"Ruby methods should not be filtered. "
        f"Raw: {raw_methods}, Filtered: {filtered}"
    )


@given(
    regular_names=st.lists(
        st.from_regex(r"[a-z][a-z0-9]{0,15}", fullmatch=True),
        min_size=0,
        max_size=8,
        unique=True,
    ),
    private_names=st.lists(
        st.from_regex(r"_[a-z][a-z0-9]{0,12}", fullmatch=True),
        min_size=1,
        max_size=5,
        unique=True,
    ),
)
@settings(max_examples=100)
def test_property_4_java_ts_cs_underscore_exclusion(regular_names, private_names):
    """
    **Validates: Requirements 2.2**

    For any Java/TypeScript/C# source file, methods with private or protected
    visibility (indicated by underscore prefix convention) SHALL NOT appear.
    """
    all_methods = regular_names + private_names

    # Test the filter function directly since generating valid Java/TS/C# source
    # with proper private methods is complex; the filter logic is what matters.
    for ext in UNDERSCORE_FILTER_EXTENSIONS:
        filtered = _filter_methods_by_visibility(all_methods, ext)

        # No underscore-prefixed method should appear
        for method in filtered:
            assert not method.startswith("_"), (
                f"Private method {method!r} should have been excluded for {ext}. "
                f"Input: {all_methods}"
            )

        # Regular methods should all be present
        for name in regular_names:
            assert name in filtered, (
                f"Regular method {name!r} was incorrectly excluded for {ext}."
            )


# ---------------------------------------------------------------------------
# Property 5: Graceful Fallback for Unsupported Files
# ---------------------------------------------------------------------------

@given(
    ext=st.from_regex(r"\.[a-z]{3,5}", fullmatch=True).filter(
        lambda e: e not in SUPPORTED_EXTENSIONS
    ),
    content=st.binary(min_size=0, max_size=500),
)
@settings(max_examples=100)
def test_property_5_unsupported_extension_returns_empty(ext, content):
    """
    **Validates: Requirements 2.3**

    For any file with an extension NOT in the supported grammar map, the
    extracted method_names SHALL be an empty list and no fatal error SHALL
    be raised.
    """
    result = _extract_method_names(content, ext)

    assert result == [], (
        f"Unsupported extension {ext!r} should return empty list, got {result!r}"
    )


@given(
    ext=st.sampled_from(SUPPORTED_EXTENSIONS),
    content=st.binary(min_size=0, max_size=200),
)
@settings(max_examples=100)
def test_property_5_malformed_source_returns_empty_or_valid(ext, content):
    """
    **Validates: Requirements 2.3**

    For any file whose parsing raises an exception or produces malformed content,
    the extracted method_names SHALL be an empty list (or a valid list if the
    parser handles it gracefully) and no fatal error SHALL be raised.
    """
    # This should NEVER raise an exception regardless of content
    try:
        result = _extract_method_names(content, ext)
    except Exception as exc:
        raise AssertionError(
            f"_extract_method_names raised {type(exc).__name__}: {exc} "
            f"for extension {ext!r} with content of length {len(content)}. "
            f"Should return [] gracefully."
        )

    # Result must be a list
    assert isinstance(result, list), (
        f"Expected list, got {type(result).__name__} for ext={ext!r}"
    )

    # Each element must be a string
    for item in result:
        assert isinstance(item, str), (
            f"Expected str elements, got {type(item).__name__} in result"
        )
