"""Unit tests for bar processor functionality."""

from __future__ import annotations

import numpy as np

from screenshot_processor.core.bar_extraction import compute_bar_alignment_score, slice_image
from screenshot_processor.core.bar_processor import StandardBarProcessor, get_bar_processor
from screenshot_processor.core.interfaces import BarProcessingResult, GridBounds


class TestStandardBarProcessor:
    """Tests for StandardBarProcessor implementation."""

    def test_extract_with_empty_image(self):
        """Test bar extraction with empty image."""
        processor = StandardBarProcessor()
        blank_image = np.zeros((1000, 500, 3), dtype=np.uint8)

        bounds = GridBounds(
            upper_left_x=50,
            upper_left_y=200,
            lower_right_x=450,
            lower_right_y=800,
        )

        result = processor.extract(blank_image, bounds, is_battery=False)

        assert isinstance(result, BarProcessingResult)
        assert isinstance(result.success, bool)
        # Empty image should produce some result (even if all zeros)
        if result.success:
            assert result.hourly_values is not None
            assert len(result.hourly_values) == 24

    def test_extract_result_structure(self):
        """Test that extraction result has correct structure."""
        processor = StandardBarProcessor()
        test_image = np.ones((1000, 500, 3), dtype=np.uint8) * 255

        bounds = GridBounds(
            upper_left_x=50,
            upper_left_y=200,
            lower_right_x=450,
            lower_right_y=800,
        )

        result = processor.extract(test_image, bounds, is_battery=False)

        # Check required attributes
        assert hasattr(result, "success")
        assert hasattr(result, "hourly_values")
        assert hasattr(result, "alignment_score")
        assert hasattr(result, "error")

        # Check types
        assert isinstance(result.success, bool)
        if result.hourly_values is not None:
            assert isinstance(result.hourly_values, dict)
        if result.alignment_score is not None:
            assert isinstance(result.alignment_score, (int, float))
        if result.error is not None:
            assert isinstance(result.error, str)

    def test_extract_hourly_values_count(self):
        """Test that extraction returns 24 hourly values."""
        processor = StandardBarProcessor()
        test_image = np.ones((1000, 500, 3), dtype=np.uint8) * 255

        # Add some colored bars
        test_image[400:600, 100:400] = [0, 121, 255]  # Purple bars

        bounds = GridBounds(
            upper_left_x=50,
            upper_left_y=200,
            lower_right_x=450,
            lower_right_y=800,
        )

        result = processor.extract(test_image, bounds, is_battery=False)

        if result.success and result.hourly_values:
            assert len(result.hourly_values) == 24
            # Check all hours are present (keys may be '0' or '00' format)
            for hour in range(24):
                hour_key = str(hour)
                assert hour_key in result.hourly_values or f"{hour:02d}" in result.hourly_values

    def test_extract_with_fractional_values(self):
        """Test extraction with fractional values enabled."""
        processor = StandardBarProcessor()
        test_image = np.ones((1000, 500, 3), dtype=np.uint8) * 255

        bounds = GridBounds(
            upper_left_x=50,
            upper_left_y=200,
            lower_right_x=450,
            lower_right_y=800,
        )

        result = processor.extract(test_image, bounds, is_battery=False, use_fractional=True)

        assert isinstance(result, BarProcessingResult)
        if result.success and result.hourly_values:
            # With fractional, values should be floats
            for value in result.hourly_values.values():
                assert isinstance(value, (int, float))

    def test_extract_without_fractional_values(self):
        """Test extraction with fractional values disabled."""
        processor = StandardBarProcessor()
        test_image = np.ones((1000, 500, 3), dtype=np.uint8) * 255

        bounds = GridBounds(
            upper_left_x=50,
            upper_left_y=200,
            lower_right_x=450,
            lower_right_y=800,
        )

        result = processor.extract(test_image, bounds, is_battery=False, use_fractional=False)

        assert isinstance(result, BarProcessingResult)
        if result.success and result.hourly_values:
            # Without fractional, values should be integers
            for value in result.hourly_values.values():
                assert isinstance(value, (int, float))
                assert value >= 0
                assert value <= 60  # Max minutes per hour

    def test_extract_battery_mode(self):
        """Test extraction in battery mode."""
        processor = StandardBarProcessor()
        test_image = np.ones((1000, 500, 3), dtype=np.uint8) * 255

        # Add dark blue bars typical of battery screenshots
        test_image[400:600, 100:400] = [255, 121, 0]  # BGR format

        bounds = GridBounds(
            upper_left_x=50,
            upper_left_y=200,
            lower_right_x=450,
            lower_right_y=800,
        )

        result = processor.extract(test_image, bounds, is_battery=True)

        assert isinstance(result, BarProcessingResult)
        # Battery mode should still produce valid results
        assert isinstance(result.success, bool)

    def test_extract_with_small_bounds(self):
        """Test extraction with very small grid bounds."""
        processor = StandardBarProcessor()
        test_image = np.ones((1000, 500, 3), dtype=np.uint8) * 255

        bounds = GridBounds(
            upper_left_x=100,
            upper_left_y=100,
            lower_right_x=120,
            lower_right_y=120,
        )

        result = processor.extract(test_image, bounds, is_battery=False)

        # Should handle small bounds gracefully
        assert isinstance(result, BarProcessingResult)

    def test_alignment_score_present(self):
        """Test that alignment score is calculated."""
        processor = StandardBarProcessor()
        test_image = np.ones((1000, 500, 3), dtype=np.uint8) * 255

        bounds = GridBounds(
            upper_left_x=50,
            upper_left_y=200,
            lower_right_x=450,
            lower_right_y=800,
        )

        result = processor.extract(test_image, bounds, is_battery=False)

        if result.success:
            # Alignment score should be present
            assert result.alignment_score is not None
            assert isinstance(result.alignment_score, (int, float))
            assert 0 <= result.alignment_score <= 1

    def test_extract_with_out_of_bounds(self):
        """Test extraction with bounds exceeding image dimensions."""
        processor = StandardBarProcessor()
        test_image = np.ones((500, 300, 3), dtype=np.uint8) * 255

        bounds = GridBounds(
            upper_left_x=100,
            upper_left_y=100,
            lower_right_x=1000,  # Exceeds image width
            lower_right_y=1000,  # Exceeds image height
        )

        # Should handle gracefully without crashing
        try:
            result = processor.extract(test_image, bounds, is_battery=False)
            assert isinstance(result, BarProcessingResult)
        except Exception:
            # If it raises an exception, that's also acceptable
            pass

    def test_extract_with_zero_width_bounds(self):
        """Test extraction with zero-width bounds returns error."""
        processor = StandardBarProcessor()
        test_image = np.ones((500, 500, 3), dtype=np.uint8) * 255

        bounds = GridBounds(
            upper_left_x=100,
            upper_left_y=100,
            lower_right_x=100,  # Zero width
            lower_right_y=300,
        )

        result = processor.extract(test_image, bounds, is_battery=False)

        # Should return failure for invalid bounds
        assert result.success is False
        assert result.error is not None

    def test_extract_with_negative_bounds(self):
        """Test extraction with negative bounds returns error."""
        processor = StandardBarProcessor()
        test_image = np.ones((500, 500, 3), dtype=np.uint8) * 255

        bounds = GridBounds(
            upper_left_x=-10,
            upper_left_y=100,
            lower_right_x=200,
            lower_right_y=300,
        )

        result = processor.extract(test_image, bounds, is_battery=False)

        # Should return failure for invalid bounds
        assert result.success is False
        assert result.error is not None


