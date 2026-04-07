"""Grid anchor detection for bar graph region localization.

This module provides functions to find the "12AM" and "60" text anchors
that define the boundaries of the bar graph region in iOS Screen Time screenshots.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import cv2
import numpy as np

from .image_utils import extract_line, show_until_destroyed
from .models import LineExtractionMode

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

DEBUG_ENABLED = False


def find_right_anchor(
    ocr_dict: dict,
    img: np.ndarray,
    img_copy: np.ndarray,
) -> tuple[bool, int, int]:
    """Find the "60" anchor text on the right side of the graph.

    The "60" label marks the top-right corner of the bar graph region,
    indicating the maximum value (60 minutes) for any hour bar.

    Args:
        ocr_dict: OCR results dict with keys: level, left, top, width, height, text
        img: Image for line detection
        img_copy: Image copy for debug visualization

    Returns:
        tuple: (found_flag, upper_right_x, upper_right_y)
    """
    found_flag = False
    n_boxes = len(ocr_dict["level"])
    upper_right_x = -1
    upper_right_y = -1
    buffer = 25
    maximum_offset = 100
    key_list = ["60"]

    for i in range(n_boxes):
        (x, y, w, h) = (ocr_dict["left"][i], ocr_dict["top"][i], ocr_dict["width"][i], ocr_dict["height"][i])
        cv2.rectangle(img_copy, (x, y), (x + w, y + h), (0, 255, 0), 2)

        if any(key in ocr_dict["text"][i] for key in key_list) and not found_flag:
            found_flag = True
            if DEBUG_ENABLED:
                cv2.rectangle(img_copy, (x - buffer, y), (x, y + buffer), (255, 0, 3), 2)
                show_until_destroyed("Image", img_copy)

            line_row = None
            line_col = None

            logger.debug("Moving up to search for right anchor...")
            moving_index = 0
            while line_row is None and moving_index < maximum_offset:
                line_row = extract_line(
                    img,
                    x - buffer,
                    x,
                    y - moving_index,
                    y - moving_index + h + buffer,
                    LineExtractionMode.HORIZONTAL,
                )
                moving_index = moving_index + 1
            upper_right_y = y + line_row - moving_index + 1

            logger.debug("Moving left to search for right anchor...")
            moving_index = 0
            while line_col is None and moving_index < maximum_offset:
                line_col = extract_line(
                    img,
                    x - buffer - moving_index,
                    x - moving_index,
                    y,
                    y + h + buffer,
                    LineExtractionMode.VERTICAL,
                )
                moving_index = moving_index + 1
            upper_right_x = x - buffer + line_col - moving_index + 1

            if DEBUG_ENABLED:
                cv2.rectangle(
                    img_copy,
                    (upper_right_x, upper_right_y),
                    (upper_right_x + buffer, upper_right_y + buffer),
                    (0, 0, 3),
                    2,
                )

                show_until_destroyed("Image", img_copy)

    return found_flag, upper_right_x, upper_right_y


def find_left_anchor(
    ocr_dict: dict,
    img: np.ndarray,
    img_copy: np.ndarray,
    *,
    detections_to_skip: int = 0,
) -> tuple[bool, int, int]:
    """Find the "12AM" anchor text on the left side of the graph.

    The "12AM" label marks the bottom-left corner of the bar graph region,
    indicating the start of the hourly display (midnight).

    Args:
        ocr_dict: OCR results dict with keys: level, left, top, width, height, text
        img: Image for line detection
        img_copy: Image copy for debug visualization
        detections_to_skip: Number of matching detections to skip (for retry logic)

    Returns:
        tuple: (found_flag, lower_left_x, lower_left_y)
    """
    found_flag = False
    n_boxes = len(ocr_dict["level"])
    lower_left_x = -1
    lower_left_y = -1
    buffer = 25
    key_list = ["2A", "12", "AM"]
    detection_count = 0
    maximum_offset = 100

    for i in range(n_boxes):
        (x, y, w, h) = (
            ocr_dict["left"][i],
            ocr_dict["top"][i],
            ocr_dict["width"][i],
            ocr_dict["height"][i],
        )
        cv2.rectangle(img_copy, (x, y), (x + w, y + h), (0, 255, 0), 2)

        if any(key in ocr_dict["text"][i] for key in key_list):
            detection_count += 1
            if detection_count <= detections_to_skip:
                continue
            cv2.rectangle(img, (x, y), (x + w, y + h), (255, 255, 255), -1)

            if not found_flag:
                found_flag = True

                if DEBUG_ENABLED:
                    cv2.rectangle(
                        img_copy,
                        (x - buffer, y - buffer),
                        (x + buffer + w, y + buffer + h),
                        (255, 0, 3),
                        2,
                    )
                    show_until_destroyed("Image", img_copy)

                line_row = None
                line_col = None

                logger.debug("Moving up to search for left anchor...")
                moving_index = 0
                while line_row is None and moving_index < maximum_offset:
                    line_row = extract_line(
                        img,
                        x - buffer,
                        x + w + buffer,
                        y - moving_index - buffer,
                        y - moving_index + buffer,
                        LineExtractionMode.HORIZONTAL,
                    )

                    moving_index = moving_index + 1
                lower_left_y = y - buffer + line_row - moving_index + 1

                logger.debug("Moving left to search for left anchor...")
                moving_index = 0
                while line_col is None and moving_index < maximum_offset:
                    line_col = extract_line(
                        img,
                        x - moving_index - buffer,
                        x - moving_index + buffer,
                        y - buffer,
                        y,
                        LineExtractionMode.VERTICAL,
                    )
                    moving_index = moving_index + 1
                lower_left_x = x - buffer + line_col - moving_index + 1

                if DEBUG_ENABLED:
                    cv2.rectangle(
                        img_copy,
                        (x - 2 * buffer, y - buffer),
                        (x - buffer, y + h + buffer),
                        (0, 255, 255),
                        2,
                    )
                    cv2.rectangle(
                        img_copy,
                        (lower_left_x, lower_left_y),
                        (lower_left_x + buffer, lower_left_y + buffer),
                        (255, 0, 3),
                        2,
                    )
                    show_until_destroyed("Image", img_copy)

    return found_flag, lower_left_x, lower_left_y


def find_grid_anchors_and_calculate_roi(
    d_left: dict,
    d_right: dict,
    img: np.ndarray,
    img_copy: np.ndarray,
    snap_to_grid,
    calculate_roi_func,
) -> tuple[int, int, int, int] | None:
    """Find grid anchors and calculate the ROI for the bar graph region.

    Tries to find both the "12AM" (left) and "60" (right) anchors,
    then calculates the region of interest (ROI) from their positions.

    Args:
        d_left: OCR results for left portion of image
        d_right: OCR results for right portion of image
        img: Image for line detection
        img_copy: Image copy for debug visualization
        snap_to_grid: Function to snap ROI to grid lines
        calculate_roi_func: Function to calculate ROI from anchor positions

    Returns:
        tuple (roi_x, roi_y, roi_width, roi_height) or None if anchors not found
    """
    found_12, lower_left_x, lower_left_y = find_left_anchor(d_left, img, img_copy, detections_to_skip=0)
    found_60, upper_right_x, upper_right_y = find_right_anchor(d_right, img, img_copy)

    if found_12 and found_60:
        try:
            return calculate_roi_func(
                lower_left_x,
                upper_right_y,
                upper_right_x - lower_left_x,
                lower_left_y - upper_right_y,
                img,
                snap_to_grid=snap_to_grid,
            )
        except (ValueError, IndexError) as e:
            logger.debug(f"First attempt failed: {e}")

    for skip_value in range(1, 4):
        found_12, lower_left_x, lower_left_y = find_left_anchor(d_left, img, img_copy, detections_to_skip=skip_value)
        found_60, upper_right_x, upper_right_y = find_right_anchor(d_right, img, img_copy)

        if found_12 and found_60:
            try:
                return calculate_roi_func(
                    lower_left_x,
                    upper_right_y,
                    upper_right_x - lower_left_x,
                    lower_left_y - upper_right_y,
                    img,
                    snap_to_grid=snap_to_grid,
                )
            except (ValueError, IndexError) as e:
                logger.debug(f"Attempt with skip={skip_value} failed: {e}")
                continue

    return None
