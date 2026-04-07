"""
Screenshot processing orchestrator using dependency injection.

This module provides the ScreenshotProcessingService that coordinates
grid detection, bar processing, and title extraction using injected
dependencies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np

from .bar_processor import get_bar_processor
from .boundary_optimizer import optimize_boundaries
from .grid_detectors import (
    get_grid_detector,
)
from .interfaces import (
    GridBounds,
    GridDetectionMethod,
    GridDetectionResult,
    IBarProcessor,
    IGridDetector,
    ITitleExtractor,
)
from .title_extractor import get_title_extractor

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Complete result of screenshot processing."""

    success: bool
    processing_status: str  # "completed", "failed", "skipped"

    # Grid detection
    grid_bounds: GridBounds | None = None
    grid_detection_method: GridDetectionMethod | None = None
    grid_detection_confidence: float | None = None

    # Bar extraction
    hourly_values: dict[str, int] | None = None
    alignment_score: float | None = None

    # Title/Total extraction
    extracted_title: str | None = None
    extracted_total: str | None = None
    title_y_position: int | None = None

    # Status
    is_daily_total: bool = False
    has_blocking_issues: bool = False
    issues: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        # Convert numpy types to native Python types for JSON/DB serialization
        confidence = self.grid_detection_confidence
        if confidence is not None and hasattr(confidence, "item"):
            confidence = float(confidence)

        alignment = self.alignment_score
        if alignment is not None and hasattr(alignment, "item"):
            alignment = float(alignment)

        return {
            "success": self.success,
            "processing_status": self.processing_status,
            "grid_coords": self.grid_bounds.to_dict() if self.grid_bounds else None,
            "processing_method": self.grid_detection_method.value if self.grid_detection_method else None,
            "grid_detection_confidence": confidence,
            "extracted_hourly_data": self.hourly_values,
            "alignment_score": alignment,
            "extracted_title": self.extracted_title,
            "extracted_total": self.extracted_total,
            "title_y_position": self.title_y_position,
            "is_daily_total": self.is_daily_total,
            "has_blocking_issues": self.has_blocking_issues,
            "issues": self.issues,
        }


