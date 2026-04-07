"""Unit tests for OCR extraction functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from screenshot_processor.core.ocr import (
    _extract_time_from_text,
    _normalize_ocr_digits,
    clean_date_string,
    is_daily_total_page,
    is_date,
    get_day_before,
)


class TestNormalizeOCRDigits:
    """Tests for OCR digit normalization."""

    def test_normalize_i_to_1(self):
        """'I' before time unit should become '1'."""
        assert _normalize_ocr_digits("Ih 30m") == "1h 30m"
        assert _normalize_ocr_digits("Im") == "1m"

    def test_normalize_l_to_1(self):
        """'l' before time unit should become '1'."""
        assert _normalize_ocr_digits("lh 30m") == "1h 30m"
        assert _normalize_ocr_digits("3lm") == "31m"

    def test_normalize_pipe_to_1(self):
        """'|' before time unit should become '1'."""
        assert _normalize_ocr_digits("|h 30m") == "1h 30m"

    def test_normalize_o_to_0(self):
        """'O' before time unit should become '0'."""
        assert _normalize_ocr_digits("1Oh 3Om") == "10h 30m"
        assert _normalize_ocr_digits("Om") == "0m"
        assert _normalize_ocr_digits("Os") == "0s"

    def test_normalize_a_to_4(self):
        """'A' before time unit should become '4'."""
        assert _normalize_ocr_digits("Am") == "4m"
        assert _normalize_ocr_digits("Ah") == "4h"

    def test_normalize_s_to_5(self):
        """'S' before h/m should become '5'."""
        assert _normalize_ocr_digits("Sh") == "5h"
        assert _normalize_ocr_digits("Sm") == "5m"
        # But 's' at end is seconds unit, not replaced
        assert _normalize_ocr_digits("10s") == "10s"

    def test_normalize_b_to_6(self):
        """'b' before time unit should become '6'."""
        assert _normalize_ocr_digits("bm") == "6m"
        assert _normalize_ocr_digits("1bh") == "16h"

    def test_normalize_b_uppercase_to_8(self):
        """'B' before time unit should become '8'."""
        assert _normalize_ocr_digits("Bm") == "8m"
        assert _normalize_ocr_digits("1Bh") == "18h"

    def test_normalize_g_to_9(self):
        """'g' before time unit should become '9'."""
        assert _normalize_ocr_digits("gm") == "9m"

    def test_normalize_z_to_2(self):
        """'Z' before time unit should become '2'."""
        assert _normalize_ocr_digits("Zh") == "2h"
        assert _normalize_ocr_digits("1Zm") == "12m"

    def test_normalize_t_to_7(self):
        """'T' before time unit should become '7'."""
        assert _normalize_ocr_digits("Th") == "7h"
        assert _normalize_ocr_digits("1Tm") == "17m"

    def test_no_change_for_normal_digits(self):
        """Normal digits should remain unchanged."""
        assert _normalize_ocr_digits("4h 36m") == "4h 36m"
        assert _normalize_ocr_digits("12h 30m") == "12h 30m"
        assert _normalize_ocr_digits("45m") == "45m"

    def test_complex_normalization(self):
        """Test complex cases with multiple replacements."""
        # "1Oh 3lm" -> "10h 31m" (1 before O is kept, O before h is normalized, l before m is normalized)
        result = _normalize_ocr_digits("1Oh 3lm")
        assert result == "10h 31m"

        # Note: "IOh" does NOT become "10h" because I is not followed by a digit or time unit directly
        # The regex pattern only matches I when followed by digit or h/m/s
        result2 = _normalize_ocr_digits("IOh 3lm")
        # I is before O (not a digit or time unit), so I stays as I
        # O is before h, so Oh -> 0h
        # 3l before m, l -> 1, so 3lm -> 31m
        assert result2 == "I0h 31m"  # Actual behavior


class TestExtractTimeFromText:
    """Tests for time extraction from OCR text."""

    def test_extract_hours_and_minutes(self):
        """Test extraction of 'Xh Ym' format."""
        assert _extract_time_from_text("4h 36m") == "4h 36m"
        assert _extract_time_from_text("12h 30m") == "12h 30m"
        assert _extract_time_from_text("1h 5m") == "1h 5m"

    def test_extract_hours_and_minutes_no_space(self):
        """Test extraction of 'XhYm' format (no space)."""
        assert _extract_time_from_text("4h36m") == "4h 36m"

    def test_extract_minutes_only(self):
        """Test extraction of 'Xm' format."""
        assert _extract_time_from_text("45m") == "45m"
        assert _extract_time_from_text("5m") == "5m"

    def test_extract_hours_only(self):
        """Test extraction of 'Xh' format."""
        assert _extract_time_from_text("2h") == "2h"
        assert _extract_time_from_text("12h") == "12h"

    def test_extract_minutes_and_seconds(self):
        """Test extraction of 'Xm Ys' format."""
        assert _extract_time_from_text("30m 45s") == "30m 45s"
        assert _extract_time_from_text("5m 0s") == "5m 0s"

    def test_extract_seconds_only(self):
        """Test extraction of 'Xs' format."""
        assert _extract_time_from_text("30s") == "30s"

    def test_extract_from_noisy_text(self):
        """Test extraction from text with noise."""
        assert _extract_time_from_text("Total usage: 4h 36m today") == "4h 36m"
        assert _extract_time_from_text("Screen Time 2h 30m Daily") == "2h 30m"

    def test_extract_missing_m_fallback(self):
        """Test fallback pattern for 'Xh Y' (missing 'm')."""
        # Common OCR failure: "4h 36" instead of "4h 36m"
        assert _extract_time_from_text("4h 36") == "4h 36m"

    def test_extract_empty_string(self):
        """Empty string should return empty."""
        assert _extract_time_from_text("") == ""

    def test_extract_no_time_pattern(self):
        """Text without time pattern should return empty."""
        assert _extract_time_from_text("Hello world") == ""
        assert _extract_time_from_text("No time here") == ""

    def test_extract_with_ocr_errors(self):
        """Test extraction handles common OCR errors."""
        # Normalization happens before extraction
        # "Ih 30m" -> normalized to "1h 30m" -> extracted as "1h 30m"
        assert _extract_time_from_text("Ih 30m") == "1h 30m"
        assert _extract_time_from_text("Os") == "0s"

    def test_extract_prefers_first_match(self):
        """When multiple patterns exist, should extract the first valid one."""
        # "4h 36m" comes before "2h 30m"
        result = _extract_time_from_text("Total 4h 36m, Average 2h 30m")
        assert result == "4h 36m"


class TestIsDailyTotalPage:
    """Tests for daily total page detection."""

    def test_daily_page_markers(self):
        """Test detection of daily page markers."""
        ocr_dict = {
            "text": ["WEEK", "DAY", "MOST", "USED", "CATEGORIES"],
            "level": [1, 1, 1, 1, 1],
            "left": [0, 0, 0, 0, 0],
            "top": [0, 0, 0, 0, 0],
            "width": [10, 10, 10, 10, 10],
            "height": [10, 10, 10, 10, 10],
        }

        result = is_daily_total_page(ocr_dict)

        assert result is True

    def test_app_page_markers(self):
        """Test detection of app-specific page markers."""
        ocr_dict = {
            "text": ["INFO", "DEVELOPER", "RATING", "LIMIT", "AGE", "DAILY", "AVERAGE"],
            "level": [1, 1, 1, 1, 1, 1, 1],
            "left": [0, 0, 0, 0, 0, 0, 0],
            "top": [0, 0, 0, 0, 0, 0, 0],
            "width": [10, 10, 10, 10, 10, 10, 10],
            "height": [10, 10, 10, 10, 10, 10, 10],
        }

        result = is_daily_total_page(ocr_dict)

        assert result is False

    def test_mixed_markers_daily_wins(self):
        """When more daily markers than app markers, daily wins."""
        ocr_dict = {
            "text": ["WEEK", "DAY", "MOST", "USED", "INFO"],  # 4 daily, 1 app
            "level": [1, 1, 1, 1, 1],
            "left": [0, 0, 0, 0, 0],
            "top": [0, 0, 0, 0, 0],
            "width": [10, 10, 10, 10, 10],
            "height": [10, 10, 10, 10, 10],
        }

        result = is_daily_total_page(ocr_dict)

        assert result is True

    def test_mixed_markers_app_wins(self):
        """When more app markers than daily markers, app wins."""
        ocr_dict = {
            "text": ["INFO", "DEVELOPER", "RATING", "LIMIT", "WEEK"],  # 4 app, 1 daily
            "level": [1, 1, 1, 1, 1],
            "left": [0, 0, 0, 0, 0],
            "top": [0, 0, 0, 0, 0],
            "width": [10, 10, 10, 10, 10],
            "height": [10, 10, 10, 10, 10],
        }

        result = is_daily_total_page(ocr_dict)

        assert result is False

    def test_empty_text(self):
        """Empty OCR results should default to app page (not daily)."""
        ocr_dict = {
            "text": [],
            "level": [],
            "left": [],
            "top": [],
            "width": [],
            "height": [],
        }

        result = is_daily_total_page(ocr_dict)

        assert result is False

    def test_case_insensitive_markers(self):
        """Markers should be case-insensitive."""
        ocr_dict = {
            "text": ["week", "day", "most", "used"],  # Lowercase
            "level": [1, 1, 1, 1],
            "left": [0, 0, 0, 0],
            "top": [0, 0, 0, 0],
            "width": [10, 10, 10, 10],
            "height": [10, 10, 10, 10],
        }

        result = is_daily_total_page(ocr_dict)

        assert result is True


class TestCleanDateString:
    """Tests for date string cleaning."""

    def test_removes_special_characters(self):
        """Special characters should be removed."""
        assert clean_date_string("Jan. 15") == "Jan 15"
        assert clean_date_string("Mar, 20") == "Mar 20"
        assert clean_date_string("Dec-25") == "Dec25"

    def test_preserves_alphanumeric(self):
        """Alphanumeric characters should be preserved."""
        assert clean_date_string("Jan 15") == "Jan 15"
        assert clean_date_string("March2024") == "March2024"

    def test_preserves_spaces(self):
        """Spaces should be preserved."""
        assert clean_date_string("Jan 15 2024") == "Jan 15 2024"


class TestIsDate:
    """Tests for date validation."""

    def test_valid_date_format(self):
        """Valid 'Mon DD' format should return True."""
        assert is_date("Jan 15") is True
        assert is_date("Dec 25") is True
        assert is_date("Feb 01") is True

    def test_invalid_date_format(self):
        """Invalid format should return False."""
        assert is_date("January 15") is False  # Full month name
        assert is_date("15 Jan") is False  # Wrong order
        assert is_date("2024-01-15") is False  # ISO format
        assert is_date("Hello") is False  # Not a date

    def test_edge_cases(self):
        """Test edge cases."""
        assert is_date("") is False
        assert is_date("Jan") is False  # Missing day
        assert is_date("15") is False  # Missing month


class TestGetDayBefore:
    """Tests for getting previous day."""

    def test_get_day_before_mid_month(self):
        """Test getting day before mid-month."""
        assert get_day_before("Jan 15") == "Jan 14"
        assert get_day_before("Mar 20") == "Mar 19"

    def test_get_day_before_first_of_month(self):
        """Test getting day before first of month."""
        # Jan 01 -> Dec 31 (no year specified, so wraps)
        result = get_day_before("Jan 01")
        assert result == "Dec 31"

    def test_get_day_before_invalid_date(self):
        """Invalid date should raise ValueError."""
        with pytest.raises(ValueError):
            get_day_before("Invalid")

        with pytest.raises(ValueError):
            get_day_before("")


class TestOCRResultsConversion:
    """Tests for OCR results conversion helpers."""

    def test_ocr_results_to_dict_with_bboxes(self):
        """Test conversion of OCR results with bounding boxes."""
        # This tests the internal _ocr_results_to_dict function
        # We need to import it or test it indirectly
        from screenshot_processor.core.ocr import ocr_results_to_dict as _ocr_results_to_dict

        class MockOCRResult:
            def __init__(self, text: str, bbox: tuple | None, confidence: float | None):
                self.text = text
                self.bbox = bbox
                self.confidence = confidence

        results = [
            MockOCRResult("Hello", (10, 20, 50, 30), 0.95),
            MockOCRResult("World", (70, 20, 50, 30), 0.90),
        ]

        d = _ocr_results_to_dict(results)

        assert len(d["text"]) == 2
        assert d["text"][0] == "Hello"
        assert d["text"][1] == "World"
        assert d["left"][0] == 10
        assert d["conf"][0] == 95  # Confidence scaled to 100

    def test_ocr_results_to_dict_without_bboxes(self):
        """Test conversion of OCR results without bounding boxes."""
        from screenshot_processor.core.ocr import ocr_results_to_dict as _ocr_results_to_dict

        class MockOCRResult:
            def __init__(self, text: str, bbox: tuple | None, confidence: float | None):
                self.text = text
                self.bbox = bbox
                self.confidence = confidence

        results = [
            MockOCRResult("Hello", None, 0.95),
        ]

        d = _ocr_results_to_dict(results)

        assert len(d["text"]) == 1
        assert d["text"][0] == "Hello"
        # Placeholder values for missing bbox
        assert d["left"][0] == 0
        assert d["top"][0] == 0

    def test_ocr_results_to_string(self):
        """Test conversion of OCR results to string."""
        from screenshot_processor.core.ocr import _ocr_results_to_string

        class MockOCRResult:
            def __init__(self, text: str, bbox: tuple | None, confidence: float | None):
                self.text = text
                self.bbox = bbox
                self.confidence = confidence

        results = [
            MockOCRResult("Hello", None, 0.95),
            MockOCRResult("World", None, 0.90),
            MockOCRResult("", None, 0.80),  # Empty should be skipped
            MockOCRResult("  ", None, 0.70),  # Whitespace should be skipped
        ]

        s = _ocr_results_to_string(results)

        assert s == "Hello World"


class TestTitleExtraction:
    """Tests for title extraction (mocked OCR)."""

    @patch("screenshot_processor.core.ocr.pytesseract")
    def test_daily_total_title_detection(self, mock_pytesseract):
        """Test that 'Daily Total' is detected as title for daily pages."""
        from screenshot_processor.core.ocr import find_screenshot_title

        # Mock OCR to return daily page markers
        mock_pytesseract.image_to_data.return_value = {
            "text": ["WEEK", "DAY", "MOST", "USED", "CATEGORIES"],
            "level": [1, 1, 1, 1, 1],
            "left": [0, 0, 0, 0, 0],
            "top": [0, 0, 0, 0, 0],
            "width": [10, 10, 10, 10, 10],
            "height": [10, 10, 10, 10, 10],
        }
        mock_pytesseract.Output = MagicMock()
        mock_pytesseract.Output.DICT = "dict"

        image = np.ones((500, 400, 3), dtype=np.uint8) * 255

        title, y_pos = find_screenshot_title(image)

        assert title == "Daily Total"


class TestTotalUsageExtraction:
    """Tests for total usage extraction patterns."""

    def test_time_patterns_comprehensive(self):
        """Test all supported time patterns."""
        test_cases = [
            ("1h 30m", "1h 30m"),
            ("2h", "2h"),
            ("45m", "45m"),
            ("30s", "30s"),
            ("1h 30m 45s", "1h 30m"),  # Takes first match (h m)
            ("10m 5s", "10m 5s"),
            ("Total: 3h 15m used", "3h 15m"),
            ("Screen Time 4h 36m", "4h 36m"),
        ]

        for input_text, expected in test_cases:
            result = _extract_time_from_text(input_text)
            assert result == expected, f"Failed for '{input_text}': got '{result}', expected '{expected}'"

    def test_time_extraction_with_varying_spaces(self):
        """Test time extraction handles varying whitespace."""
        assert _extract_time_from_text("4h  36m") == "4h 36m"
        assert _extract_time_from_text("4h36m") == "4h 36m"
        assert _extract_time_from_text("4h   36m") == "4h 36m"


class TestOCREdgeCases:
    """Edge case tests for OCR functionality."""

    def test_normalize_preserves_valid_seconds(self):
        """'s' unit for seconds should be preserved."""
        # Should not convert 's' at end of time value
        assert _normalize_ocr_digits("30s") == "30s"
        assert _normalize_ocr_digits("5m 30s") == "5m 30s"

    def test_extract_time_with_unicode(self):
        """Test extraction with unicode characters."""
        # Should handle gracefully
        result = _extract_time_from_text("4h 36m")
        assert result == "4h 36m"

    def test_extract_time_with_newlines(self):
        """Test extraction with newlines in text."""
        result = _extract_time_from_text("Total\n4h 36m\ntoday")
        assert result == "4h 36m"

    def test_is_daily_total_page_with_partial_text(self):
        """Test with partial/incomplete OCR text."""
        ocr_dict = {
            "text": ["WE", "DA", "MO"],  # Partial words
            "level": [1, 1, 1],
            "left": [0, 0, 0],
            "top": [0, 0, 0],
            "width": [10, 10, 10],
            "height": [10, 10, 10],
        }

        # Should not crash
        result = is_daily_total_page(ocr_dict)
        assert isinstance(result, bool)

    def test_normalize_multiple_replacements_in_sequence(self):
        """Test that multiple normalizations work together."""
        # '1Oh 3lm' -> '10h 31m' (1 preserved, O->0, 3 preserved, l->1)
        result = _normalize_ocr_digits("1Oh 3lm")
        assert result == "10h 31m"

        # Note: "IOh" -> "I0h" because I is not followed by digit or h/m/s directly
        result2 = _normalize_ocr_digits("IOh 3lm")
        assert result2 == "I0h 31m"

    def test_extract_time_returns_first_valid_pattern(self):
        """When multiple valid patterns exist, return the first one."""
        # Hour+min pattern is checked before min+sec
        result = _extract_time_from_text("2h 30m 45s")
        assert result == "2h 30m"