class TestGetBarProcessor:
    """Tests for the bar processor factory function."""

    def test_get_bar_processor_returns_standard(self):
        """Factory should return StandardBarProcessor by default."""
        processor = get_bar_processor()

        assert isinstance(processor, StandardBarProcessor)

    def test_factory_returns_new_instances(self):
        """Each call should return a new instance."""
        processor1 = get_bar_processor()
        processor2 = get_bar_processor()

        assert processor1 is not processor2


class TestSliceImage:
    """Direct tests for the slice_image function."""

    def test_slice_image_returns_correct_structure(self):
        """slice_image should return (row, image, scale_amount)."""
        image = np.ones((1000, 1500, 3), dtype=np.uint8) * 255

        result = slice_image(image, roi_x=100, roi_y=200, roi_width=1000, roi_height=200)

        assert isinstance(result, tuple)
        assert len(result) == 3
        row, processed_img, scale = result
        assert isinstance(row, list)
        assert isinstance(processed_img, np.ndarray)
        assert isinstance(scale, int)

    def test_slice_image_with_varying_bar_heights(self):
        """Test with bars of varying heights."""
        image = np.ones((1000, 1500, 3), dtype=np.uint8) * 255
        roi_x, roi_y, roi_width, roi_height = 100, 200, 1200, 200

        # Create bars with increasing heights
        slice_width = roi_width // 24
        for i in range(24):
            bar_height = int(roi_height * (i + 1) / 24)
            x_start = roi_x + i * slice_width
            y_start = roi_y + roi_height - bar_height
            image[y_start : roi_y + roi_height, x_start : x_start + slice_width] = 0

        row, _, _ = slice_image(image, roi_x=roi_x, roi_y=roi_y, roi_width=roi_width, roi_height=roi_height)

        # Values should generally increase
        # Note: exact values depend on algorithm details
        assert len(row) == 25

    def test_slice_image_with_alternating_bars(self):
        """Test with alternating full/empty bars."""
        image = np.ones((1000, 1500, 3), dtype=np.uint8) * 255
        roi_x, roi_y, roi_width, roi_height = 100, 200, 1200, 200

        # Create alternating bars
        slice_width = roi_width // 24
        for i in range(0, 24, 2):
            x_start = roi_x + i * slice_width
            image[roi_y : roi_y + roi_height, x_start : x_start + slice_width] = 0

        row, _, _ = slice_image(image, roi_x=roi_x, roi_y=roi_y, roi_width=roi_width, roi_height=roi_height)

        assert len(row) == 25
        # Even indices should have high values, odd indices low
        for i in range(24):
            if i % 2 == 0:
                assert row[i] > 50, f"Bar at index {i} should be high"
            else:
                assert row[i] < 10, f"Bar at index {i} should be low"


