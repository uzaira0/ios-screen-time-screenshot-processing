"""
Title and total extractor implementation.

This module provides the concrete implementation of ITitleExtractor
for extracting app titles and total usage from screenshots.
"""

from __future__ import annotations

import logging

import numpy as np

from .config import get_hybrid_ocr_config
from .image_utils import convert_dark_mode
from .interfaces import ITitleExtractor, TitleTotalResult
from .ocr import find_screenshot_title, find_screenshot_total_usage, find_title_and_total

logger = logging.getLogger(__name__)


class OCRTitleExtractor(ITitleExtractor):
    """
    Title extractor that uses OCR to find app titles and total usage.
    """

    def extract(
        self,
        image: np.ndarray,
        image_type: str,
        existing_title: str | None = None,
        existing_total: str | None = None,
    ) -> TitleTotalResult:
        """
        Extract title and total usage from an image.

        Args:
            image: BGR image array
            image_type: "screen_time" or "battery"
            existing_title: Existing title to preserve (skip OCR)
            existing_total: Existing total to preserve (skip OCR)

        Returns:
            TitleTotalResult with extracted values
        """
        # If we already know it's a daily total page, skip OCR and return immediately.
        if existing_title == "Daily Total":
            return TitleTotalResult(
                title="Daily Total",
                total=existing_total if existing_total and existing_total != "N/A" else None,
                is_daily_total=True,
            )

        # Check if we have valid existing data
        has_valid_title = existing_title is not None and existing_title != ""
        has_valid_total = existing_total is not None and existing_total != "" and existing_total != "N/A"

        # Initialize result with existing values
        result = TitleTotalResult(
            title=existing_title if has_valid_title else None,
            total=existing_total if has_valid_total else None,
        )

        # Skip OCR entirely if we have both values
        if has_valid_title and has_valid_total:
            return result

        # Only process screen_time images for title/total
        if image_type.lower() not in ["screen_time", "screentime"]:
            return result

        try:
            # Convert dark mode for OCR
            img = convert_dark_mode(image.copy())
            ocr_config = get_hybrid_ocr_config()

            need_title = not has_valid_title
            need_total = not has_valid_total

            if need_title and need_total:
                # Extract both with a single Tesseract call (saves ~1-3s)
                try:
                    title, title_y_position, total, _ = find_title_and_total(img, ocr_config)
                    result.title = title
                    result.title_y_position = title_y_position
                    if title == "Daily Total":
                        result.is_daily_total = True
                    result.total = total if total and total != "N/A" else None
                except Exception as e:
                    logger.warning(f"Error extracting title and total: {e}")
            elif need_title:
                try:
                    title, title_y_position = find_screenshot_title(img, ocr_config)
                    result.title = title
                    result.title_y_position = title_y_position
                    if title == "Daily Total":
                        result.is_daily_total = True
                except Exception as e:
                    logger.warning(f"Error extracting title: {e}")
            elif need_total:
                try:
                    total, _ = find_screenshot_total_usage(img, ocr_config)
                    result.total = total if total and total != "N/A" else None
                except Exception as e:
                    logger.warning(f"Error extracting total: {e}")

        except Exception as e:
            logger.error(f"Title extraction failed: {e}")

        return result


def get_title_extractor() -> ITitleExtractor:
    """Factory function to get the default title extractor."""
    return OCRTitleExtractor()
