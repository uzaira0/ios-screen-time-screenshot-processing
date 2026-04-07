"""Unit tests for screenshot_processing module — high-level orchestration.

This file covers ScreenshotProcessingService and ProcessingResult from
screenshot_processing.py, complementing the existing test_processing_pipeline.py
which covers the older ProcessingPipeline class and its config/metadata models.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from screenshot_processor.core.interfaces import (
    BarProcessingResult,
    GridBounds,
    GridDetectionMethod,
    GridDetectionResult,
    IBarProcessor,
    IGridDetector,
    ITitleExtractor,
    TitleTotalResult,
)
from screenshot_processor.core.screenshot_processing import (
    ProcessingResult,
    ScreenshotProcessingService,
    create_processing_service,
)


# ---------------------------------------------------------------------------
# Helpers / Stubs
# ---------------------------------------------------------------------------
class StubTitleExtractor(ITitleExtractor):
    def __init__(self, title=None, total=None, is_daily=False, y_pos=None):
        self._title = title
        self._total = total
        self._is_daily = is_daily
        self._y_pos = y_pos

    def extract(self, image, image_type, existing_title=None, existing_total=None):
        return TitleTotalResult(
            title=existing_title or self._title,
            total=existing_total or self._total,
            title_y_position=self._y_pos,
            is_daily_total=self._is_daily,
        )


class StubGridDetector(IGridDetector):
    def __init__(self, success=True, bounds=None, confidence=0.9):
        self._success = success
        self._bounds = bounds or GridBounds(100, 200, 500, 600)
        self._confidence = confidence

    @property
    def method(self):
        return GridDetectionMethod.OCR_ANCHORED

    def detect(self, image, **kwargs):
        return GridDetectionResult(
            success=self._success,
            bounds=self._bounds if self._success else None,
            confidence=self._confidence,
            method=self.method,
            error=None if self._success else "Detection failed",
        )


class StubBarProcessor(IBarProcessor):
    def __init__(self, success=True, values=None, alignment=0.9):
        self._success = success
        self._values = values or {str(i): 2.5 for i in range(24)}
        self._alignment = alignment

    def extract(self, image, bounds, is_battery=False, use_fractional=True):
        return BarProcessingResult(
            success=self._success,
            hourly_values=self._values if self._success else None,
            alignment_score=self._alignment if self._success else None,
            error=None if self._success else "Bar extraction failed",
        )


def _white_image(h=1000, w=800):
    return np.full((h, w, 3), 255, dtype=np.uint8)


# ---------------------------------------------------------------------------
# ProcessingResult dataclass
# ---------------------------------------------------------------------------
class TestProcessingResultDataclass:
    def test_successful_result_to_dict(self):
        bounds = GridBounds(10, 20, 300, 400)
        r = ProcessingResult(
            success=True,
            processing_status="completed",
            grid_bounds=bounds,
            grid_detection_method=GridDetectionMethod.OCR_ANCHORED,
            grid_detection_confidence=0.95,
            hourly_values={"0": 5},
            alignment_score=0.85,
            extracted_title="Safari",
            extracted_total="2h 30m",
        )
        d = r.to_dict()
        assert d["success"] is True
        assert d["processing_status"] == "completed"
        assert d["grid_coords"]["upper_left_x"] == 10
        assert d["processing_method"] == "ocr_anchored"
        assert d["extracted_title"] == "Safari"

    def test_failed_result_to_dict(self):
        r = ProcessingResult(success=False, processing_status="failed")
        d = r.to_dict()
        assert d["success"] is False
        assert d["grid_coords"] is None
        assert d["processing_method"] is None

    def test_numpy_confidence_converted(self):
        """numpy float64 should be converted to native float."""
        r = ProcessingResult(
            success=True,
            processing_status="completed",
            grid_detection_confidence=np.float64(0.88),
            alignment_score=np.float32(0.77),
        )
        d = r.to_dict()
        assert isinstance(d["grid_detection_confidence"], float)
        assert isinstance(d["alignment_score"], float)

    def test_default_issues_empty(self):
        r = ProcessingResult(success=True, processing_status="completed")
        assert r.issues == []
        assert r.is_daily_total is False
        assert r.has_blocking_issues is False


# ---------------------------------------------------------------------------
# ScreenshotProcessingService.process_image
# ---------------------------------------------------------------------------
class TestScreenshotProcessingService:
    def test_daily_total_early_exit(self):
        svc = ScreenshotProcessingService(
            title_extractor=StubTitleExtractor(title="Daily Total", is_daily=True),
            bar_processor=StubBarProcessor(),
        )
        result = svc.process_image(_white_image(), "screen_time")
        assert result.success is True
        assert result.processing_status == "skipped"
        assert result.is_daily_total is True

    def test_successful_processing(self):
        svc = ScreenshotProcessingService(
            grid_detector=StubGridDetector(),
            bar_processor=StubBarProcessor(),
            title_extractor=StubTitleExtractor(title="Safari", total="1h 0m"),
        )
        result = svc.process_image(_white_image(), "screen_time")
        assert result.success is True
        assert result.processing_status == "completed"
        assert result.extracted_title == "Safari"
        assert result.hourly_values is not None

    def test_grid_detection_failure(self):
        svc = ScreenshotProcessingService(
            grid_detector=StubGridDetector(success=False),
            bar_processor=StubBarProcessor(),
            title_extractor=StubTitleExtractor(title="App"),
        )
        result = svc.process_image(_white_image(), "screen_time")
        assert result.success is False
        assert result.processing_status == "failed"
        assert result.has_blocking_issues is True

    def test_bar_extraction_failure(self):
        svc = ScreenshotProcessingService(
            grid_detector=StubGridDetector(),
            bar_processor=StubBarProcessor(success=False),
            title_extractor=StubTitleExtractor(title="App"),
        )
        result = svc.process_image(_white_image(), "screen_time")
        assert result.success is False
        assert result.processing_status == "failed"
        assert result.has_blocking_issues is True
        assert any(i["issue_type"] == "BarExtractionError" for i in result.issues)

    def test_manual_bounds_bypass_detection(self):
        svc = ScreenshotProcessingService(
            grid_detector=StubGridDetector(success=False),  # would fail
            bar_processor=StubBarProcessor(),
            title_extractor=StubTitleExtractor(title="App"),
        )
        manual = GridBounds(50, 100, 400, 500)
        result = svc.process_image(
            _white_image(), "screen_time", manual_bounds=manual
        )
        assert result.success is True
        assert result.grid_bounds is not None
        assert result.grid_detection_method == GridDetectionMethod.MANUAL

    def test_string_detection_method_converted(self):
        svc = ScreenshotProcessingService(
            grid_detector=StubGridDetector(),
            bar_processor=StubBarProcessor(),
            title_extractor=StubTitleExtractor(title="App"),
        )
        result = svc.process_image(
            _white_image(), "screen_time", detection_method="ocr_anchored"
        )
        assert result.success is True

    def test_preserves_existing_title_and_total(self):
        svc = ScreenshotProcessingService(
            grid_detector=StubGridDetector(),
            bar_processor=StubBarProcessor(),
            title_extractor=StubTitleExtractor(),
        )
        result = svc.process_image(
            _white_image(), "screen_time",
            existing_title="Existing",
            existing_total="3h",
        )
        assert result.extracted_title == "Existing"
        assert result.extracted_total == "3h"


# ---------------------------------------------------------------------------
# ScreenshotProcessingService.process (file-based)
# ---------------------------------------------------------------------------
class TestProcessFromFile:
    @patch("screenshot_processor.core.screenshot_processing.cv2.imread")
    def test_invalid_file_returns_failure(self, mock_imread):
        mock_imread.return_value = None
        svc = ScreenshotProcessingService(
            title_extractor=StubTitleExtractor(),
            bar_processor=StubBarProcessor(),
        )
        result = svc.process("/nonexistent/img.png", "screen_time")
        assert result.success is False
        assert result.processing_status == "failed"
        assert any("FileError" in i["issue_type"] for i in result.issues)

    @patch("screenshot_processor.core.screenshot_processing.cv2.imread")
    def test_valid_file_delegates_to_process_image(self, mock_imread):
        mock_imread.return_value = _white_image()
        svc = ScreenshotProcessingService(
            grid_detector=StubGridDetector(),
            bar_processor=StubBarProcessor(),
            title_extractor=StubTitleExtractor(title="TestApp"),
        )
        result = svc.process("/some/img.png", "screen_time")
        assert result.success is True


# ---------------------------------------------------------------------------
# create_processing_service factory
# ---------------------------------------------------------------------------
class TestCreateProcessingService:
    def test_creates_service_without_method(self):
        svc = create_processing_service()
        assert isinstance(svc, ScreenshotProcessingService)

    def test_creates_service_with_string_method(self):
        try:
            svc = create_processing_service("line_based")
            assert isinstance(svc, ScreenshotProcessingService)
        except (ImportError, RuntimeError):
            pytest.skip("Line-based detector not available")

    def test_creates_service_with_enum_method(self):
        try:
            svc = create_processing_service(GridDetectionMethod.LINE_BASED)
            assert isinstance(svc, ScreenshotProcessingService)
        except (ImportError, RuntimeError):
            pytest.skip("Line-based detector not available")
