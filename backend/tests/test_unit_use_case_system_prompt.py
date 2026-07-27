"""
Unit tests for Artifacts_Generator._build_use_case_system_prompt().

Verifies the system prompt contains key instructions for LLM use case generation.
Requirements: 1.6, 2.6, 6.1, 6.2, 6.3
"""

from dev_ghost_parser.artifacts_generator import Artifacts_Generator


class TestSystemPromptContainsKeyInstructions:
    """Verify _build_use_case_system_prompt() contains required formatting instructions."""

    def setup_method(self):
        self.generator = Artifacts_Generator()
        self.prompt = self.generator._build_use_case_system_prompt()

    def test_system_prompt_contains_espanol(self):
        """The prompt must instruct the LLM to generate content in Spanish."""
        assert "español" in self.prompt

    def test_system_prompt_contains_como_rol(self):
        """The prompt must include the 'Como [rol]' user story format instruction."""
        assert "Como" in self.prompt
        assert "rol" in self.prompt

    def test_system_prompt_contains_precondiciones(self):
        """The prompt must include 'Precondiciones' as a required section."""
        assert "Precondiciones" in self.prompt

    def test_system_prompt_contains_flujo_principal(self):
        """The prompt must include 'Flujo Principal' as a required section."""
        assert "Flujo Principal" in self.prompt

    def test_system_prompt_contains_entre_3_y_10_pasos(self):
        """The prompt must specify between 3 and 10 steps for the main flow."""
        assert "entre 3 y 10 pasos" in self.prompt

    def test_system_prompt_contains_flujos_alternativos(self):
        """The prompt must include 'Flujos Alternativos' as a required section."""
        assert "Flujos Alternativos" in self.prompt

    def test_system_prompt_markdown_only_no_code_blocks(self):
        """The prompt must instruct the LLM to respond in Markdown only, no code blocks."""
        assert "sin bloques de código" in self.prompt
