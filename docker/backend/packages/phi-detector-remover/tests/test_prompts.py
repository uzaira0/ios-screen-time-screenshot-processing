"""Tests for prompt templates."""

from __future__ import annotations

import pytest

from phi_detector_remover.core.prompts import (
    PROMPTS,
    PHIDetectionPrompt,
    PromptStyle,
    get_prompt,
)


class TestPromptStyle:
    """Tests for PromptStyle enum."""

    def test_style_values(self):
        """Test enum values are strings."""
        assert PromptStyle.HIPAA_STRICT == "hipaa_strict"
        assert PromptStyle.BALANCED == "balanced"
        assert PromptStyle.CONSERVATIVE == "conservative"

    def test_style_is_string(self):
        """Test that styles can be used as strings."""
        style = PromptStyle.BALANCED
        assert f"mode: {style}" == "mode: balanced"


class TestPHIDetectionPrompt:
    """Tests for PHIDetectionPrompt class."""

    def test_default_system_prompt(self):
        """Test default system prompt is set."""
        prompt = PHIDetectionPrompt()

        assert "PHI" in prompt.system_prompt
        assert "JSON" in prompt.system_prompt

    def test_default_positive_prompt(self):
        """Test default positive prompt (what to detect)."""
        prompt = PHIDetectionPrompt()

        assert len(prompt.positive_prompt) > 0
        assert any("name" in cat.lower() for cat in prompt.positive_prompt)
        assert any("email" in cat.lower() for cat in prompt.positive_prompt)

    def test_default_negative_prompt(self):
        """Test default negative prompt (what to ignore)."""
        prompt = PHIDetectionPrompt()

        assert len(prompt.negative_prompt) > 0
        assert any("app" in cat.lower() for cat in prompt.negative_prompt)
        assert any("ui" in cat.lower() for cat in prompt.negative_prompt)

    def test_default_style(self):
        """Test default style is balanced."""
        prompt = PHIDetectionPrompt()

        assert prompt.style == PromptStyle.BALANCED

    def test_build_full_prompt_text_mode(self):
        """Test building prompt for text analysis."""
        prompt = PHIDetectionPrompt()
        test_text = "John's iPhone - Screen Time Report"

        full_prompt = prompt.build_full_prompt(content=test_text, is_vision=False)

        assert "DETECT" in full_prompt
        assert "IGNORE" in full_prompt
        assert test_text in full_prompt
        assert "Text to Analyze" in full_prompt

    def test_build_full_prompt_vision_mode(self):
        """Test building prompt for vision analysis."""
        prompt = PHIDetectionPrompt()

        full_prompt = prompt.build_full_prompt(is_vision=True)

        assert "DETECT" in full_prompt
        assert "IGNORE" in full_prompt
        assert "Vision Instructions" in full_prompt
        assert "Scan the entire image" in full_prompt

    def test_build_full_prompt_hipaa_style(self):
        """Test HIPAA strict style in prompt."""
        prompt = PHIDetectionPrompt(style=PromptStyle.HIPAA_STRICT)

        full_prompt = prompt.build_full_prompt()

        assert "STRICT" in full_prompt
        assert "HIPAA" in full_prompt

    def test_build_full_prompt_conservative_style(self):
        """Test conservative style in prompt."""
        prompt = PHIDetectionPrompt(style=PromptStyle.CONSERVATIVE)

        full_prompt = prompt.build_full_prompt()

        assert "CONSERVATIVE" in full_prompt
        assert "High Precision" in full_prompt

    def test_with_positive_adds_category(self):
        """Test adding to positive prompt."""
        prompt = PHIDetectionPrompt()
        original_count = len(prompt.positive_prompt)

        new_prompt = prompt.with_positive("Study participant IDs in format EXAMPLE_STUDY-XXXX")

        assert len(new_prompt.positive_prompt) == original_count + 1
        assert "EXAMPLE_STUDY-XXXX" in new_prompt.positive_prompt[-1]
        # Original unchanged
        assert len(prompt.positive_prompt) == original_count

    def test_with_positive_multiple_categories(self):
        """Test adding multiple categories to positive prompt."""
        prompt = PHIDetectionPrompt()

        new_prompt = prompt.with_positive(
            "Category 1",
            "Category 2",
            "Category 3",
        )

        assert "Category 1" in new_prompt.positive_prompt
        assert "Category 2" in new_prompt.positive_prompt
        assert "Category 3" in new_prompt.positive_prompt

    def test_with_negative_adds_category(self):
        """Test adding to negative prompt."""
        prompt = PHIDetectionPrompt()
        original_count = len(prompt.negative_prompt)

        new_prompt = prompt.with_negative("Research app icons specific to this study")

        assert len(new_prompt.negative_prompt) == original_count + 1
        # Original unchanged
        assert len(prompt.negative_prompt) == original_count

    def test_with_system_overrides(self):
        """Test overriding system prompt."""
        prompt = PHIDetectionPrompt()
        custom_system = "You are a custom PHI detector."

        new_prompt = prompt.with_system(custom_system)

        assert new_prompt.system_prompt == custom_system
        assert prompt.system_prompt != custom_system  # Original unchanged

    def test_with_style_changes_style(self):
        """Test changing prompt style."""
        prompt = PHIDetectionPrompt(style=PromptStyle.BALANCED)

        new_prompt = prompt.with_style(PromptStyle.HIPAA_STRICT)

        assert new_prompt.style == PromptStyle.HIPAA_STRICT
        assert prompt.style == PromptStyle.BALANCED  # Original unchanged

    def test_chaining_methods(self):
        """Test method chaining."""
        prompt = (
            PHIDetectionPrompt()
            .with_positive("Custom positive 1")
            .with_negative("Custom negative 1")
            .with_style(PromptStyle.CONSERVATIVE)
        )

        assert "Custom positive 1" in prompt.positive_prompt
        assert "Custom negative 1" in prompt.negative_prompt
        assert prompt.style == PromptStyle.CONSERVATIVE

    def test_output_format_in_system_prompt(self):
        """Test output format is in system prompt."""
        prompt = PHIDetectionPrompt()

        assert "JSON" in prompt.system_prompt
        assert "entities" in prompt.system_prompt
        assert "confidence" in prompt.system_prompt


