# pyright: reportPossiblyUnboundVariable=false
"""Cross-implementation parity tests: Python backend vs TypeScript/WASM frontend.

Both the Python backend and the TypeScript WASM frontend implement the same
algorithms for bar extraction, grid detection, dark mode handling, alignment
scoring, and time parsing. These tests define known input/output fixtures from
the Python side and verify the Python functions produce them. The inline
constants serve as a contract: the TypeScript implementation MUST produce
identical results for the same inputs.

Each test documents the corresponding TypeScript function that must match.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Guard imports
# ---------------------------------------------------------------------------
try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    from screenshot_processor.core.bar_extraction import (
        compute_bar_alignment_score,
        slice_image,
    )

    HAS_BAR_EXTRACTION = True
except ImportError:
    HAS_BAR_EXTRACTION = False

try:
    from screenshot_processor.core.image_utils import (
        convert_dark_mode,
        darken_non_white,
        reduce_color_count,
        scale_up,
    )

    HAS_IMAGE_UTILS = True
except ImportError:
    HAS_IMAGE_UTILS = False

try:
    from screenshot_processor.core.roi import calculate_roi_from_clicks

    HAS_ROI = True
except ImportError:
    HAS_ROI = False

try:
    from screenshot_processor.core.ocr import (
        _extract_time_from_text,
        _normalize_ocr_digits,
    )

    HAS_OCR = True
except ImportError:
    HAS_OCR = False

try:
    from screenshot_processor.core.interfaces import GridBounds

    HAS_INTERFACES = True
except ImportError:
    HAS_INTERFACES = False


# ============================================================================
# 1. compute_bar_alignment_score parity
#    TS: computeBarAlignmentScore() in barExtraction.canvas.ts
# ============================================================================


@pytest.mark.skipif(
    not (HAS_BAR_EXTRACTION and HAS_NUMPY),
    reason="bar_extraction or numpy unavailable",
)
class TestBarAlignmentScoreParity:
    """Python compute_bar_alignment_score must match TS computeBarAlignmentScore."""

    def test_perfect_alignment_both_zero(self):
        """When both extracted and computed are all zeros, score = 1.0.

        TS equivalent:
          computeBarAlignmentScore(emptyROI, {0:0, 1:0, ..., 23:0}) === 1.0
        """
        # Create a plain white ROI (no blue bars)
        roi = np.full((100, 480, 3), 255, dtype=np.uint8)
        hourly = [0.0] * 24
        score = compute_bar_alignment_score(roi, hourly)
        assert score == 1.0

    def test_one_side_zero_high_values(self):
        """When computed has bars but ROI has none, score should be low (0.1).

        TS equivalent:
          computeBarAlignmentScore(whiteROI, {0:30, 1:30, ...}) === 0.1
        """
        roi = np.full((100, 480, 3), 255, dtype=np.uint8)
        hourly = [30.0] * 24  # Sum > 30
        score = compute_bar_alignment_score(roi, hourly)
        assert score == pytest.approx(0.1, abs=0.01)

    def test_one_side_zero_low_values(self):
        """When computed has small bars but ROI has none, score = 0.3.

        TS equivalent:
          computeBarAlignmentScore(whiteROI, {0:1, 1:0, ...}) === 0.3
        """
        roi = np.full((100, 480, 3), 255, dtype=np.uint8)
        hourly = [1.0] + [0.0] * 23  # Sum = 1 < 30
        score = compute_bar_alignment_score(roi, hourly)
        assert score == pytest.approx(0.3, abs=0.01)

    def test_shift_penalty_applied(self):
        """Shift penalty reduces score when bar start positions differ by >= 2.

        Both Python and TS use: penalty = min(startDiff * 0.15, 0.5)

        TS equivalent:
          // Create ROI with blue bar at hour 5, computed has bar at hour 0
          // Score should have shift penalty applied
        """
        roi_height = 100
        roi_width = 480
        # Create ROI with a blue bar starting at slice 5
        roi = np.full((roi_height, roi_width, 3), 255, dtype=np.uint8)
        slice_width = roi_width // 24

        # Paint blue bars at hours 5-8
        for hour in range(5, 9):
            x_start = hour * slice_width + slice_width // 4
            x_end = hour * slice_width + 3 * slice_width // 4
            # Blue in BGR: B=200, G=100, R=50 -> HSV hue ~210 -> /2 = ~105
            roi[20:roi_height, x_start:x_end] = [200, 100, 50]

        # But computed values say bars are at hours 0-3
        hourly = [0.0] * 24
        for hour in range(0, 4):
            hourly[hour] = 40.0

        score = compute_bar_alignment_score(roi, hourly)
        # Shift of 5 -> penalty = min(5*0.15, 0.5) = 0.5
        # Score should be significantly penalized
        assert score < 0.7


# ============================================================================
# 2. Time parsing parity
#    TS: These are handled by shared time parsing logic
# ============================================================================


@pytest.mark.skipif(not HAS_OCR, reason="OCR imports unavailable")
class TestTimeParsingParity:
    """Time string parsing must match across Python and TS implementations."""

    # Expected outputs serve as the parity contract for TypeScript.
    # TS must parse these exact same strings to identical minute values.
    PARITY_CASES = [
        # (input_text, expected_output, total_minutes_comment)
        ("4h 36m", "4h 36m", "276 minutes"),
        ("2h 30m", "2h 30m", "150 minutes"),
        ("1h 0m", "1h 0m", "60 minutes"),
        ("45m", "45m", "45 minutes"),
        ("3h", "3h", "180 minutes"),
        ("12m 30s", "12m 30s", "12.5 minutes"),
        ("0m 45s", "0m 45s", "0.75 minutes"),
        ("15s", "15s", "0.25 minutes"),
        ("4h 36", "4h 36m", "276 minutes - missing m fallback"),
    ]

    @pytest.mark.parametrize("input_text, expected, _comment", PARITY_CASES)
    def test_time_extraction_parity(self, input_text: str, expected: str, _comment: str):
        """Python _extract_time_from_text must produce this exact output.

        TS equivalent:
          extractTimeFromText(input_text) === expected
        """
        result = _extract_time_from_text(input_text)
        assert result == expected

    def test_ocr_digit_normalization_parity(self):
        """OCR digit normalization produces the same corrections in both impls.

        TS equivalent:
          normalizeOcrDigits("Ih 3Om") === "1h 30m"
        """
        cases = [
            ("Ih 3Om", "1h 30m"),
            ("Oh 45m", "0h 45m"),
            ("4h Am", "4h 4m"),
        ]
        for input_text, expected in cases:
            result = _normalize_ocr_digits(input_text)
            assert result == expected, f"'{input_text}' -> '{result}', expected '{expected}'"


# ============================================================================
# 3. Bar height normalization parity
#    TS: analyzeBarHeight() in barExtraction.canvas.ts
# ============================================================================


@pytest.mark.skipif(
    not (HAS_BAR_EXTRACTION and HAS_NUMPY),
    reason="bar_extraction or numpy unavailable",
)
class TestBarHeightNormalizationParity:
    """Bar height calculation: pixel counts -> minutes (0-60 scale).

    Both Python and TS use: usage = MAX_MINUTES * counter / scaledRoiHeight

    TS equivalent:
      analyzeBarHeight(slice, middleColumn, maxHeight) returns Math.floor((60 * counter) / maxHeight)

    Note: Python keeps float precision, TS uses Math.floor. This is a known
    parity difference documented here.
    """

    def test_full_bar_height(self):
        """A column that is entirely black should produce 60 minutes.

        Python: 60 * roi_height * scale / (roi_height * scale) = 60.0
        TS:     Math.floor(60 * maxHeight / maxHeight) = 60
        """
        roi_height = 50
        roi_width = 24  # minimal width, one pixel per slice
        scale_amount = 4

        # Create an ROI that is entirely black (all bars = max)
        roi = np.zeros((roi_height, roi_width, 3), dtype=np.uint8)

        row, _, _ = slice_image(roi, 0, 0, roi_width, roi_height)

        # Each hour should be 60 minutes (full height)
        for i in range(24):
            assert row[i] == pytest.approx(60.0, abs=0.5), (
                f"Hour {i}: {row[i]} != 60.0"
            )

    def test_empty_bar_height(self):
        """A column that is entirely white should produce 0 minutes.

        Python: counter stays 0, result = 0.0
        TS:     counter stays 0, result = 0
        """
        roi_height = 50
        roi_width = 24

        roi = np.full((roi_height, roi_width, 3), 255, dtype=np.uint8)

        row, _, _ = slice_image(roi, 0, 0, roi_width, roi_height)

        for i in range(24):
            assert row[i] == pytest.approx(0.0, abs=0.1), (
                f"Hour {i}: {row[i]} != 0.0"
            )

    def test_half_bar_height(self):
        """Bottom half black, top half white -> ~30 minutes.

        Python: counter = roi_height*scale/2, result = 60 * (h*s/2) / (h*s) = 30.0
        TS:     Math.floor(60 * counter / maxHeight) = 30
        """
        roi_height = 100
        roi_width = 24

        roi = np.full((roi_height, roi_width, 3), 255, dtype=np.uint8)
        # Bottom half is black
        roi[roi_height // 2 :, :, :] = 0

        row, _, _ = slice_image(roi, 0, 0, roi_width, roi_height)

        for i in range(24):
            assert row[i] == pytest.approx(30.0, abs=1.0), (
                f"Hour {i}: {row[i]}, expected ~30.0"
            )


# ============================================================================
# 4. Grid ROI calculation parity
#    TS: calculateROI() in gridDetection.canvas.ts
# ============================================================================


@pytest.mark.skipif(not HAS_ROI, reason="ROI imports unavailable")
class TestGridROICalculationParity:
    """ROI calculation from anchor/click positions must match across impls.

    TS equivalent:
      calculateROI(lowerLeftX, upperRightY, width, height, img) returns
      { x, y, width, height } or null
    """

    def test_basic_roi_from_clicks(self):
        """Given two corner points, ROI dimensions are computed correctly.

        Both implementations: width = lower_right.x - upper_left.x
                              height = lower_right.y - upper_left.y

        TS:
          const roi = calculateROI(100, 200, 400, 300, img)
          assert roi.x === 100 && roi.y === 200 && roi.width === 400 && roi.height === 300
        """
        upper_left = (100, 200)
        lower_right = (500, 500)

        roi_x, roi_y, roi_w, roi_h = calculate_roi_from_clicks(upper_left, lower_right)

        assert roi_x == 100
        assert roi_y == 200
        assert roi_w == 400
        assert roi_h == 300

    def test_roi_rejects_inverted_coordinates(self):
        """Both impls reject when lower_right is above/left of upper_left.

        TS: calculateROI returns null for negative width/height
        Python: raises ImageProcessingError
        """
        from screenshot_processor.core.exceptions import ImageProcessingError

        with pytest.raises(ImageProcessingError):
            calculate_roi_from_clicks((500, 500), (100, 100))

    def test_roi_rejects_negative_coordinates(self):
        """Both impls reject negative coordinates.

        TS: calculateROI returns null for lowerLeftX < 0
        Python: raises ImageProcessingError
        """
        from screenshot_processor.core.exceptions import ImageProcessingError

        with pytest.raises(ImageProcessingError):
            calculate_roi_from_clicks((-10, 200), (500, 500))


# ============================================================================
# 5. Dark mode detection parity
#    TS: convertDarkMode() in imageUtils.canvas.ts
# ============================================================================


@pytest.mark.skipif(
    not (HAS_IMAGE_UTILS and HAS_NUMPY),
    reason="image_utils or numpy unavailable",
)
class TestDarkModeDetectionParity:
    """Dark mode detection threshold must be identical across implementations.

    Both use: if mean(image) < 100 -> invert + adjust contrast

    TS equivalent:
      convertDarkMode(imageMat) inverts when mean < 100
    """

    DARK_MODE_THRESHOLD = 100

    def test_dark_image_gets_inverted(self):
        """An image with mean < 100 should be inverted (become lighter).

        TS: convertDarkMode inverts when mean pixel value < 100
        """
        # Create a dark image (mean ~30)
        dark_img = np.full((100, 100, 3), 30, dtype=np.uint8)
        result = convert_dark_mode(dark_img.copy())

        # After inversion, mean should be higher
        assert np.mean(result) > self.DARK_MODE_THRESHOLD

    def test_light_image_unchanged(self):
        """An image with mean >= 100 should NOT be inverted.

        TS: convertDarkMode returns unchanged when mean >= 100
        """
        light_img = np.full((100, 100, 3), 200, dtype=np.uint8)
        original_mean = np.mean(light_img)
        result = convert_dark_mode(light_img.copy())

        # Should remain approximately the same
        assert np.mean(result) == pytest.approx(original_mean, abs=1.0)

    def test_threshold_boundary(self):
        """Image with mean exactly at threshold (100) should NOT be inverted.

        Both impls use strict less-than: mean < 100
        """
        boundary_img = np.full((100, 100, 3), 100, dtype=np.uint8)
        result = convert_dark_mode(boundary_img.copy())

        # Mean 100 is NOT < 100, so no inversion should happen
        assert np.mean(result) == pytest.approx(100.0, abs=1.0)


# ============================================================================
# 6. Image processing constants parity
#    TS: SCALE_AMOUNT, NUM_HOURS, MAX_MINUTES, LOWER_GRID_BUFFER
# ============================================================================


@pytest.mark.skipif(not HAS_NUMPY, reason="numpy unavailable")
class TestProcessingConstantsParity:
    """Shared algorithm constants must be identical across implementations.

    TS constants (barExtraction.canvas.ts):
      SCALE_AMOUNT = 4
      NUM_HOURS = 24
      MAX_MINUTES = 60
      LOWER_GRID_BUFFER = 2
    """

    # These values are extracted from both Python (bar_extraction.py, bar_processor.py)
    # and TypeScript (barExtraction.canvas.ts). If either side changes, this test
    # catches the drift.
    EXPECTED_SCALE_AMOUNT = 4
    EXPECTED_NUM_SLICES = 24
    EXPECTED_MAX_Y = 60
    EXPECTED_LOWER_GRID_BUFFER = 2

    def test_scale_amount(self):
        """Scale factor must be 4 in both implementations."""
        # Verify Python uses these values by inspecting slice_image behavior
        # with a known-size ROI
        roi_height = 10
        roi_width = 24
        roi = np.full((roi_height, roi_width, 3), 255, dtype=np.uint8)

        _, processed_img, scale = slice_image(roi, 0, 0, roi_width, roi_height)
        assert scale == self.EXPECTED_SCALE_AMOUNT

    def test_slice_count(self):
        """Both implementations divide the ROI into exactly 24 slices."""
        roi = np.full((50, 240, 3), 255, dtype=np.uint8)
        row, _, _ = slice_image(roi, 0, 0, 240, 50)

        # 24 hourly values + 1 total
        assert len(row) == self.EXPECTED_NUM_SLICES + 1


# ============================================================================
# 7. GridBounds / GridCoordinates parity
#    TS: GridCoordinates = { upper_left: {x, y}, lower_right: {x, y} }
# ============================================================================


@pytest.mark.skipif(not HAS_INTERFACES, reason="interfaces unavailable")
class TestGridBoundsParity:
    """GridBounds (Python) and GridCoordinates (TS) must represent the same data.

    Python: GridBounds(upper_left_x, upper_left_y, lower_right_x, lower_right_y)
            .width = lower_right_x - upper_left_x
            .height = lower_right_y - upper_left_y

    TS: { upper_left: {x, y}, lower_right: {x, y} }
        width = lower_right.x - upper_left.x
        height = lower_right.y - upper_left.y
    """

    def test_dimensions_computed_correctly(self):
        bounds = GridBounds(
            upper_left_x=100,
            upper_left_y=200,
            lower_right_x=500,
            lower_right_y=400,
        )
        assert bounds.width == 400
        assert bounds.height == 200
        assert bounds.upper_left == (100, 200)
        assert bounds.lower_right == (500, 400)

    def test_to_dict_matches_ts_shape(self):
        """to_dict() produces the flat format used by the API.

        TS GridCoordinates uses nested format: {upper_left: {x, y}, lower_right: {x, y}}
        but the API uses flat: {upper_left_x, upper_left_y, lower_right_x, lower_right_y}
        """
        bounds = GridBounds(
            upper_left_x=50,
            upper_left_y=100,
            lower_right_x=450,
            lower_right_y=300,
        )
        expected = {
            "upper_left_x": 50,
            "upper_left_y": 100,
            "lower_right_x": 450,
            "lower_right_y": 300,
        }
        assert bounds.to_dict() == expected


# ============================================================================
# 8. Image utility parity: darken_non_white, reduce_color_count, scale_up
#    TS: darkenNonWhite(), reduceColorCount(), scaleUp() in imageUtils.canvas.ts
# ============================================================================


@pytest.mark.skipif(
    not (HAS_IMAGE_UTILS and HAS_NUMPY),
    reason="image_utils or numpy unavailable",
)
class TestImageUtilityParity:
    """Low-level image utilities must produce equivalent results."""

    def test_darken_non_white_makes_non_white_black(self):
        """Pixels below gray threshold (240) become black.

        TS: darkenNonWhite applies grayscale threshold at 240,
            sets pixels below to [0,0,0]

        Python: cv2.threshold(gray, 240, 255, THRESH_BINARY) then img[thresh<250] = 0
        """
        img = np.full((10, 10, 3), 128, dtype=np.uint8)  # Gray (128 < 240)
        result = darken_non_white(img.copy())

        # All pixels should now be black
        assert np.all(result == 0)

    def test_darken_non_white_preserves_white(self):
        """Pure white pixels (255) remain white.

        TS: pixels at 255 pass the threshold and are preserved.
        """
        img = np.full((10, 10, 3), 255, dtype=np.uint8)
        result = darken_non_white(img.copy())

        # All pixels should remain white
        assert np.all(result == 255)

    def test_scale_up_dimensions(self):
        """scale_up(img, 4) produces 4x dimensions.

        TS: scaleUp(mat, 4) scales width and height by 4
        """
        img = np.zeros((25, 50, 3), dtype=np.uint8)
        result = scale_up(img, 4)

        assert result.shape[0] == 100  # height * 4
        assert result.shape[1] == 200  # width * 4

    def test_reduce_color_count_binary(self):
        """reduce_color_count(img, 2) produces only 0 and 255 values.

        TS: reduceColorCount(mat, 2) quantizes to 2 levels: 0 and 255
        """
        # Create image with various gray values
        img = np.array([[[64, 64, 64], [192, 192, 192]]], dtype=np.uint8)
        result = reduce_color_count(img.copy(), 2)

        # All values should be either 0 or 255
        unique_vals = set(np.unique(result))
        assert unique_vals.issubset({0, 255}), f"Unexpected values: {unique_vals}"


# ============================================================================
# 9. Extended time parsing edge cases (parametrized)
#    TS: extractTimeFromText() must match for all these inputs
# ============================================================================


@pytest.mark.skipif(not HAS_OCR, reason="OCR imports unavailable")
class TestTimeParsingEdgeCases:
    """Additional time parsing edge cases to ensure parity."""

    EDGE_CASES = [
        # (input, expected, description)
        ("1h", "1h", "hours only, single digit"),
        ("59m", "59m", "minutes only, max single-unit"),
        ("0m", "0m", "zero minutes"),
        ("23h 59m", "23h 59m", "max valid time"),
        ("1h 0m", "1h 0m", "hours with zero minutes"),
        ("0h 0m", "0h 0m", "all zeros"),
        ("10h 10m", "10h 10m", "double digit hours and minutes"),
        ("1h 1m", "1h 1m", "single digit both"),
        ("0h 1m", "0h 1m", "zero hours with one minute"),
        ("12h", "12h", "noon hours only"),
        ("0s", "0s", "zero seconds"),
        ("59s", "59s", "max seconds"),
        ("1m 0s", "1m 0s", "minute with zero seconds"),
        ("0m 1s", "0m 1s", "zero minutes with one second"),
    ]

    @pytest.mark.parametrize("input_text, expected, description", EDGE_CASES)
    def test_edge_case(self, input_text: str, expected: str, description: str):
        """TS equivalent: extractTimeFromText(input_text) === expected"""
        result = _extract_time_from_text(input_text)
        assert result == expected, f"[{description}] '{input_text}' -> '{result}', expected '{expected}'"

    def test_no_time_returns_empty(self):
        """When no time pattern found, both impls return empty string.

        TS: extractTimeFromText("hello world") === ""
        """
        assert _extract_time_from_text("hello world") == ""
        assert _extract_time_from_text("") == ""
        assert _extract_time_from_text("SCREEN TIME") == ""

    def test_time_embedded_in_text(self):
        """Time patterns embedded in surrounding text are still found.

        TS: extractTimeFromText("Total: 2h 30m today") === "2h 30m"
        """
        assert _extract_time_from_text("Total: 2h 30m today") == "2h 30m"
        assert _extract_time_from_text("Screen Time 45m remaining") == "45m"
        assert _extract_time_from_text("Used 3h so far") == "3h"

    def test_first_match_wins(self):
        """When multiple time patterns exist, the first matching pattern wins.

        Both impls check hour+min pattern before min-only or sec-only.
        """
        # hour+min pattern matched first
        result = _extract_time_from_text("2h 30m and also 45m")
        assert result == "2h 30m"

    def test_missing_m_fallback(self):
        """OCR sometimes drops the 'm' - both impls must recover.

        TS: extractTimeFromText("4h 36") === "4h 36m"
        """
        assert _extract_time_from_text("4h 36") == "4h 36m"
        assert _extract_time_from_text("1h 0") == "1h 0m"
        assert _extract_time_from_text("12h 59") == "12h 59m"


# ============================================================================
# 10. Extended OCR digit normalization (parametrized)
#     TS: normalizeOcrDigits() in shared utilities
# ============================================================================


@pytest.mark.skipif(not HAS_OCR, reason="OCR imports unavailable")
class TestOCRDigitNormalizationParity:
    """Comprehensive OCR digit normalization parity tests."""

    NORMALIZATION_CASES = [
        # (input, expected, description)
        ("Ih 3Om", "1h 30m", "I->1, O->0"),
        ("Oh 45m", "0h 45m", "O->0"),
        ("4h Am", "4h 4m", "A->4"),
        ("lh 30m", "1h 30m", "l->1"),
        ("|h 30m", "1h 30m", "|->1"),
        ("Sh 30m", "5h 30m", "S->5"),
        ("Bh 30m", "8h 30m", "B->8"),
        ("Gh 30m", "6h 30m", "G->6"),
        ("Zh 30m", "2h 30m", "Z->2"),
        ("Th 30m", "7h 30m", "T->7"),
    ]

    @pytest.mark.parametrize("input_text, expected, description", NORMALIZATION_CASES)
    def test_normalization(self, input_text: str, expected: str, description: str):
        """TS: normalizeOcrDigits(input) === expected"""
        result = _normalize_ocr_digits(input_text)
        assert result == expected, f"[{description}] '{input_text}' -> '{result}', expected '{expected}'"

    def test_already_correct_unchanged(self):
        """Correct digit text should not be altered by normalization.

        TS: normalizeOcrDigits("4h 36m") === "4h 36m"
        """
        assert _normalize_ocr_digits("4h 36m") == "4h 36m"
        assert _normalize_ocr_digits("0h 0m") == "0h 0m"
        assert _normalize_ocr_digits("12h 59m") == "12h 59m"


# ============================================================================
# 11. Bar extraction with specific pixel patterns (parametrized)
#     TS: sliceImage() in barExtraction.canvas.ts
# ============================================================================


@pytest.mark.skipif(
    not (HAS_BAR_EXTRACTION and HAS_NUMPY),
    reason="bar_extraction or numpy unavailable",
)
class TestBarExtractionPixelPatternsParity:
    """Bar extraction with controlled pixel patterns for parity verification."""

    def test_single_bar_at_hour_0(self):
        """Only hour 0 has a bar (bottom quarter black).

        TS: sliceImage with same pattern should have non-zero only at index 0.
        """
        roi_height = 100
        roi_width = 240  # 10px per slice
        roi = np.full((roi_height, roi_width, 3), 255, dtype=np.uint8)

        # Make bottom quarter of hour-0 slice black
        slice_w = roi_width // 24
        roi[75:100, 0:slice_w, :] = 0

        row, _, _ = slice_image(roi, 0, 0, roi_width, roi_height)

        assert row[0] > 0, "Hour 0 should have a non-zero value"
        # Hours 1-23 should be zero or near-zero
        for i in range(1, 24):
            assert row[i] == pytest.approx(0.0, abs=1.0), f"Hour {i} should be ~0"

    def test_alternating_bars(self):
        """Even hours have full bars, odd hours empty.

        TS must produce the same pattern of 60/0 alternating.
        """
        roi_height = 50
        roi_width = 240
        roi = np.full((roi_height, roi_width, 3), 255, dtype=np.uint8)
        slice_w = roi_width // 24

        for hour in range(0, 24, 2):  # Even hours
            x_start = hour * slice_w
            x_end = (hour + 1) * slice_w
            roi[:, x_start:x_end, :] = 0  # Full black

        row, _, _ = slice_image(roi, 0, 0, roi_width, roi_height)

        for i in range(24):
            if i % 2 == 0:
                assert row[i] == pytest.approx(60.0, abs=1.0), f"Even hour {i} should be ~60"
            else:
                assert row[i] == pytest.approx(0.0, abs=1.0), f"Odd hour {i} should be ~0"

    def test_gradient_bars(self):
        """Bars increase in height from hour 0 to 23.

        Hour i has (i+1)/24 of the roi_height filled from bottom.
        """
        roi_height = 240
        roi_width = 240
        roi = np.full((roi_height, roi_width, 3), 255, dtype=np.uint8)
        slice_w = roi_width // 24

        for hour in range(24):
            fill_height = (hour + 1) * (roi_height // 24)
            x_start = hour * slice_w
            x_end = (hour + 1) * slice_w
            roi[roi_height - fill_height:roi_height, x_start:x_end, :] = 0

        row, _, _ = slice_image(roi, 0, 0, roi_width, roi_height)

        # Values should be monotonically non-decreasing
        for i in range(1, 24):
            assert row[i] >= row[i - 1] - 1.0, (
                f"Hour {i} ({row[i]}) should be >= hour {i-1} ({row[i-1]})"
            )

    def test_total_is_sum_of_hourly(self):
        """The 25th element (index 24) is the sum of hours 0-23.

        Both Python and TS append np.sum(row) / sum(hourlyValues).
        """
        roi_height = 100
        roi_width = 240
        roi = np.full((roi_height, roi_width, 3), 255, dtype=np.uint8)
        # Make bottom half black for all hours
        roi[50:100, :, :] = 0

        row, _, _ = slice_image(roi, 0, 0, roi_width, roi_height)

        hourly_sum = sum(row[:24])
        assert row[24] == pytest.approx(hourly_sum, abs=0.01), (
            f"Total {row[24]} != sum of hourly {hourly_sum}"
        )


# ============================================================================
# 12. Processing status enum values match
#     TS: ProcessingStatus enum in types
# ============================================================================


class TestEnumValuesParity:
    """Enum values must be identical between Python and TS implementations."""

    def test_processing_status_values(self):
        """ProcessingStatus enum values must match TS ProcessingStatus.

        TS: type ProcessingStatus = "pending" | "processing" | "completed" | "failed" | "skipped" | "deleted"
        """
        try:
            from screenshot_processor.web.database.models import ProcessingStatus

            expected_values = {"pending", "processing", "completed", "failed", "skipped", "deleted"}
            actual_values = {s.value for s in ProcessingStatus}
            assert actual_values == expected_values
        except ImportError:
            pytest.skip("Models not importable")

    def test_annotation_status_values(self):
        """AnnotationStatus enum values must match TS AnnotationStatus.

        TS: type AnnotationStatus = "pending" | "annotated" | "verified" | "skipped"
        """
        try:
            from screenshot_processor.web.database.models import AnnotationStatus

            expected_values = {"pending", "annotated", "verified", "skipped"}
            actual_values = {s.value for s in AnnotationStatus}
            assert actual_values == expected_values
        except ImportError:
            pytest.skip("Models not importable")

    def test_processing_method_values(self):
        """ProcessingMethod enum values must match TS ProcessingMethod.

        TS: type ProcessingMethod = "ocr_anchored" | "line_based" | "manual"
        """
        try:
            from screenshot_processor.web.database.models import ProcessingMethod

            expected_values = {"ocr_anchored", "line_based", "manual"}
            actual_values = {s.value for s in ProcessingMethod}
            assert actual_values == expected_values
        except ImportError:
            pytest.skip("Models not importable")

    def test_user_role_values(self):
        """UserRole enum values must match TS UserRole.

        TS: type UserRole = "admin" | "annotator"
        """
        try:
            from screenshot_processor.web.database.models import UserRole

            expected_values = {"admin", "annotator"}
            actual_values = {s.value for s in UserRole}
            assert actual_values == expected_values
        except ImportError:
            pytest.skip("Models not importable")

    def test_image_type_literal_values(self):
        """ImageType literal values must match TS ImageType.

        TS: type ImageType = "battery" | "screen_time"
        """
        try:
            from typing import get_args

            from screenshot_processor.web.database.schemas import ImageType

            expected_values = {"battery", "screen_time"}
            actual_values = set(get_args(ImageType))
            assert actual_values == expected_values
        except ImportError:
            pytest.skip("Schemas not importable")

    def test_grid_detection_method_values(self):
        """GridDetectionMethod enum values must match TS constants.

        TS: "ocr_anchored" | "line_based" | "manual"
        """
        try:
            from screenshot_processor.core.interfaces import GridDetectionMethod

            expected_values = {"ocr_anchored", "line_based", "manual"}
            actual_values = {m.value for m in GridDetectionMethod}
            assert actual_values == expected_values
        except ImportError:
            pytest.skip("Interfaces not importable")


# ============================================================================
# 13. Scale factor and color threshold constants parity
# ============================================================================


@pytest.mark.skipif(
    not (HAS_BAR_EXTRACTION and HAS_NUMPY),
    reason="bar_extraction or numpy unavailable",
)
class TestScaleFactorConstantsParity:
    """Verify scale factor is consistently 4 across all code paths."""

    def test_scale_factor_value(self):
        """Scale factor returned by slice_image must be exactly 4.

        TS constant: SCALE_AMOUNT = 4
        """
        roi = np.full((50, 120, 3), 255, dtype=np.uint8)
        _, _, scale = slice_image(roi, 0, 0, 120, 50)
        assert scale == 4

    def test_scale_up_preserves_scale_factor(self):
        """scale_up(img, 4) produces dimensions that are 4x original.

        TS: scaleUp(mat, SCALE_AMOUNT) where SCALE_AMOUNT = 4
        """
        img = np.zeros((10, 10, 3), dtype=np.uint8)
        result = scale_up(img, 4)
        assert result.shape[0] == 40
        assert result.shape[1] == 40

    def test_scale_up_factor_2(self):
        """scale_up(img, 2) produces 2x dimensions.

        Verifies the function works with other factors too.
        """
        img = np.zeros((10, 10, 3), dtype=np.uint8)
        result = scale_up(img, 2)
        assert result.shape[0] == 20
        assert result.shape[1] == 20


# ============================================================================
# 14. Color threshold constants parity
# ============================================================================


@pytest.mark.skipif(
    not (HAS_IMAGE_UTILS and HAS_NUMPY),
    reason="image_utils or numpy unavailable",
)
class TestColorThresholdConstantsParity:
    """Color thresholds must be identical across implementations."""

    def test_darken_threshold_is_240(self):
        """Darken threshold is 240 — pixels with gray value > 240 stay white.

        TS: darkenNonWhite uses threshold 240 for binary classification.
        """
        # Pixel at 241 (above threshold) should remain white-ish
        img_above = np.full((10, 10, 3), 241, dtype=np.uint8)
        result_above = darken_non_white(img_above.copy())
        assert np.all(result_above == 255) or np.all(result_above == 241), (
            "Pixels at 241 should pass threshold"
        )

        # Pixel at 239 (below threshold) should become black
        img_below = np.full((10, 10, 3), 239, dtype=np.uint8)
        result_below = darken_non_white(img_below.copy())
        assert np.all(result_below == 0), "Pixels at 239 should become black"

    def test_darken_threshold_exact_240(self):
        """Pixel value exactly at 240 — boundary behavior.

        TS and Python both use cv2.threshold(gray, 240, 255, THRESH_BINARY).
        OpenCV THRESH_BINARY: src > 240 -> 255, else 0. So 240 -> 0 (darkened).
        """
        img = np.full((10, 10, 3), 240, dtype=np.uint8)
        result = darken_non_white(img.copy())
        # 240 is NOT > 240, so threshold outputs 0, meaning img[thresh<250] = 0
        assert np.all(result == 0), "Pixel value 240 should be darkened (not > 240)"


# ============================================================================
# 15. Dark mode threshold boundary cases
# ============================================================================


@pytest.mark.skipif(
    not (HAS_IMAGE_UTILS and HAS_NUMPY),
    reason="image_utils or numpy unavailable",
)
class TestDarkModeThresholdBoundaryCases:
    """Dark mode threshold boundary testing for parity verification."""

    def test_mean_99_is_dark(self):
        """Image with mean = 99 is dark (< 100), should be inverted.

        TS: mean < 100 triggers inversion.
        """
        img = np.full((100, 100, 3), 99, dtype=np.uint8)
        result = convert_dark_mode(img.copy())
        assert np.mean(result) > 100

    def test_mean_101_is_light(self):
        """Image with mean = 101 is light (>= 100), should NOT be inverted.

        TS: mean >= 100 skips inversion.
        """
        img = np.full((100, 100, 3), 101, dtype=np.uint8)
        result = convert_dark_mode(img.copy())
        assert np.mean(result) == pytest.approx(101.0, abs=1.0)

    def test_completely_black_image(self):
        """Mean = 0, definitively dark. Inversion produces white (255).

        After inversion: 255. After contrast adjustment (3.0, 10):
        brightness = 10 + round(255 * (1-3.0)/2) = 10 - 255 = -245
        result = clip(3.0*255 + (-245)) = clip(520) = 255
        """
        img = np.zeros((50, 50, 3), dtype=np.uint8)
        result = convert_dark_mode(img.copy())
        assert np.mean(result) > 200  # Should be very bright after inversion

    def test_completely_white_image(self):
        """Mean = 255, definitively light. No inversion.

        TS: convertDarkMode returns input unchanged when mean >= 100
        """
        img = np.full((50, 50, 3), 255, dtype=np.uint8)
        result = convert_dark_mode(img.copy())
        assert np.mean(result) == pytest.approx(255.0, abs=1.0)

    def test_mixed_dark_light_pixels(self):
        """Image where overall mean < 100 but has some bright pixels.

        Mean = (30*3 + 200*1) / 4 = 72.5 -> dark -> inverted.
        """
        img = np.full((100, 100, 3), 30, dtype=np.uint8)
        # Top-left quarter is bright
        img[:25, :100, :] = 200
        overall_mean = np.mean(img)
        assert overall_mean < 100, f"Setup check: mean={overall_mean} should be < 100"
        result = convert_dark_mode(img.copy())
        assert np.mean(result) > 100


# ============================================================================
# 16. Alignment score edge cases
#     TS: computeBarAlignmentScore edge cases
# ============================================================================


@pytest.mark.skipif(
    not (HAS_BAR_EXTRACTION and HAS_NUMPY),
    reason="bar_extraction or numpy unavailable",
)
class TestAlignmentScoreEdgeCases:
    """Alignment score edge cases for parity verification."""

    def test_all_zeros_both_sides(self):
        """Both extracted and computed are zeros -> score = 1.0.

        TS: computeBarAlignmentScore(whiteROI, allZeros) === 1.0
        """
        roi = np.full((100, 480, 3), 255, dtype=np.uint8)
        score = compute_bar_alignment_score(roi, [0.0] * 24)
        assert score == 1.0

    def test_all_max_values(self):
        """All computed values at 60 with a non-white ROI.

        Score depends on how much blue is detected vs expected.
        """
        # Dark ROI (not blue, just dark)
        roi = np.full((100, 480, 3), 50, dtype=np.uint8)
        hourly = [60.0] * 24
        score = compute_bar_alignment_score(roi, hourly)
        # With a non-blue dark ROI, extracted heights may be 0
        # so one side is zero, max_possible = 60*24 = 1440 > 30 -> score = 0.1
        assert 0.0 <= score <= 1.0

    def test_alternating_values(self):
        """Alternating high/low values — tests per-slice comparison."""
        roi = np.full((100, 480, 3), 255, dtype=np.uint8)
        hourly = [60.0 if i % 2 == 0 else 0.0 for i in range(24)]
        score = compute_bar_alignment_score(roi, hourly)
        # White ROI with some non-zero computed -> one_side_zero path
        assert 0.0 <= score <= 1.0

    def test_single_bar_match(self):
        """Single blue bar at hour 12, computed value at hour 12 only."""
        roi = np.full((100, 480, 3), 255, dtype=np.uint8)
        slice_width = 480 // 24
        hour = 12
        x_start = hour * slice_width + slice_width // 4
        x_end = hour * slice_width + 3 * slice_width // 4
        roi[20:100, x_start:x_end] = [200, 100, 50]  # Blue BGR

        hourly = [0.0] * 24
        hourly[12] = 48.0  # roughly matches the bar height
        score = compute_bar_alignment_score(roi, hourly)
        # Should be reasonable since the bar is in the right position
        assert score > 0.3

    def test_empty_roi(self):
        """Empty ROI (0 size) should return 0.0.

        TS: Returns 0 for empty input.
        """
        roi = np.array([], dtype=np.uint8).reshape(0, 0, 3)
        score = compute_bar_alignment_score(roi, [0.0] * 24)
        assert score == 0.0

    def test_fewer_than_24_values(self):
        """Fewer than 24 hourly values — padded with zeros.

        Both impls pad to 24 values if fewer provided.
        """
        roi = np.full((100, 480, 3), 255, dtype=np.uint8)
        hourly = [10.0] * 10  # Only 10 values
        score = compute_bar_alignment_score(roi, hourly)
        assert 0.0 <= score <= 1.0

    def test_more_than_24_values(self):
        """More than 24 hourly values — truncated to 24.

        Both impls take only the first 24.
        """
        roi = np.full((100, 480, 3), 255, dtype=np.uint8)
        hourly = [5.0] * 30  # 30 values
        score = compute_bar_alignment_score(roi, hourly)
        assert 0.0 <= score <= 1.0


# ============================================================================
# 17. GridBounds additional parity tests
# ============================================================================


@pytest.mark.skipif(not HAS_INTERFACES, reason="interfaces unavailable")
class TestGridBoundsAdditionalParity:
    """Additional GridBounds tests for parity."""

    def test_zero_area_grid(self):
        """GridBounds with zero dimensions."""
        bounds = GridBounds(
            upper_left_x=100, upper_left_y=200,
            lower_right_x=100, lower_right_y=200,
        )
        assert bounds.width == 0
        assert bounds.height == 0

    def test_very_large_grid(self):
        """GridBounds for a large screenshot area."""
        bounds = GridBounds(
            upper_left_x=0, upper_left_y=0,
            lower_right_x=4096, lower_right_y=8192,
        )
        assert bounds.width == 4096
        assert bounds.height == 8192

    def test_from_dict_roundtrip(self):
        """to_dict -> from_dict roundtrip preserves all values.

        TS: GridCoordinates serialization/deserialization must be lossless.
        """
        original = GridBounds(
            upper_left_x=42, upper_left_y=99,
            lower_right_x=1234, lower_right_y=5678,
        )
        roundtripped = GridBounds.from_dict(original.to_dict())
        assert roundtripped.upper_left_x == original.upper_left_x
        assert roundtripped.upper_left_y == original.upper_left_y
        assert roundtripped.lower_right_x == original.lower_right_x
        assert roundtripped.lower_right_y == original.lower_right_y
        assert roundtripped.width == original.width
        assert roundtripped.height == original.height


# ============================================================================
# 18. Reduce color count parity with various levels
# ============================================================================


@pytest.mark.skipif(
    not (HAS_IMAGE_UTILS and HAS_NUMPY),
    reason="image_utils or numpy unavailable",
)
class TestReduceColorCountParity:
    """reduce_color_count with various num_colors for parity verification."""

    def test_reduce_to_4_colors(self):
        """reduce_color_count(img, 4) produces at most 4 unique gray levels.

        TS: reduceColorCount(mat, 4) quantizes to 4 levels: 0, 85, 170, 255
        """
        img = np.arange(256, dtype=np.uint8).reshape(16, 16, 1)
        img = np.repeat(img, 3, axis=2)
        result = reduce_color_count(img.copy(), 4)
        unique_vals = np.unique(result)
        assert len(unique_vals) <= 4, f"Expected <= 4 unique values, got {len(unique_vals)}: {unique_vals}"

    def test_reduce_preserves_pure_black(self):
        """Pure black (0) should remain 0 after any reduction.

        TS: reduceColorCount preserves 0
        """
        img = np.zeros((5, 5, 3), dtype=np.uint8)
        result = reduce_color_count(img.copy(), 2)
        assert np.all(result == 0)

    def test_reduce_preserves_near_white(self):
        """Near-white (254) should map to 255 with 2-color reduction.

        TS: reduceColorCount(mat, 2) maps 128-255 -> 255
        """
        img = np.full((5, 5, 3), 254, dtype=np.uint8)
        result = reduce_color_count(img.copy(), 2)
        assert np.all(result == 255)


# ============================================================================
# 19. Scale up with different factors
# ============================================================================


@pytest.mark.skipif(
    not (HAS_IMAGE_UTILS and HAS_NUMPY),
    reason="image_utils or numpy unavailable",
)
class TestScaleUpParity:
    """scale_up factor parity tests."""

    @pytest.mark.parametrize("factor", [1, 2, 3, 4, 8])
    def test_scale_factor_dimensions(self, factor):
        """scale_up(img, N) produces N*height x N*width.

        TS: scaleUp(mat, N) produces same dimensions.
        """
        h, w = 10, 20
        img = np.zeros((h, w, 3), dtype=np.uint8)
        result = scale_up(img, factor)
        assert result.shape[0] == h * factor
        assert result.shape[1] == w * factor

    def test_scale_preserves_channel_count(self):
        """Scaling should not change the number of channels.

        TS: scaleUp preserves 3-channel (or 4-channel) images.
        """
        img = np.zeros((10, 10, 3), dtype=np.uint8)
        result = scale_up(img, 4)
        assert result.shape[2] == 3


# ============================================================================
# 20. ROI edge cases
# ============================================================================


@pytest.mark.skipif(not HAS_ROI, reason="ROI imports unavailable")
class TestROIEdgeCasesParity:
    """Additional ROI calculation edge cases for parity."""

    def test_roi_minimum_valid(self):
        """Smallest valid ROI: 1x1 pixel.

        TS: calculateROI returns valid for 1px region.
        """
        roi_x, roi_y, roi_w, roi_h = calculate_roi_from_clicks((0, 0), (1, 1))
        assert roi_w == 1
        assert roi_h == 1

    def test_roi_preserves_coordinates(self):
        """Returned coordinates match input upper_left exactly.

        TS: roi.x === upper_left.x, roi.y === upper_left.y
        """
        roi_x, roi_y, roi_w, roi_h = calculate_roi_from_clicks((250, 300), (750, 600))
        assert roi_x == 250
        assert roi_y == 300
        assert roi_w == 500
        assert roi_h == 300

    def test_roi_with_image_bounds_validation(self):
        """ROI coordinates validated against image dimensions.

        TS: Returns null if ROI exceeds image bounds.
        """
        from screenshot_processor.core.exceptions import ImageProcessingError

        img = np.zeros((500, 400, 3), dtype=np.uint8)
        # Valid: fits within bounds
        roi_x, roi_y, roi_w, roi_h = calculate_roi_from_clicks(
            (100, 100), (300, 400), img=img
        )
        assert roi_w == 200
        assert roi_h == 300

        # Invalid: exceeds image width
        with pytest.raises(ImageProcessingError):
            calculate_roi_from_clicks((100, 100), (500, 400), img=img)

    def test_roi_rejects_zero_dimension(self):
        """ROI with width=0 or height=0 is rejected.

        TS: calculateROI returns null for zero dimensions.
        """
        from screenshot_processor.core.exceptions import ImageProcessingError

        # Same x coordinates -> width = 0
        with pytest.raises(ImageProcessingError):
            calculate_roi_from_clicks((100, 100), (100, 200))

        # Same y coordinates -> height = 0
        with pytest.raises(ImageProcessingError):
            calculate_roi_from_clicks((100, 100), (200, 100))
