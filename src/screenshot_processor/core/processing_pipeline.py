"""Multi-stage screenshot processing pipeline with automatic tagging and queue assignment.

This module implements a sophisticated 5-stage processing pipeline that:
1. Detects daily screenshots and skips them
2. Attempts OCR total detection
3. Tries fixed grid method with Y-shift variations
4. Falls back to anchor detection method
5. Validates title detection throughout

Each stage adds tags to track processing history and automatically assigns
screenshots to appropriate queues for manual validation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import cv2

from .image_processor import process_image
from .image_utils import convert_dark_mode
from .models import BatteryRow, ImageType, ProcessingResult, ScreenTimeRow
from .ocr import find_title_and_total, parse_time_to_minutes
from .queue_models import ProcessingMetadata, ProcessingMethod, ProcessingTag

if TYPE_CHECKING:
    from .config import ProcessorConfig

logger = logging.getLogger(__name__)


class ProcessingPipeline:
    """Multi-stage processing pipeline for screenshot analysis.

    Implements a 5-stage pipeline:
    - Stage 1: Daily screenshot detection
    - Stage 2: OCR total detection
    - Stage 3: Fixed grid method with Y-shifts (if enabled)
    - Stage 4: Anchor detection fallback
    - Stage 5: Title validation (throughout all stages)
    """

    def __init__(self, config: ProcessorConfig) -> None:
        """Initialize the processing pipeline.

        Args:
            config: Processor configuration with thresholds and settings
        """
        self.config = config

    def process_single_image(self, image_path: str | Path) -> ProcessingResult:
        """Process a single image through the multi-stage pipeline.

        Args:
            image_path: Path to the screenshot image

        Returns:
            ProcessingResult with metadata, tags, and queue assignment
        """
        image_path = str(image_path)
        tags: set[str] = set()
        method: ProcessingMethod | None = None

        try:
            # Load and prepare image
            img = cv2.imread(image_path)
            if img is None:
                raise ValueError(f"Failed to load image: {image_path}")

            img = convert_dark_mode(img)

            # ========== Stage 1+2: Title & Total Extraction (single Tesseract call) ==========
            logger.debug(f"Stage 1+2: Extracting title and total - {image_path}")
            title, title_y_position, total_str, total_image_path = find_title_and_total(img)

            if title and title.strip().lower() == "daily total":
                logger.info(f"Detected daily screenshot: {image_path}")
                tags.add(ProcessingTag.DAILY_SCREENSHOT.value)

                metadata = ProcessingMetadata(
                    tags=frozenset(tags),
                    processed_at=datetime.now(timezone.utc).isoformat(),
                )

                return ProcessingResult(
                    image_path=image_path,
                    success=True,
                    row_data=None,
                    metadata=metadata,
                )
            ocr_total_minutes = self._parse_time_to_minutes(total_str) if total_str else None

            if ocr_total_minutes is None or ocr_total_minutes == 0:
                logger.warning(f"Failed to detect OCR total: {image_path}")
                tags.add(ProcessingTag.TOTAL_NOT_FOUND.value)
                tags.add(ProcessingTag.NEEDS_MANUAL.value)

                metadata = ProcessingMetadata(
                    tags=frozenset(tags),
                    processed_at=datetime.now(timezone.utc).isoformat(),
                )

                return ProcessingResult(
                    image_path=image_path,
                    success=False,
                    metadata=metadata,
                )

            tags.add(ProcessingTag.TOTAL_DETECTED.value)
            logger.info(f"Detected OCR total: {ocr_total_minutes} minutes - {image_path}")

            # ========== Stage 3: Fixed Grid Method with Y-Shifts ==========
            # Note: Fixed grid method requires implementation of grid coordinates
            # For now, we skip to Stage 4 (anchor detection)
            # TODO: Implement fixed grid method when grid coordinates are configured

            # ========== Stage 4: Anchor Detection Fallback ==========
            logger.debug(f"Stage 4: Attempting anchor detection - {image_path}")
            try:
                processed_path, graph_path, row_data, extracted_title, extracted_total, _, _ = process_image(
                    image_path,
                    is_battery=self.config.image_type == ImageType.BATTERY,
                    snap_to_grid=self.config.snap_to_grid,
                )

                method = ProcessingMethod.ANCHOR_DETECTION

                # Calculate extracted total (sum of hourly values, excluding the final total column)
                extracted_total_minutes = float(sum(row_data[:-1])) if row_data else 0.0

                # Calculate accuracy
                diff_minutes = abs(extracted_total_minutes - ocr_total_minutes)
                diff_percent = (diff_minutes / ocr_total_minutes * 100) if ocr_total_minutes > 0 else 0.0

                logger.info(
                    f"Anchor detection results: extracted={extracted_total_minutes}min, "
                    f"ocr={ocr_total_minutes}min, diff={diff_minutes}min ({diff_percent:.1f}%)"
                )

                # Categorize accuracy using thresholds
                exact_match_tolerance = 0.0  # Exact match only
                close_match_tolerance = self.config.thresholds.small_total_diff_threshold  # e.g., 2 minutes
                poor_match_threshold = self.config.thresholds.large_total_percent_threshold  # e.g., 10%

                if diff_minutes <= exact_match_tolerance:
                    # Exact match - auto-processed
                    tags.add(ProcessingTag.ANCHOR_METHOD_SUCCESS.value)
                    tags.add(ProcessingTag.EXACT_MATCH.value)
                    tags.add(ProcessingTag.AUTO_PROCESSED.value)
                    logger.info(f"✅ Exact match - auto-processed: {image_path}")

                elif diff_minutes <= close_match_tolerance:
                    # Close match - needs validation
                    tags.add(ProcessingTag.ANCHOR_METHOD_CLOSE.value)
                    tags.add(ProcessingTag.CLOSE_MATCH.value)
                    tags.add(ProcessingTag.NEEDS_VALIDATION.value)
                    logger.info(f"⚠️  Close match - needs review: {image_path}")

                elif diff_percent >= poor_match_threshold:
                    # Poor match - needs manual processing
                    tags.add(ProcessingTag.ANCHOR_METHOD_FAILED.value)
                    tags.add(ProcessingTag.POOR_MATCH.value)
                    tags.add(ProcessingTag.NEEDS_MANUAL.value)
                    logger.warning(f"❌ Poor match - manual required: {image_path}")

                else:
                    # Between close and poor - still needs manual
                    tags.add(ProcessingTag.ANCHOR_METHOD_FAILED.value)
                    tags.add(ProcessingTag.POOR_MATCH.value)
                    tags.add(ProcessingTag.NEEDS_MANUAL.value)
                    logger.warning(f"❌ Match below threshold - manual required: {image_path}")

                # ========== Stage 5: Title Validation ==========
                # Use extracted_title from process_image, or fall back to title from Stage 1
                final_title = extracted_title or title

                if not final_title or final_title.strip() in ["", " "]:
                    tags.add(ProcessingTag.TITLE_NOT_FOUND.value)
                    logger.warning(f"Title not found or empty: {image_path}")

                # Create metadata
                metadata = ProcessingMetadata(
                    method=method,
                    tags=frozenset(tags),
                    ocr_total_minutes=ocr_total_minutes,
                    extracted_total_minutes=extracted_total_minutes,
                    accuracy_diff_minutes=diff_minutes,
                    accuracy_diff_percent=diff_percent,
                    processed_at=datetime.now(timezone.utc).isoformat(),
                )

                # Create row data object
                if self.config.image_type == ImageType.BATTERY:
                    row_data_obj = BatteryRow(
                        full_path=image_path,
                        file_name=Path(image_path).name,
                        date_from_image=final_title or "",
                        time_from_ui="Midnight",
                        rows=row_data,
                    )
                else:
                    row_data_obj = ScreenTimeRow(
                        full_path=image_path,
                        file_name=Path(image_path).name,
                        app_title=final_title or "",
                        rows=row_data,
                    )

                logger.info(f"Processing complete: {image_path} -> Queue: {metadata.queue}, Tags: {len(metadata.tags)}")

                return ProcessingResult(
                    image_path=image_path,
                    success=True,
                    row_data=row_data_obj,
                    metadata=metadata,
                )

            except Exception as e:
                # Extraction failed completely
                logger.error(f"Extraction failed: {image_path} - {e}")
                tags.add(ProcessingTag.EXTRACTION_FAILED.value)
                tags.add(ProcessingTag.BARS_NOT_DETECTED.value)
                tags.add(ProcessingTag.NEEDS_MANUAL.value)

                metadata = ProcessingMetadata(
                    tags=frozenset(tags),
                    ocr_total_minutes=ocr_total_minutes,
                    processed_at=datetime.now(timezone.utc).isoformat(),
                )

                return ProcessingResult(
                    image_path=image_path,
                    success=False,
                    error=e,
                    metadata=metadata,
                )

        except Exception as e:
            # Unexpected error in pipeline
            logger.error(f"Pipeline error: {image_path} - {e}", exc_info=True)
            tags.add(ProcessingTag.EXTRACTION_FAILED.value)
            tags.add(ProcessingTag.NEEDS_MANUAL.value)

            metadata = ProcessingMetadata(
                tags=frozenset(tags),
                processed_at=datetime.now(timezone.utc).isoformat(),
            )

            return ProcessingResult(
                image_path=image_path,
                success=False,
                error=e,
                metadata=metadata,
            )

    def _parse_time_to_minutes(self, time_str: str) -> float | None:
        """Parse time string to total minutes.

        Delegates to the shared parse_time_to_minutes() in ocr.py.
        """
        return parse_time_to_minutes(time_str)
