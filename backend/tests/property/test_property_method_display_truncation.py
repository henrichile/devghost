# Feature: precision-analysis-enhancements, Property 12: Method Display Name Truncation
"""
Property 12: Method Display Name Truncation

Validates: Requirements 5.3

For any method name string, the display formatting function SHALL prepend "ƒ "
and, when the method name exceeds 40 characters, SHALL truncate to the first 37
characters followed by "...".
"""

from hypothesis import given, settings
from hypothesis import strategies as st


def format_method_display_name(method_name: str) -> str:
    """
    Pure function implementing the method display truncation logic
    matching the frontend InspectionPanel.tsx behavior:
      ƒ {method.length > 40 ? method.slice(0, 37) + '...' : method}
    """
    if len(method_name) > 40:
        return "ƒ " + method_name[:37] + "..."
    return "ƒ " + method_name


# --- Strategies ---

# Method names of varying lengths including edge cases around the 40-char boundary
method_name_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Z"),
        blacklist_characters="\x00",
    ),
    min_size=0,
    max_size=200,
)


@given(method_name=method_name_strategy)
@settings(max_examples=200)
def test_property_12_display_always_starts_with_function_indicator(method_name):
    """
    **Validates: Requirements 5.3**

    For any method name string, the formatted display name SHALL always
    start with the function indicator "ƒ " (ƒ followed by a space).
    """
    result = format_method_display_name(method_name)

    assert result.startswith("ƒ "), (
        f"Display name must start with 'ƒ '. "
        f"Got: {result!r} for method_name={method_name!r}"
    )


@given(method_name=st.text(min_size=41, max_size=200))
@settings(max_examples=200)
def test_property_12_long_names_are_truncated(method_name):
    """
    **Validates: Requirements 5.3**

    For any method name exceeding 40 characters, the display SHALL truncate
    to the first 37 characters of the original name followed by "...".
    The total display is "ƒ " + first_37_chars + "..." = 42 characters.
    """
    result = format_method_display_name(method_name)

    # Must end with "..."
    assert result.endswith("..."), (
        f"Long method name (len={len(method_name)}) must be truncated with '...'. "
        f"Got: {result!r}"
    )

    # Total length must be exactly 42: "ƒ " (2) + 37 chars + "..." (3) = 42
    assert len(result) == 42, (
        f"Truncated display name must be exactly 42 chars. "
        f"Got length={len(result)}, result={result!r}"
    )

    # The content between "ƒ " and "..." must be the first 37 chars of input
    expected = "ƒ " + method_name[:37] + "..."
    assert result == expected, (
        f"Expected: {expected!r}, Got: {result!r}"
    )


@given(method_name=st.text(min_size=0, max_size=40))
@settings(max_examples=200)
def test_property_12_short_names_are_not_truncated(method_name):
    """
    **Validates: Requirements 5.3**

    For any method name of 40 characters or fewer, the display SHALL be
    exactly "ƒ " + the full method name without any truncation.
    """
    result = format_method_display_name(method_name)

    expected = "ƒ " + method_name
    assert result == expected, (
        f"Short method name (len={len(method_name)}) must not be truncated. "
        f"Expected: {expected!r}, Got: {result!r}"
    )

    # Must NOT end with "..." unless the original method name ends with "..."
    if not method_name.endswith("..."):
        assert not result.endswith("..."), (
            f"Short method name should not have truncation indicator. "
            f"Got: {result!r}"
        )


@given(method_name=method_name_strategy)
@settings(max_examples=200)
def test_property_12_truncated_display_never_exceeds_max_length(method_name):
    """
    **Validates: Requirements 5.3**

    For any method name, the display name SHALL never exceed 42 characters
    when truncated (i.e., "ƒ " prefix (2) + 37 chars + "..." (3) = 42).
    For non-truncated names (input <= 40 chars), the max is "ƒ " (2) + 40 = 42.
    Therefore, the display name is always at most 42 characters.
    """
    result = format_method_display_name(method_name)

    max_display_length = 42  # "ƒ " (2 chars) + 40 chars max display
    assert len(result) <= max_display_length, (
        f"Display name length {len(result)} exceeds maximum of {max_display_length}. "
        f"Result: {result!r}, method_name (len={len(method_name)}): {method_name!r}"
    )
