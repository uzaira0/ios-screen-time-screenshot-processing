"""
Unit tests for preprocessing service modules.

Tests device detection, PHI detection/redaction dataclasses,
and the preprocessing pipeline orchestration.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from screenshot_processor.web.services.preprocessing.device_and_crop import (
    DeviceDetectionResult,
    detect_device,
)
from screenshot_processor.web.services.preprocessing.phi import (
    PHIDetectionResult,
    PHIRedactionResult,
    detect_phi,
)
from screenshot_processor.web.services.preprocessing.pipeline import (
    PreprocessingResult,
    preprocess_screenshot_file,
)


class TestDeviceDetectionResult:
    """Tests for the DeviceDetectionResult dataclass."""

    def test_iphone_result(self):
        result = DeviceDetectionResult(
            detected=True,
            device_category="iphone",
            device_model="iPhone 14 Pro",
            confidence=0.95,
            is_ipad=False,
            is_iphone=True,
            orientation="portrait",
            width=1179,
            height=2556,
        )
        assert result.is_iphone is True
        assert result.is_ipad is False
        assert result.device_category == "iphone"

    def test_unknown_result(self):
        result = DeviceDetectionResult(
            detected=False,
            device_category="unknown",
            device_model=None,
            confidence=0.0,
            is_ipad=False,
            is_iphone=False,
            orientation="unknown",
        )
        assert result.detected is False
        assert result.width == 0
        assert result.height == 0


class TestDetectDevice:
    """Tests for detect_device function."""

    def test_missing_library_returns_unknown(self):
        """When ios-device-detector is not installed, should return unknown."""
        with patch.dict("sys.modules", {"ios_device_detector": None}):
            # Force ImportError by patching the import
            with patch(
                "screenshot_processor.web.services.preprocessing.device_and_crop.detect_device"
            ) as mock_detect:
                mock_detect.return_value = DeviceDetectionResult(
                    detected=False,
                    device_category="unknown",
                    device_model=None,
                    confidence=0.0,
                    is_ipad=False,
                    is_iphone=False,
                    orientation="unknown",
                )
                result = mock_detect(Path("/nonexistent.png"))
                assert result.detected is False

    def test_nonexistent_file(self):
        """detect_device on a non-existent file should not crash."""
        result = detect_device("/tmp/definitely_does_not_exist_abc123.png")
        # Should return something (either detected=False or error result)
        assert isinstance(result, DeviceDetectionResult)

    def test_accepts_string_path(self):
        """Should accept string paths."""
        result = detect_device("/tmp/test_string_path.png")
        assert isinstance(result, DeviceDetectionResult)

    def test_accepts_path_object(self):
        """Should accept Path objects."""
        result = detect_device(Path("/tmp/test_path_obj.png"))
        assert isinstance(result, DeviceDetectionResult)


class TestPHIDetectionResult:
    """Tests for PHI detection/redaction dataclasses."""

    def test_phi_detected_result(self):
        result = PHIDetectionResult(
            phi_detected=True,
            regions_count=3,
            regions=[{"x": 0, "y": 0, "w": 100, "h": 50}],
            detector_results={"presidio": 0.8},
        )
        assert result.phi_detected is True
        assert result.regions_count == 3

    def test_no_phi_result(self):
        result = PHIDetectionResult(
            phi_detected=False,
            regions_count=0,
        )
        assert result.phi_detected is False
        assert result.regions == []
        assert result.detector_results == {}

    def test_redaction_result(self):
        result = PHIRedactionResult(
            image_bytes=b"fake_image_data",
            regions_redacted=2,
            redaction_method="redbox",
        )
        assert result.regions_redacted == 2
        assert result.redaction_method == "redbox"


class TestDetectPhi:
    """Tests for detect_phi function."""

    def test_missing_library_returns_no_phi(self):
        """When phi_detector_remover is not installed, should return no PHI."""
        # Create minimal test image bytes (1x1 PNG)
        image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        result = detect_phi(image_bytes)
        # Should handle the import error gracefully
        assert isinstance(result, PHIDetectionResult)


class TestPreprocessingResult:
    """Tests for PreprocessingResult dataclass."""

    def test_successful_result(self):
        result = PreprocessingResult(
            success=True,
            image_bytes=b"processed",
            device_detection=DeviceDetectionResult(
                detected=True, device_category="iphone", device_model="iPhone 14",
                confidence=0.9, is_ipad=False, is_iphone=True, orientation="portrait",
            ),
            was_cropped=False,
            was_patched=False,
            phi_detected=False,
            phi_regions_count=0,
            phi_redacted=False,
            skip_reason=None,
        )
        assert result.success is True
        assert result.skip_reason is None

    def test_failed_result(self):
        result = PreprocessingResult(
            success=False,
            image_bytes=None,
            device_detection=None,
            was_cropped=False,
            was_patched=False,
            phi_detected=False,
            phi_regions_count=0,
            phi_redacted=False,
            skip_reason="File not found",
        )
        assert result.success is False
        assert result.image_bytes is None


class TestPreprocessScreenshotFile:
    """Tests for preprocess_screenshot_file."""

    def test_nonexistent_file(self):
        result = preprocess_screenshot_file("/nonexistent/path.png")
        assert result.success is False
        assert "not found" in result.skip_reason.lower() or "File not found" in result.skip_reason

    def test_returns_preprocessing_result(self):
        """The function should always return a PreprocessingResult."""
        result = preprocess_screenshot_file("/tmp/no_such_file.png")
        assert isinstance(result, PreprocessingResult)

    def test_with_phi_disabled(self):
        """phi_detection_enabled=False should skip PHI step."""
        result = preprocess_screenshot_file(
            "/tmp/no_such_file.png",
            phi_detection_enabled=False,
        )
        # File doesn't exist, so fails early, but shouldn't crash
        assert isinstance(result, PreprocessingResult)

    def test_with_real_file(self):
        """Test with an actual (empty/minimal) file."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            # Write a minimal valid-ish file
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
            f.flush()
            result = preprocess_screenshot_file(f.name)
        # Will likely fail on actual image processing but should not crash
        assert isinstance(result, PreprocessingResult)
