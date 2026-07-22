# Feature: dev-ghost-parser, Property 10: Orden de validación de entrada
"""
Property 10: Orden de validación de entrada
============================================
Validates: Requisito 5.5

For any combination of "error conditions":
  - If path is None or empty string     → errors[0].message == "A Target_Codebase path is required."
  - If path is non-empty but not found  → errors[0].message contains "was not found"
  - If path points to a file (not dir)  → errors[0].message contains "is not a directory"

The mandatory validation order is:
  (1) missing/empty  →  (2) path not found  →  (3) permission denied  →  (4) not a directory

The property under test guarantees that the *highest-priority* failing check
dominates: when condition N is true, only error N is returned — never an error
from condition N+1, N+2, …
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from dev_ghost_parser import DevGhost_Parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse(result: bytes) -> dict:
    """Decode the UTF-8 bytes returned by DevGhost_Parser.analyze() into a dict."""
    return json.loads(result.decode("utf-8"))


def _first_message(result: bytes) -> str:
    """Return the message of the first error entry in the result."""
    data = _parse(result)
    return data["errors"][0]["message"]


# ---------------------------------------------------------------------------
# Property 10a — Missing / empty path always yields the "required" error
# ---------------------------------------------------------------------------

@given(path=st.one_of(st.just(None), st.just("")))
@settings(max_examples=100)
def test_property_10a_missing_empty_path_required_error(path):
    """
    **Validates: Requisito 5.5 — Check 1 dominates all lower-priority checks**

    When path is None or an empty string the parser MUST return the
    "A Target_Codebase path is required." error regardless of any filesystem state.
    """
    parser = DevGhost_Parser()
    result = parser.analyze(path)
    data = _parse(result)

    # The response must be a JSON object with only the 'errors' key
    assert "errors" in data, "Response must contain 'errors' key"
    assert len(data["errors"]) == 1, "Response must have exactly one error"

    msg = data["errors"][0]["message"]
    assert msg == "A Target_Codebase path is required.", (
        f"Expected 'A Target_Codebase path is required.' but got: {msg!r}"
    )


# ---------------------------------------------------------------------------
# Property 10b — Non-existent paths always yield the "was not found" error
# ---------------------------------------------------------------------------

# Strategy: generate text of at least 1 char and filter to paths that
# genuinely do not exist. To avoid slowness from filesystem probing we use
# a fixed-prefix that is very unlikely to exist on any machine.
_NONEXISTENT_PREFIX = "/this_path_definitely_does_not_exist_devghost"


def _nonexistent_path(suffix: str) -> str:
    """Build a path guaranteed not to exist by prepending a sentinel prefix."""
    return _NONEXISTENT_PREFIX + "/" + suffix.replace("\x00", "")


@given(
    suffix=st.text(
        alphabet=st.characters(blacklist_categories=("Cc",), blacklist_characters="/\\:\x00"),
        min_size=1,
        max_size=64,
    )
)
@settings(max_examples=100)
def test_property_10b_nonexistent_path_not_found_error(suffix):
    """
    **Validates: Requisito 5.5 — Check 2 dominates checks 3 and 4**

    When path is non-empty but does not exist, the parser MUST return an
    error whose message contains "was not found", NOT a permission or
    "not a directory" error.
    """
    path = _nonexistent_path(suffix)
    assume(not os.path.exists(path))  # safety guard

    parser = DevGhost_Parser()
    result = parser.analyze(path)
    data = _parse(result)

    assert "errors" in data
    assert len(data["errors"]) == 1

    msg = data["errors"][0]["message"]
    assert "was not found" in msg, (
        f"Expected 'was not found' in error message but got: {msg!r}"
    )
    # Must NOT surface a lower-priority error
    assert "is not a directory" not in msg
    assert "Permission denied" not in msg


# ---------------------------------------------------------------------------
# Property 10c — Path pointing to a file (not a directory) yields the
#                "is not a directory" error (checks 1–3 all pass)
# ---------------------------------------------------------------------------

@given(content=st.binary(min_size=0, max_size=128))
@settings(max_examples=100)
def test_property_10c_file_path_not_directory_error(content):
    """
    **Validates: Requisito 5.5 — Check 4 fires when checks 1–3 pass**

    When path is non-empty, exists, is readable, and points to a regular
    file, the parser MUST return an error whose message contains
    "is not a directory".
    """
    parser = DevGhost_Parser()

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = parser.analyze(tmp_path)
        data = _parse(result)

        assert "errors" in data
        assert len(data["errors"]) == 1

        msg = data["errors"][0]["message"]
        assert "is not a directory" in msg, (
            f"Expected 'is not a directory' in error message but got: {msg!r}"
        )
        # Must NOT surface higher-priority errors that do not apply here
        assert "required" not in msg.lower()
        assert "was not found" not in msg
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Property 10d — Permission denied error dominates "not a directory" check
#                (skip on Windows: requires admin to set no-read permissions)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Setting no-read permissions requires administrator rights on Windows",
)
@given(content=st.binary(min_size=0, max_size=128))
@settings(max_examples=50)
def test_property_10d_permission_denied_dominates_not_a_directory(content):
    """
    **Validates: Requisito 5.5 — Check 3 dominates Check 4**

    When path exists and is a directory but the process lacks read permission,
    the parser MUST return a "Permission denied" error — NOT a "not a
    directory" error — confirming Check 3 fires before Check 4.
    """
    parser = DevGhost_Parser()

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Remove read (and execute) permissions from the directory
        os.chmod(tmp_dir, 0o000)
        try:
            result = parser.analyze(tmp_dir)
            data = _parse(result)

            assert "errors" in data
            assert len(data["errors"]) == 1

            msg = data["errors"][0]["message"]
            assert "Permission denied" in msg, (
                f"Expected 'Permission denied' in error message but got: {msg!r}"
            )
            assert "is not a directory" not in msg
        finally:
            # Restore permissions so TemporaryDirectory cleanup can proceed
            os.chmod(tmp_dir, 0o700)


# ---------------------------------------------------------------------------
# Property 10e — Empty string dominates any filesystem state
#                (even if a path named "" somehow existed, check 1 fires first)
# ---------------------------------------------------------------------------

@given(irrelevant=st.integers())
@settings(max_examples=100)
def test_property_10e_empty_string_always_triggers_check1(irrelevant):
    """
    **Validates: Requisito 5.5 — Check 1 is unconditional for empty/None**

    No matter what other state exists in the system, an empty-string path
    always returns the "required" error.  The ``irrelevant`` integer parameter
    is included to satisfy the @given requirement and confirm the property
    holds across many generated inputs.
    """
    parser = DevGhost_Parser()
    result = parser.analyze("")
    msg = _first_message(result)
    assert msg == "A Target_Codebase path is required."


# ---------------------------------------------------------------------------
# Property 10f — Non-existent path dominates "file vs directory" distinction
# ---------------------------------------------------------------------------

@given(
    name=st.text(
        alphabet=st.characters(
            blacklist_categories=("Cc",),
            blacklist_characters="/\\:\x00",
        ),
        min_size=1,
        max_size=32,
    )
)
@settings(max_examples=100)
def test_property_10f_nonexistent_path_dominates_file_check(name):
    """
    **Validates: Requisito 5.5 — Check 2 dominates Check 4**

    A path that points to a non-existent file (not a directory) must trigger
    "was not found", not "is not a directory".  This confirms Check 2 fires
    before Check 4 even when the path name implies it could be a file.
    """
    # Build a path that looks like a regular file but does not exist
    path = _NONEXISTENT_PREFIX + "/files/" + name + ".txt"
    assume(not os.path.exists(path))

    parser = DevGhost_Parser()
    result = parser.analyze(path)
    data = _parse(result)

    assert "errors" in data
    assert len(data["errors"]) == 1

    msg = data["errors"][0]["message"]
    assert "was not found" in msg, (
        f"Expected 'was not found' but got: {msg!r}"
    )
    assert "is not a directory" not in msg
