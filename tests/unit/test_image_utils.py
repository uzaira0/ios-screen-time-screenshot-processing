"""Unit tests for image_utils module — image manipulation utilities."""

from __future__ import annotations

import numpy as np
import pytest

from screenshot_processor.core.image_utils import (
    adjust_contrast_brightness,
    convert_dark_mode,
    darken_non_white,
    extract_line,
    extract_line_snap_to_grid,
    get_pixel,
    is_close,
    reduce_color_count,
    remove_all_but,
    remove_line_color,
    scale_up,
)
from screenshot_processor.core.models import LineExtractionMode


# ---------------------------------------------------------------------------
# convert_dark_mode
# ---------------------------------------------------------------------------
class TestConvertDarkMode:
    def test_inverts_dark_image(self):
        img = np.full((50, 50, 3), 30, dtype=np.uint8)
        result = convert_dark_mode(img)
        assert np.mean(result) > 100

    def test_leaves_light_image_unchanged(self):
        img = np.full((50, 50, 3), 200, dtype=np.uint8)
        original = img.copy()
        result = convert_dark_mode(img)
        np.testing.assert_array_equal(result, original)

    def test_boundary_value_not_inverted(self):
        img = np.full((50, 50, 3), 100, dtype=np.uint8)
        original = img.copy()
        result = convert_dark_mode(img)
        np.testing.assert_array_equal(result, original)

    def test_just_below_threshold_inverted(self):
        img = np.full((50, 50, 3), 99, dtype=np.uint8)
        result = convert_dark_mode(img)
        assert np.mean(result) > np.mean(np.full((50, 50, 3), 99, dtype=np.uint8))

    def test_preserves_shape(self):
        img = np.full((120, 80, 3), 20, dtype=np.uint8)
        result = convert_dark_mode(img)
        assert result.shape == (120, 80, 3)


# ---------------------------------------------------------------------------
# adjust_contrast_brightness
# ---------------------------------------------------------------------------
class TestAdjustContrastBrightness:
    def test_identity_transform(self):
        img = np.full((30, 30, 3), 128, dtype=np.uint8)
        result = adjust_contrast_brightness(img, 1.0, 0)
        np.testing.assert_allclose(result, img, atol=1)

    def test_brightness_increase(self):
        img = np.full((30, 30, 3), 100, dtype=np.uint8)
        result = adjust_contrast_brightness(img, 1.0, 50)
        assert np.mean(result) > np.mean(img)

    def test_brightness_decrease(self):
        img = np.full((30, 30, 3), 200, dtype=np.uint8)
        result = adjust_contrast_brightness(img, 1.0, -50)
        assert np.mean(result) < np.mean(img)

    def test_high_contrast_widens_range(self):
        img = np.zeros((30, 30, 3), dtype=np.uint8)
        img[:15] = 64
        img[15:] = 192
        result = adjust_contrast_brightness(img, 2.0, 0)
        assert np.mean(result[15:]) - np.mean(result[:15]) >= 192 - 64

    def test_clips_above_255(self):
        img = np.full((10, 10, 3), 250, dtype=np.uint8)
        result = adjust_contrast_brightness(img, 1.0, 100)
        assert np.all(result <= 255)

    def test_clips_below_0(self):
        img = np.full((10, 10, 3), 5, dtype=np.uint8)
        result = adjust_contrast_brightness(img, 1.0, -100)
        assert np.all(result >= 0)


# ---------------------------------------------------------------------------
# get_pixel
# ---------------------------------------------------------------------------
class TestGetPixel:
    def test_returns_second_most_common_pixel(self):
        img = np.zeros((10, 10, 3), dtype=np.uint8)
        img[:5] = [255, 255, 255]
        result = get_pixel(img, -2)
        assert result is not None
        # -2 = second from the end of sorted unique pixels by count

    def test_uniform_image_returns_none(self):
        img = np.full((10, 10, 3), 128, dtype=np.uint8)
        result = get_pixel(img, -2)
        assert result is None

    def test_arg_exceeds_unique_count(self):
        img = np.zeros((10, 10, 3), dtype=np.uint8)
        img[0, 0] = [1, 1, 1]
        # Only 2 unique colors, arg=-5 should clamp
        result = get_pixel(img, -5)
        assert result is not None


# ---------------------------------------------------------------------------
# is_close
# ---------------------------------------------------------------------------
class TestIsClose:
    def test_identical_pixels(self):
        assert is_close(np.array([100, 100, 100]), np.array([100, 100, 100]))

    def test_within_default_threshold(self):
        assert is_close(np.array([100, 100, 100]), np.array([101, 100, 100]))

    def test_outside_default_threshold(self):
        assert not is_close(np.array([100, 100, 100]), np.array([110, 110, 110]))

    def test_custom_threshold(self):
        assert is_close(np.array([100, 100, 100]), np.array([110, 110, 110]), thresh=10)

    def test_with_arrays_from_lists(self):
        assert is_close(np.array([100, 100, 100]), np.array([101, 100, 100]))


# ---------------------------------------------------------------------------
# reduce_color_count
# ---------------------------------------------------------------------------
class TestReduceColorCount:
    def test_two_colors_binary(self):
        img = np.array([0, 64, 128, 192, 255], dtype=np.uint8)
        result = reduce_color_count(img.copy(), 2)
        unique = np.unique(result)
        assert len(unique) <= 2

    def test_preserves_shape(self):
        img = np.random.randint(0, 256, (20, 20, 3), dtype=np.uint8)
        result = reduce_color_count(img.copy(), 3)
        assert result.shape == (20, 20, 3)