class TestGetPrompt:
    """Tests for get_prompt function."""

    def test_get_default_prompt(self):
        """Test getting default prompt."""
        prompt = get_prompt("default")

        assert isinstance(prompt, PHIDetectionPrompt)
        assert prompt.style == PromptStyle.BALANCED

    def test_get_hipaa_prompt(self):
        """Test getting HIPAA strict prompt."""
        prompt = get_prompt("hipaa")

        assert prompt.style == PromptStyle.HIPAA_STRICT

    def test_get_conservative_prompt(self):
        """Test getting conservative prompt."""
        prompt = get_prompt("conservative")

        assert prompt.style == PromptStyle.CONSERVATIVE

    def test_get_screen_time_prompt(self):
        """Test getting screen time specific prompt."""
        prompt = get_prompt("screen_time")

        # Screen time has specific positive/negative for that use case
        assert len(prompt.positive_prompt) > 0
        assert len(prompt.negative_prompt) > 0

    def test_get_messages_prompt(self):
        """Test getting messages specific prompt."""
        prompt = get_prompt("messages")

        assert any("contact" in cat.lower() for cat in prompt.positive_prompt)

    def test_get_unknown_prompt_raises(self):
        """Test getting unknown prompt raises error."""
        with pytest.raises(ValueError) as exc_info:
            get_prompt("nonexistent")

        assert "Unknown prompt" in str(exc_info.value)
        assert "Available:" in str(exc_info.value)

    def test_get_prompt_no_arg_defaults(self):
        """Test get_prompt with no argument returns default."""
        prompt = get_prompt()

        assert prompt.style == PromptStyle.BALANCED


class TestPromptPresets:
    """Tests for pre-built prompt configurations."""

    def test_all_presets_exist(self):
        """Test all expected presets exist."""
        expected = ["default", "hipaa", "conservative", "screen_time", "messages"]

        for name in expected:
            assert name in PROMPTS

    def test_all_presets_are_valid(self):
        """Test all presets are valid PHIDetectionPrompt instances."""
        for name, prompt in PROMPTS.items():
            assert isinstance(prompt, PHIDetectionPrompt), f"{name} is not valid"
            # Should be able to build prompts without error
            assert prompt.build_full_prompt()
            assert prompt.build_full_prompt(is_vision=True)
            assert prompt.build_full_prompt(content="test text")

    def test_presets_have_non_empty_prompts(self):
        """Test all presets have non-empty positive and negative prompts."""
        for name, prompt in PROMPTS.items():
            assert len(prompt.positive_prompt) > 0, f"{name} has empty positive"
            assert len(prompt.negative_prompt) > 0, f"{name} has empty negative"
