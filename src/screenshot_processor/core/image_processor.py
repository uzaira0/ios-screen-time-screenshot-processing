"""Image processing for iOS Screen Time screenshot analysis.

This module provides the main entry points for processing screenshots
and extracting bar graph data. It coordinates between specialized modules:

- grid_anchors: Detects "12AM" and "60" text anchors
- bar_extraction: Extracts hourly values from bar graphs
- roi: Calculates regions of interest
- ocr_integration: Handles OCR for anchor detection
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from .bar_extraction import slice_image
from .config import OCRConfig
from .exceptions import ImageProcessingError
from .grid_anchors import find_grid_anchors_and_calculate_roi
from .image_utils import (
    adjust_contrast_brightness,
    convert_dark_mode,
    convert_dark_mode_for_ocr,
    is_dark_mode,
    remove_all_but,
)
from .ocr import find_title_and_total, get_text
from .ocr_integration import adjust_anchor_offsets, perform_ocr, prepare_image_chunks
from .roi import calculate_roi, calculate_roi_from_clicks

logger = logging.getLogger(__name__)

DEBUG_ENABLED = False


def load_and_validate_image(filename: Path | str) -> np.ndarray:
    """Load an image and convert from dark mode if necessary.

    Args:
        filename: Path to image file

    Returns:
        Loaded image in BGR format

    Raises:
        ImageProcessingError: If image cannot be loaded
    """
    img = cv2.imread(str(filename))
    if img is None:
        raise ImageProcessingError("Failed to load image.")
    img = convert_dark_mode(img)
    return img


def extract_hourly_data_only(
    filename: Path | str,
    upper_left: tuple[int, int],
    lower_right: tuple[int, int],
    is_battery: bool,
) -> list:
    """Extract only hourly bar values without running full OCR.

    Much faster than process_image_with_grid when title/total are already known.

    Args:
        filename: Path to image file
        upper_left: (x, y) of grid upper-left corner
        lower_right: (x, y) of grid lower-right corner
        is_battery: Whether this is a battery screenshot

    Returns:
        List of 25 values (24 hours + total)
    """
    img_raw = cv2.imread(str(filename))
    if img_raw is None:
        raise ImageProcessingError("Failed to load image.")

    img = convert_dark_mode(img_raw)
    img = adjust_contrast_brightness(img, contrast=2.0, brightness=-220)

    upper_left_x, upper_left_y, roi_width, roi_height = calculate_roi_from_clicks(upper_left, lower_right, None, img)

    if upper_left_x < 0 or upper_left_y < 0:
        raise ImageProcessingError("ROI coordinates are out of image bounds.")

    if is_battery:
        img_new = remove_all_but(img_raw.copy(), np.array([255, 121, 0]))
        no_dark_blue_detected = (
            np.sum(255 - img_new[upper_left_y : upper_left_y + roi_height, upper_left_x : upper_left_x + roi_width])
            < 10
        )
        if no_dark_blue_detected:
            img_new = remove_all_but(img_raw.copy(), np.array([0, 255 - 121, 255]))
        img_for_slice = img_new
    else:
        img_for_slice = img_raw

    row, _, _ = slice_image(img_for_slice, upper_left_x, upper_left_y, roi_width, roi_height)
    return row


def process_image_with_grid(
    filename: Path | str,
    upper_left: tuple[int, int],
    lower_right: tuple[int, int],
    is_battery: bool,
    snap_to_grid: Callable | None,
    ocr_config: OCRConfig | None = None,
) -> tuple:
    """Process image with user-provided grid coordinates.

    Args:
        filename: Path to image file
        upper_left: (x, y) of grid upper-left corner
        lower_right: (x, y) of grid lower-right corner
        is_battery: Whether this is a battery screenshot
        snap_to_grid: Optional function to snap to grid lines
        ocr_config: Optional OCR configuration

    Returns:
        Tuple of (filename, graph_filename, row, title, total, total_image_path)
    """
    try:
        raw_img = load_and_validate_image(filename)
        img = adjust_contrast_brightness(raw_img, contrast=2.0, brightness=-220)

        snap_func = snap_to_grid if snap_to_grid else None

        logger.debug("Calculating region of interest from clicks...")
        upper_left_x, upper_left_y, roi_width, roi_height = calculate_roi_from_clicks(
            upper_left, lower_right, snap_func, img
        )

        if upper_left_x < 0 or upper_left_y < 0:
            raise ImageProcessingError("ROI coordinates are out of image bounds.")

        roi_x = upper_left_x
        roi_y = upper_left_y

        if is_battery:
            logger.debug("Extracting time...")
            title = find_time(raw_img, roi_x, roi_y, roi_width, roi_height)
            total = "N/A"
            total_image_path = None
        else:
            logger.debug("Extracting title and total...")
            title, _, total, total_image_path = find_title_and_total(raw_img, ocr_config)

        filename, row, graph_filename = save_image(
            filename, roi_x, roi_y, roi_width, roi_height, is_battery, preloaded_img=raw_img
        )

    except ImageProcessingError as e:
        logger.error(f"Image processing failed: {e}")
        raise

    return filename, graph_filename, row, title, total, total_image_path


def process_image(
    filename: str,
    is_battery: bool,
    snap_to_grid: Callable | None,
    ocr_config: OCRConfig | None = None,
) -> tuple[str, str, list, str, str, str | None, dict | None]:
    """Process an image with automatic grid detection.

    Args:
        filename: Path to image file
        is_battery: Whether this is a battery screenshot
        snap_to_grid: Optional function to snap to grid lines
        ocr_config: Optional OCR configuration

    Returns:
        Tuple of (filename, graph_filename, row, title, total, total_image_path, grid_coords)
    """
    img_original = cv2.imread(str(filename))
    if img_original is None:
        raise ImageProcessingError("Failed to load image.")
    img = convert_dark_mode(img_original.copy())
    return apply_processing(filename, img, is_battery, snap_to_grid, ocr_config, raw_img=img, original_img=img_original)


def apply_processing(
    filename: str,
    img: np.ndarray,
    is_battery: bool,
    snap_to_grid: Callable | None,
    ocr_config: OCRConfig | None = None,
    raw_img: np.ndarray | None = None,
    original_img: np.ndarray | None = None,
) -> tuple[str, str, list, str, str, str | None, dict | None]:
    """Apply processing pipeline to a loaded image.

    Args:
        filename: Path to image file (for saving outputs)
        img: Loaded image in BGR format (dark-mode-converted)
        is_battery: Whether this is a battery screenshot
        snap_to_grid: Optional function to snap to grid lines
        ocr_config: Optional OCR configuration
        raw_img: Dark-mode-converted image for bar extraction
        original_img: Original image before dark mode conversion (for OCR fallback)

    Returns:
        Tuple of (filename, graph_filename, row, title, total, total_image_path, grid_coords)
    """
    img = adjust_contrast_brightness(img.copy(), contrast=2.0, brightness=-220)
    img_left, img_right, right_offset = prepare_image_chunks(img)

    d_left, d_right = perform_ocr(img_left, img_right, ocr_config)
    adjust_anchor_offsets(d_right, right_offset)

    roi_params = find_grid_anchors_and_calculate_roi(d_left, d_right, img, img, snap_to_grid, calculate_roi)

    # Dark mode fallback: standard preprocessing destroys faint text contrast
    # (contrast=3.0 clips both text and background to ~255). Use adaptive
    # thresholding which preserves text for Tesseract anchor detection.
    orig = original_img if original_img is not None else raw_img
    if roi_params is None and orig is not None and is_dark_mode(orig):
        logger.info("Standard anchor detection failed on dark mode image, retrying with adaptive threshold OCR")
        img_ocr = convert_dark_mode_for_ocr(orig.copy())
        img_ocr = adjust_contrast_brightness(img_ocr, contrast=2.0, brightness=-220)
        ocr_left, ocr_right, ocr_right_offset = prepare_image_chunks(img_ocr)
        d_left, d_right = perform_ocr(ocr_left, ocr_right, ocr_config)
        adjust_anchor_offsets(d_right, ocr_right_offset)
        roi_params = find_grid_anchors_and_calculate_roi(d_left, d_right, img, img, snap_to_grid, calculate_roi)

    if roi_params is None:
        raise ValueError("Couldn't find graph anchors!")

    roi_x, roi_y, roi_width, roi_height = roi_params

    grid_coords = {
        "upper_left_x": roi_x,
        "upper_left_y": roi_y,
        "lower_right_x": roi_x + roi_width,
        "lower_right_y": roi_y + roi_height,
    }

    if is_battery:
        title = find_time(img, roi_x, roi_y, roi_width, roi_height)
        total, total_image_path = "N/A", None
    else:
        title, _, total, total_image_path = find_title_and_total(img, ocr_config)

    filename, row, graph_filename = save_image(
        filename, roi_x, roi_y, roi_width, roi_height, is_battery, preloaded_img=raw_img
    )
    return filename, graph_filename, row, title, total, total_image_path, grid_coords


def find_time(
    img: np.ndarray,
    roi_x: int,
    roi_y: int,
    roi_width: int,
    roi_height: int,
) -> str:
    """Extract time string for battery screenshots."""
    text1, text2, is_pm = get_text(img, roi_x, roi_y, roi_width, roi_height)
    return text1


def save_image(
    filename: Path | str,
    roi_x: int,
    roi_y: int,
    roi_width: int,
    roi_height: int,
    is_battery: bool,
    preloaded_img: np.ndarray | None = None,
) -> tuple[str | None, list, str | None]:
    """Extract bar values and optionally save debug images.

    Args:
        filename: Path to image file
        roi_x: X coordinate of ROI
        roi_y: Y coordinate of ROI
        roi_width: Width of ROI
        roi_height: Height of ROI
        is_battery: Whether this is a battery screenshot
        preloaded_img: Pre-loaded dark-mode-converted image (avoids re-reading from disk)

    Returns:
        Tuple of (selection_save_path, row values, graph_save_path)
    """
    logger.debug("Preparing to extract grid")
    img = preloaded_img if preloaded_img is not None else load_and_validate_image(filename)

    if is_battery:
        logger.debug("Removing all but the dark blue color...")
        img_new = remove_all_but(img.copy(), np.array([255, 121, 0]))
        no_dark_blue_detected = np.sum(255 - img_new[roi_y : roi_y + roi_height, roi_x : roi_x + roi_width]) < 10
        if no_dark_blue_detected:
            logger.debug("No dark blue color detected; assuming dark mode...")
            img_new = remove_all_but(img.copy(), np.array([0, 255 - 121, 255]))
        img = img_new

    row, img, scale_amount = slice_image(img, roi_x, roi_y, roi_width, roi_height)

    selection_save_path = None
    graph_save_path = None

    if DEBUG_ENABLED:
        logger.debug("Saving processed image...")
        selection_save_path = _save_processed_image(img, roi_x, roi_y, roi_width, roi_height, filename, scale_amount)
        graph_save_path = _save_debug_graph(filename, row, roi_height)

    return selection_save_path, row, graph_save_path


def _save_processed_image(
    image: np.ndarray,
    x: int,
    y: int,
    width: int,
    height: int,
    original_filename: str | Path,
    scale_amount: int,
) -> str:
    """Save processed ROI image for debugging."""
    debug_folder = "debug"
    Path(debug_folder).mkdir(parents=True, exist_ok=True)
    save_name = Path(debug_folder) / Path(original_filename).name
    roi = image[
        scale_amount * y : scale_amount * y + scale_amount * height,
        scale_amount * x : scale_amount * x + scale_amount * width,
    ]

    save_name = str(save_name).replace(".jfif", ".jpg")
    cv2.imwrite(save_name, roi)
    return save_name


def _save_debug_graph(filename: str | Path, row: list, roi_height: int) -> str:
    """Save bar graph visualization for debugging."""
    import matplotlib.pyplot as plt

    debug_folder = "debug"
    Path(debug_folder).mkdir(parents=True, exist_ok=True)

    graph_save_path = Path(debug_folder) / f"graph_{Path(filename).name}"
    graph_save_path = str(graph_save_path).replace(".jfif", ".jpg")

    plt.figure(figsize=(8, 3))

    total_minutes = row[-1]
    hours = int(total_minutes // 60)
    minutes = int(total_minutes % 60)
    total_text = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

    ax = plt.gca()
    plt.xlabel(
        f"Calculated Total: {total_text}",
        ha="center",
        va="center",
        labelpad=20,
        fontsize=16,
        fontweight="bold",
        color="#0066CC",
    )

    x = range(len(row[:-1]))
    height = row[:-1]
    plt.bar(np.array(x) + 0.5, height, color="#4682B4")
    plt.ylim([0, 60])
    plt.xlim([0, 24])

    tick_positions = np.array(range(24)) + 0.5
    tick_labels = [f"{int(v)}" for v in height]
    plt.xticks(tick_positions, tick_labels, fontsize=9, fontweight="bold")

    plt.yticks([])
    ax.yaxis.set_visible(False)

    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)

    for x_val in range(25):
        plt.axvline(x=x_val, color="gray", linestyle="--", linewidth=0.7, alpha=0.4)

    plt.tight_layout(pad=0)
    plt.savefig(graph_save_path, bbox_inches="tight", pad_inches=0, dpi=120)
    plt.close()

    return graph_save_path


# Utility functions for image comparison (used in testing/validation)


def mse_between_loaded_images(image1: np.ndarray, image2: np.ndarray) -> float:
    """Calculate mean squared error between two images."""
    if image2.shape[:2] != image1.shape[:2]:
        image2 = cv2.resize(image2, (image1.shape[1], image1.shape[0]))

    height, width, _ = image1.shape
    diff = cv2.subtract(image1, image2)
    error = np.sum(diff**2)
    mean_squared_error = error / float(height * width)
    logger.debug(f"MSE between selection and graph: {mean_squared_error}")
    return float(mean_squared_error)


def hconcat_resize(
    img_list: list[np.ndarray],
    interpolation: cv2.InterpolationFlags = cv2.INTER_CUBIC,
) -> np.ndarray:
    """Horizontally concatenate images with height normalization."""
    h_max = max(img.shape[0] for img in img_list)

    im_list_resize = [
        cv2.resize(
            img,
            (int(img.shape[1] * h_max / img.shape[0]), h_max),
            interpolation=interpolation,
        )
        for img in img_list
    ]

    return cv2.hconcat(im_list_resize)


def compare_blue_in_images(
    image1_path: str | Path | None = None,
    image2_path: str | Path | None = None,
    image1: np.ndarray | None = None,
    image2: np.ndarray | None = None,
) -> None:
    """Compare blue bar content between two images for validation."""
    if image1_path is not None and image2_path is not None:
        image1 = cv2.imread(str(image1_path))
        image2 = cv2.imread(str(image2_path))
    elif image1 is not None and image2 is not None:
        pass
    else:
        raise ValueError("Incorrect argument set entered.")

    hsv1 = cv2.cvtColor(image1, cv2.COLOR_BGR2HSV)
    hsv2 = cv2.cvtColor(image2, cv2.COLOR_BGR2HSV)

    lower_blue = np.array([90, 50, 50])
    upper_blue = np.array([150, 255, 255])

    mask1 = cv2.inRange(hsv1, lower_blue, upper_blue)
    mask2 = cv2.inRange(hsv2, lower_blue, upper_blue)

    blue_only_image1 = cv2.bitwise_and(image1, image1, mask=mask1)
    blue_only_image2 = cv2.bitwise_and(image2, image2, mask=mask2)

    gray_image1 = cv2.cvtColor(blue_only_image1, cv2.COLOR_BGR2GRAY)
    gray_image2 = cv2.cvtColor(blue_only_image2, cv2.COLOR_BGR2GRAY)

    _, binary_image1 = cv2.threshold(gray_image1, 1, 255, cv2.THRESH_BINARY)
    _, binary_image2 = cv2.threshold(gray_image2, 1, 255, cv2.THRESH_BINARY)

    binary_image2 = cv2.resize(binary_image2, (binary_image1.shape[1], binary_image1.shape[0]))

    height, width = binary_image1.shape
    diff = cv2.subtract(binary_image1, binary_image2)
    error = np.sum(diff**2)
    mean_squared_error = error / float(height * width)

    logger.debug(f"MSE between selection and graph based on blue bars: {mean_squared_error}")
