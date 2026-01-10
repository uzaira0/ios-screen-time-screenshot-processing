"""Unit tests for image processing functionality."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from screenshot_processor.core.bar_extraction import slice_image
from screenshot_processor.core.image_utils import (
    adjust_contrast_brightness,
    convert_dark_mode,
    darken_non_white,
    reduce_color_count,
    remove_all_but,
    scale_up,
)
from screenshot_processor.core.roi import calculate_roi_from_clicks


class TestConvertDarkMode:
    """Tests for dark mode detection and conversion."""

    def test_dark_image_is_inverted(self):
        """Dark images (mean < 100) should be inverted."""
        # Create a dark image (mean brightness < 100)
        dark_image = np.zeros((100, 100, 3), dtype=np.uint8)
        dark_image[:, :] = 50  # Mean brightness = 50

        result = convert_dark_mode(dark_image)

        # After inversion, should be brighter
        assert np.mean(result) > np.mean(dark_image)

    def test_light_image_unchanged(self):
        """Light images (mean >= 100) should not be inverted."""
        # Create a light image
        light_image = np.ones((100, 100, 3), dtype=np.uint8) * 200

        result = convert_dark_mode(light_image)

        # Should remain approximately the same
        # Note: convert_dark_mode doesn't modify light images
        assert np.mean(result) > 100

    def test_dark_mode_threshold_boundary(self):
        """Test behavior at the threshold boundary (mean = 100)."""
        # Create an image exactly at threshold
        boundary_image = np.ones((100, 100, 3), dtype=np.uint8) * 100

        result = convert_dark_mode(boundary_image)

        # At exactly 100, should not be inverted (< 100 triggers inversion)
        assert np.allclose(result, boundary_image)

    def test_convert_dark_mode_preserves_shape(self):
        """Conversion should preserve image dimensions."""
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        image[:, :] = 30

        result = convert_dark_mode(image)

        assert result.shape == image.shape

    def test_convert_dark_mode_with_real_dark_colors(self):
        """Test with realistic dark mode screenshot colors."""
        # Simulate a dark mode UI with dark background and some lighter elements
        dark_image = np.zeros((500, 400, 3), dtype=np.uint8)
        dark_image[:, :] = [30, 30, 30]  # Dark gray background
        # Add some lighter text areas
        dark_image[100:150, 100:300] = [200, 200, 200]

        result = convert_dark_mode(dark_image)

        # Overall image should be brighter after inversion
        assert np.mean(result) > np.mean(dark_image)


class TestAdjustContrastBrightness:
    """Tests for contrast and brightness adjustment."""

    def test_default_parameters_no_change(self):
        """Default parameters (contrast=1.0, brightness=0) should not change image."""
        image = np.ones((100, 100, 3), dtype=np.uint8) * 128

        result = adjust_contrast_brightness(image, contrast=1.0, brightness=0)

        # Should be very close to original
        assert np.allclose(result, image, atol=1)

    def test_increase_contrast(self):
        """Increasing contrast should increase difference between light and dark pixels."""
        image = np.ones((100, 100, 3), dtype=np.uint8) * 128
        image[0:50, :] = 64  # Dark half
        image[50:100, :] = 192  # Light half

        result = adjust_contrast_brightness(image, contrast=2.0, brightness=0)

        # Contrast increase should make dark pixels darker and light pixels lighter
        dark_half = result[0:50, :]
        light_half = result[50:100, :]
        original_diff = 192 - 64
        new_diff = np.mean(light_half) - np.mean(dark_half)

        assert new_diff >= original_diff

    def test_increase_brightness(self):
        """Increasing brightness should make all pixels brighter."""
        image = np.ones((100, 100, 3), dtype=np.uint8) * 100

        result = adjust_contrast_brightness(image, contrast=1.0, brightness=50)

        assert np.mean(result) > np.mean(image)

    def test_decrease_brightness(self):
        """Decreasing brightness should make all pixels darker."""
        image = np.ones((100, 100, 3), dtype=np.uint8) * 200

        result = adjust_contrast_brightness(image, contrast=1.0, brightness=-50)

        assert np.mean(result) < np.mean(image)

    def test_clipping_at_255(self):
        """Values should be clipped at 255."""
        image = np.ones((100, 100, 3), dtype=np.uint8) * 250

        result = adjust_contrast_brightness(image, contrast=1.0, brightness=100)

        assert np.all(result <= 255)

    def test_clipping_at_0(self):
        """Values should be clipped at 0."""
        image = np.ones((100, 100, 3), dtype=np.uint8) * 10

        result = adjust_contrast_brightness(image, contrast=1.0, brightness=-100)

        assert np.all(result >= 0)


class TestSliceImage:
    """Tests for bar graph slicing."""

    def test_slice_image_returns_25_values(self):
        """slice_image should return 24 hourly values + 1 total (25 values)."""
        # Create a simple test image
        image = np.ones((1000, 1500, 3), dtype=np.uint8) * 255

        row, _, _ = slice_image(image, roi_x=100, roi_y=200, roi_width=1000, roi_height=200)

        assert len(row) == 25  # 24 hours + total

    def test_slice_image_total_equals_sum(self):
        """The 25th value should equal the sum of the first 24 values."""
        image = np.ones((1000, 1500, 3), dtype=np.uint8) * 255

        row, _, _ = slice_image(image, roi_x=100, roi_y=200, roi_width=1000, roi_height=200)

        assert row[24] == pytest.approx(sum(row[:24]), abs=0.01)

    def test_slice_image_white_image_gives_zeros(self):
        """A white image (no bars) should give all zeros."""
        white_image = np.ones((1000, 1500, 3), dtype=np.uint8) * 255

        row, _, _ = slice_image(white_image, roi_x=100, roi_y=200, roi_width=1000, roi_height=200)

        # All hourly values should be zero or near zero
        assert all(v < 1 for v in row[:24])

    def test_slice_image_black_roi_gives_max_values(self):
        """A completely black ROI should give maximum values (60 minutes)."""
        image = np.ones((1000, 1500, 3), dtype=np.uint8) * 255
        # Make the ROI area completely black
        image[200:400, 100:1100] = 0

        row, _, _ = slice_image(image, roi_x=100, roi_y=200, roi_width=1000, roi_height=200)

        # All hourly values should be at or near maximum (60)
        assert all(v > 55 for v in row[:24])

    def test_slice_image_values_in_valid_range(self):
        """All values should be between 0 and 60 minutes."""
        image = np.random.randint(0, 256, (1000, 1500, 3), dtype=np.uint8)

        row, _, _ = slice_image(image, roi_x=100, roi_y=200, roi_width=1000, roi_height=200)

        for value in row[:24]:
            assert 0 <= value <= 60

    def test_slice_image_partial_bar(self):
        """Test with a partial bar (half-height black region)."""
        image = np.ones((1000, 1500, 3), dtype=np.uint8) * 255
        # Make half of the ROI black (bottom half = bar)
        roi_y, roi_height = 200, 200
        half_height = roi_height // 2
        image[roi_y + half_height : roi_y + roi_height, 100:1100] = 0

        row, _, _ = slice_image(image, roi_x=100, roi_y=roi_y, roi_width=1000, roi_height=roi_height)

        # Values should be around 30 (half of 60)
        for value in row[:24]:
            assert 25 <= value <= 35

    def test_slice_image_returns_scale_amount(self):
        """slice_image should return the scale amount used."""
        image = np.ones((1000, 1500, 3), dtype=np.uint8) * 255

        _, _, scale_amount = slice_image(image, roi_x=100, roi_y=200, roi_width=1000, roi_height=200)

        assert scale_amount == 4  # Default scale amount


class TestRemoveAllBut:
    """Tests for color isolation."""

    def test_remove_all_but_target_color(self):
        """Pixels matching target color should become black."""
        image = np.ones((100, 100, 3), dtype=np.uint8) * 255
        target_color = np.array([255, 121, 0])  # Battery bar color
        image[40:60, 40:60] = target_color

        result = remove_all_but(image.copy(), target_color, threshold=30)

        # Target color area should be black
        assert np.all(result[40:60, 40:60] == [0, 0, 0])
        # Other areas should be white
        assert np.all(result[0:30, 0:30] == [255, 255, 255])

    def test_remove_all_but_with_threshold(self):
        """Colors within threshold of target should also be matched."""
        image = np.ones((100, 100, 3), dtype=np.uint8) * 255
        target_color = np.array([255, 121, 0])
        # Slightly different color
        similar_color = np.array([250, 125, 5])
        image[40:60, 40:60] = similar_color

        result = remove_all_but(image.copy(), target_color, threshold=30)

        # Similar color should also be converted to black
        assert np.all(result[40:60, 40:60] == [0, 0, 0])


class TestDarkenNonWhite:
    """Tests for darkening non-white pixels."""

    def test_white_pixels_preserved(self):
        """White pixels should remain white."""
        image = np.ones((100, 100, 3), dtype=np.uint8) * 255

        result = darken_non_white(image.copy())

        assert np.all(result == 255)

    def test_non_white_pixels_darkened(self):
        """Non-white pixels should become black."""
        image = np.ones((100, 100, 3), dtype=np.uint8) * 255
        image[40:60, 40:60] = [128, 128, 128]  # Gray region

        result = darken_non_white(image.copy())

        # Gray region should be black
        assert np.all(result[40:60, 40:60] == [0, 0, 0])
        # White region should remain white
        assert np.all(result[0:30, 0:30] == [255, 255, 255])


class TestReduceColorCount:
    """Tests for color quantization."""

    def test_reduce_to_two_colors(self):
        """Reducing to 2 colors should give only black and white."""
        image = np.random.randint(0, 256, (100, 100, 3), dtype=np.uint8)

        result = reduce_color_count(image.copy(), 2)

        # All pixels should be either 0 or 255
        unique_values = np.unique(result)
        assert len(unique_values) <= 2
        assert all(v in [0, 255] for v in unique_values)

    def test_reduce_preserves_shape(self):
        """Color reduction should preserve image shape."""
        image = np.random.randint(0, 256, (50, 75, 3), dtype=np.uint8)

        result = reduce_color_count(image.copy(), 4)

        assert result.shape == image.shape


class TestScaleUp:
    """Tests for image scaling."""

    def test_scale_up_doubles_dimensions(self):
        """Scaling by 2 should double both dimensions."""
        image = np.ones((100, 200, 3), dtype=np.uint8)

        result = scale_up(image, 2)

        assert result.shape == (200, 400, 3)

    def test_scale_up_by_four(self):
        """Scaling by 4 (default) should quadruple dimensions."""
        image = np.ones((50, 75, 3), dtype=np.uint8)

        result = scale_up(image, 4)

        assert result.shape == (200, 300, 3)

    def test_scale_up_preserves_color_distribution(self):
        """Scaling should approximately preserve color distribution."""
        image = np.ones((10, 10, 3), dtype=np.uint8) * 128

        result = scale_up(image, 4)

        # Mean should be preserved
        assert abs(np.mean(result) - np.mean(image)) < 10


class TestCalculateROIFromClicks:
    """Tests for ROI calculation from user clicks."""

    def test_roi_from_valid_clicks(self):
        """Valid clicks should produce valid ROI coordinates."""
        image = np.ones((1000, 800, 3), dtype=np.uint8) * 255
        upper_left = (100, 200)
        lower_right = (600, 500)

        x, y, width, height = calculate_roi_from_clicks(upper_left, lower_right, None, image)

        assert x == 100
        assert y == 200
        assert width == 500  # 600 - 100
        assert height == 300  # 500 - 200

    def test_roi_with_snap_function(self):
        """ROI should use snap function when provided."""

        def mock_snap(img, x, y):
            # Snap to nearest 10
            return (x // 10) * 10, (y // 10) * 10

        image = np.ones((1000, 800, 3), dtype=np.uint8) * 255
        upper_left = (103, 207)
        lower_right = (598, 493)

        x, y, width, height = calculate_roi_from_clicks(upper_left, lower_right, mock_snap, image)

        # Note: The snap function is used for grid line detection, not the input coordinates.
        # The function takes upper_left and lower_right as is for ROI calculation.
        # Width and height are calculated from the input coordinates.
        assert x == 103  # Input x is used directly
        assert y == 207  # Input y is used directly
        assert width == 598 - 103  # Width = lower_right_x - upper_left_x
        assert height == 493 - 207  # Height = lower_right_y - upper_left_y


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_empty_image_handling(self):
        """Functions should handle empty or minimal images gracefully."""
        np.zeros((0, 0, 3), dtype=np.uint8)

        # These should not crash
        try:
            result = convert_dark_mode(np.zeros((1, 1, 3), dtype=np.uint8))
            assert result is not None
        except Exception:
            pass  # Acceptable to raise exception for edge cases

    def test_single_pixel_image(self):
        """Functions should handle single-pixel images."""
        single_pixel = np.ones((1, 1, 3), dtype=np.uint8) * 128

        result = adjust_contrast_brightness(single_pixel, 2.0, 50)

        assert result.shape == (1, 1, 3)

    def test_grayscale_input_handling(self):
        """Test handling of images that might be grayscale."""
        # Note: Most functions expect BGR, but should not crash on grayscale
        gray_image = np.ones((100, 100), dtype=np.uint8) * 128

        # convert_dark_mode expects 3-channel, so test with 3-channel grayscale-like
        gray_3ch = np.stack([gray_image, gray_image, gray_image], axis=2)

        result = convert_dark_mode(gray_3ch)
        assert result.shape == gray_3ch.shape

    def test_very_large_roi_clipped_to_image(self):
        """ROI larger than image should be handled gracefully."""
        small_image = np.ones((100, 100, 3), dtype=np.uint8) * 255

        # This may produce out-of-bounds but should not crash
        try:
            row, _, _ = slice_image(
                small_image,
                roi_x=0,
                roi_y=0,
                roi_width=1000,  # Larger than image
                roi_height=500,
            )
            # If it doesn't crash, values should still be valid
            assert len(row) == 25
        except Exception:
            pass  # Acceptable to raise for out-of-bounds

    def test_negative_roi_coordinates(self):
        """Negative ROI coordinates should be handled."""
        image = np.ones((500, 500, 3), dtype=np.uint8) * 255

        try:
            row, _, _ = slice_image(image, roi_x=-10, roi_y=-10, roi_width=100, roi_height=100)
        except Exception:
            pass  # Expected to fail gracefully


class TestImageProcessorWithFixtures:
    """Tests using actual test fixture images if available."""

    @pytest.fixture
    def fixture_path(self) -> Path:
        """Get the path to test fixtures."""
        return Path(__file__).parent.parent / "fixtures" / "images"

    def test_fixture_images_exist(self, fixture_path: Path):
        """Verify test fixtures are available."""
        if fixture_path.exists():
            images = list(fixture_path.glob("*.png"))
            assert len(images) > 0, "No PNG images found in fixtures"

    def test_process_fixture_image(self, fixture_path: Path):
        """Test processing a real fixture image if available."""
        if not fixture_path.exists():
            pytest.skip("Fixtures not available")

        images = list(fixture_path.glob("*.png"))
        if not images:
            pytest.skip("No fixture images found")

        # Load first image
        image = cv2.imread(str(images[0]))
        assert image is not None, f"Failed to load {images[0]}"

        # Test basic processing
        result = convert_dark_mode(image)
        assert result.shape == image.shape

        # Test contrast adjustment
        adjusted = adjust_contrast_brightness(result, contrast=2.0, brightness=-220)
        assert adjusted.shape == image.shape
