"""Bar graph value extraction from ROI regions.

This module extracts hourly usage values from the bar graph region
by analyzing pixel colors and measuring bar heights.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from .image_utils import darken_non_white, reduce_color_count, scale_up

logger = logging.getLogger(__name__)

DEBUG_ENABLED = False


def slice_image(
    img: np.ndarray,
    roi_x: int = 1215,
    roi_y: int = 384,
    roi_width: int = 1078,
    roi_height: int = 177,
) -> tuple[list, np.ndarray, int]:
    """Extract hourly usage values from the bar graph region.

    Scans 24 vertical slices (one per hour) and measures bar heights
    by counting black pixels from top to bottom.

    Args:
        img: Input image (BGR format)
        roi_x: X coordinate of ROI top-left
        roi_y: Y coordinate of ROI top-left
        roi_width: Width of ROI
        roi_height: Height of ROI

    Returns:
        tuple: (row values list with 25 elements [24 hours + total],
                processed ROI image, scale factor)
    """
    logger.debug("Slicing image...")
    num_slice = 24
    max_y = 60
    scale_amount = 4
    lower_grid_buffer = 2

    # Extract ROI first, then process (much faster)
    roi = img[roi_y : roi_y + roi_height, roi_x : roi_x + roi_width]

    # Process only the ROI — binarize to black/white
    roi_processed = darken_non_white(roi.copy())
    roi_processed = reduce_color_count(roi_processed, 2)

    # Work at original resolution — scale_up is mathematically redundant on
    # binarized images since counter/height ratio is scale-invariant.
    # The scaled image is only needed for debug visualization.
    slice_width = roi_width // num_slice

    # Extract all 24 middle columns at once (batch vectorized)
    mid_cols = np.array(
        [min(i * slice_width + slice_width // 2, roi_width - 1) for i in range(num_slice)]
    )
    # columns shape: (roi_height, 24, 3)
    columns = roi_processed[:, mid_cols, :]

    # Batch pixel analysis for all 24 columns simultaneously
    pixel_sums = columns.sum(axis=2)  # (H, 24)
    is_black = pixel_sums == 0  # (H, 24)
    # White check: all channels >= 253 (equivalent to abs(ch-255) <= 2, no int16 alloc)
    is_white = np.all(columns >= 253, axis=2)  # (H, 24)

    # Compute bar heights for all 24 slices — fully vectorized (no Python loop)
    reset_limit = max(1, roi_height - max(1, lower_grid_buffer // scale_amount))

    # Find last white pixel row per column using flipped argmax
    white_region = is_white[:reset_limit]  # (reset_limit, 24)
    flipped = white_region[::-1]  # flip vertically
    has_white = flipped.any(axis=0)  # (24,) — does column have any white?
    first_true_flipped = np.argmax(flipped, axis=0)  # (24,) — first True in flipped
    last_white = reset_limit - 1 - first_true_flipped  # (24,) — last white in original
    start_after = np.where(has_white, last_white + 1, 0)  # (24,)

    # Count black pixels below start_after for each column
    row_indices = np.arange(roi_height)[:, np.newaxis]  # (H, 1)
    active_mask = row_indices >= start_after[np.newaxis, :]  # (H, 24) broadcast
    counters = (is_black & active_mask).sum(axis=0)  # (24,)
    row = (max_y * counters / roi_height).tolist()

    if DEBUG_ENABLED:
        for s in range(num_slice):
            logger.debug(f"Slice {s}: {row[s]:.2f}")

    # Append total
    row.append(np.sum(row))

    # Debug visualization — only scale up when needed for display
    if DEBUG_ENABLED:
        roi_scaled = scale_up(roi_processed, scale_amount)
        img_copy = scale_up(img.copy(), scale_amount)
        scaled_roi_x = roi_x * scale_amount
        scaled_roi_y = roi_y * scale_amount
        scaled_slice_width = slice_width * scale_amount
        for slice_index in range(num_slice):
            slice_x = scaled_roi_x + slice_index * scaled_slice_width
            cv2.rectangle(
                img_copy,
                (slice_x, scaled_roi_y),
                (slice_x + scaled_slice_width, scaled_roi_y + roi_height * scale_amount),
                (0, 255, 0),
                2,
            )
        cv2.imshow("Grid ROI", roi_scaled)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    else:
        # Return unscaled processed ROI — callers only use the image in
        # debug paths. Skipping scale_up saves ~300µs per call.
        img_copy = roi_processed

    logger.debug("Slice complete, returning")
    return row, img_copy, scale_amount


def compute_bar_alignment_score(
    roi: np.ndarray,
    hourly_values: list[float],
) -> float:
    """Compute alignment score between visual bar graph and computed values.

    Detects misalignment issues when grid coordinates are off or bars
    are aligned to wrong hours.

    Args:
        roi: The cropped graph region (BGR format)
        hourly_values: Computed bar values for each hour (24 values)

    Returns:
        Score from 0.0 to 1.0 where 1.0 = perfect alignment
    """
    try:
        num_slices = 24
        roi_height, roi_width = roi.shape[:2]

        # Ensure exactly 24 hourly values
        values = hourly_values[:24] if len(hourly_values) > 24 else hourly_values
        if len(values) < 24:
            values = values + [0.0] * (24 - len(values))

        if roi.size == 0:
            return 0.0

        # Convert to HSV to detect blue bars
        if len(roi.shape) == 3:
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        else:
            hsv = None

        # Extract bar heights from image
        slice_width = roi_width // num_slices
        extracted_heights = []

        for i in range(num_slices):
            mid_start = i * slice_width + slice_width // 4
            mid_end = i * slice_width + 3 * slice_width // 4
            if mid_end > roi_width:
                mid_end = roi_width

            if hsv is not None:
                col_slice = hsv[:, mid_start:mid_end]

                if col_slice.size == 0:
                    extracted_heights.append(0.0)
                    continue

                hue = col_slice[:, :, 0]
                sat = col_slice[:, :, 1]
                val = col_slice[:, :, 2]

                # Blue bars: hue 90-130, saturation > 50, value > 100
                blue_mask = (hue >= 90) & (hue <= 130) & (sat > 50) & (val > 100)
                row_has_blue = np.any(blue_mask, axis=1)

                blue_rows = np.where(row_has_blue)[0]
                bar_height = roi_height - int(blue_rows[0]) if len(blue_rows) > 0 else 0

                normalized_height = (bar_height / roi_height) * 60
                extracted_heights.append(normalized_height)
            else:
                # Grayscale fallback
                gray_slice = roi[:, mid_start:mid_end]
                if gray_slice.size == 0:
                    extracted_heights.append(0.0)
                    continue

                col_avg = np.mean(gray_slice, axis=1)
                threshold = np.mean(col_avg) * 0.8

                dark_rows = np.where(col_avg < threshold)[0]
                bar_height = roi_height - int(dark_rows[0]) if len(dark_rows) > 0 else 0

                normalized_height = (bar_height / roi_height) * 60
                extracted_heights.append(normalized_height)

        # Compare extracted vs computed
        extracted = np.array(extracted_heights, dtype=float)
        computed = np.array(values, dtype=float)

        extracted_sum = np.sum(extracted)
        computed_sum = np.sum(computed)

        if extracted_sum == 0 and computed_sum == 0:
            return 1.0

        if extracted_sum == 0 or computed_sum == 0:
            max_possible = max(extracted_sum, computed_sum)
            if max_possible > 30:
                return 0.1
            else:
                return 0.3

        # Normalize and compute MAE
        extracted_norm = extracted / (np.max(extracted) + 1e-10)
        computed_norm = computed / (np.max(computed) + 1e-10)
        mae = np.mean(np.abs(extracted_norm - computed_norm))
        score = 1.0 - mae

        # Check for shift detection
        extracted_nonzero = np.where(extracted_norm > 0.1)[0]
        computed_nonzero = np.where(computed_norm > 0.1)[0]

        if len(extracted_nonzero) > 0 and len(computed_nonzero) > 0:
            start_diff = abs(extracted_nonzero[0] - computed_nonzero[0])
            if start_diff >= 2:
                shift_penalty = min(start_diff * 0.15, 0.5)
                score = max(0.0, score - shift_penalty)

        return float(score)

    except Exception as e:
        logger.warning(f"Error computing bar alignment score: {e}")
        return 0.5
