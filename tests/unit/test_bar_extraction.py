"""Unit tests for bar_extraction module — bar graph value extraction."""

from __future__ import annotations

import numpy as np
import pytest

from screenshot_processor.core.bar_extraction import (
    compute_bar_alignment_score,
    slice_image,
)


# ---------------------------------------------------------------------------
# slice_image
# ---------------------------------------------------------------------------
class TestSliceImage:
    """Tests for the slice_image function."""

    def test_returns_25_element_list(self):
        img = np.full((600, 1400, 3), 255, dtype=np.uint8)
        row, _, _ = slice_image(img, roi_x=50, roi_y=100, roi_width=1000, roi_height=200)
        assert len(row) == 25

    def test_last_element_is_sum_of_first_24(self):
        img = np.full((600, 1400, 3), 255, dtype=np.uint8)
        row, _, _ = slice_image(img, roi_x=50, roi_y=100, roi_width=1000, roi_height=200)
        assert row[24] == pytest.approx(sum(row[:24]), abs=0.01)

    def test_all_white_gives_zeros(self):
        img = np.full((600, 1400, 3), 255, dtype=np.uint8)
        row, _, _ = slice_image(img, roi_x=50, roi_y=100, roi_width=1000, roi_height=200)
        assert all(v < 1 for v in row[:24])

    def test_all_black_gives_max(self):
        img = np.full((600, 1400, 3), 255, dtype=np.uint8)
        img[100:300, 50:1050] = 0  # black ROI
        row, _, _ = slice_image(img, roi_x=50, roi_y=100, roi_width=1000, roi_height=200)
        assert all(v > 55 for v in row[:24])

    def test_half_black_gives_roughly_30(self):
        img = np.full((600, 1400, 3), 255, dtype=np.uint8)
        img[200:300, 50:1050] = 0  # bottom half of 100-300 ROI
        row, _, _ = slice_image(img, roi_x=50, roi_y=100, roi_width=1000, roi_height=200)
        for v in row[:24]:
            assert 20 <= v <= 40, f"Expected ~30, got {v}"

    def test_values_in_valid_range(self):
        img = np.random.randint(0, 256, (600, 1400, 3), dtype=np.uint8)
        row, _, _ = slice_image(img, roi_x=50, roi_y=100, roi_width=1000, roi_height=200)
        for v in row[:24]:
            assert 0 <= v <= 60

    def test_returns_scale_amount_4(self):
        img = np.full((600, 1400, 3), 255, dtype=np.uint8)
        _, _, scale = slice_image(img, roi_x=50, roi_y=100, roi_width=1000, roi_height=200)
        assert scale == 4

    def test_returns_processed_roi_image(self):
        img = np.full((600, 1400, 3), 255, dtype=np.uint8)
        _, processed, _ = slice_image(img, roi_x=50, roi_y=100, roi_width=1000, roi_height=200)
        assert isinstance(processed, np.ndarray)
        assert len(processed.shape) == 3

    def test_single_bar_at_noon(self):
        """One bar in the middle should show value only around hour 12."""
        img = np.full((600, 1400, 3), 255, dtype=np.uint8)
        roi_x, roi_y, roi_w, roi_h = 50, 100, 1200, 200
        slice_w = roi_w // 24
        bar_x = roi_x + 12 * slice_w
        img[roi_y:roi_y + roi_h, bar_x:bar_x + slice_w] = 0
        row, _, _ = slice_image(img, roi_x=roi_x, roi_y=roi_y, roi_width=roi_w, roi_height=roi_h)
        # Hour 12 should be high, most others should be near zero
        assert row[12] > 50

    def test_alternating_bars(self):
        img = np.full((600, 1400, 3), 255, dtype=np.uint8)
        roi_x, roi_y, roi_w, roi_h = 50, 100, 1200, 200
        slice_w = roi_w // 24
        for i in range(0, 24, 2):
            x_start = roi_x + i * slice_w
            img[roi_y:roi_y + roi_h, x_start:x_start + slice_w] = 0
        row, _, _ = slice_image(img, roi_x=roi_x, roi_y=roi_y, roi_width=roi_w, roi_height=roi_h)
        for i in range(24):
            if i % 2 == 0:
                assert row[i] > 50, f"Even hour {i} should be high"
            else:
                assert row[i] < 10, f"Odd hour {i} should be low"


# ---------------------------------------------------------------------------
# compute_bar_alignment_score
# ---------------------------------------------------------------------------
class TestComputeBarAlignmentScore:

    def test_empty_roi_returns_zero(self):
        roi = np.zeros((0, 0, 3), dtype=np.uint8)
        score = compute_bar_alignment_score(roi, [30.0] * 24)
        assert score == 0.0

    def test_both_zero_returns_one(self):
        roi = np.full((100, 600, 3), 255, dtype=np.uint8)
        score = compute_bar_alignment_score(roi, [0.0] * 24)
        assert score == 1.0

    def test_score_in_valid_range(self):
        roi = np.random.randint(0, 256, (100, 600, 3), dtype=np.uint8)
        vals = np.random.uniform(0, 60, 24).tolist()
        score = compute_bar_alignment_score(roi, vals)
        assert 0.0 <= score <= 1.0

    def test_short_value_list_padded(self):
        roi = np.full((100, 600, 3), 255, dtype=np.uint8)
        score = compute_bar_alignment_score(roi, [10.0, 20.0])
        assert 0.0 <= score <= 1.0

    def test_long_value_list_truncated(self):
        roi = np.full((100, 600, 3), 255, dtype=np.uint8)
        score = compute_bar_alignment_score(roi, [5.0] * 30)
        assert 0.0 <= score <= 1.0

    def test_grayscale_roi_does_not_crash(self):
        roi = np.full((100, 600), 200, dtype=np.uint8)
        score = compute_bar_alignment_score(roi, [30.0] * 24)
        assert 0.0 <= score <= 1.0

    def test_mismatch_one_nonzero_other_zero(self):
        roi = np.full((100, 600, 3), 255, dtype=np.uint8)
        score = compute_bar_alignment_score(roi, [60.0] * 24)
        # ROI is white (no bars), values are high => low score
        assert score <= 0.5
