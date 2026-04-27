from __future__ import annotations

import logging

import cv2
import numpy as np

from .models import LineExtractionMode

logger = logging.getLogger(__name__)

DEBUG_ENABLED = False


def is_dark_mode(img: np.ndarray) -> bool:
    """Check if an image is in dark mode based on average brightness."""
    dark_mode_threshold = 100
    channel_means = cv2.mean(img)
    avg = sum(channel_means[:3]) / 3.0 if len(img.shape) == 3 else channel_means[0]
    return avg < dark_mode_threshold


def convert_dark_mode(img: np.ndarray) -> np.ndarray:
    if is_dark_mode(img):
        cv2.bitwise_not(img, dst=img)
        img = adjust_contrast_brightness(img, 3.0, 10)

    return img


def simple_grayscale(image: np.ndarray) -> np.ndarray:
    """Convert BGR/RGB image to grayscale using simple (R+G+B)/3 average.

    Matches the Rust implementation's grayscale conversion exactly.
    """
    if len(image.shape) == 2:
        return image
    return (image[..., :3].astype(np.uint16).sum(axis=2) // 3).astype(np.uint8)


def convert_dark_mode_for_ocr(img: np.ndarray) -> np.ndarray:
    """Convert dark mode image using adaptive thresholding optimized for OCR.

    The standard convert_dark_mode uses contrast=3.0 which clips faint gray text
    (e.g., "12 AM", "60" labels) to near-white, destroying contrast for Tesseract.
    This function uses adaptive thresholding to preserve text readability.
    """
    if not is_dark_mode(img):
        return img

    inverted = cv2.bitwise_not(img)
    gray = simple_grayscale(inverted)
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 31, 10)
    # Convert back to 3-channel for compatibility with downstream code
    return cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)


def adjust_contrast_brightness(img: np.ndarray, contrast: float = 1.0, brightness: int = 0) -> np.ndarray:
    brightness += int(round(255 * (1 - contrast) / 2))
    return cv2.addWeighted(img, contrast, img, 0, brightness)


def get_pixel(img: np.ndarray, arg: int) -> np.ndarray | None:
    unq, count = np.unique(img.reshape(-1, img.shape[-1]), axis=0, return_counts=True)
    sort = np.argsort(count)
    sorted_unq = unq[sort]
    if len(sorted_unq) <= 1:
        return None
    if np.abs(arg) >= len(sorted_unq):
        return sorted_unq[0]
    return sorted_unq[arg]


def reduce_color_count(img: np.ndarray, num_colors: int) -> np.ndarray:
    # Use OpenCV LUT for SIMD-optimized color quantization.
    # Build a 256-entry lookup table mapping each value to its quantized bin.
    input_vals = np.arange(256, dtype=np.float64)
    bin_indices = np.clip((input_vals * num_colors / 255).astype(int), 0, num_colors - 1)
    output_vals = (bin_indices * 255 / (num_colors - 1)).astype(np.uint8)
    # Only values in [i*255/n, (i+1)*255/n) are mapped; values >= last boundary
    # are left untouched (identity).
    lut = np.arange(256, dtype=np.uint8)
    boundary = num_colors * 255.0 / num_colors
    mapped = input_vals < boundary
    lut[mapped] = output_vals[mapped]
    # cv2.LUT is SIMD-optimized C++ — faster than np.take for image LUT ops.
    cv2.LUT(img, lut, dst=img)
    return img


def remove_all_but(img: np.ndarray, color: np.ndarray, threshold: int = 30):
    # Squared L2 distance avoids sqrt (faster than np.linalg.norm).
    # threshold² comparison is equivalent to threshold comparison on norm.
    diff = img.astype(np.int16) - color.astype(np.int16)
    sq_dist = (diff * diff).sum(axis=2)
    mask = sq_dist <= threshold * threshold
    img[mask] = [0, 0, 0]
    img[~mask] = [255, 255, 255]
    return img


def darken_non_white(img: np.ndarray) -> np.ndarray:
    # BT.601 luma > threshold = white. Mirrors crates/processing/src/image_utils.rs
    # and the canvas cvtColorToGray path. Constants come from the SSoT pipeline
    # (shared/processing_constants.json -> generated_constants.py).
    from screenshot_processor.core.generated_constants import (
        DARKEN_NON_WHITE_LUMA_COEFFS,
        DARKEN_NON_WHITE_LUMA_SHIFT,
        DARKEN_NON_WHITE_LUMA_THRESHOLD,
    )

    c0, c1, c2 = DARKEN_NON_WHITE_LUMA_COEFFS
    rgb = img.astype(np.uint32)
    luma = (rgb[..., 0] * c0 + rgb[..., 1] * c1 + rgb[..., 2] * c2) >> DARKEN_NON_WHITE_LUMA_SHIFT
    mask = luma > DARKEN_NON_WHITE_LUMA_THRESHOLD
    img[~mask] = 0
    return img


def scale_up(img, scale_amount):
    width = int(img.shape[1] * scale_amount)
    height = int(img.shape[0] * scale_amount)
    dim = (width, height)

    return cv2.resize(img, dim, interpolation=cv2.INTER_AREA)


def remove_line_color(img: np.ndarray) -> np.ndarray:
    line_color = np.array([203, 199, 199], dtype=np.int16)
    # Vectorized: compute per-pixel L1 distance to line_color, threshold <= 3 (len*thresh)
    diff = np.abs(img.astype(np.int16) - line_color)
    distances = diff.sum(axis=2)
    img[distances <= 3] = 255
    return img


def show_until_destroyed(img_name: str, img: np.ndarray) -> None:
    cv2.imshow(img_name, img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def extract_line(img, x0: int, x1: int, y0: int, y1: int, line_extraction_mode: LineExtractionMode) -> int:
    sub_image = img[y0:y1, x0:x1]

    sub_image = reduce_color_count(sub_image, 2)
    pixel_value = get_pixel(sub_image, -2)
    if pixel_value is None:
        return 0

    if DEBUG_ENABLED:
        cv2.imshow("img", sub_image)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    # Vectorized pixel matching: L1 distance per pixel <= threshold (len * 1)
    pixel_ref = pixel_value.astype(np.int16)
    diff = np.abs(sub_image.astype(np.int16) - pixel_ref)
    close_mask = diff.sum(axis=2) <= len(pixel_value)  # is_close with thresh=1

    if line_extraction_mode == LineExtractionMode.HORIZONTAL:
        row_scores = close_mask.sum(axis=1)
        matches = np.where(row_scores > 0.5 * sub_image.shape[1])[0]
        return int(matches[0]) if len(matches) > 0 else 0

    elif line_extraction_mode == LineExtractionMode.VERTICAL:
        col_scores = close_mask.sum(axis=0)
        matches = np.where(col_scores > 0.25 * sub_image.shape[0])[0]
        return int(matches[0]) if len(matches) > 0 else 0

    else:
        msg = "Invalid mode for line extraction"
        raise ValueError(msg)


