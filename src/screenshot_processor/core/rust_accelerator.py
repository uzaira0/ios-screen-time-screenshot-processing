"""Rust acceleration layer — try Rust (PyO3) first, fall back to Python.

If screenshot_processor_rs is installed, functions run in Rust (~30x faster).
Otherwise, they transparently fall back to the pure-Python implementations.
Runtime Rust errors also fall back to Python (not just import failures).

Usage:
    from screenshot_processor.core.rust_accelerator import (
        normalize_ocr_digits, extract_time_from_text, detect_grid, process_image,
        process_image_with_grid,
    )
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_RUST_AVAILABLE: bool | None = None
_rs = None


def _check_rust():
    global _RUST_AVAILABLE, _rs
    if _RUST_AVAILABLE is None:
        try:
            import screenshot_processor_rs  # pyright: ignore[reportMissingImports]

            # Set _rs BEFORE _RUST_AVAILABLE to prevent race where another
            # thread sees True but _rs is still None
            _rs = screenshot_processor_rs
            _RUST_AVAILABLE = True
            logger.info("Rust acceleration enabled (screenshot_processor_rs)")
        except ImportError:
            _RUST_AVAILABLE = False
            logger.debug("screenshot_processor_rs not installed, using Python fallback")
    return _RUST_AVAILABLE


def normalize_ocr_digits(text: str) -> str:
    """Normalize OCR digit confusions. Rust if available, else Python."""
    if _check_rust():
        try:
            return _rs.normalize_ocr_digits(text)
        except Exception as e:
            logger.warning("Rust normalize_ocr_digits failed, falling back to Python: %s", e)
    from .ocr import _normalize_ocr_digits

    return _normalize_ocr_digits(text)


def extract_time_from_text(text: str) -> str:
    """Extract time from OCR text. Rust if available, else Python."""
    if _check_rust():
        try:
            return _rs.extract_time_from_text(text)
        except Exception as e:
            logger.warning("Rust extract_time_from_text failed, falling back to Python: %s", e)
    from .ocr import _extract_time_from_text

    return _extract_time_from_text(text)


def detect_grid(image_path: str, method: str = "line_based") -> dict | None:
    """Detect grid bounds. Rust if available, else Python."""
    if _check_rust():
        try:
            return _rs.detect_grid(image_path, method)
        except Exception as e:
            logger.warning("Rust detect_grid failed, falling back to Python: %s", e)

    from .image_processor import load_and_validate_image
    from .line_based_detection import LineBasedDetector

    img = load_and_validate_image(image_path)
    h, w = img.shape[:2]
    detector = LineBasedDetector.default()
    result = detector.detect(img, resolution=f"{w}x{h}")
    if result.success and result.bounds:
        b = result.bounds
        return {
            "upper_left_x": b.x,
            "upper_left_y": b.y,
            "lower_right_x": b.x + b.width,
            "lower_right_y": b.y + b.height,
        }
    return None


def process_image_optimized(
    image_path: str,
    image_type: str = "screen_time",
    detection_method: str = "line_based",
    max_shift: int = 5,
) -> dict | None:
    """Full pipeline + boundary optimizer, fully in Rust. Returns None if Rust unavailable."""
    if _check_rust():
        try:
            return _rs.process_image_optimized(image_path, image_type, detection_method, max_shift)
        except Exception as e:
            logger.warning("Rust process_image_optimized failed, falling back to Python: %s", e)
    return None


def process_image(
    image_path: str,
    image_type: str = "screen_time",
    detection_method: str = "line_based",
) -> dict:
    """Full pipeline processing. Rust if available, else Python."""
    if _check_rust():
        try:
            return _rs.process_image(image_path, image_type, detection_method)
        except Exception as e:
            logger.warning("Rust process_image failed, falling back to Python: %s", e)

    # Python fallback
    from .image_processor import process_image as py_process_image

    is_battery = image_type == "battery"
    result = py_process_image(image_path, is_battery, snap_to_grid=None)
    if result is None:
        raise RuntimeError("Python process_image returned None")

    filename, graph_filename, row, title, total, total_image_path, grid_coords = result
    return {
        "hourly_values": list(row[:24]) if row else [0.0] * 24,
        "total": sum(row[:24]) if row else 0.0,
        "title": title,
        "total_text": total,
        "grid_bounds": grid_coords,
        "alignment_score": 0.0,
        "detection_method": detection_method,
        "processing_time_ms": 0,
    }


def extract_hourly_data(
    image_path: str,
    upper_left: tuple[int, int],
    lower_right: tuple[int, int],
    image_type: str = "screen_time",
) -> list[float] | None:
    """Extract only hourly bar values from known grid bounds. No OCR — fast path.

    Returns:
        list of 24 floats (minutes per hour), or None if extraction failed
    """
    if _check_rust():
        try:
            result = _rs.extract_hourly_data(
                image_path,
                [int(upper_left[0]), int(upper_left[1])],
                [int(lower_right[0]), int(lower_right[1])],
                image_type,
            )
            return list(result)
        except Exception as e:
            logger.warning("Rust extract_hourly_data failed, falling back to Python: %s", e)

    # Python fallback
    from .image_processor import extract_hourly_data_only

    is_battery = image_type == "battery"
    try:
        row = extract_hourly_data_only(image_path, upper_left, lower_right, is_battery)
    except Exception as e:
        logger.warning("Python extract_hourly_data_only failed for %s: %s", image_path, e)
        row = None
    return list(row[:24]) if row is not None else None


def process_image_with_grid(
    image_path: str,
    upper_left: tuple[int, int],
    lower_right: tuple[int, int],
    image_type: str = "screen_time",
) -> dict:
    """Extract hourly data using pre-computed grid bounds. Rust if available, else Python.

    Note: The PyO3 wrapper strips OCR results (title/total) — the Rust pipeline
    runs OCR internally but does not expose them through this function.
    Callers that need title/total should pass them separately.

    Returns:
        dict with keys: hourly_values (list[float], len=24), total (float),
        alignment_score (float), processing_time_ms (int)
    """
    if _check_rust():
        try:
            return _rs.process_image_with_grid(
                image_path,
                [int(upper_left[0]), int(upper_left[1])],
                [int(lower_right[0]), int(lower_right[1])],
                image_type,
            )
        except Exception as e:
            logger.warning("Rust process_image_with_grid failed, falling back to Python: %s", e)

    # Python fallback
    from .image_processor import extract_hourly_data_only

    is_battery = image_type == "battery"
    try:
        row = extract_hourly_data_only(image_path, upper_left, lower_right, is_battery)
    except Exception as e:
        logger.warning("Python extract_hourly_data_only failed for %s: %s", image_path, e)
        row = None
    hourly = list(row[:24]) if row is not None else [0.0] * 24
    return {
        "hourly_values": hourly,
        "total": sum(hourly),
        "alignment_score": 0.0,
        "processing_time_ms": 0,
    }
