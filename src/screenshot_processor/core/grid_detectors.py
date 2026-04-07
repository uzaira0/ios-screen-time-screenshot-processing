"""
Grid detector implementations.

This module provides concrete implementations of IGridDetector:
- OCRAnchoredGridDetector: Uses OCR to find "12 AM" and "60" text anchors
- LineBasedGridDetector: Uses visual line patterns (wraps existing LineBasedDetector)
"""

from __future__ import annotations

import logging

import numpy as np

from .config import get_hybrid_ocr_config
from .image_utils import convert_dark_mode, convert_dark_mode_for_ocr, is_dark_mode
from .interfaces import (
    GridBounds,
    GridDetectionMethod,
    GridDetectionResult,
    IGridDetector,
)

logger = logging.getLogger(__name__)


class OCRAnchoredGridDetector(IGridDetector):
    """
    Grid detector that uses OCR to find text anchors.

    Looks for "12 AM" on the left side and "60" on the right side
    of the graph to determine the grid boundaries.
    """

    @property
    def method(self) -> GridDetectionMethod:
        return GridDetectionMethod.OCR_ANCHORED

    def detect(self, image: np.ndarray, **kwargs) -> GridDetectionResult:
        """
        Detect grid using OCR text anchors.

        Args:
            image: BGR image array
            **kwargs: Optional parameters (unused)

        Returns:
            GridDetectionResult with bounds if successful
        """
        from .grid_anchors import find_grid_anchors_and_calculate_roi
        from .image_utils import adjust_contrast_brightness
        from .ocr_integration import adjust_anchor_offsets, perform_ocr, prepare_image_chunks
        from .roi import calculate_roi

        try:
            # Convert dark mode if needed
            img = convert_dark_mode(image.copy())

            # Apply contrast/brightness adjustment
            img = adjust_contrast_brightness(img, contrast=2.0, brightness=-220)
            img_copy = img.copy()

            # Prepare image chunks for OCR
            img_left, img_right, right_offset = prepare_image_chunks(img)

            # Perform OCR on left and right chunks using HybridOCR
            ocr_config = get_hybrid_ocr_config()
            d_left, d_right = perform_ocr(img_left, img_right, ocr_config)
            adjust_anchor_offsets(d_right, right_offset)

            # Find grid anchors and calculate ROI
            roi_params = find_grid_anchors_and_calculate_roi(
                d_left, d_right, img, img_copy, snap_to_grid=None, calculate_roi_func=calculate_roi
            )

            # Dark mode fallback: standard preprocessing destroys faint text contrast.
            # Use adaptive thresholding which preserves text for Tesseract.
            if roi_params is None and is_dark_mode(image):
                logger.info("OCR anchor detection failed on dark mode image, retrying with adaptive threshold")
                img_ocr = convert_dark_mode_for_ocr(image.copy())
                img_ocr = adjust_contrast_brightness(img_ocr, contrast=2.0, brightness=-220)
                ocr_left, ocr_right, ocr_right_offset = prepare_image_chunks(img_ocr)
                d_left_retry, d_right_retry = perform_ocr(ocr_left, ocr_right, ocr_config)
                adjust_anchor_offsets(d_right_retry, ocr_right_offset)
                roi_params = find_grid_anchors_and_calculate_roi(
                    d_left_retry, d_right_retry, img, img_copy, snap_to_grid=None, calculate_roi_func=calculate_roi
                )

            if roi_params is None:
                return GridDetectionResult(
                    success=False,
                    method=self.method,
                    error="Could not find graph anchors (12 AM / 60)",
                    diagnostics={"reason": "anchor_not_found"},
                )

            roi_x, roi_y, roi_width, roi_height = roi_params

            bounds = GridBounds(
                upper_left_x=roi_x,
                upper_left_y=roi_y,
                lower_right_x=roi_x + roi_width,
                lower_right_y=roi_y + roi_height,
            )

            return GridDetectionResult(
                success=True,
                bounds=bounds,
                confidence=1.0,  # OCR anchors are deterministic
                method=self.method,
            )

        except ValueError as e:
            error_msg = str(e)
            return GridDetectionResult(
                success=False,
                method=self.method,
                error=error_msg,
                diagnostics={"exception": "ValueError", "message": error_msg},
            )
        except Exception as e:
            logger.error(f"OCR grid detection failed: {e}")
            return GridDetectionResult(
                success=False,
                method=self.method,
                error=str(e),
                diagnostics={"exception": type(e).__name__, "message": str(e)},
            )


