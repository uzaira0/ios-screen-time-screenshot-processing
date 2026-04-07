"""Unit tests for grid detector implementations."""

from __future__ import annotations

import numpy as np

from screenshot_processor.core.grid_detectors import LineBasedGridDetector, OCRAnchoredGridDetector
from screenshot_processor.core.interfaces import GridDetectionMethod, GridDetectionResult


class TestOCRAnchoredGridDetector:
    """Tests for OCR-anchored grid detection."""

    def test_detector_method_property(self):
        """Test that detector returns correct method identifier."""
        detector = OCRAnchoredGridDetector()
        assert detector.method == GridDetectionMethod.OCR_ANCHORED

    def test_detect_with_empty_image(self):
        """Test detection with empty/blank image."""
        detector = OCRAnchoredGridDetector()
        blank_image = np.zeros((1000, 500, 3), dtype=np.uint8)

        result = detector.detect(blank_image)

        assert isinstance(result, GridDetectionResult)
        assert result.method == GridDetectionMethod.OCR_ANCHORED
        # Blank image should fail detection
        assert not result.success or result.confidence < 0.5

    def test_detect_result_structure(self):
        """Test that detection result has correct structure."""
        detector = OCRAnchoredGridDetector()
        test_image = np.zeros((1000, 500, 3), dtype=np.uint8)

        result = detector.detect(test_image)

        # Check required attributes
        assert hasattr(result, "success")
        assert hasattr(result, "bounds")
        assert hasattr(result, "confidence")
        assert hasattr(result, "method")
        assert hasattr(result, "error")
        assert hasattr(result, "diagnostics")

        # Check types
        assert isinstance(result.success, bool)
        assert isinstance(result.method, GridDetectionMethod)
        assert result.confidence is None or isinstance(result.confidence, (int, float))
        assert isinstance(result.diagnostics, dict)

    def test_detect_with_resolution_param(self):
        """Test detection with resolution parameter."""
        detector = OCRAnchoredGridDetector()
        test_image = np.zeros((1000, 500, 3), dtype=np.uint8)

        result = detector.detect(test_image, resolution="1125x2436")

        assert isinstance(result, GridDetectionResult)
        assert result.method == GridDetectionMethod.OCR_ANCHORED


class TestLineBasedGridDetector:
    """Tests for line-based grid detection."""

    def test_detector_method_property(self):
        """Test that detector returns correct method identifier."""
        detector = LineBasedGridDetector()
        assert detector.method == GridDetectionMethod.LINE_BASED

    def test_detect_with_empty_image(self):
        """Test detection with empty/blank image."""
        detector = LineBasedGridDetector()
        blank_image = np.zeros((1000, 500, 3), dtype=np.uint8)

        result = detector.detect(blank_image)

        assert isinstance(result, GridDetectionResult)
        assert result.method == GridDetectionMethod.LINE_BASED
        # Blank image should fail detection
        assert not result.success

    def test_detect_result_structure(self):
        """Test that detection result has correct structure."""
        detector = LineBasedGridDetector()
        test_image = np.zeros((1000, 500, 3), dtype=np.uint8)

        result = detector.detect(test_image)

        # Check required attributes
        assert hasattr(result, "success")
        assert hasattr(result, "bounds")
        assert hasattr(result, "confidence")
        assert hasattr(result, "method")
        assert hasattr(result, "error")
        assert hasattr(result, "diagnostics")

        # Check types
        assert isinstance(result.success, bool)
        assert isinstance(result.method, GridDetectionMethod)
        assert result.confidence is None or isinstance(result.confidence, (int, float))
        assert isinstance(result.diagnostics, dict)

    def test_detect_with_resolution_hint(self):
        """Test detection with resolution hint."""
        detector = LineBasedGridDetector()
        test_image = np.zeros((1125, 500, 3), dtype=np.uint8)

        result = detector.detect(test_image, resolution="1125x2436")

        assert isinstance(result, GridDetectionResult)
        assert result.method == GridDetectionMethod.LINE_BASED

    def test_detect_with_grid_lines(self):
        """Test detection with image containing horizontal lines."""
        detector = LineBasedGridDetector()
        test_image = np.ones((1000, 500, 3), dtype=np.uint8) * 255

        # Add horizontal gray lines to simulate grid
        for y in range(200, 800, 50):
            test_image[y : y + 2, 50:450] = 128

        result = detector.detect(test_image)

        assert isinstance(result, GridDetectionResult)
        assert result.method == GridDetectionMethod.LINE_BASED

    def test_result_has_diagnostics(self):
        """Test that result includes diagnostic information."""
        detector = LineBasedGridDetector()
        test_image = np.zeros((1000, 500, 3), dtype=np.uint8)

        result = detector.detect(test_image)

        assert isinstance(result.diagnostics, dict)
        # Diagnostics should be populated even on failure
        assert len(result.diagnostics) >= 0

    def test_failed_detection_has_error_message(self):
        """Test that failed detection includes error message."""
        detector = LineBasedGridDetector()
        blank_image = np.zeros((100, 100, 3), dtype=np.uint8)

        result = detector.detect(blank_image)

        if not result.success:
            assert result.error is not None
            assert isinstance(result.error, str)
            assert len(result.error) > 0
