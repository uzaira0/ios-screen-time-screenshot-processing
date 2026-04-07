"""Region of Interest (ROI) calculation for bar graph extraction.

This module provides functions to calculate and validate the ROI
that contains the bar graph region in iOS Screen Time screenshots.
"""

from __future__ import annotations

import logging

import numpy as np

from .exceptions import ImageProcessingError

logger = logging.getLogger(__name__)


def calculate_roi_from_clicks(
    upper_left: tuple[int, int],
    lower_right: tuple[int, int],
    snap_to_grid_func=None,
    img: np.ndarray | None = None,
) -> tuple[int, int, int, int]:
    """Calculate ROI from user click coordinates.

    Args:
        upper_left: (x, y) of upper-left corner
        lower_right: (x, y) of lower-right corner
        snap_to_grid_func: Optional function to snap to grid lines
        img: Optional image for bounds validation

    Returns:
        tuple: (roi_x, roi_y, roi_width, roi_height)

    Raises:
        ImageProcessingError: If coordinates are invalid
    """
    if len(upper_left) != 2 or len(lower_right) != 2:
        raise ImageProcessingError("Coordinates must be tuples of (x, y)")

    if any(coord < 0 for coord in upper_left + lower_right):
        raise ImageProcessingError("Coordinates cannot be negative")

    roi_width = lower_right[0] - upper_left[0]
    roi_height = lower_right[1] - upper_left[1]

    if roi_width <= 0 or roi_height <= 0:
        raise ImageProcessingError(f"Invalid region dimensions: width={roi_width}, height={roi_height}")

    if img is not None:
        img_height, img_width = img.shape[:2]
        if upper_left[0] >= img_width or upper_left[1] >= img_height:
            raise ImageProcessingError(
                f"Upper left coordinate {upper_left} exceeds image bounds ({img_width}, {img_height})"
            )
        if lower_right[0] > img_width or lower_right[1] > img_height:
            raise ImageProcessingError(
                f"Lower right coordinate {lower_right} exceeds image bounds ({img_width}, {img_height})"
            )

    return upper_left[0], upper_left[1], roi_width, roi_height


def calculate_roi(
    lower_left_x: int,
    upper_right_y: int,
    roi_width: int,
    roi_height: int,
    img: np.ndarray,
    snap_to_grid=None,
) -> tuple[int, int, int, int]:
    """Calculate and validate ROI from anchor positions.

    Args:
        lower_left_x: X coordinate of lower-left anchor
        upper_right_y: Y coordinate of upper-right anchor
        roi_width: Calculated width
        roi_height: Calculated height
        img: Image for bounds validation
        snap_to_grid: Optional function to snap to grid lines

    Returns:
        tuple: (roi_x, roi_y, roi_width, roi_height)

    Raises:
        ValueError: If ROI is invalid or out of bounds
    """
    if img is None or img.size == 0:
        raise ValueError("Invalid image provided for ROI calculation")

    img_height, img_width = img.shape[:2]

    if snap_to_grid:
        lower_left_x, upper_right_y, roi_width, roi_height = snap_to_grid(
            img, lower_left_x, upper_right_y, roi_width, roi_height
        )

    if lower_left_x < 0:
        raise ValueError(f"Invalid ROI lower left x coordinate: {lower_left_x}")
    if upper_right_y < 0:
        raise ValueError(f"Invalid ROI upper right y coordinate: {upper_right_y}")
    if roi_width <= 0:
        raise ValueError(f"Invalid ROI width value: {roi_width}")
    if roi_height <= 0:
        raise ValueError(f"Invalid ROI height value: {roi_height}")

    if lower_left_x >= img_width:
        raise ValueError(f"ROI x coordinate {lower_left_x} exceeds image width {img_width}")
    if upper_right_y >= img_height:
        raise ValueError(f"ROI y coordinate {upper_right_y} exceeds image height {img_height}")
    if lower_left_x + roi_width > img_width:
        raise ValueError(f"ROI extends beyond image width: {lower_left_x + roi_width} > {img_width}")
    if upper_right_y + roi_height > img_height:
        raise ValueError(f"ROI extends beyond image height: {upper_right_y + roi_height} > {img_height}")

    return lower_left_x, upper_right_y, roi_width, roi_height
