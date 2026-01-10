"""OCR integration for grid anchor detection.

This module provides OCR functions specifically for detecting
"12AM" and "60" text anchors that define bar graph boundaries.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
from pytesseract import Output, pytesseract

from .config import OCRConfig
from .image_utils import get_pixel
from .ocr import ocr_results_to_dict
from .ocr_provider import get_ocr_engine

logger = logging.getLogger(__name__)


def prepare_image_chunks(
    img: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Prepare left and right image chunks for OCR anchor detection.

    Splits the image into left and right portions for separate OCR
    to find "12AM" (left) and "60" (right) anchors.

    Args:
        img: Input image (BGR format)

    Returns:
        tuple: (left_chunk, right_chunk, right_offset)
    """
    img_chunk_num = 3
    img_width, img_height = img.shape[1], img.shape[0]
    top_removal = int(img_height * 0.05)

    img_left = img[:, : int(img_width / img_chunk_num)]
    img_right = img[:, -int(img_width / img_chunk_num) :]

    img_left[0:top_removal, :] = get_pixel(img_left, 1)
    img_right[0:top_removal, :] = get_pixel(img_right, 1)
    right_offset = img_width - int(img_width / img_chunk_num)

    return img_left, img_right, right_offset


def perform_ocr(
    img_left: np.ndarray,
    img_right: np.ndarray,
    ocr_config: OCRConfig | None = None,
) -> tuple[dict, dict]:
    """Perform OCR on left and right image chunks for grid anchor detection.

    Uses HybridOCREngine (PaddleOCR -> Tesseract fallback) when configured,
    otherwise uses Tesseract directly.

    Args:
        img_left: Left portion of image (contains "12AM" anchor)
        img_right: Right portion of image (contains "60" anchor)
        ocr_config: Optional OCR configuration

    Returns:
        Tuple of (left_dict, right_dict) in pytesseract format
    """
    psm_mode = ocr_config.psm_mode_data if ocr_config else "12"
    psm_config = f"--psm {psm_mode}"

    use_hybrid = ocr_config is not None and ocr_config.use_hybrid
    use_paddleocr_for_grid = ocr_config.hybrid_paddleocr_for_grid if ocr_config else False

    if use_hybrid and use_paddleocr_for_grid:
        try:
            engine = get_ocr_engine()

            # Convert BGR to RGB for the engine
            img_left_rgb = cv2.cvtColor(img_left, cv2.COLOR_BGR2RGB)
            img_right_rgb = cv2.cvtColor(img_right, cv2.COLOR_BGR2RGB)

            # Run left and right OCR in parallel (each is a network call or CPU-bound Tesseract)
            with ThreadPoolExecutor(max_workers=2) as pool:
                future_left = pool.submit(engine.extract_text_with_bboxes, img_left_rgb, psm_config)
                future_right = pool.submit(engine.extract_text_with_bboxes, img_right_rgb, psm_config)
                results_left = future_left.result()
                results_right = future_right.result()

            used_engine = engine.last_engine_used
            logger.debug(f"Grid anchor OCR used: {used_engine}")

            d_left = ocr_results_to_dict(results_left, require_bbox=True)
            d_right = ocr_results_to_dict(results_right, require_bbox=True)

            # Validate results contain expected anchor patterns
            left_texts = " ".join(d_left["text"]).upper()
            right_texts = " ".join(d_right["text"]).upper()

            left_has_anchor = any(key in left_texts for key in ["12", "AM", "2A"])
            right_has_anchor = any(key in right_texts for key in ["60", "GO", "6O"])

            # Log bbox details for debugging
            if left_has_anchor:
                for i, txt in enumerate(d_left["text"]):
                    if any(key in txt.upper() for key in ["12", "AM", "2A"]):
                        logger.info(
                            f"HybridOCR ({used_engine}) left anchor '{txt}' at "
                            f"x={d_left['left'][i]}, y={d_left['top'][i]}, "
                            f"w={d_left['width'][i]}, h={d_left['height'][i]}"
                        )
            if right_has_anchor:
                for i, txt in enumerate(d_right["text"]):
                    if any(key in txt.upper() for key in ["60", "GO", "6O"]):
                        logger.info(
                            f"HybridOCR ({used_engine}) right anchor '{txt}' at "
                            f"x={d_right['left'][i]}, y={d_right['top'][i]}, "
                            f"w={d_right['width'][i]}, h={d_right['height'][i]}"
                        )

            if left_has_anchor and right_has_anchor:
                logger.debug(f"HybridOCR ({used_engine}) found valid anchors")
                return d_left, d_right
            else:
                logger.warning(
                    f"HybridOCR ({used_engine}) didn't find expected anchors "
                    f"(left={left_has_anchor}, right={right_has_anchor}), "
                    f"falling back to direct Tesseract"
                )

        except Exception as e:
            logger.warning(f"HybridOCR failed, falling back to direct Tesseract: {e}")

    # Default/fallback: use Tesseract directly (parallelize left + right)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future_left = pool.submit(pytesseract.image_to_data, img_left, config=psm_config, output_type=Output.DICT)
        future_right = pool.submit(pytesseract.image_to_data, img_right, config=psm_config, output_type=Output.DICT)
        try:
            d_left = future_left.result()
        except Exception as e:
            logger.error(f"Left-side Tesseract OCR failed: {e}")
            raise
        try:
            d_right = future_right.result()
        except Exception as e:
            logger.error(f"Right-side Tesseract OCR failed: {e}")
            raise

    # Log Tesseract bbox details
    for i, txt in enumerate(d_left["text"]):
        if any(key in txt.upper() for key in ["12", "AM", "2A"]):
            logger.info(
                f"Tesseract left anchor '{txt}' at "
                f"x={d_left['left'][i]}, y={d_left['top'][i]}, "
                f"w={d_left['width'][i]}, h={d_left['height'][i]}"
            )
    for i, txt in enumerate(d_right["text"]):
        if any(key in txt.upper() for key in ["60", "GO", "6O"]):
            logger.info(
                f"Tesseract right anchor '{txt}' at "
                f"x={d_right['left'][i]}, y={d_right['top'][i]}, "
                f"w={d_right['width'][i]}, h={d_right['height'][i]}"
            )

    return d_left, d_right


def adjust_anchor_offsets(data: dict, offset: int) -> None:
    """Adjust anchor offsets for right-side detection.

    The right image chunk is offset from the original image,
    so OCR coordinates need adjustment.

    Args:
        data: OCR results dict to modify in-place
        offset: X offset to add to all left coordinates
    """
    for i in range(len(data["level"])):
        data["left"][i] += offset
