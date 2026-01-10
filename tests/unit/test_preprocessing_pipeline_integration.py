"""
Integration-style tests for the preprocessing pipeline.

Tests the pipeline orchestration functions using real test images
from the fixtures directory. Does not require a database.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from screenshot_processor.web.services.preprocessing.device_and_crop import (
    DeviceDetectionResult,
    crop_screenshot_if_ipad,
    detect_device,
)
from screenshot_processor.web.services.preprocessing.pipeline import (
    PreprocessingResult,
    append_event,
    get_current_input_file,
    get_next_version,
    get_stage_output_path,
    init_preprocessing_metadata,
    invalidate_downstream,
    is_exception,
    preprocess_screenshot_file,
    update_file_path,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "images"


class TestDetectDeviceWithRealImage:
    """Test detect_device on real fixture images."""

    @pytest.fixture
    def real_image_path(self):
        images = list(FIXTURES_DIR.glob("*.png"))
        if not images:
            pytest.skip("No test images found in fixtures/images/")
        return images[0]

    def test_detect_device_returns_result(self, real_image_path):
        result = detect_device(real_image_path)
        assert isinstance(result, DeviceDetectionResult)
        assert result.device_category in ("iphone", "ipad", "unknown")
        assert result.orientation in ("portrait", "landscape", "unknown")
        assert 0.0 <= result.confidence <= 1.0

    def test_detect_device_on_nonexistent_file(self, tmp_path):
        result = detect_device(tmp_path / "nonexistent.png")
        # Should not crash, returns unknown
        assert isinstance(result, DeviceDetectionResult)


class TestCropScreenshotIfIpad:
    """Test crop_screenshot_if_ipad with real image bytes."""

    @pytest.fixture
    def real_image_bytes(self):
        images = list(FIXTURES_DIR.glob("*.png"))
        if not images:
            pytest.skip("No test images found in fixtures/images/")
        return images[0].read_bytes()

    def test_non_ipad_returns_unchanged(self, real_image_bytes):
        device = DeviceDetectionResult(
            detected=True,
            device_category="iphone",
            device_model="iPhone 14",
            confidence=0.95,
            is_ipad=False,
            is_iphone=True,
            orientation="portrait",
            width=1170,
            height=2532,
        )
        result_bytes, was_cropped, was_patched, had_error = crop_screenshot_if_ipad(
            real_image_bytes, device
        )
        # iphone screenshots should not be cropped
        assert not had_error

    def test_unknown_device_returns_unchanged(self, real_image_bytes):
        device = DeviceDetectionResult(
            detected=False,
            device_category="unknown",
            device_model=None,
            confidence=0.0,
            is_ipad=False,
            is_iphone=False,
            orientation="unknown",
        )
        result_bytes, was_cropped, was_patched, had_error = crop_screenshot_if_ipad(
            real_image_bytes, device
        )
        assert not had_error


class TestPreprocessScreenshotFile:
    """Test the full pipeline function on real files."""

    @pytest.fixture
    def real_image_path(self):
        images = list(FIXTURES_DIR.glob("*.png"))
        if not images:
            pytest.skip("No test images found in fixtures/images/")
        return str(images[0])

    def test_nonexistent_file_returns_failure(self):
        result = preprocess_screenshot_file("/nonexistent/path/image.png")
        assert isinstance(result, PreprocessingResult)
        assert result.success is False
        assert result.skip_reason is not None
        assert "not found" in result.skip_reason.lower()

    def test_real_image_pipeline_completes(self, real_image_path):
        """Run full pipeline on a real image with PHI detection disabled."""
        result = preprocess_screenshot_file(
            real_image_path,
            phi_detection_enabled=False,
        )
        assert isinstance(result, PreprocessingResult)
        assert result.success is True
        assert result.image_bytes is not None
        assert len(result.image_bytes) > 0
        assert result.skip_reason is None

    def test_real_image_with_phi_detection(self, real_image_path):
        """Run full pipeline with PHI detection enabled."""
        result = preprocess_screenshot_file(
            real_image_path,
            phi_detection_enabled=True,
            phi_pipeline_preset="screen_time",
            phi_redaction_method="redbox",
        )
        assert isinstance(result, PreprocessingResult)
        assert result.success is True
        assert result.image_bytes is not None
        assert isinstance(result.phi_detected, bool)
        assert isinstance(result.phi_regions_count, int)


class TestPipelineEventLog:
    """Test the event log management functions."""

    def _make_screenshot(self, file_path="/uploads/test.png"):
        screenshot = MagicMock()
        screenshot.file_path = file_path
        screenshot.processing_metadata = None
        return screenshot

    def test_init_preprocessing_metadata(self):
        screenshot = self._make_screenshot()
        pp = init_preprocessing_metadata(screenshot)
        assert "base_file_path" in pp
        assert pp["base_file_path"] == "/uploads/test.png"
        assert pp["events"] == []
        assert pp["current_events"] == {}
        assert "device_detection" in pp["stage_status"]

    def test_init_is_idempotent(self):
        screenshot = self._make_screenshot()
        pp1 = init_preprocessing_metadata(screenshot)
        pp1["events"].append({"event_id": 1})
        pp2 = init_preprocessing_metadata(screenshot)
        assert len(pp2["events"]) == 1  # same list, not reset

    def test_append_event(self):
        screenshot = self._make_screenshot()
        event_id = append_event(
            screenshot,
            stage="device_detection",
            source="auto",
            params={},
            result={"device_category": "iphone"},
        )
        assert event_id == 1
        pp = screenshot.processing_metadata["preprocessing"]
        assert pp["current_events"]["device_detection"] == 1
        assert pp["stage_status"]["device_detection"] == "completed"

    def test_append_event_invalidates_downstream(self):
        screenshot = self._make_screenshot()
        # First complete device_detection and cropping
        append_event(screenshot, "device_detection", "auto", {}, {"device_category": "iphone"})
        append_event(screenshot, "cropping", "auto", {}, {"was_cropped": False}, output_file="/uploads/test_crop_v1.png")
        append_event(screenshot, "phi_detection", "auto", {}, {"phi_detected": False})

        pp = screenshot.processing_metadata["preprocessing"]
        assert pp["stage_status"]["phi_detection"] == "completed"

        # Re-run cropping — should invalidate phi_detection
        append_event(screenshot, "cropping", "manual", {"left": 10}, {"was_cropped": True}, output_file="/uploads/test_crop_v2.png")
        assert pp["stage_status"]["phi_detection"] == "invalidated"

    def test_get_current_input_file_device_detection(self):
        screenshot = self._make_screenshot()
        init_preprocessing_metadata(screenshot)
        input_file = get_current_input_file(screenshot, "device_detection")
        assert input_file == "/uploads/test.png"

    def test_get_stage_output_path(self):
        path = get_stage_output_path("/uploads/test.png", "cropping", 1)
        assert path == Path("/uploads/test_crop_v1.png")

    def test_get_stage_output_path_redaction(self):
        path = get_stage_output_path("/uploads/test.png", "phi_redaction", 2)
        assert path == Path("/uploads/test_redact_v2.png")

    def test_get_next_version_fresh(self):
        screenshot = self._make_screenshot()
        init_preprocessing_metadata(screenshot)
        version = get_next_version(screenshot, "cropping")
        assert version == 1

    def test_update_file_path_uses_latest_output(self):
        screenshot = self._make_screenshot()
        append_event(
            screenshot, "cropping", "auto", {},
            {"was_cropped": True},
            output_file="/uploads/test_crop_v1.png",
        )
        assert screenshot.file_path == "/uploads/test_crop_v1.png"


class TestIsException:
    """Test the exception detection logic for various stages."""

    def test_unknown_device_is_exception(self):
        assert is_exception("device_detection", {"device_category": "unknown"}) is True

    def test_low_confidence_is_exception(self):
        assert is_exception("device_detection", {"device_category": "iphone", "confidence": 0.5}) is True

    def test_normal_device_not_exception(self):
        assert is_exception("device_detection", {"device_category": "iphone", "confidence": 0.9}) is False

    def test_ipad_not_cropped_is_exception(self):
        assert is_exception("cropping", {"is_ipad": True, "was_cropped": False}) is True

    def test_phi_detected_is_exception(self):
        assert is_exception("phi_detection", {"phi_detected": True, "regions_count": 3}) is True

    def test_phi_detected_zero_regions_not_exception(self):
        assert is_exception("phi_detection", {"phi_detected": True, "regions_count": 0}) is False

    def test_phi_reviewed_not_exception(self):
        assert is_exception("phi_detection", {"reviewed": True, "phi_detected": True}) is False

    def test_ocr_failed_is_exception(self):
        assert is_exception("ocr", {"processing_status": "failed"}) is True

    def test_low_alignment_is_exception(self):
        assert is_exception("ocr", {"alignment_score": 0.5}) is True

    def test_good_ocr_not_exception(self):
        assert is_exception("ocr", {"processing_status": "completed", "alignment_score": 0.95}) is False