class ScreenshotProcessingService:
    """
    Orchestrates screenshot processing using dependency injection.

    This service coordinates:
    1. Grid detection (via IGridDetector)
    2. Bar value extraction (via IBarProcessor)
    3. Title/Total extraction (via ITitleExtractor)

    Each component can be swapped independently.
    """

    def __init__(
        self,
        grid_detector: IGridDetector | None = None,
        bar_processor: IBarProcessor | None = None,
        title_extractor: ITitleExtractor | None = None,
        use_fractional: bool = True,
    ):
        """
        Initialize with optional dependency overrides.

        Args:
            grid_detector: Override the default grid detector
            bar_processor: Override the default bar processor
            title_extractor: Override the default title extractor
            use_fractional: If True, keep 2 decimal places for hourly values
        """
        self._grid_detector = grid_detector
        self._bar_processor = bar_processor or get_bar_processor()
        self._title_extractor = title_extractor or get_title_extractor()
        self._use_fractional = use_fractional

    def process(
        self,
        image_path: str | Path,
        image_type: str,
        detection_method: GridDetectionMethod | str = GridDetectionMethod.OCR_ANCHORED,
        manual_bounds: GridBounds | None = None,
        existing_title: str | None = None,
        existing_total: str | None = None,
        max_shift: int = 0,
    ) -> ProcessingResult:
        """
        Process a screenshot with the specified detection method.

        Args:
            image_path: Path to the screenshot image
            image_type: "screen_time" or "battery"
            detection_method: Which grid detection method to use
            manual_bounds: Manual grid bounds (overrides detection_method)
            existing_title: Existing title to preserve
            existing_total: Existing total to preserve
            max_shift: Maximum pixels to shift grid for optimization (0=disabled)

        Returns:
            ProcessingResult with all extracted data
        """
        # Load image
        image = cv2.imread(str(image_path))
        if image is None:
            return ProcessingResult(
                success=False,
                processing_status="failed",
                has_blocking_issues=True,
                issues=[
                    {
                        "issue_type": "FileError",
                        "severity": "blocking",
                        "description": f"Could not read image file: {image_path}",
                    }
                ],
            )

        return self.process_image(
            image=image,
            image_type=image_type,
            detection_method=detection_method,
            manual_bounds=manual_bounds,
            existing_title=existing_title,
            existing_total=existing_total,
            max_shift=max_shift,
        )

    def process_image(
        self,
        image: np.ndarray,
        image_type: str,
        detection_method: GridDetectionMethod | str = GridDetectionMethod.OCR_ANCHORED,
        manual_bounds: GridBounds | None = None,
        existing_title: str | None = None,
        existing_total: str | None = None,
        resolution: str | None = None,
        max_shift: int = 0,
    ) -> ProcessingResult:
        """
        Process an already-loaded image.

        Args:
            image: BGR numpy array
            image_type: "screen_time" or "battery"
            detection_method: Which grid detection method to use
            manual_bounds: Manual grid bounds (overrides detection_method)
            existing_title: Existing title to preserve
            existing_total: Existing total to preserve
            resolution: Image resolution string (e.g., "1170x2532") for hints
            max_shift: Maximum pixels to shift grid for optimization (0=disabled)

        Returns:
            ProcessingResult with all extracted data
        """
        if isinstance(detection_method, str):
            detection_method = GridDetectionMethod(detection_method)

        is_battery = image_type.lower() == "battery"

        # Step 1: Extract title and check for Daily Total (early exit)
        title_result = self._title_extractor.extract(image, image_type, existing_title, existing_total)

        if title_result.is_daily_total:
            return ProcessingResult(
                success=True,
                processing_status="skipped",
                is_daily_total=True,
                extracted_title=title_result.title,
                extracted_total=title_result.total,
                title_y_position=title_result.title_y_position,
            )

        # Step 2: Detect grid
        if manual_bounds:
            grid_result = GridDetectionResult(
                success=True,
                bounds=manual_bounds,
                confidence=1.0,
                method=GridDetectionMethod.MANUAL,
            )
        else:
            detector = self._get_detector(detection_method)
            grid_result = detector.detect(image, resolution=resolution)

        if not grid_result.success or grid_result.bounds is None:
            return ProcessingResult(
                success=False,
                processing_status="failed",
                grid_detection_method=grid_result.method,
                grid_detection_confidence=grid_result.confidence,
                extracted_title=title_result.title,
                extracted_total=title_result.total,
                title_y_position=title_result.title_y_position,
                has_blocking_issues=True,
                issues=[
                    {
                        "issue_type": "GridDetectionIssue",
                        "severity": "blocking",
                        "description": grid_result.error or "Grid detection failed",
                        "diagnostics": grid_result.diagnostics,
                    }
                ],
            )

        # Step 3: Extract bar values
        bar_result = self._bar_processor.extract(image, grid_result.bounds, is_battery, self._use_fractional)

        if not bar_result.success:
            return ProcessingResult(
                success=False,
                processing_status="failed",
                grid_bounds=grid_result.bounds,
                grid_detection_method=grid_result.method,
                grid_detection_confidence=grid_result.confidence,
                extracted_title=title_result.title,
                extracted_total=title_result.total,
                title_y_position=title_result.title_y_position,
                has_blocking_issues=True,
                issues=[
                    {
                        "issue_type": "BarExtractionError",
                        "severity": "blocking",
                        "description": bar_result.error or "Bar extraction failed",
                    }
                ],
            )

        # Step 3.5: Optimize grid boundaries if requested
        final_bounds = grid_result.bounds
        final_hourly_values = bar_result.hourly_values
        final_alignment_score = bar_result.alignment_score

        if max_shift > 0 and title_result.total:
            logger.debug(f"Running boundary optimization with max_shift={max_shift}")
            opt_result = optimize_boundaries(
                image=image,
                initial_bounds=grid_result.bounds,
                ocr_total=title_result.total,
                max_shift=max_shift,
                is_battery=is_battery,
            )

            # Use optimized bounds if: converged, or any shift was applied
            has_shift = opt_result.shift_x != 0 or opt_result.shift_y != 0 or opt_result.shift_width != 0

            # Reject optimization if it gives 0 minutes when OCR says non-zero
            is_bogus = opt_result.bar_total_minutes == 0 and opt_result.ocr_total_minutes > 0

            if (opt_result.converged or has_shift) and not is_bogus:
                logger.info(
                    f"Optimization result: shift_x={opt_result.shift_x}, shift_y={opt_result.shift_y}, "
                    f"shift_width={opt_result.shift_width}, bar_total={opt_result.bar_total_minutes}, "
                    f"ocr_total={opt_result.ocr_total_minutes}, converged={opt_result.converged}"
                )
                final_bounds = opt_result.bounds
                # Re-extract bars with optimized bounds to get proper alignment score
                optimized_bar_result = self._bar_processor.extract(
                    image, final_bounds, is_battery, self._use_fractional
                )
                if optimized_bar_result.success:
                    final_hourly_values = optimized_bar_result.hourly_values
                    final_alignment_score = optimized_bar_result.alignment_score
            elif is_bogus:
                logger.warning(f"Rejecting optimization: bar_total=0 but ocr_total={opt_result.ocr_total_minutes}")

        # Step 4: Return complete result
        return ProcessingResult(
            success=True,
            processing_status="completed",
            grid_bounds=final_bounds,
            grid_detection_method=grid_result.method,
            grid_detection_confidence=grid_result.confidence,
            hourly_values=final_hourly_values,
            alignment_score=final_alignment_score,
            extracted_title=title_result.title,
            extracted_total=title_result.total,
            title_y_position=title_result.title_y_position,
        )

    def _get_detector(self, method: GridDetectionMethod) -> IGridDetector:
        """Get the appropriate grid detector for the method."""
        if self._grid_detector and self._grid_detector.method == method:
            return self._grid_detector

        return get_grid_detector(method)


def create_processing_service(
    detection_method: GridDetectionMethod | str | None = None,
) -> ScreenshotProcessingService:
    """
    Factory function to create a processing service with optional default detector.

    Args:
        detection_method: Default grid detection method to use

    Returns:
        Configured ScreenshotProcessingService
    """
    grid_detector = None
    if detection_method:
        if isinstance(detection_method, str):
            detection_method = GridDetectionMethod(detection_method)
        grid_detector = get_grid_detector(detection_method)

    return ScreenshotProcessingService(grid_detector=grid_detector)
