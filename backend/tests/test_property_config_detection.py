"""
Property 11: Configuration file detection

For any directory structure that contains one or more files from the defined config
file list (package.json, pyproject.toml, Dockerfile, etc.) at the root or first-level
subdirectories, the System Reporter SHALL detect and return all of them; and for each
detected config file, the extracted TechStack SHALL contain at least one entry with a
valid category.

Validates: Requirements 6.1, 6.2
"""

import os
import shutil
import tempfile

from hypothesis import given, settings, strategies as st

from dev_ghost_parser.agents.system_reporter_agent import (
    ConfigFileInfo,
    SystemReporterAgent,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIG_FILES = [
    "package.json",
    "pyproject.toml",
    "Dockerfile",
    "Makefile",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "requirements.txt",
    "composer.json",
    "Gemfile",
    "build.gradle",
]

VALID_CATEGORIES = {"language", "framework", "database", "infrastructure"}

# Minimal valid content for each config file so _extract_tech_stack can parse them
CONFIG_FILE_CONTENT = {
    "package.json": '{"name": "test-project", "dependencies": {"express": "^4.0.0"}}',
    "pyproject.toml": '[project]\nname = "test"\ndependencies = ["fastapi"]',
    "Dockerfile": "FROM python:3.11\nRUN pip install fastapi",
    "Makefile": "all:\n\techo hello",
    "Cargo.toml": '[package]\nname = "test"\nversion = "0.1.0"',
    "go.mod": "module example.com/test\n\ngo 1.21",
    "pom.xml": "<project><modelVersion>4.0.0</modelVersion></project>",
    "requirements.txt": "flask>=2.0\nredis>=4.0",
    "composer.json": '{"require": {"laravel/framework": "^10.0"}}',
    "Gemfile": 'source "https://rubygems.org"\ngem "rails"',
    "build.gradle": 'plugins {\n    id "java"\n}',
}


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate a non-empty subset of config files
config_subset_strategy = st.lists(
    st.sampled_from(CONFIG_FILES),
    min_size=1,
    max_size=len(CONFIG_FILES),
    unique=True,
)

# Generate subdirectory names (simple lowercase names, no dots to avoid hidden dirs)
subdir_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll",), whitelist_characters="_"),
    min_size=1,
    max_size=10,
).filter(lambda s: not s.startswith("."))


# Composite strategy: generate a placement plan (root vs subdir) for config files
@st.composite
def config_placement_strategy(draw):
    """Generate a plan for placing config files in root and/or subdirectories.

    Returns a list of (config_filename, relative_dir) tuples where relative_dir
    is either "" (root) or a first-level subdirectory name.
    """
    config_files = draw(config_subset_strategy)
    placements = []

    for config_file in config_files:
        # Decide: place in root or a subdirectory
        in_subdir = draw(st.booleans())
        if in_subdir:
            subdir = draw(subdir_name_strategy)
            placements.append((config_file, subdir))
        else:
            placements.append((config_file, ""))

    return placements


# ---------------------------------------------------------------------------
# Property Test
# ---------------------------------------------------------------------------


class TestProperty11ConfigFileDetection:
    """Feature: agent-streaming-reporting, Property 11: Configuration file detection"""

    @settings(max_examples=100)
    @given(placements=config_placement_strategy())
    def test_property_11_all_config_files_detected(self, placements):
        """All placed config files are detected by _scan_config_files (no false negatives).

        **Validates: Requirements 6.1, 6.2**
        """
        # Create a temporary directory structure
        tmp_dir = tempfile.mkdtemp()
        try:
            # Place config files according to the generated plan
            placed_paths = set()
            for config_file, rel_dir in placements:
                if rel_dir:
                    dir_path = os.path.join(tmp_dir, rel_dir)
                    os.makedirs(dir_path, exist_ok=True)
                else:
                    dir_path = tmp_dir

                file_path = os.path.join(dir_path, config_file)
                content = CONFIG_FILE_CONTENT.get(config_file, "")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                placed_paths.add(file_path)

            # Call _scan_config_files
            agent = SystemReporterAgent()
            detected = agent._scan_config_files(tmp_dir)

            # Verify no false negatives: all placed files are detected
            detected_paths = {cfg.path for cfg in detected}
            for placed_path in placed_paths:
                assert placed_path in detected_paths, (
                    f"Config file at {placed_path} was not detected. "
                    f"Detected: {detected_paths}"
                )

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @settings(max_examples=100)
    @given(placements=config_placement_strategy())
    def test_property_11_detected_files_produce_valid_tech_stack(self, placements):
        """For each detected config file, _extract_tech_stack produces at least one
        entry with a valid category.

        **Validates: Requirements 6.1, 6.2**
        """
        # Create a temporary directory structure
        tmp_dir = tempfile.mkdtemp()
        try:
            # Place config files
            for config_file, rel_dir in placements:
                if rel_dir:
                    dir_path = os.path.join(tmp_dir, rel_dir)
                    os.makedirs(dir_path, exist_ok=True)
                else:
                    dir_path = tmp_dir

                file_path = os.path.join(dir_path, config_file)
                content = CONFIG_FILE_CONTENT.get(config_file, "")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)

            # Scan and extract
            agent = SystemReporterAgent()
            detected = agent._scan_config_files(tmp_dir)

            # Extract tech stack from all detected files
            tech_stack = agent._extract_tech_stack(detected)

            # With at least one config file placed, the tech stack must have
            # at least one entry with a valid category
            assert len(tech_stack.entries) >= 1, (
                f"Expected at least 1 TechStack entry for config files "
                f"{[p[0] for p in placements]}, got {len(tech_stack.entries)}"
            )

            # Every entry must have a valid category
            for entry in tech_stack.entries:
                assert entry.category in VALID_CATEGORIES, (
                    f"TechStack entry '{entry.name}' has invalid category "
                    f"'{entry.category}'. Valid: {VALID_CATEGORIES}"
                )

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