# ---------------------------------------------------------------------------
# remove_all_but
# ---------------------------------------------------------------------------
class TestRemoveAllBut:
    def test_matching_pixels_become_black(self):
        img = np.full((10, 10, 3), 128, dtype=np.uint8)
        target = np.array([128, 128, 128])
        result = remove_all_but(img.copy(), target, threshold=5)
        assert np.all(result == [0, 0, 0])

    def test_non_matching_pixels_become_white(self):
        img = np.full((10, 10, 3), 50, dtype=np.uint8)
        target = np.array([200, 200, 200])
        result = remove_all_but(img.copy(), target, threshold=5)
        assert np.all(result == [255, 255, 255])

    def test_threshold_boundary(self):
        img = np.full((5, 5, 3), 100, dtype=np.uint8)
        target = np.array([130, 100, 100])
        result_tight = remove_all_but(img.copy(), target, threshold=10)
        assert np.all(result_tight == [255, 255, 255])
        result_loose = remove_all_but(img.copy(), target, threshold=40)
        assert np.all(result_loose == [0, 0, 0])


# ---------------------------------------------------------------------------
# darken_non_white
# ---------------------------------------------------------------------------
class TestDarkenNonWhite:
    def test_white_pixels_preserved(self):
        img = np.full((10, 10, 3), 255, dtype=np.uint8)
        result = darken_non_white(img.copy())
        assert np.all(result == 255)

    def test_gray_pixels_become_black(self):
        img = np.full((10, 10, 3), 128, dtype=np.uint8)
        result = darken_non_white(img.copy())
        assert np.all(result == 0)


# ---------------------------------------------------------------------------
# scale_up
# ---------------------------------------------------------------------------
class TestScaleUp:
    def test_doubles_dimensions(self):
        img = np.ones((40, 60, 3), dtype=np.uint8)
        result = scale_up(img, 2)
        assert result.shape == (80, 120, 3)

    def test_quadruples(self):
        img = np.ones((10, 15, 3), dtype=np.uint8)
        result = scale_up(img, 4)
        assert result.shape == (40, 60, 3)

    def test_fractional_scale(self):
        img = np.ones((20, 20, 3), dtype=np.uint8)
        result = scale_up(img, 1.5)
        assert result.shape == (30, 30, 3)


# ---------------------------------------------------------------------------
# remove_line_color
# ---------------------------------------------------------------------------
class TestRemoveLineColor:
    def test_replaces_line_color_with_white(self):
        line_color = np.array([203, 199, 199], dtype=np.uint8)
        img = np.full((5, 5, 3), 0, dtype=np.uint8)
        img[2, :] = line_color
        result = remove_line_color(img.copy())
        assert np.all(result[2, :] == [255, 255, 255])
        # Non-line-color rows unchanged
        assert np.all(result[0, :] == [0, 0, 0])


# ---------------------------------------------------------------------------
# extract_line — horizontal and vertical
# ---------------------------------------------------------------------------
class TestExtractLine:
    def _make_horizontal_line_image(self, h=50, w=50, line_row=20):
        """Create a white image with a black horizontal line at line_row."""
        img = np.full((h, w, 3), 255, dtype=np.uint8)
        img[line_row, :] = 0
        return img

    def _make_vertical_line_image(self, h=50, w=50, line_col=15):
        """Create a white image with a black vertical line at line_col."""
        img = np.full((h, w, 3), 255, dtype=np.uint8)
        img[:, line_col] = 0
        return img

    def test_horizontal_line_detected(self):
        img = self._make_horizontal_line_image(line_row=20)
        result = extract_line(img, 0, 50, 0, 50, LineExtractionMode.HORIZONTAL)
        assert result == 20

    def test_vertical_line_detected(self):
        img = self._make_vertical_line_image(line_col=15)
        result = extract_line(img, 0, 50, 0, 50, LineExtractionMode.VERTICAL)
        assert result == 15

    def test_no_line_returns_zero(self):
        img = np.full((50, 50, 3), 255, dtype=np.uint8)
        result = extract_line(img, 0, 50, 0, 50, LineExtractionMode.HORIZONTAL)
        assert result == 0

    def test_invalid_mode_raises(self):
        """Passing a non-enum mode should raise ValueError from StrEnum or from the function."""
        img = np.full((10, 10, 3), 128, dtype=np.uint8)
        with pytest.raises((ValueError, KeyError)):
            extract_line(img, 0, 10, 0, 10, LineExtractionMode("diagonal"))

    def test_uniform_subimage_returns_zero(self):
        img = np.full((30, 30, 3), 100, dtype=np.uint8)
        result = extract_line(img, 0, 30, 0, 30, LineExtractionMode.HORIZONTAL)
        assert result == 0


# ---------------------------------------------------------------------------
# extract_line_snap_to_grid
# ---------------------------------------------------------------------------
class TestExtractLineSnapToGrid:
    def test_horizontal_snap(self):
        img = np.full((50, 50, 3), 255, dtype=np.uint8)
        img[25, :] = 0  # strong horizontal line
        result = extract_line_snap_to_grid(img, 0, 50, 0, 50, LineExtractionMode.HORIZONTAL)
        assert result == 25

    def test_vertical_snap(self):
        img = np.full((50, 50, 3), 255, dtype=np.uint8)
        img[:, 10] = 0
        result = extract_line_snap_to_grid(img, 0, 50, 0, 50, LineExtractionMode.VERTICAL)
        assert result == 10

    def test_uniform_returns_none(self):
        img = np.full((30, 30, 3), 100, dtype=np.uint8)
        result = extract_line_snap_to_grid(img, 0, 30, 0, 30, LineExtractionMode.HORIZONTAL)
        assert result is None
