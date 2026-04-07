"""Unit tests for title extraction functionality."""

from __future__ import annotations

import numpy as np

from screenshot_processor.core.title_extractor import OCRTitleExtractor
from screenshot_processor.core.interfaces import TitleTotalResult


class TestTitleExtractor:
    """Tests for OCRTitleExtractor implementation."""

    def test_extract_with_empty_image(self):
        """Test title extraction with empty image."""
        extractor = OCRTitleExtractor()
        blank_image = np.zeros((1000, 500, 3), dtype=np.uint8)

        result = extractor.extract(blank_image, "screen_time")

        assert isinstance(result, TitleTotalResult)
        # Empty image should return None or empty results
        assert result.title is None or result.title == ""

    def test_extract_result_structure(self):
        """Test that extraction result has correct structure."""
        extractor = OCRTitleExtractor()
        test_image = np.ones((1000, 500, 3), dtype=np.uint8) * 255

        result = extractor.extract(test_image, "screen_time")

        # Check required attributes
        assert hasattr(result, "title")
        assert hasattr(result, "total")
        assert hasattr(result, "title_y_position")
        assert hasattr(result, "is_daily_total")

        # Check types
        assert result.title is None or isinstance(result.title, str)
        assert result.total is None or isinstance(result.total, str)
        assert result.title_y_position is None or isinstance(result.title_y_position, int)
        assert isinstance(result.is_daily_total, bool)

    def test_extract_screen_time_type(self):
        """Test extraction for screen_time image type."""
        extractor = OCRTitleExtractor()
        test_image = np.ones((1000, 500, 3), dtype=np.uint8) * 255

        result = extractor.extract(test_image, "screen_time")

        assert isinstance(result, TitleTotalResult)

    def test_extract_battery_type(self):
        """Test extraction for battery image type."""
        extractor = OCRTitleExtractor()
        test_image = np.ones((1000, 500, 3), dtype=np.uint8) * 255

        result = extractor.extract(test_image, "battery")

        assert isinstance(result, TitleTotalResult)

    def test_extract_with_existing_title(self):
        """Test extraction with existing title (skip OCR)."""
        extractor = OCRTitleExtractor()
        test_image = np.ones((1000, 500, 3), dtype=np.uint8) * 255

        result = extractor.extract(test_image, "screen_time", existing_title="Social Networking")

        assert isinstance(result, TitleTotalResult)
        # Should preserve existing title
        assert result.title == "Social Networking"

    def test_extract_with_existing_total(self):
        """Test extraction with existing total (skip OCR)."""
        extractor = OCRTitleExtractor()
        test_image = np.ones((1000, 500, 3), dtype=np.uint8) * 255

        result = extractor.extract(test_image, "screen_time", existing_total="2h 30m")

        assert isinstance(result, TitleTotalResult)
        # Should preserve existing total
        assert result.total == "2h 30m"

    def test_extract_with_both_existing_values(self):
        """Test extraction with both existing title and total."""
        extractor = OCRTitleExtractor()
        test_image = np.ones((1000, 500, 3), dtype=np.uint8) * 255

        result = extractor.extract(
            test_image,
            "screen_time",
            existing_title="Social Networking",
            existing_total="2h 30m",
        )

        assert isinstance(result, TitleTotalResult)
        assert result.title == "Social Networking"
        assert result.total == "2h 30m"

    def test_daily_total_detection(self):
        """Test detection of Daily Total screenshots."""
        extractor = OCRTitleExtractor()
        # Would need actual image with "Daily Total" text
        # For now, test the structure
        test_image = np.ones((1000, 500, 3), dtype=np.uint8) * 255

        result = extractor.extract(test_image, "screen_time")

        assert isinstance(result.is_daily_total, bool)

    def test_extract_with_invalid_image_type(self):
        """Test extraction with invalid image type."""
        extractor = OCRTitleExtractor()
        test_image = np.ones((1000, 500, 3), dtype=np.uint8) * 255

        # Should handle gracefully
        try:
            result = extractor.extract(test_image, "invalid_type")
            assert isinstance(result, TitleTotalResult)
        except ValueError:
            # Acceptable to raise ValueError for invalid type
            pass

    def test_title_y_position_when_found(self):
        """Test that title_y_position is set when title is found."""
        extractor = OCRTitleExtractor()
        test_image = np.ones((1000, 500, 3), dtype=np.uint8) * 255

        result = extractor.extract(test_image, "screen_time")

        if result.title is not None and result.title != "":
            # Y position should be set when title is found
            assert result.title_y_position is not None
            assert isinstance(result.title_y_position, int)
            assert result.title_y_position >= 0

    def test_extract_handles_grayscale_conversion(self):
        """Test that extraction handles color-to-grayscale conversion."""
        extractor = OCRTitleExtractor()
        # RGB image
        rgb_image = np.ones((1000, 500, 3), dtype=np.uint8) * 200

        result = extractor.extract(rgb_image, "screen_time")

        assert isinstance(result, TitleTotalResult)
        # Should complete without errors

    def test_extract_with_small_image(self):
        """Test extraction with very small image."""
        extractor = OCRTitleExtractor()
        small_image = np.ones((100, 100, 3), dtype=np.uint8) * 255

        result = extractor.extract(small_image, "screen_time")

        assert isinstance(result, TitleTotalResult)
        # Should handle small images gracefully

    def test_extract_with_large_image(self):
        """Test extraction with very large image."""
        extractor = OCRTitleExtractor()
        large_image = np.ones((4000, 2000, 3), dtype=np.uint8) * 255

        result = extractor.extract(large_image, "screen_time")

        assert isinstance(result, TitleTotalResult)
        # Should handle large images without memory issues