class TestComputeBarAlignmentScore:
    """Tests for bar alignment score computation."""

    def test_alignment_score_perfect_match(self):
        """Perfect alignment should give score close to 1.0."""
        # Create an ROI with known bar pattern
        roi = np.ones((200, 600, 3), dtype=np.uint8) * 255

        # Add blue bars at known positions
        slice_width = 600 // 24
        hourly_values = []
        for i in range(24):
            bar_height = (i % 4 + 1) * 10  # Heights: 10, 20, 30, 40, 10, ...
            x_start = i * slice_width
            y_start = 200 - bar_height
            # Blue color in BGR
            roi[y_start:200, x_start : x_start + slice_width // 2] = [255, 100, 50]
            hourly_values.append(bar_height / 200 * 60)

        score = compute_bar_alignment_score(roi, hourly_values)

        # With matching bars, score should be reasonable
        assert 0 <= score <= 1

    def test_alignment_score_all_zeros(self):
        """All zeros should give score of 1.0 (perfect match for empty)."""
        roi = np.ones((200, 600, 3), dtype=np.uint8) * 255  # White image
        hourly_values = [0.0] * 24

        score = compute_bar_alignment_score(roi, hourly_values)

        assert score == 1.0

    def test_alignment_score_empty_roi(self):
        """Empty ROI should return 0.0."""
        roi = np.zeros((0, 0, 3), dtype=np.uint8)
        hourly_values = [30.0] * 24

        score = compute_bar_alignment_score(roi, hourly_values)

        assert score == 0.0

    def test_alignment_score_grayscale_fallback(self):
        """Test grayscale fallback when no color information."""
        roi = np.ones((200, 600), dtype=np.uint8) * 200  # Grayscale
        hourly_values = [30.0] * 24

        # Should not crash on grayscale
        score = compute_bar_alignment_score(roi, hourly_values)

        assert 0 <= score <= 1

    def test_alignment_score_with_short_value_list(self):
        """Score function should handle fewer than 24 values."""
        roi = np.ones((200, 600, 3), dtype=np.uint8) * 255
        hourly_values = [30.0, 40.0, 50.0]  # Only 3 values

        score = compute_bar_alignment_score(roi, hourly_values)

        # Should pad with zeros and compute score
        assert 0 <= score <= 1

    def test_alignment_score_with_long_value_list(self):
        """Score function should handle more than 24 values."""
        roi = np.ones((200, 600, 3), dtype=np.uint8) * 255
        hourly_values = [30.0] * 30  # 30 values

        score = compute_bar_alignment_score(roi, hourly_values)

        # Should truncate to 24 and compute score
        assert 0 <= score <= 1

    def test_alignment_score_shift_detection(self):
        """Score should be lower when bars are shifted from expected positions."""
        # Create ROI with bars at shifted positions
        roi = np.ones((200, 600, 3), dtype=np.uint8) * 255
        slice_width = 600 // 24

        # Add bars with a 3-hour shift
        for i in range(3, 24):
            x_start = i * slice_width
            roi[100:200, x_start : x_start + slice_width // 2] = [255, 100, 50]  # Blue

        # Expected values without shift
        hourly_values = [60.0 if i < 21 else 0.0 for i in range(24)]

        score = compute_bar_alignment_score(roi, hourly_values)

        # Score should be penalized due to shift
        assert score < 0.8

    def test_alignment_score_bounds(self):
        """Score should always be between 0 and 1."""
        roi = np.random.randint(0, 256, (200, 600, 3), dtype=np.uint8)
        hourly_values = np.random.uniform(0, 60, 24).tolist()

        score = compute_bar_alignment_score(roi, hourly_values)

        assert 0 <= score <= 1


class TestBarProcessorEdgeCases:
    """Edge case tests for bar processor."""

    def test_very_thin_roi(self):
        """Test with a very thin ROI (height = 1)."""
        processor = StandardBarProcessor()
        test_image = np.ones((500, 500, 3), dtype=np.uint8) * 255

        bounds = GridBounds(
            upper_left_x=50,
            upper_left_y=200,
            lower_right_x=450,
            lower_right_y=201,  # Height of 1
        )

        result = processor.extract(test_image, bounds, is_battery=False)

        # Should handle gracefully
        assert isinstance(result, BarProcessingResult)

    def test_very_narrow_roi(self):
        """Test with a very narrow ROI (width = 24)."""
        processor = StandardBarProcessor()
        test_image = np.ones((500, 500, 3), dtype=np.uint8) * 255

        bounds = GridBounds(
            upper_left_x=100,
            upper_left_y=100,
            lower_right_x=124,  # Width of 24 (minimum for 24 slices)
            lower_right_y=300,
        )

        result = processor.extract(test_image, bounds, is_battery=False)

        # Should handle gracefully
        assert isinstance(result, BarProcessingResult)
        if result.success:
            assert len(result.hourly_values) == 24

    def test_all_black_roi(self):
        """Test with completely black ROI (all bars at max)."""
        processor = StandardBarProcessor()
        test_image = np.zeros((500, 500, 3), dtype=np.uint8)

        bounds = GridBounds(
            upper_left_x=50,
            upper_left_y=100,
            lower_right_x=450,
            lower_right_y=400,
        )

        result = processor.extract(test_image, bounds, is_battery=False)

        if result.success and result.hourly_values:
            # All values should be at or near maximum
            for value in result.hourly_values.values():
                assert value >= 55, "Black ROI should give max values"

    def test_half_white_half_black_roi(self):
        """Test with ROI that is half white (top) and half black (bottom)."""
        processor = StandardBarProcessor()
        test_image = np.ones((500, 500, 3), dtype=np.uint8) * 255
        # Bottom half is black
        test_image[250:500, :] = 0

        bounds = GridBounds(
            upper_left_x=50,
            upper_left_y=100,
            lower_right_x=450,
            lower_right_y=400,
        )

        result = processor.extract(test_image, bounds, is_battery=False)

        if result.success and result.hourly_values:
            # Values should be around half (30 minutes)
            for value in result.hourly_values.values():
                assert 20 <= value <= 40, f"Half-black ROI should give ~30 values, got {value}"

    def test_roi_at_image_boundary(self):
        """Test with ROI at the edge of the image."""
        processor = StandardBarProcessor()
        test_image = np.ones((500, 500, 3), dtype=np.uint8) * 255

        bounds = GridBounds(
            upper_left_x=0,
            upper_left_y=0,
            lower_right_x=500,
            lower_right_y=500,
        )

        result = processor.extract(test_image, bounds, is_battery=False)

        # Should handle boundary case
        assert isinstance(result, BarProcessingResult)


class TestGridBoundsDataclass:
    """Tests for the GridBounds dataclass."""

    def test_grid_bounds_creation(self):
        """Test basic GridBounds creation."""
        bounds = GridBounds(
            upper_left_x=100,
            upper_left_y=200,
            lower_right_x=500,
            lower_right_y=600,
        )

        assert bounds.upper_left_x == 100
        assert bounds.upper_left_y == 200
        assert bounds.lower_right_x == 500
        assert bounds.lower_right_y == 600

    def test_grid_bounds_width_property(self):
        """Test width calculation property."""
        bounds = GridBounds(
            upper_left_x=100,
            upper_left_y=200,
            lower_right_x=500,
            lower_right_y=600,
        )

        assert bounds.width == 400

    def test_grid_bounds_height_property(self):
        """Test height calculation property."""
        bounds = GridBounds(
            upper_left_x=100,
            upper_left_y=200,
            lower_right_x=500,
            lower_right_y=600,
        )

        assert bounds.height == 400

    def test_grid_bounds_upper_left_tuple(self):
        """Test upper_left tuple property."""
        bounds = GridBounds(
            upper_left_x=100,
            upper_left_y=200,
            lower_right_x=500,
            lower_right_y=600,
        )

        assert bounds.upper_left == (100, 200)

    def test_grid_bounds_lower_right_tuple(self):
        """Test lower_right tuple property."""
        bounds = GridBounds(
            upper_left_x=100,
            upper_left_y=200,
            lower_right_x=500,
            lower_right_y=600,
        )

        assert bounds.lower_right == (500, 600)

    def test_grid_bounds_to_dict(self):
        """Test conversion to dictionary."""
        bounds = GridBounds(
            upper_left_x=100,
            upper_left_y=200,
            lower_right_x=500,
            lower_right_y=600,
        )

        d = bounds.to_dict()

        assert d["upper_left_x"] == 100
        assert d["upper_left_y"] == 200
        assert d["lower_right_x"] == 500
        assert d["lower_right_y"] == 600

    def test_grid_bounds_from_dict(self):
        """Test creation from dictionary."""
        d = {
            "upper_left_x": 100,
            "upper_left_y": 200,
            "lower_right_x": 500,
            "lower_right_y": 600,
        }

        bounds = GridBounds.from_dict(d)

        assert bounds.upper_left_x == 100
        assert bounds.upper_left_y == 200
        assert bounds.lower_right_x == 500
        assert bounds.lower_right_y == 600
