"""Preprocessing pipeline orchestration and event log management."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from screenshot_processor.core.generated_constants import PREPROCESSING_STAGES
from screenshot_processor.web.database.models import StageStatus

from .device_and_crop import DeviceDetectionResult, crop_screenshot_if_ipad, detect_device
from .phi import detect_phi, redact_phi

logger = logging.getLogger(__name__)


@dataclass
class PreprocessingResult:
    """Result of full preprocessing pipeline."""

    success: bool
    image_bytes: bytes | None
    device_detection: DeviceDetectionResult | None
    was_cropped: bool
    was_patched: bool
    phi_detected: bool
    phi_regions_count: int
    phi_redacted: bool
    skip_reason: str | None


# =============================================================================
# Full pipeline functions
# =============================================================================


def preprocess_screenshot_file(
    file_path: str,
    phi_detection_enabled: bool = True,
    phi_pipeline_preset: str = "screen_time",
    phi_redaction_method: str = "redbox",
    phi_ocr_engine: str = "pytesseract",
    phi_ner_detector: str = "presidio",
) -> PreprocessingResult:
    """Run full preprocessing pipeline on a screenshot file. No DB operations.

    Order: device detect -> crop (if iPad) -> PHI detect -> PHI redact

    Args:
        file_path: Path to raw screenshot
        phi_detection_enabled: Whether to run PHI detection/redaction
        phi_pipeline_preset: PHI pipeline preset (fast/balanced/hipaa_compliant/thorough)
        phi_redaction_method: PHI redaction method (redbox/blackbox/pixelate)

    Returns:
        PreprocessingResult with processed image and metadata
    """
    image_path = Path(file_path)

    if not image_path.exists():
        return PreprocessingResult(
            success=False,
            image_bytes=None,
            device_detection=None,
            was_cropped=False,
            was_patched=False,
            phi_detected=False,
            phi_regions_count=0,
            phi_redacted=False,
            skip_reason=f"File not found: {image_path}",
        )

    # 1. Device detection
    device = detect_device(image_path)

    # 2. Read image bytes
    try:
        image_bytes = image_path.read_bytes()
    except Exception as e:
        return PreprocessingResult(
            success=False,
            image_bytes=None,
            device_detection=device,
            was_cropped=False,
            was_patched=False,
            phi_detected=False,
            phi_regions_count=0,
            phi_redacted=False,
            skip_reason=f"Failed to read image: {e}",
        )

    # 3. Crop if iPad
    cropped_bytes, was_cropped, was_patched, crop_had_error = crop_screenshot_if_ipad(image_bytes, device)
    if crop_had_error:
        logger.warning("iPad cropping encountered an error", extra={"file_path": file_path})

    # 4. PHI detection and redaction
    phi_detected = False
    phi_count = 0
    phi_redacted = False
    final_bytes = cropped_bytes

    if phi_detection_enabled:
        detection_result = detect_phi(
            cropped_bytes,
            preset=phi_pipeline_preset,
            ocr_engine=phi_ocr_engine,
            ner_detector=phi_ner_detector,
        )
        phi_detected = detection_result.phi_detected
        phi_count = detection_result.regions_count

        if detection_result.phi_detected:
            redaction_result = redact_phi(
                cropped_bytes, detection_result.regions, redaction_method=phi_redaction_method
            )
            final_bytes = redaction_result.image_bytes
            phi_redacted = redaction_result.regions_redacted > 0

    return PreprocessingResult(
        success=True,
        image_bytes=final_bytes,
        device_detection=device,
        was_cropped=was_cropped,
        was_patched=was_patched,
        phi_detected=phi_detected,
        phi_regions_count=phi_count,
        phi_redacted=phi_redacted,
        skip_reason=None,
    )


def preprocess_screenshot_sync(
    db: Session,
    screenshot: Any,
    settings: Any | None = None,
    *,
    phi_pipeline_preset: str | None = None,
    phi_redaction_method: str | None = None,
    phi_detection_enabled: bool | None = None,
    phi_ocr_engine: str | None = None,
    phi_ner_detector: str | None = None,
) -> dict:
    """Run preprocessing on a screenshot and update DB metadata.

    This is the sync function used by workflow activities. It:
    1. Runs the full preprocessing pipeline
    2. Saves the preprocessed image alongside the original
    3. Updates processing_metadata JSON with preprocessing results
    4. Returns a result dict

    Args:
        db: SQLAlchemy sync session
        screenshot: Screenshot model instance
        settings: Optional Settings instance (uses get_settings() if None)
        phi_pipeline_preset: Override PHI pipeline preset (takes precedence over settings)
        phi_redaction_method: Override PHI redaction method (takes precedence over settings)
        phi_detection_enabled: Override PHI detection toggle (takes precedence over settings)

    Returns:
        dict with preprocessing results and metadata
    """
    from sqlalchemy.orm.attributes import flag_modified

    from screenshot_processor.web.config import get_settings

    if settings is None:
        settings = get_settings()

    # Resolve effective values: explicit overrides > settings defaults
    effective_phi_detection = (
        phi_detection_enabled if phi_detection_enabled is not None else getattr(settings, "PHI_DETECTION_ENABLED", True)
    )
    effective_phi_preset = phi_pipeline_preset or getattr(settings, "PHI_PIPELINE_PRESET", "screen_time")
    effective_phi_method = phi_redaction_method or getattr(settings, "PHI_REDACTION_METHOD", "redbox")
    effective_phi_ocr = phi_ocr_engine or getattr(settings, "PHI_OCR_ENGINE", "pytesseract")
    effective_phi_ner = phi_ner_detector or getattr(settings, "PHI_NER_DETECTOR", "presidio")

    # Always preprocess from the original file, not a previously preprocessed version
    existing_preprocessing = (screenshot.processing_metadata or {}).get("preprocessing", {})
    file_path = existing_preprocessing.get("original_file_path", screenshot.file_path)
    logger.info("Preprocessing screenshot", extra={"screenshot_id": screenshot.id, "file_path": file_path})

    # Run preprocessing pipeline
    result = preprocess_screenshot_file(
        file_path=file_path,
        phi_detection_enabled=effective_phi_detection,
        phi_pipeline_preset=effective_phi_preset,
        phi_redaction_method=effective_phi_method,
        phi_ocr_engine=effective_phi_ocr,
        phi_ner_detector=effective_phi_ner,
    )

    # Build metadata dict
    preprocessing_metadata: dict[str, Any] = {
        "preprocessing_timestamp": datetime.now(timezone.utc).isoformat(),
        "original_file_path": file_path,
    }

    if result.device_detection:
        preprocessing_metadata["device_detection"] = {
            "device_category": result.device_detection.device_category,
            "device_model": result.device_detection.device_model,
            "confidence": result.device_detection.confidence,
            "is_ipad": result.device_detection.is_ipad,
            "is_iphone": result.device_detection.is_iphone,
            "orientation": result.device_detection.orientation,
        }

        # Update device_type on the screenshot model if detected
        if result.device_detection.detected:
            if result.device_detection.is_ipad:
                screenshot.device_type = "ipad"
            elif result.device_detection.is_iphone:
                screenshot.device_type = "iphone"

    preprocessing_metadata["cropping"] = {
        "was_cropped": result.was_cropped,
        "was_patched": result.was_patched,
    }

    if result.was_cropped and result.device_detection:
        preprocessing_metadata["cropping"]["original_dimensions"] = [
            result.device_detection.width,
            result.device_detection.height,
        ]

    preprocessing_metadata["phi_detection"] = {
        "phi_detected": result.phi_detected,
        "regions_count": result.phi_regions_count,
        "preset": effective_phi_preset,
    }

    preprocessing_metadata["phi_redaction"] = {
        "redacted": result.phi_redacted,
        "regions_redacted": result.phi_regions_count if result.phi_redacted else 0,
        "method": effective_phi_method,
    }

    # Save preprocessed image if pipeline produced output
    preprocessed_file_path = None
    if result.success and result.image_bytes:
        original_path = Path(file_path)
        preprocessed_path = original_path.parent / f"{original_path.stem}_preprocessed{original_path.suffix}"
        try:
            preprocessed_path.write_bytes(result.image_bytes)
            preprocessed_file_path = str(preprocessed_path)
            preprocessing_metadata["preprocessed_file_path"] = preprocessed_file_path
            logger.info(
                "Saved preprocessed image",
                extra={"screenshot_id": screenshot.id, "preprocessed_path": str(preprocessed_path)},
            )
        except Exception as e:
            preprocessing_metadata["image_write_failed"] = True
            logger.error("Failed to save preprocessed image", extra={"screenshot_id": screenshot.id, "error": str(e)})

    if not result.success:
        preprocessing_metadata["skip_reason"] = result.skip_reason

    # Merge preprocessing metadata into existing processing_metadata
    existing_metadata = screenshot.processing_metadata or {}
    existing_metadata["preprocessing"] = preprocessing_metadata
    screenshot.processing_metadata = existing_metadata
    flag_modified(screenshot, "processing_metadata")

    db.commit()
    db.refresh(screenshot)

    logger.info(
        "Preprocessing complete",
        extra={
            "screenshot_id": screenshot.id,
            "was_cropped": result.was_cropped,
            "phi_detected": result.phi_detected,
            "phi_redacted": result.phi_redacted,
        },
    )

    return {
        "success": result.success,
        "screenshot_id": screenshot.id,
        "preprocessed_file_path": preprocessed_file_path,
        "was_cropped": result.was_cropped,
        "phi_detected": result.phi_detected,
        "phi_redacted": result.phi_redacted,
        "skip_reason": result.skip_reason,
    }


# =============================================================================
# Event log management — composable per-stage pipeline
# =============================================================================

STAGE_ORDER = list(PREPROCESSING_STAGES)

# Stages that produce an output file (others are metadata-only)
STAGE_FILE_SUFFIX = {
    "cropping": "crop",
    "phi_redaction": "redact",
}

# Pattern that matches pipeline-generated output suffixes.
# Handles: _crop_v1.png, _redact_v2.jpg, _redact_v1_preprocessed.png, etc.
_PIPELINE_SUFFIX_RE = re.compile(r"_(crop|redact)_v\d+(?:_preprocessed)?(\.[^.]+)$")
# Standalone _preprocessed suffix from the old full-pipeline code path.
_PREPROCESSED_SUFFIX_RE = re.compile(r"_preprocessed(\.[^.]+)$")


def _resolve_original_path(path: str) -> str:
    """Strip all pipeline output suffixes to recover the original upload path.

    Handles _crop_v{N}, _redact_v{N}, _preprocessed, and combinations like
    _redact_v1_preprocessed.  If the candidate original path exists on disk,
    return it. Otherwise return path unchanged.  This ensures device_detection
    and cropping always use the file that was actually uploaded.
    """
    p = Path(path)
    # Strip pipeline suffixes iteratively (handles stacked suffixes)
    candidate_name = p.name
    candidate_name = _PIPELINE_SUFFIX_RE.sub(r"\2", candidate_name)
    candidate_name = _PREPROCESSED_SUFFIX_RE.sub(r"\1", candidate_name)
    if candidate_name != p.name:
        candidate = p.parent / candidate_name
        if candidate.exists():
            return str(candidate)
    return path


def init_preprocessing_metadata(screenshot: Any) -> dict:
    """Initialize preprocessing metadata on a screenshot if not already present.

    Sets base_file_path and initializes empty events/status structures.
    Returns the preprocessing sub-dict.
    """
    metadata = screenshot.processing_metadata or {}
    pp = metadata.setdefault("preprocessing", {})
    if "base_file_path" not in pp:
        # Always resolve to the original upload — strip any pipeline-generated
        # suffixes (_crop_v1, _redact_v1) in case file_path was updated by a
        # previous pipeline run before metadata was cleared/re-initialized.
        pp["base_file_path"] = _resolve_original_path(screenshot.file_path)
        pp["events"] = []
        pp["current_events"] = {}
        pp["stage_status"] = dict.fromkeys(STAGE_ORDER, StageStatus.PENDING)
    # Ensure all keys exist (for screenshots initialized before event log)
    pp.setdefault("events", [])
    pp.setdefault("current_events", {})
    pp.setdefault("stage_status", dict.fromkeys(STAGE_ORDER, StageStatus.PENDING))
    screenshot.processing_metadata = metadata
    return pp


def append_event(
    screenshot: Any,
    stage: str,
    source: str,
    params: dict,
    result: dict,
    output_file: str | None = None,
    input_file: str | None = None,
) -> int:
    """Append an event to the preprocessing log. Returns the new event_id.

    After appending, updates current_events and stage_status, then
    invalidates any downstream stages whose input is now stale.
    """
    pp = init_preprocessing_metadata(screenshot)
    events = pp["events"]
    current = pp["current_events"]
    stage_status = pp["stage_status"]

    # Determine what this event supersedes
    prev_event_id = current.get(stage)

    event_id = len(events) + 1
    events.append(
        {
            "event_id": event_id,
            "stage": stage,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "params": params,
            "result": result,
            "output_file": output_file,
            "input_file": input_file,
            "supersedes": prev_event_id,
        }
    )

    # Update current state
    current[stage] = event_id
    stage_status[stage] = StageStatus.COMPLETED

    # Invalidate downstream stages
    invalidate_downstream(screenshot, stage)

    # Update file_path to latest valid output
    update_file_path(screenshot)

    return event_id


def set_stage_running(screenshot: Any, stage: str) -> None:
    """Mark a stage as running before execution starts."""
    pp = init_preprocessing_metadata(screenshot)
    pp["stage_status"][stage] = StageStatus.RUNNING


def append_error_event(
    screenshot: Any,
    stage: str,
    source: str,
    params: dict,
    error_message: str,
    input_file: str | None = None,
) -> int:
    """Append a failed event. Sets stage_status to 'failed'."""
    pp = init_preprocessing_metadata(screenshot)
    events = pp["events"]
    stage_status = pp["stage_status"]

    event_id = len(events) + 1
    events.append(
        {
            "event_id": event_id,
            "stage": stage,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "params": params,
            "result": {"error": error_message},
            "output_file": None,
            "input_file": input_file,
            "supersedes": None,
        }
    )

    stage_status[stage] = StageStatus.FAILED
    return event_id


def invalidate_downstream(screenshot: Any, from_stage: str) -> None:
    """Mark all stages after from_stage as invalidated."""
    pp = screenshot.processing_metadata["preprocessing"]
    stage_status = pp["stage_status"]
    current = pp["current_events"]

    idx = STAGE_ORDER.index(from_stage)
    for downstream in STAGE_ORDER[idx + 1 :]:
        if current.get(downstream) is not None:
            stage_status[downstream] = StageStatus.INVALIDATED
            current[downstream] = None


def update_file_path(screenshot: Any) -> None:
    """Set screenshot.file_path to the output of the latest completed stage."""
    pp = screenshot.processing_metadata["preprocessing"]
    events = pp.get("events", [])
    current = pp.get("current_events", {})

    # Walk stages in reverse, find latest with an output file
    for stage in reversed(STAGE_ORDER):
        eid = current.get(stage)
        if eid is not None:
            event = next((e for e in events if e["event_id"] == eid), None)
            if event and event.get("output_file"):
                screenshot.file_path = event["output_file"]
                return
    # Fallback to base
    screenshot.file_path = pp.get("base_file_path", screenshot.file_path)


def get_current_input_file(screenshot: Any, stage: str) -> str:
    """Get the input file for a stage based on current events.

    device_detection and cropping ALWAYS receive the original uploaded image —
    never a previously-generated crop or redaction output.  PHI/OCR stages
    receive the latest crop output (if any), or the original as fallback.
    """
    pp = screenshot.processing_metadata.get("preprocessing", {})
    base = pp.get("base_file_path", screenshot.file_path)

    if stage in ("device_detection", "cropping"):
        # Resolve the original upload path — strips _crop_v{N}/_redact_v{N}
        # suffixes in case base_file_path was set incorrectly in a prior run.
        return _resolve_original_path(base)
    if stage in ("phi_detection", "phi_redaction"):
        # Use latest crop output, or base if no crop
        crop_eid = pp.get("current_events", {}).get("cropping")
        if crop_eid:
            event = next(
                (e for e in pp.get("events", []) if e["event_id"] == crop_eid),
                None,
            )
            if event and event.get("output_file"):
                return event["output_file"]
        return base
    return base


def get_stage_output_path(base_path: str, stage: str, version: int) -> Path:
    """Build versioned output path for a stage. E.g. IMG_crop_v2.png."""
    tag = STAGE_FILE_SUFFIX.get(stage)
    if not tag:
        raise ValueError(f"Stage {stage} does not produce output files")
    p = Path(base_path)
    return p.parent / f"{p.stem}_{tag}_v{version}{p.suffix}"


def get_next_version(screenshot: Any, stage: str) -> int:
    """Get the next version number for a stage's output file.

    Only counts the current (non-superseded) event. After a reset,
    the version resets to 1 instead of accumulating forever.
    """
    pp = screenshot.processing_metadata.get("preprocessing", {})
    current_events = pp.get("current_events", {})
    current_eid = current_events.get(stage)

    if current_eid is None:
        # No current event — this is a fresh run (after reset or first time)
        return 1

    # There's a current event — increment from it
    events = pp.get("events", [])
    current = next((e for e in events if e["event_id"] == current_eid), None)
    if current and current.get("output_file"):
        # Reuse the same version to avoid accumulation
        m = re.search(r"_v(\d+)\.", current["output_file"])
        if m:
            return int(m.group(1))

    return 1


def get_stage_counts(screenshots: list, stage: str) -> dict:
    """Compute per-status counts for a stage across a list of screenshots."""
    counts = {"completed": 0, "pending": 0, "skipped": 0, "invalidated": 0, "running": 0, "failed": 0, "cancelled": 0, "exceptions": 0}
    for s in screenshots:
        pp = (s.processing_metadata or {}).get("preprocessing", {})
        status = pp.get("stage_status", {}).get(stage, "pending")
        if status in counts:
            counts[status] += 1
        else:
            counts["pending"] += 1

        # Exception detection
        if status == "completed":
            current_events = pp.get("current_events", {})
            eid = current_events.get(stage)
            if eid:
                event = next((e for e in pp.get("events", []) if e["event_id"] == eid), None)
                if event and is_exception(stage, event.get("result", {})):
                    counts["exceptions"] += 1
                    continue
            # OCR: also check bar total vs OCR total mismatch on the screenshot model
            if stage == "ocr" and _is_ocr_mismatch(s):
                counts["exceptions"] += 1
    return counts


def get_stage_counts_from_metadata(rows: list, stage: str) -> dict:
    """Compute per-status counts for a stage from lightweight query rows.

    Each row is a tuple of (processing_metadata, extracted_hourly_data, extracted_total).
    Like get_stage_counts but works with raw column tuples instead of ORM objects,
    avoiding the need to load full Screenshot objects.
    """
    counts = {"completed": 0, "pending": 0, "skipped": 0, "invalidated": 0, "running": 0, "failed": 0, "cancelled": 0, "exceptions": 0}
    for row in rows:
        metadata, hourly_data, ocr_total = row[0], row[1], row[2]
        pp = (metadata or {}).get("preprocessing", {})
        status = pp.get("stage_status", {}).get(stage, "pending")
        if status in counts:
            counts[status] += 1
        else:
            counts["pending"] += 1

        # Exception detection
        if status == "completed":
            current_events = pp.get("current_events", {})
            eid = current_events.get(stage)
            if eid:
                event = next((e for e in pp.get("events", []) if e["event_id"] == eid), None)
                if event and is_exception(stage, event.get("result", {})):
                    counts["exceptions"] += 1
                    continue
            # OCR: also check bar total vs OCR total mismatch
            if stage == "ocr" and hourly_data and ocr_total:
                from screenshot_processor.core.ocr import parse_time_to_minutes

                bar_total = sum(v for k, v in hourly_data.items() if k.isdigit() and isinstance(v, (int, float)))
                ocr_minutes = parse_time_to_minutes(ocr_total)
                if ocr_minutes is not None and ocr_minutes > 0 and abs(bar_total - ocr_minutes) > max(ocr_minutes * 0.1, 5):
                    counts["exceptions"] += 1
    return counts


def _is_ocr_mismatch(screenshot) -> bool:
    """Check if bar total differs significantly from OCR total."""
    from screenshot_processor.core.ocr import parse_time_to_minutes

    hourly = getattr(screenshot, "extracted_hourly_data", None)
    ocr_total = getattr(screenshot, "extracted_total", None)
    if not hourly or not ocr_total:
        return False
    bar_total = sum(v for k, v in hourly.items() if k.isdigit() and isinstance(v, (int, float)))
    ocr_minutes = parse_time_to_minutes(ocr_total)
    if ocr_minutes is None or ocr_minutes == 0:
        return False
    return abs(bar_total - ocr_minutes) > max(ocr_minutes * 0.1, 5)


def is_exception(stage: str, result: dict) -> bool:
    """Check if a stage result should be flagged for review."""
    if stage == "device_detection":
        if result.get("device_category") == "unknown":
            return True
        if result.get("confidence", 1.0) < 0.7:
            return True
    elif stage == "cropping":
        if result.get("is_ipad") and not result.get("was_cropped"):
            return True
    elif stage == "phi_detection":
        if result.get("reviewed"):
            return False  # Manually reviewed — no longer needs review
        regions = result.get("regions", [])
        regions_count = result.get("regions_count", len(regions) if isinstance(regions, list) else 0)
        if regions_count == 0:
            return False  # No regions (all removed/whitelisted) — nothing to review
        if result.get("phi_detected"):
            return True
        if regions_count > 10:
            return True
    elif stage == "phi_redaction":
        if result.get("phi_detected") and not result.get("redacted"):
            return True
    elif stage == "ocr":
        if result.get("processing_status") == "failed":
            return True
        if result.get("has_blocking_issues"):
            return True
        align = result.get("alignment_score")
        if isinstance(align, (int, float)) and align < 0.8:
            return True
    return False
