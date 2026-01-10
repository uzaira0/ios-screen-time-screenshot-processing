"""Tests for configuration models."""

from __future__ import annotations

import pytest

from phi_detector_remover.core.config import (
    AllowlistConfig,
    DenylistConfig,
    OCRConfig,
    PHIPipelineConfig,
    PresidioConfig,
    RedactionConfig,
    RegexConfig,
)


class TestAllowlistConfig:
    """Tests for allowlist configuration."""

    def test_default_allowlist(self):
        """Test default allowlist contains common app names."""
        config = AllowlistConfig()

        assert "Safari" in config.app_names
        assert "Instagram" in config.app_names
        assert "Screen Time" in config.app_names

    def test_should_ignore_app_names(self):
        """Test that app names are ignored."""
        config = AllowlistConfig()

        assert config.should_ignore("Safari") is True
        assert config.should_ignore("safari") is True  # Case insensitive
        assert config.should_ignore("Instagram") is True

    def test_should_not_ignore_phi(self):
        """Test that PHI is not ignored."""
        config = AllowlistConfig()

        assert config.should_ignore("John Doe") is False
        assert config.should_ignore("john@email.com") is False

    def test_custom_terms(self):
        """Test adding custom terms to ignore."""
        config = AllowlistConfig(custom_terms={"MyCustomApp", "StudyName"})

        assert config.should_ignore("MyCustomApp") is True
        assert config.should_ignore("StudyName") is True

    def test_ignore_patterns(self):
        """Test regex pattern ignoring."""
        config = AllowlistConfig(
            ignore_patterns=[r"v\d+\.\d+\.\d+"]  # Version numbers
        )

        assert config.should_ignore("v1.2.3") is True
        assert config.should_ignore("v10.0.0") is True

    def test_get_all_terms(self):
        """Test combining all terms."""
        config = AllowlistConfig(custom_terms={"Custom1", "Custom2"})

        all_terms = config.get_all_terms()

        assert "custom1" in all_terms  # Lowercase
        assert "safari" in all_terms


class TestDenylistConfig:
    """Tests for denylist configuration."""

    def test_default_device_patterns(self):
        """Test default device name patterns."""
        config = DenylistConfig()

        assert len(config.device_name_patterns) > 0

    def test_default_wifi_patterns(self):
        """Test default WiFi patterns."""
        config = DenylistConfig()

        assert len(config.wifi_patterns) > 0

    def test_get_all_patterns(self):
        """Test getting all denylist patterns."""
        config = DenylistConfig(custom_patterns=[r"CUSTOM-\d+"])

        all_patterns = config.get_all_patterns()

        # Should include device, wifi, airdrop, and custom
        assert len(all_patterns) >= 1
        assert r"CUSTOM-\d+" in all_patterns


class TestOCRConfig:
    """Tests for OCR configuration."""

    def test_default_config(self):
        """Test default OCR config values."""
        config = OCRConfig()

        assert config.engine == "tesseract"
        assert config.language == "eng"
        assert config.psm == 6
        assert config.oem == 3


class TestPresidioConfig:
    """Tests for Presidio configuration."""

    def test_default_entities(self):
        """Test default entity types."""
        config = PresidioConfig()

        assert "PERSON" in config.entities
        assert "EMAIL_ADDRESS" in config.entities
        assert "PHONE_NUMBER" in config.entities

    def test_score_threshold(self):
        """Test default score threshold."""
        config = PresidioConfig()

        assert config.score_threshold == 0.7


class TestRegexConfig:
    """Tests for regex configuration."""

    def test_default_patterns_enabled(self):
        """Test default patterns are enabled."""
        config = RegexConfig()

        assert config.use_default_patterns is True

    def test_custom_patterns(self):
        """Test custom pattern addition."""
        config = RegexConfig(custom_patterns={"CUSTOM_ID": r"CID-\d{6}"})

        assert "CUSTOM_ID" in config.custom_patterns


class TestRedactionConfig:
    """Tests for redaction configuration."""

    def test_default_method(self):
        """Test default redaction method."""
        config = RedactionConfig()

        assert config.method == "redbox"

    def test_default_redbox_color(self):
        """Test default redbox color is red in BGR."""
        config = RedactionConfig()

        assert config.redbox_color == (0, 0, 255)  # Red in BGR

    def test_padding_validation(self):
        """Test padding must be non-negative."""
        with pytest.raises(ValueError):
            RedactionConfig(padding=-5)

    def test_pixelate_block_size_validation(self):
        """Test pixelate block size must be positive."""
        with pytest.raises(ValueError):
            RedactionConfig(pixelate_block_size=0)


class TestPHIPipelineConfig:
    """Tests for pipeline configuration."""

    def test_default_config(self):
        """Test default pipeline configuration."""
        config = PHIPipelineConfig()

        assert config.parallel is True
        assert config.merge_nearby is True
        assert config.min_bbox_area == 100
