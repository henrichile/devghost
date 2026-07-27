# Feature: precision-analysis-enhancements, Property 1: Config Classification Correctness
# Feature: precision-analysis-enhancements, Property 2: Classification Priority — Config Over Others Except Controller
"""
Property 1: Config Classification Correctness

For any filename or class_name (case-insensitive) containing any of the substrings
"config", "configuration", "connection", "database", "appconfig", "dbconfig", or
"settings", the classification function SHALL return NodeType "Config". Similarly,
for any filename containing "init", "bootstrap", "setup", or "startup" (without
config substrings), the classification SHALL return "Utility".

**Validates: Requirements 1.1, 1.2**

Property 2: Classification Priority — Config Over Others Except Controller

For any filename that matches both a Config pattern and any other non-Controller
pattern (Route, Service, Middleware, Repository, Utility), the classification
function SHALL assign "Config". For any filename matching both Config and Controller
patterns, the classification SHALL assign "Controller". For any filename matching
both Config and Init patterns, the classification SHALL assign "Config".

**Validates: Requirements 1.3, 1.4, 1.5**
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from dev_ghost_parser.code_flow_analyzer import (
    _classify_for_file,
    _CONFIG_PATTERNS,
    _INIT_PATTERNS,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Config substrings that should trigger "Config" classification
CONFIG_SUBSTRINGS = ["config", "configuration", "connection", "database", "appconfig", "dbconfig", "settings"]

# Init substrings that should trigger "Utility" classification (when no Config match)
INIT_SUBSTRINGS = ["init", "bootstrap", "setup", "startup"]

# Non-Controller patterns that overlap with other types (used for priority tests)
# These are substrings that match Route, Service, Middleware, Repository via fnmatch
ROUTE_TRIGGERS = ["Route", "router", "routes"]
SERVICE_TRIGGERS = ["Service", "Manager", "Handler", "Provider"]
MIDDLEWARE_TRIGGERS = ["Middleware", "Filter", "Interceptor", "Guard"]
REPOSITORY_TRIGGERS = ["Repository", "Repo", "Dao", "DAO", "Mapper", "Store"]

# Controller triggers (Controller wins over Config)
CONTROLLER_TRIGGERS = ["Controller", "Endpoint", "Resource"]

# File extensions for generating realistic filenames
EXTENSIONS = [".py", ".ts", ".java", ".js", ".go", ".rs", ".cs", ".rb", ".tsx", ".php"]

# Strategy: generate a random prefix/suffix for filenames
_identifier_chars = st.characters(
    whitelist_categories=("Lu", "Ll", "Nd"),
    whitelist_characters="_-",
)
identifier = st.text(alphabet=_identifier_chars, min_size=0, max_size=15)


def filename_with_substring(substring: str) -> st.SearchStrategy[str]:
    """Generate a filename containing *substring* with random prefix/suffix and extension."""
    return st.builds(
        lambda prefix, suffix, ext: f"{prefix}{substring}{suffix}{ext}",
        prefix=identifier,
        suffix=identifier,
        ext=st.sampled_from(EXTENSIONS),
    )


# Strategy for Config filenames: pick a config substring and embed it
config_filename = st.one_of(
    *[filename_with_substring(sub) for sub in CONFIG_SUBSTRINGS]
)

# Strategy for Init filenames (must NOT contain any config substring)
init_filename = st.one_of(
    *[filename_with_substring(sub) for sub in INIT_SUBSTRINGS]
)

# Strategy for case variations of a config pattern
config_case_variants = st.builds(
    lambda sub, prefix, suffix, ext, case_fn: f"{prefix}{case_fn(sub)}{suffix}{ext}",
    sub=st.sampled_from(CONFIG_SUBSTRINGS),
    prefix=identifier,
    suffix=identifier,
    ext=st.sampled_from(EXTENSIONS),
    case_fn=st.sampled_from([str.lower, str.upper, str.title, str.swapcase]),
)


# ---------------------------------------------------------------------------
# Property 1: Config Classification Correctness
# ---------------------------------------------------------------------------


@given(filename=config_filename)
@settings(max_examples=200)
def test_property_1_config_pattern_in_filename_classifies_as_config(filename):
    """
    **Validates: Requirements 1.1, 1.2**

    For any filename containing a Config pattern substring (case-insensitive),
    _classify_for_file SHALL return "Config".
    """
    result = _classify_for_file(filename, None)
    assert result == "Config", (
        f"Expected 'Config' for filename '{filename}', got '{result}'"
    )


@given(
    config_sub=st.sampled_from(CONFIG_SUBSTRINGS),
    prefix=identifier,
    suffix=identifier,
    ext=st.sampled_from(EXTENSIONS),
)
@settings(max_examples=200)
def test_property_1_config_pattern_in_class_name_classifies_as_config(
    config_sub, prefix, suffix, ext
):
    """
    **Validates: Requirements 1.1, 1.2**

    For any class_name containing a Config pattern substring (case-insensitive),
    _classify_for_file SHALL return "Config" regardless of filename.
    """
    class_name = f"{prefix}{config_sub}{suffix}"
    # Filename without config pattern to isolate class_name behavior
    filename = f"some_file{ext}"
    result = _classify_for_file(filename, class_name)
    assert result == "Config", (
        f"Expected 'Config' for class_name '{class_name}' (filename '{filename}'), got '{result}'"
    )


@given(filename=config_case_variants)
@settings(max_examples=200)
def test_property_1_config_classification_is_case_insensitive(filename):
    """
    **Validates: Requirements 1.1, 1.2**

    Config pattern matching is case-insensitive: filenames with any case
    variant of config substrings SHALL classify as "Config".
    """
    result = _classify_for_file(filename, None)
    assert result == "Config", (
        f"Expected 'Config' for case-variant filename '{filename}', got '{result}'"
    )


@given(
    init_sub=st.sampled_from(INIT_SUBSTRINGS),
    prefix=identifier,
    suffix=identifier,
    ext=st.sampled_from(EXTENSIONS),
)
@settings(max_examples=200)
def test_property_1_init_pattern_without_config_classifies_as_utility(
    init_sub, prefix, suffix, ext
):
    """
    **Validates: Requirements 1.1, 1.2**

    For any filename containing an Init pattern but NOT containing a Config
    pattern, _classify_for_file SHALL return "Utility".
    """
    filename = f"{prefix}{init_sub}{suffix}{ext}"
    # Ensure no config pattern is present
    filename_lower = filename.lower()
    assume(not any(cfg in filename_lower for cfg in CONFIG_SUBSTRINGS))
    result = _classify_for_file(filename, None)
    assert result == "Utility", (
        f"Expected 'Utility' for init-only filename '{filename}', got '{result}'"
    )


# ---------------------------------------------------------------------------
# Property 2: Classification Priority — Config Over Others Except Controller
# ---------------------------------------------------------------------------


@given(
    config_sub=st.sampled_from(CONFIG_SUBSTRINGS),
    route_trigger=st.sampled_from(ROUTE_TRIGGERS),
    ext=st.sampled_from(EXTENSIONS),
)
@settings(max_examples=150)
def test_property_2_config_over_route(config_sub, route_trigger, ext):
    """
    **Validates: Requirements 1.3, 1.4, 1.5**

    For any filename matching both a Config pattern and a Route pattern,
    the classification SHALL assign "Config" (Config wins over Route).
    """
    filename = f"{route_trigger}{config_sub}{ext}"
    result = _classify_for_file(filename, None)
    assert result == "Config", (
        f"Expected 'Config' for '{filename}' (Config+Route overlap), got '{result}'"
    )


@given(
    config_sub=st.sampled_from(CONFIG_SUBSTRINGS),
    service_trigger=st.sampled_from(SERVICE_TRIGGERS),
    ext=st.sampled_from(EXTENSIONS),
)
@settings(max_examples=150)
def test_property_2_config_over_service(config_sub, service_trigger, ext):
    """
    **Validates: Requirements 1.3, 1.4, 1.5**

    For any filename matching both a Config pattern and a Service pattern,
    the classification SHALL assign "Config" (Config wins over Service).
    """
    filename = f"{service_trigger}{config_sub}{ext}"
    result = _classify_for_file(filename, None)
    assert result == "Config", (
        f"Expected 'Config' for '{filename}' (Config+Service overlap), got '{result}'"
    )


@given(
    config_sub=st.sampled_from(CONFIG_SUBSTRINGS),
    middleware_trigger=st.sampled_from(MIDDLEWARE_TRIGGERS),
    ext=st.sampled_from(EXTENSIONS),
)
@settings(max_examples=150)
def test_property_2_config_over_middleware(config_sub, middleware_trigger, ext):
    """
    **Validates: Requirements 1.3, 1.4, 1.5**

    For any filename matching both a Config pattern and a Middleware pattern,
    the classification SHALL assign "Config" (Config wins over Middleware).
    """
    filename = f"{middleware_trigger}{config_sub}{ext}"
    result = _classify_for_file(filename, None)
    assert result == "Config", (
        f"Expected 'Config' for '{filename}' (Config+Middleware overlap), got '{result}'"
    )


@given(
    config_sub=st.sampled_from(CONFIG_SUBSTRINGS),
    repo_trigger=st.sampled_from(REPOSITORY_TRIGGERS),
    ext=st.sampled_from(EXTENSIONS),
)
@settings(max_examples=150)
def test_property_2_config_over_repository(config_sub, repo_trigger, ext):
    """
    **Validates: Requirements 1.3, 1.4, 1.5**

    For any filename matching both a Config pattern and a Repository pattern,
    the classification SHALL assign "Config" (Config wins over Repository).
    """
    filename = f"{repo_trigger}{config_sub}{ext}"
    result = _classify_for_file(filename, None)
    assert result == "Config", (
        f"Expected 'Config' for '{filename}' (Config+Repository overlap), got '{result}'"
    )


@given(
    config_sub=st.sampled_from(CONFIG_SUBSTRINGS),
    controller_trigger=st.sampled_from(CONTROLLER_TRIGGERS),
    ext=st.sampled_from(EXTENSIONS),
)
@settings(max_examples=150)
def test_property_2_controller_over_config(config_sub, controller_trigger, ext):
    """
    **Validates: Requirements 1.3, 1.4, 1.5**

    For any filename matching both a Config pattern and a Controller pattern,
    the classification SHALL assign "Controller" (Controller wins over Config).
    """
    filename = f"{controller_trigger}{config_sub}{ext}"
    result = _classify_for_file(filename, None)
    assert result == "Controller", (
        f"Expected 'Controller' for '{filename}' (Config+Controller overlap), got '{result}'"
    )


@given(
    config_sub=st.sampled_from(CONFIG_SUBSTRINGS),
    init_sub=st.sampled_from(INIT_SUBSTRINGS),
    ext=st.sampled_from(EXTENSIONS),
)
@settings(max_examples=150)
def test_property_2_config_over_init(config_sub, init_sub, ext):
    """
    **Validates: Requirements 1.3, 1.4, 1.5**

    For any filename matching both Config and Init patterns,
    the classification SHALL assign "Config" (Config wins over Init/Utility).
    """
    filename = f"{init_sub}{config_sub}{ext}"
    result = _classify_for_file(filename, None)
    assert result == "Config", (
        f"Expected 'Config' for '{filename}' (Config+Init overlap), got '{result}'"
    )


@given(
    config_sub=st.sampled_from(CONFIG_SUBSTRINGS),
    service_trigger=st.sampled_from(SERVICE_TRIGGERS),
    ext=st.sampled_from(EXTENSIONS),
)
@settings(max_examples=100)
def test_property_2_config_over_service_via_class_name(config_sub, service_trigger, ext):
    """
    **Validates: Requirements 1.3, 1.4, 1.5**

    For any class_name matching a Config pattern, even when the filename matches
    a Service pattern, the classification SHALL assign "Config".
    """
    filename = f"{service_trigger}Something{ext}"
    class_name = f"My{config_sub.title()}Class"
    result = _classify_for_file(filename, class_name)
    assert result == "Config", (
        f"Expected 'Config' for class '{class_name}' (file '{filename}'), got '{result}'"
    )


@given(
    config_sub=st.sampled_from(CONFIG_SUBSTRINGS),
    controller_trigger=st.sampled_from(CONTROLLER_TRIGGERS),
    ext=st.sampled_from(EXTENSIONS),
)
@settings(max_examples=100)
def test_property_2_controller_over_config_via_class_name(config_sub, controller_trigger, ext):
    """
    **Validates: Requirements 1.3, 1.4, 1.5**

    For any filename with a Config pattern and a class_name matching Controller,
    the classification SHALL assign "Controller".
    """
    filename = f"my_{config_sub}_file{ext}"
    class_name = f"My{controller_trigger}"
    result = _classify_for_file(filename, class_name)
    assert result == "Controller", (
        f"Expected 'Controller' for class '{class_name}' (config file '{filename}'), got '{result}'"
    )
