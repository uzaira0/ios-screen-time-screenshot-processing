"""Unit tests for grid_anchors module — anchor detection logic."""

from __future__ import annotations

import numpy as np

from screenshot_processor.core.grid_anchors import (
    find_grid_anchors_and_calculate_roi,
    find_left_anchor,
    find_right_anchor,
)


def _make_ocr_dict(texts, lefts, tops, widths, heights):
    """Helper to build an OCR dict matching pytesseract output structure."""
    n = len(texts)
    return {
        "level": [1] * n,
        "left": lefts,
        "top": tops,
        "width": widths,
        "height": heights,
        "text": texts,
    }


class TestFindRightAnchor:
    def test_finds_60_label(self):
        img = np.full((500, 500, 3), 255, dtype=np.uint8)
        # Draw a grid line for the search to find
        img[195:205, 145:155] = 0
        ocr_dict = _make_ocr_dict(
            texts=["60"],
            lefts=[180],
            tops=[200],
            widths=[30],
            heights=[20],
        )
        found, x, y = find_right_anchor(ocr_dict, img, img.copy())
        assert found is True
        assert x != -1
        assert y != -1

    def test_no_60_label_returns_not_found(self):
        img = np.full((500, 500, 3), 255, dtype=np.uint8)
        ocr_dict = _make_ocr_dict(
            texts=["hello", "world"],
            lefts=[10, 100],
            tops=[10, 100],
            widths=[40, 40],
            heights=[20, 20],
        )
        found, x, y = find_right_anchor(ocr_dict, img, img.copy())
        assert found is False
        assert x == -1
        assert y == -1

    def test_empty_ocr_dict(self):
        img = np.full((200, 200, 3), 255, dtype=np.uint8)
        ocr_dict = _make_ocr_dict([], [], [], [], [])
        found, x, y = find_right_anchor(ocr_dict, img, img.copy())
        assert found is False

    def test_only_first_60_used(self):
        """If multiple '60' appear, only the first should be used."""
        img = np.full((500, 500, 3), 255, dtype=np.uint8)
        img[95:105, 45:55] = 0
        ocr_dict = _make_ocr_dict(
            texts=["60", "60"],
            lefts=[80, 300],
            tops=[100, 100],
            widths=[30, 30],
            heights=[20, 20],
        )
        found, x, y = find_right_anchor(ocr_dict, img, img.copy())
        assert found is True
        # Coordinates should relate to the first detection, not the second
        assert x < 300


class TestFindLeftAnchor:
    def test_finds_12AM_label(self):
        img = np.full((500, 500, 3), 255, dtype=np.uint8)
        img[145:155, 45:55] = 0  # grid lines
        ocr_dict = _make_ocr_dict(
            texts=["12AM"],
            lefts=[80],
            tops=[160],
            widths=[50],
            heights=[20],
        )
        found, x, y = find_left_anchor(ocr_dict, img, img.copy())
        assert found is True
        assert x != -1
        assert y != -1

    def test_finds_AM_keyword(self):
        img = np.full((500, 500, 3), 255, dtype=np.uint8)
        img[145:155, 45:55] = 0
        ocr_dict = _make_ocr_dict(
            texts=["AM"],
            lefts=[80],
            tops=[160],
            widths=[30],
            heights=[20],
        )
        found, _, _ = find_left_anchor(ocr_dict, img, img.copy())
        assert found is True

    def test_no_anchor_returns_not_found(self):
        img = np.full((200, 200, 3), 255, dtype=np.uint8)
        ocr_dict = _make_ocr_dict(
            texts=["nothing", "here"],
            lefts=[10, 100],
            tops=[10, 100],
            widths=[40, 40],
            heights=[20, 20],
        )
        found, x, y = find_left_anchor(ocr_dict, img, img.copy())
        assert found is False
        assert x == -1
        assert y == -1

    def test_detections_to_skip(self):
        """With detections_to_skip=1, skip the first matching detection."""
        img = np.full((500, 500, 3), 255, dtype=np.uint8)
        img[245:255, 195:205] = 0
        ocr_dict = _make_ocr_dict(
            texts=["12", "12"],
            lefts=[80, 230],
            tops=[160, 260],
            widths=[30, 30],
            heights=[20, 20],
        )
        found, x, y = find_left_anchor(ocr_dict, img, img.copy(), detections_to_skip=1)
        # Should use the second detection
        assert found is True


class TestFindGridAnchorsAndCalculateROI:
    def test_returns_none_when_no_anchors_found(self):
        img = np.full((500, 500, 3), 255, dtype=np.uint8)
        empty_dict = _make_ocr_dict([], [], [], [], [])
        result = find_grid_anchors_and_calculate_roi(
            empty_dict, empty_dict, img, img.copy(),
            snap_to_grid=False,
            calculate_roi_func=lambda *a, **kw: (0, 0, 100, 100),
        )
        assert result is None

    def test_calls_calculate_roi_when_both_found(self):
        img = np.full((600, 600, 3), 255, dtype=np.uint8)
        # Draw lines for anchor detection
        img[195:205, 45:55] = 0
        img[145:155, 45:55] = 0

        d_left = _make_ocr_dict(["12AM"], [80], [160], [50], [20])
        d_right = _make_ocr_dict(["60"], [180], [200], [30], [20])

        called = []

        def mock_calculate_roi(x, y, w, h, image, snap_to_grid=False):
            called.append((x, y, w, h))
            return (x, y, w, h)

        result = find_grid_anchors_and_calculate_roi(
            d_left, d_right, img, img.copy(),
            snap_to_grid=False,
            calculate_roi_func=mock_calculate_roi,
        )
        assert len(called) > 0  # was invoked

    def test_retries_with_skip_on_failure(self):
        """If first attempt raises ValueError, should retry with skip."""
        img = np.full((600, 600, 3), 255, dtype=np.uint8)
        img[195:205, 45:55] = 0
        img[145:155, 45:55] = 0

        d_left = _make_ocr_dict(["12", "12"], [80, 80], [160, 300], [30, 30], [20, 20])
        d_right = _make_ocr_dict(["60"], [180], [200], [30], [20])

        call_count = [0]

        def mock_calculate_roi(x, y, w, h, image, snap_to_grid=False):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ValueError("First attempt failed")
            return (x, y, w, h)

        result = find_grid_anchors_and_calculate_roi(
            d_left, d_right, img, img.copy(),
            snap_to_grid=False,
            calculate_roi_func=mock_calculate_roi,
        )
        # Should have retried
        assert call_count[0] >= 2