class LineBasedGridDetector(IGridDetector):
    """
    Grid detector that uses visual line patterns.

    Wraps the existing LineBasedDetector to conform to the IGridDetector interface.
    """

    def __init__(self):
        from .line_based_detection import LineBasedDetector as LBD

        self._detector = LBD.default()

    @property
    def method(self) -> GridDetectionMethod:
        return GridDetectionMethod.LINE_BASED

    def detect(self, image: np.ndarray, **kwargs) -> GridDetectionResult:
        """
        Detect grid using visual line patterns.
        Tries Rust (30x faster) first, falls back to Python.

        Args:
            image: BGR image array
            **kwargs: Optional parameters:
                - resolution: str like "1170x2532" for lookup table hints

        Returns:
            GridDetectionResult with bounds if successful
        """
        resolution = kwargs.get("resolution")

        # Try Rust acceleration first (saves image to temp file, calls leptess-based detector)
        try:
            from .rust_accelerator import _check_rust

            if _check_rust():
                import tempfile

                import cv2

                from .rust_accelerator import _rs

                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    cv2.imwrite(f.name, image)
                    rust_result = _rs.detect_grid(f.name, "line_based")
                    import os

                    os.unlink(f.name)

                if rust_result is not None:
                    bounds = GridBounds(
                        upper_left_x=rust_result["upper_left_x"],
                        upper_left_y=rust_result["upper_left_y"],
                        lower_right_x=rust_result["lower_right_x"],
                        lower_right_y=rust_result["lower_right_y"],
                    )
                    return GridDetectionResult(
                        success=True,
                        bounds=bounds,
                        confidence=1.0,
                        method=self.method,
                        diagnostics={"engine": "rust"},
                    )
                # Rust returned None (no grid found) — fall through to Python
                logger.debug("Rust grid detection returned None, trying Python")
        except Exception as e:
            logger.debug(f"Rust grid detection failed, falling back to Python: {e}")

        try:
            # Convert dark mode if needed (same as OCRAnchoredGridDetector)
            img = convert_dark_mode(image.copy())

            # The existing LineBasedDetector returns a different result type
            result = self._detector.detect(img, resolution=resolution)

            if not result.success or not result.bounds:
                return GridDetectionResult(
                    success=False,
                    method=self.method,
                    confidence=result.confidence,
                    error=result.error or "Line-based detection failed",
                    diagnostics=result.diagnostics or {},
                )

            # Convert bounds from the detector's format
            bounds = GridBounds(
                upper_left_x=result.bounds.x,
                upper_left_y=result.bounds.y,
                lower_right_x=result.bounds.x + result.bounds.width,
                lower_right_y=result.bounds.y + result.bounds.height,
            )

            return GridDetectionResult(
                success=True,
                bounds=bounds,
                confidence=result.confidence,
                method=self.method,
                diagnostics=result.diagnostics or {},
            )

        except Exception as e:
            logger.error(f"Line-based grid detection failed: {e}")
            return GridDetectionResult(
                success=False,
                method=self.method,
                error=str(e),
                diagnostics={"exception": type(e).__name__, "message": str(e)},
            )


class ManualGridDetector(IGridDetector):
    """
    'Detector' that uses manually-provided grid coordinates.

    This is a pass-through that wraps user-provided coordinates
    in the standard GridDetectionResult format.
    """

    def __init__(self, bounds: GridBounds):
        self._bounds = bounds

    @property
    def method(self) -> GridDetectionMethod:
        return GridDetectionMethod.MANUAL

    def detect(self, image: np.ndarray, **kwargs) -> GridDetectionResult:
        """Return the pre-configured manual bounds."""
        return GridDetectionResult(
            success=True,
            bounds=self._bounds,
            confidence=1.0,
            method=self.method,
        )


def get_grid_detector(method: GridDetectionMethod | str, **kwargs) -> IGridDetector:
    """
    Factory function to get a grid detector by method.

    Args:
        method: The detection method to use
        **kwargs: Additional parameters for specific detectors:
            - For MANUAL: requires 'bounds' (GridBounds)

    Returns:
        An IGridDetector instance
    """
    if isinstance(method, str):
        method = GridDetectionMethod(method)

    if method == GridDetectionMethod.OCR_ANCHORED:
        return OCRAnchoredGridDetector()
    elif method == GridDetectionMethod.LINE_BASED:
        return LineBasedGridDetector()
    elif method == GridDetectionMethod.MANUAL:
        bounds = kwargs.get("bounds")
        if bounds is None:
            raise ValueError("Manual detection requires 'bounds' parameter")
        return ManualGridDetector(bounds)
    else:
        raise ValueError(f"Unknown grid detection method: {method}")
