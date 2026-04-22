"""
Screenshot processing service — the web/API entry point for processing.

Canonical processing path (web/API):
    1. process_screenshot_async() or process_screenshot_sync()
       - Async (FastAPI) / sync (workflow activity) wrappers that handle DB commits.
    2. process_screenshot_file()
       - Core sync function in THIS module. No DB operations.
       - First attempts the Rust fast-path (rust_accelerator).
       - On Rust unavailability, delegates to ScreenshotProcessingService (Python).
    3. core/screenshot_processing.py :: ScreenshotProcessingService
       - DI-based orchestrator (IGridDetector, IBarProcessor, ITitleExtractor).
       - The CURRENT canonical Python processing implementation for the web app.
       - Supports line_based, ocr_anchored, and manual grid detection methods.
    4. update_screenshot_from_result()
       - Maps the result dict onto the SQLAlchemy Screenshot model.

Legacy layers (CLI/GUI pipeline, NOT used by the web app):
    - core/processor.py :: ScreenshotProcessor
        Legacy CLI/GUI processor with its own folder-based workflow, Y-shift
        grid search, and issue manager. Used by the PyQt6 desktop app.
    - core/processing_pipeline.py :: ProcessingPipeline
        Multi-stage pipeline with automatic tagging and queue assignment.
        Used by the CLI batch processor alongside ScreenshotProcessor.
    - core/image_processor.py :: process_image()
        Low-level function called by BOTH the legacy and current pipelines
        for OCR anchor detection and grid extraction. Shared, not legacy.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ...core.interfaces import GridBounds, GridDetectionMethod
from ..config import get_settings

# Lazy sentinel — actual import in process_screenshot_file() to avoid pulling in
# pytesseract/pandas/matplotlib at module load time. Module-level attribute
# needed for unittest.mock.patch() to work.
ScreenshotProcessingService = None

if TYPE_CHECKING:
    from ..database.models import Screenshot

from ..database.models import AnnotationStatus, ProcessingMethod, ProcessingStatus

logger = logging.getLogger(__name__)


# ─── Rust fast-path helpers ──────────────────────────────────────────────────


def _hourly_list_to_dict(hourly: list) -> dict:
    """Convert [v0, v1, ...] → {"0": v0, "1": v1, ...} as stored in DB.

    Uses largest-remainder method with floor-based target to match iOS behavior.
    iOS Screen Time truncates (floors) fractional minutes — e.g. 23.67 min
    displays as "23m", not "24m". So the target total is floor(raw_sum), and
    individual hours are floored then the residual is distributed to hours
    with the largest fractional parts.
    """
    import math

    floats = [float(v) for v in hourly]
    target_total = math.floor(sum(floats))
    floors = [math.floor(v) for v in floats]
    residual = target_total - sum(floors)
    if residual > 0:
        # Sort by fractional part descending; hand out +1 to top `residual` items
        remainders = sorted(range(len(floats)), key=lambda i: floats[i] - floors[i], reverse=True)
        for j in range(residual):
            floors[remainders[j]] += 1
    return {str(i): floors[i] for i in range(len(floors))}


def _try_rust_process_with_grid(
    file_path: str,
    image_type: str,
    grid_coords: dict,
    existing_title: str | None,
    existing_total: str | None,
) -> dict | None:
    """
    Extract bar data for a known manual grid using Rust.

    Returns the result dict on success, or None to trigger Python fallback.
    """
    from ...core import rust_accelerator

    if not rust_accelerator._check_rust():
        return None

    try:
        rust_result = rust_accelerator.process_image_with_grid(
            file_path,
            upper_left=(grid_coords["upper_left_x"], grid_coords["upper_left_y"]),
            lower_right=(grid_coords["lower_right_x"], grid_coords["lower_right_y"]),
            image_type=image_type,
        )
        hourly_vals = rust_result.get("hourly_values")
        hourly = _hourly_list_to_dict(hourly_vals) if hourly_vals is not None else None
        return {
            "success": True,
            "processing_status": "completed",
            "extracted_hourly_data": hourly,
            "extracted_title": existing_title,
            "extracted_total": existing_total,
            "grid_coords": grid_coords,
            "processing_method": "manual",
            "grid_detection_confidence": None,
            "alignment_score": rust_result.get("alignment_score"),
            "title_y_position": rust_result.get("title_y_position"),
            "is_daily_total": rust_result.get("is_daily_total", False),
            "has_blocking_issues": rust_result.get("has_blocking_issues", False),
            "issues": rust_result.get("issues", []),
        }
    except Exception as e:
        logger.warning("Rust manual-grid fast path failed, falling back to Python: %s", e)
        return None


def process_screenshot_file(
    file_path: str,
    image_type: str,
    grid_coords: dict | None = None,
    processing_method: str | None = None,
    existing_title: str | None = None,
    existing_total: str | None = None,
    use_fallback: bool = True,
    max_shift: int = 5,
    force: bool = False,
) -> dict:
    """
    Process a screenshot file. Core sync function - no database operations.

    This is the single source of truth for screenshot processing logic.

    Args:
        file_path: Path to the image file
        image_type: "screen_time" or "battery"
        grid_coords: Optional manual grid coordinates (skips auto-detection)
        processing_method: Optional specific method ("line_based" or "ocr_anchored")
        existing_title: Existing title to preserve (skip OCR)
        existing_total: Existing total to preserve (skip OCR)
        use_fallback: If True and no specific method requested, fall back from
                      line_based to ocr_anchored on failure
        max_shift: Maximum pixels to shift grid boundaries for optimization (0=disabled)

    Returns:
        dict with processing results
    """
    # ── Early exit for known daily total pages ────────────────────────────────
    # If we already identified this as a daily total page, skip immediately.
    # Re-running OCR would risk overwriting the correct finding with a wrong one.
    # Bypassed when force=True (explicit user reprocessing).
    if existing_title == "Daily Total" and not grid_coords and not force:
        return {
            "success": True,
            "processing_status": "skipped",
            "extracted_title": "Daily Total",
            "extracted_total": existing_total,
            "extracted_hourly_data": None,
            "grid_coords": None,
            "processing_method": processing_method or "line_based",
            "grid_detection_confidence": None,
            "alignment_score": None,
            "title_y_position": None,
            "is_daily_total": True,
            "has_blocking_issues": False,
            "issues": [],
        }

    # ── Rust fast-path ────────────────────────────────────────────────────────
    from ...core import rust_accelerator

    if grid_coords:
        # Manual grid coords: skip detection, extract bars only.
        rust_result = _try_rust_process_with_grid(
            file_path, image_type, grid_coords, existing_title, existing_total
        )
        if rust_result is not None:
            logger.info("Rust fast path succeeded (manual grid)", extra={"file_path": file_path})
            return rust_result
    else:
        # No manual grid: use the Rust optimizer pipeline (process_image_optimized).
        method = processing_method or "line_based"
        rust_result = rust_accelerator.process_image_optimized(file_path, image_type, method, max_shift)

        # Note: Rust process_image_optimized handles line_based→ocr_anchored
        # fallback internally, so no Python-level retry is needed.

        if rust_result is not None:
            # process_image_optimized returns "grid_bounds" dict; alias to "grid_coords".
            if "grid_bounds" in rust_result and isinstance(rust_result.get("grid_bounds"), dict):
                rust_result = {**rust_result, "grid_coords": rust_result["grid_bounds"]}

            # Rust already determined is_daily_total via is_daily_total_page().
            # Bypassed when force=True (user explicitly reprocessing).
            if rust_result.get("is_daily_total") and not force:
                return {
                    "success": True,
                    "processing_status": "skipped",
                    "extracted_title": rust_result.get("title") or existing_title,
                    "extracted_total": rust_result.get("total_text") or existing_total,
                    "grid_coords": None,
                    "processing_method": rust_result.get("detection_method") or method,
                    "grid_detection_confidence": rust_result.get("grid_detection_confidence"),
                    "alignment_score": rust_result.get("alignment_score"),
                    "title_y_position": rust_result.get("title_y_position"),
                    "is_daily_total": True,
                    "has_blocking_issues": rust_result.get("has_blocking_issues", False),
                    "issues": rust_result.get("issues", []),
                }

            grid_coords = rust_result.get("grid_coords")
            hourly_vals = rust_result.get("hourly_values")
            processing_time = rust_result.get("processing_time_ms", 0)
            rust_total = rust_result.get("total_text") or ""
            ocr_total_text = rust_total or existing_total or ""
            final_hourly = _hourly_list_to_dict(hourly_vals[:24]) if hourly_vals is not None else None

            # ── Python OCR fallback for total ─────────────────────────────────
            # Rust total extraction sometimes misses hours ("5h 55m" → "55m")
            # or fails entirely. Fall back to Python OCR if Rust total is empty
            # or suspiciously short (no 'h' when bar total suggests hours).
            if hourly_vals is not None:
                bar_total_raw = sum(float(v) for v in hourly_vals[:24])
                rust_has_hours = "h" in rust_total
                bar_suggests_hours = bar_total_raw >= 55  # ~1 hour
                if not rust_total or (bar_suggests_hours and not rust_has_hours):
                    try:
                        import cv2

                        from ...core.image_utils import convert_dark_mode
                        from ...core.ocr import find_screenshot_total_usage

                        img = cv2.imread(file_path)
                        if img is not None:
                            img = convert_dark_mode(img)
                            py_total, _ = find_screenshot_total_usage(img)
                            if py_total and py_total.strip():
                                logger.info(
                                    "Python OCR total fallback",
                                    extra={"file_path": file_path, "rust_total": rust_total, "python_total": py_total},
                                )
                                ocr_total_text = py_total.strip()
                    except Exception as e:
                        logger.debug("Python OCR total fallback failed: %s", e)

            # ── Post-optimization refinement ──────────────────────────────────
            # Safety net: if Rust optimizer's result still doesn't match OCR total
            # (e.g., binarize-whole-image vs binarize-ROI produces different pixel values),
            # run the Python boundary optimizer to refine.
            # Use raw (unrounded) hourly values to avoid false triggers from rounding.
            if grid_coords and hourly_vals is not None and ocr_total_text and max_shift > 0:
                from ...core.boundary_optimizer import parse_ocr_total

                bar_total = sum(float(v) for v in hourly_vals[:24])
                ocr_minutes = parse_ocr_total(ocr_total_text)
                # Use 0.5 threshold — catches the common 0.7 diff that rounds to 1 min visible mismatch
                if ocr_minutes is not None and abs(bar_total - ocr_minutes) >= 0.5:
                    try:
                        import cv2

                        from ...core.boundary_optimizer import optimize_boundaries
                        from ...core.image_utils import convert_dark_mode

                        img = cv2.imread(file_path)
                        if img is not None:
                            img = convert_dark_mode(img)
                            initial = GridBounds(
                                upper_left_x=grid_coords["upper_left_x"],
                                upper_left_y=grid_coords["upper_left_y"],
                                lower_right_x=grid_coords["lower_right_x"],
                                lower_right_y=grid_coords["lower_right_y"],
                            )
                            opt = optimize_boundaries(img, initial, ocr_total_text, max_shift=3)
                            if opt.converged or abs(opt.bar_total_minutes - ocr_minutes) < abs(bar_total - ocr_minutes):
                                # Python optimizer found a better result
                                refined_grid = {
                                    "upper_left_x": opt.bounds.upper_left_x,
                                    "upper_left_y": opt.bounds.upper_left_y,
                                    "lower_right_x": opt.bounds.lower_right_x,
                                    "lower_right_y": opt.bounds.lower_right_y,
                                }
                                # Re-extract hourly values with the refined grid
                                refined_hourly = rust_accelerator.extract_hourly_data(
                                    file_path,
                                    (opt.bounds.upper_left_x, opt.bounds.upper_left_y),
                                    (opt.bounds.lower_right_x, opt.bounds.lower_right_y),
                                )
                                if refined_hourly is not None:
                                    grid_coords = refined_grid
                                    final_hourly = _hourly_list_to_dict(refined_hourly[:24])
                                    logger.info(
                                        "Python post-optimization refined Rust grid",
                                        extra={
                                            "file_path": file_path,
                                            "rust_total": bar_total,
                                            "refined_total": sum(float(v) for v in final_hourly.values()),
                                            "ocr_total": ocr_minutes,
                                            "shift": (opt.shift_x, opt.shift_y, opt.shift_width),
                                        },
                                    )
                    except Exception as e:
                        logger.debug("Post-optimization refinement failed (using Rust result): %s", e)

            logger.info(
                "Rust fast path succeeded",
                extra={"file_path": file_path, "processing_time_ms": processing_time},
            )
            return {
                "success": True,
                "processing_status": "completed" if grid_coords else "failed",
                "processing_method": rust_result.get("detection_method") or method,
                "extracted_title": rust_result.get("title") or existing_title,
                "extracted_total": ocr_total_text,
                "extracted_hourly_data": final_hourly,
                "grid_coords": grid_coords,
                "grid_detection_confidence": rust_result.get("grid_detection_confidence"),
                "alignment_score": rust_result.get("alignment_score"),
                "title_y_position": rust_result.get("title_y_position"),
                "is_daily_total": False,
                "has_blocking_issues": rust_result.get("has_blocking_issues", False),
                "issues": rust_result.get("issues", []),
                "processing_time_ms": processing_time,
            }

    logger.debug("Rust fast path unavailable, using Python", extra={"file_path": file_path})
    # ── Python path (existing code begins here, unchanged) ───────────────────

    global ScreenshotProcessingService
    if ScreenshotProcessingService is None:
        from ...core.screenshot_processing import ScreenshotProcessingService

    settings = get_settings()
    service = ScreenshotProcessingService(use_fractional=settings.USE_FRACTIONAL_HOURLY_VALUES)

    # Determine detection method and manual bounds
    if grid_coords:
        detection_method = GridDetectionMethod.MANUAL
        manual_bounds = GridBounds(
            upper_left_x=grid_coords["upper_left_x"],
            upper_left_y=grid_coords["upper_left_y"],
            lower_right_x=grid_coords["lower_right_x"],
            lower_right_y=grid_coords["lower_right_y"],
        )
        use_fallback = False  # Manual coords = no fallback needed
    else:
        manual_bounds = None
        if processing_method == "ocr_anchored":
            detection_method = GridDetectionMethod.OCR_ANCHORED
            use_fallback = False  # Specific method requested
        elif processing_method == "line_based":
            detection_method = GridDetectionMethod.LINE_BASED
            use_fallback = False  # Specific method requested
        else:
            detection_method = GridDetectionMethod.LINE_BASED

    # Process
    logger.info(
        "Processing screenshot file",
        extra={
            "file_path": file_path,
            "method": detection_method.value,
            "fallback": use_fallback,
            "max_shift": max_shift,
        },
    )
    result = service.process(
        image_path=file_path,
        image_type=image_type,
        detection_method=detection_method,
        manual_bounds=manual_bounds,
        existing_title=existing_title,
        existing_total=existing_total,
        max_shift=max_shift,
    )

    # Fallback to OCR-anchored only if line-based found no grid coords
    has_grid_coords = result.grid_bounds is not None
    if use_fallback and not has_grid_coords and result.processing_status != "skipped":
        logger.info("Line-based found no grid coords, falling back to OCR-anchored", extra={"file_path": file_path})
        result = service.process(
            image_path=file_path,
            image_type=image_type,
            detection_method=GridDetectionMethod.OCR_ANCHORED,
            existing_title=existing_title,
            existing_total=existing_total,
            max_shift=max_shift,
        )

    return result.to_dict()


def update_screenshot_from_result(screenshot: Screenshot, result: dict) -> None:
    """
    Update a Screenshot model from a processing result dict.

    Does NOT commit - caller is responsible for committing.
    """
    screenshot.processed_at = datetime.now(timezone.utc)
    screenshot.processing_status = ProcessingStatus(result["processing_status"])

    # Truncate title to fit VARCHAR(500) column
    title = result.get("extracted_title")
    screenshot.extracted_title = title[:500] if title else None
    screenshot.extracted_total = result.get("extracted_total")
    screenshot.extracted_hourly_data = result.get("extracted_hourly_data")
    screenshot.processing_issues = result.get("issues")
    screenshot.has_blocking_issues = result.get("has_blocking_issues", False)
    screenshot.alignment_score = result.get("alignment_score")
    screenshot.title_y_position = result.get("title_y_position")

    # Processing method and confidence
    method_str = result.get("processing_method")
    if method_str:
        screenshot.processing_method = ProcessingMethod(method_str)
    screenshot.grid_detection_confidence = result.get("grid_detection_confidence")

    # Grid coordinates — always overwrite (clear old manual coords on re-detection)
    coords = result.get("grid_coords")
    if coords:
        screenshot.grid_upper_left_x = coords.get("upper_left_x")
        screenshot.grid_upper_left_y = coords.get("upper_left_y")
        screenshot.grid_lower_right_x = coords.get("lower_right_x")
        screenshot.grid_lower_right_y = coords.get("lower_right_y")
    else:
        screenshot.grid_upper_left_x = None
        screenshot.grid_upper_left_y = None
        screenshot.grid_lower_right_x = None
        screenshot.grid_lower_right_y = None

    # Daily total = skip annotation
    if result["processing_status"] == "skipped":
        screenshot.annotation_status = AnnotationStatus.SKIPPED


# =============================================================================
# Async wrapper for FastAPI
# =============================================================================


async def process_screenshot_async(
    db: AsyncSession,
    screenshot: Screenshot,
    grid_coords: dict | None = None,
    processing_method: str | None = None,
    current_user_id: int | None = None,
    max_shift: int = 0,
    force: bool = False,
) -> dict:
    """
    Process a screenshot and save to database. Async version for FastAPI.

    Args:
        db: Async database session
        screenshot: Screenshot model to process
        grid_coords: Optional manual grid coordinates
        processing_method: Optional specific method
        current_user_id: If provided, block reprocessing if user verified this screenshot
        max_shift: Maximum pixels to shift grid for optimization (0=disabled)
    """
    # Block if current user already verified
    if current_user_id and screenshot.verified_by_user_ids:
        if current_user_id in screenshot.verified_by_user_ids:
            logger.info(
                "Screenshot verified by user, skipping reprocess",
                extra={"screenshot_id": screenshot.id, "user_id": current_user_id},
            )
            return {
                "success": False,
                "skipped": True,
                "skip_reason": "verified_by_user",
                "message": "This screenshot has been verified by you and cannot be reprocessed.",
                "processing_status": screenshot.processing_status.value
                if screenshot.processing_status
                else "completed",
            }

    # Process file in a thread to avoid blocking the async event loop
    # (process_screenshot_file does cv2.imread, OCR, and bar extraction — all CPU-bound)
    import asyncio

    result = await asyncio.to_thread(
        process_screenshot_file,
        file_path=screenshot.file_path,
        image_type=screenshot.image_type,
        grid_coords=grid_coords,
        processing_method=processing_method,
        existing_title=screenshot.extracted_title,
        existing_total=screenshot.extracted_total,
        max_shift=max_shift,
        force=force,
    )

    # Update model and commit
    update_screenshot_from_result(screenshot, result)
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(screenshot, "extracted_hourly_data")
    flag_modified(screenshot, "processing_issues")
    await db.commit()
    await db.refresh(screenshot)

    return result


# =============================================================================
# Sync wrapper for workflow activities
# =============================================================================


def process_screenshot_sync(
    db: Session,
    screenshot: Screenshot,
    grid_coords: dict | None = None,
    processing_method: str | None = None,
    max_shift: int = 0,
    force: bool = False,
) -> dict:
    """
    Process a screenshot and save to database. Sync version for workflow activities.

    Args:
        db: Sync database session
        screenshot: Screenshot model to process
        grid_coords: Optional manual grid coordinates
        processing_method: Optional specific method
        max_shift: Maximum pixels to shift grid for optimization (0=disabled)
        force: If True, bypass daily-total early exits
    """
    result = process_screenshot_file(
        file_path=screenshot.file_path,
        image_type=screenshot.image_type,
        grid_coords=grid_coords,
        processing_method=processing_method,
        existing_title=screenshot.extracted_title,
        existing_total=screenshot.extracted_total,
        max_shift=max_shift,
        force=force,
    )

    update_screenshot_from_result(screenshot, result)
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(screenshot, "extracted_hourly_data")
    flag_modified(screenshot, "processing_issues")
    db.commit()
    db.refresh(screenshot)

    return result


# =============================================================================
# Named wrapper for reprocessing operations
# =============================================================================


async def reprocess_screenshot(
    db: AsyncSession,
    screenshot: Screenshot,
    grid_coords: dict | None = None,
    output_dir=None,  # Unused, kept for API compatibility
    processing_method: str | None = None,
    current_user_id: int | None = None,
    max_shift: int = 0,
) -> dict:
    """Reprocess an existing screenshot with optional new parameters.

    Uses force=True to bypass daily-total early exits without modifying
    the screenshot model directly (which would persist None to DB on commit).
    """
    result = await process_screenshot_async(db, screenshot, grid_coords, processing_method, current_user_id, max_shift, force=True)

    return result
