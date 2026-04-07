"""Unit tests for boundary optimizer functionality."""

from __future__ import annotations

import numpy as np

from screenshot_processor.core.boundary_optimizer import OptimizationResult, optimize_boundaries, parse_ocr_total
from screenshot_processor.core.interfaces import GridBounds


class TestParseOCRTotal:
    """Tests for OCR total string parsing."""

    def test_parse_hours_and_minutes(self):
        """Test parsing standard hours and minutes format."""
        assert parse_ocr_total("2h 30m") == 150
        assert parse_ocr_total("1h 15m") == 75
        assert parse_ocr_total("12h 45m") == 765

    def test_parse_minutes_only(self):
        """Test parsing minutes-only format."""
        assert parse_ocr_total("45m") == 45
        assert parse_ocr_total("5m") == 5
        assert parse_ocr_total("60m") == 60

    def test_parse_hours_only(self):
        """Test parsing hours-only format."""
        assert parse_ocr_total("2h") == 120
        assert parse_ocr_total("1h") == 60
        assert parse_ocr_total("10h") == 600

    def test_parse_invalid_format(self):
        """Test parsing invalid or unparseable formats."""
        assert parse_ocr_total("invalid") is None
        assert parse_ocr_total("") is None
        assert parse_ocr_total("abc") is None
        assert parse_ocr_total("h m") is None

    def test_parse_with_extra_whitespace(self):
        """Test parsing with extra whitespace."""
        assert parse_ocr_total(" 2h 30m ") == 150
        assert parse_ocr_total("1h  15m") == 75

    def test_parse_zero_values(self):
        """Test parsing zero hours or minutes."""
        assert parse_ocr_total("0h 30m") == 30
        assert parse_ocr_total("2h 0m") == 120
        # 0h 0m may return None or 0 depending on implementation
        result = parse_ocr_total("0h 0m")
        assert result is None or result == 0


class TestOptimizeGridBounds:
    """Tests for grid bounds optimization."""

    def test_optimize_without_ocr_total(self):
        """Test optimization when OCR total cannot be parsed."""
        # Create a simple test image
        image = np.zeros((1000, 500, 3), dtype=np.uint8)
        # Add some white bars to simulate a grid
        image[200:800, 50:450] = 255

        bounds = GridBounds(
            upper_left_x=50,
            upper_left_y=200,
            lower_right_x=450,
            lower_right_y=800,
        )

        result = optimize_boundaries(image, bounds, "invalid_ocr", is_battery=False)

        assert isinstance(result, OptimizationResult)
        assert result.bounds == bounds
        assert result.shift_x == 0
        assert result.shift_width == 0
        assert result.iterations == 0
        assert not result.converged

    def test_optimize_with_valid_ocr_total(self):
        """Test optimization with a valid OCR total."""
        # Create a test image with bars
        image = np.zeros((1000, 500, 3), dtype=np.uint8)
        # Add grid region
        image[200:800, 50:450] = 255

        bounds = GridBounds(
            upper_left_x=50,
            upper_left_y=200,
            lower_right_x=450,
            lower_right_y=800,
        )

        result = optimize_boundaries(image, bounds, "2h 30m", is_battery=False)

        assert isinstance(result, OptimizationResult)
        assert result.ocr_total_minutes == 150
        assert isinstance(result.bar_total_minutes, int)
        # The optimizer should have tried some iterations
        assert result.iterations >= 0

    def test_optimization_result_structure(self):
        """Test that optimization result has correct structure."""
        image = np.zeros((1000, 500, 3), dtype=np.uint8)
        image[200:800, 50:450] = 255

        bounds = GridBounds(
            upper_left_x=50,
            upper_left_y=200,
            lower_right_x=450,
            lower_right_y=800,
        )

        result = optimize_boundaries(image, bounds, "1h", is_battery=False)

        # Check all required fields exist
        assert hasattr(result, "bounds")
        assert hasattr(result, "bar_total_minutes")
        assert hasattr(result, "ocr_total_minutes")
        assert hasattr(result, "shift_x")
        assert hasattr(result, "shift_width")
        assert hasattr(result, "iterations")
        assert hasattr(result, "converged")

        # Check types
        assert isinstance(result.bounds, GridBounds)
        assert isinstance(result.bar_total_minutes, int)
        assert isinstance(result.ocr_total_minutes, int)
        assert isinstance(result.shift_x, int)
        assert isinstance(result.shift_width, int)
        assert isinstance(result.iterations, int)
        assert isinstance(result.converged, bool)

    def test_optimize_battery_image(self):
        """Test optimization for battery screenshot."""
        image = np.zeros((1000, 500, 3), dtype=np.uint8)
        # Add dark blue color typical of battery graphs
        image[200:800, 50:450] = [255, 121, 0]  # BGR format

        bounds = GridBounds(
            upper_left_x=50,
            upper_left_y=200,
            lower_right_x=450,
            lower_right_y=800,
        )

        result = optimize_boundaries(image, bounds, "50m", is_battery=True)

        assert isinstance(result, OptimizationResult)
        assert result.ocr_total_minutes == 50
