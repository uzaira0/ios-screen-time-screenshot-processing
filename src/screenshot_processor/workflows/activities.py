"""Preprocessing activities — @activity.defn wrappers around existing processing logic.

Each activity:
1. Opens a sync DB session
2. Loads the Screenshot by ID
3. Runs the processing logic (reused from preprocessing_service)
4. Returns a result dict (stored in activity_execution.result_json by the worker)
5. Reports progress via activity.heartbeat()

These functions are direct ports of the Celery tasks in tasks.py, stripped of
Celery-specific retry/timeout logic (now handled by the workflow engine).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from screenshot_processor.web.database.models import ProcessingStatus, Screenshot, StageStatus
from screenshot_processor.workflows.engine import activity

logger = logging.getLogger(__name__)

# Sync database connection (same pattern as tasks.py)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://screenshot:screenshot@localhost:5433/screenshot_annotations",
)
SYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")

_engine = create_engine(SYNC_DATABASE_URL, pool_pre_ping=True)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _get_db() -> Session:
    return _SessionLocal()


# ---------------------------------------------------------------------------
# Activity: device_detection
# ---------------------------------------------------------------------------

@activity.defn
def device_detection(screenshot_id: int) -> dict:
    """Detect iOS device type from screenshot dimensions."""
    from sqlalchemy.orm.attributes import flag_modified

    from screenshot_processor.web.services.preprocessing_service import (
        append_event,
        detect_device,
        get_current_input_file,
        init_preprocessing_metadata,
    )

    activity.heartbeat(0)
    db = _get_db()
    try:
        screenshot = db.query(Screenshot).filter(Screenshot.id == screenshot_id).first()
        if not screenshot:
            raise FileNotFoundError(f"Screenshot {screenshot_id} not found")

        init_preprocessing_metadata(screenshot)
        flag_modified(screenshot, "processing_metadata")
        db.commit()

        input_file = get_current_input_file(screenshot, "device_detection")
        activity.heartbeat(30)

        device = detect_device(input_file)
        activity.heartbeat(80)

        result_data = {
            "detected": device.detected,
            "device_category": device.device_category,
            "device_model": device.device_model,
            "confidence": device.confidence,
            "is_ipad": device.is_ipad,
            "is_iphone": device.is_iphone,
            "orientation": device.orientation,
            "width": device.width,
            "height": device.height,
        }

        if device.detected:
            if device.is_ipad:
                screenshot.device_type = "ipad"
            elif device.is_iphone:
                screenshot.device_type = "iphone"

        append_event(screenshot, "device_detection", "auto", {}, result_data, input_file=input_file)
        flag_modified(screenshot, "processing_metadata")
        db.commit()

        activity.heartbeat(100)
        return result_data
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Activity: cropping
# ---------------------------------------------------------------------------

@activity.defn
def cropping(screenshot_id: int) -> dict:
    """Crop iPad screenshots to remove sidebar."""
    from sqlalchemy.orm.attributes import flag_modified

    from screenshot_processor.web.services.preprocessing_service import (
        DeviceDetectionResult,
        append_event,
        crop_screenshot_if_ipad,
        detect_device,
        get_current_input_file,
        get_next_version,
        get_stage_output_path,
        init_preprocessing_metadata,
    )

    activity.heartbeat(0)
    db = _get_db()
    try:
        screenshot = db.query(Screenshot).filter(Screenshot.id == screenshot_id).first()
        if not screenshot:
            raise FileNotFoundError(f"Screenshot {screenshot_id} not found")

        pp = init_preprocessing_metadata(screenshot)
        flag_modified(screenshot, "processing_metadata")
        db.commit()

        input_file = get_current_input_file(screenshot, "cropping")
        base_path = pp["base_file_path"]
        image_bytes = Path(input_file).read_bytes()
        activity.heartbeat(20)

        # Get device info from previous activity or detect fresh
        current_events = pp.get("current_events", {})
        dd_eid = current_events.get("device_detection")
        device_info = None
        if dd_eid:
            dd_event = next((e for e in pp["events"] if e["event_id"] == dd_eid), None)
            if dd_event:
                device_info = dd_event.get("result", {})

        if device_info:
            device = DeviceDetectionResult(
                detected=device_info.get("detected", False),
                device_category=device_info.get("device_category", "unknown"),
                device_model=device_info.get("device_model"),
                confidence=device_info.get("confidence", 0.0),
                is_ipad=device_info.get("is_ipad", False),
                is_iphone=device_info.get("is_iphone", False),
                orientation=device_info.get("orientation", "unknown"),
                width=device_info.get("width", 0),
                height=device_info.get("height", 0),
            )
        else:
            device = detect_device(input_file)

        activity.heartbeat(50)
        cropped_bytes, was_cropped, was_patched, crop_had_error = crop_screenshot_if_ipad(image_bytes, device)

        output_file = None
        if was_cropped:
            version = get_next_version(screenshot, "cropping")
            output_path = get_stage_output_path(base_path, "cropping", version)
            output_path.write_bytes(cropped_bytes)
            output_file = str(output_path)

        result_data: dict = {
            "was_cropped": was_cropped,
            "was_patched": was_patched,
            "had_error": crop_had_error,
            "is_ipad": device.is_ipad,
        }
        if device:
            result_data["original_dimensions"] = [device.width, device.height]
        if was_cropped:
            import cv2
            import numpy as np
            arr = np.frombuffer(cropped_bytes, np.uint8)
            cropped_img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
            if cropped_img is not None:
                result_data["cropped_dimensions"] = [cropped_img.shape[1], cropped_img.shape[0]]
        elif device:
            result_data["cropped_dimensions"] = [device.width, device.height]

        activity.heartbeat(90)
        params = {"auto_detected_device": device.device_category}
        append_event(screenshot, "cropping", "auto", params, result_data, output_file=output_file, input_file=input_file)
        flag_modified(screenshot, "processing_metadata")
        db.commit()

        activity.heartbeat(100)
        return result_data
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Activity: phi_detection
# ---------------------------------------------------------------------------

@activity.defn
def phi_detection(
    screenshot_id: int,
    preset: str = "screen_time",
    ocr_engine: str = "tesseract",
    ner_detector: str = "presidio",
    llm_endpoint: str | None = None,
    llm_model: str | None = None,
    llm_api_key: str | None = None,
) -> dict:
    """Detect PHI (Protected Health Information) in screenshot."""
    from sqlalchemy.orm.attributes import flag_modified

    from screenshot_processor.web.services.preprocessing_service import (
        append_event,
        detect_phi,
        get_current_input_file,
        init_preprocessing_metadata,
        serialize_phi_regions,
    )

    activity.heartbeat(0)
    db = _get_db()
    try:
        screenshot = db.query(Screenshot).filter(Screenshot.id == screenshot_id).first()
        if not screenshot:
            raise FileNotFoundError(f"Screenshot {screenshot_id} not found")

        init_preprocessing_metadata(screenshot)
        flag_modified(screenshot, "processing_metadata")
        db.commit()

        input_file = get_current_input_file(screenshot, "phi_detection")
        image_bytes = Path(input_file).read_bytes()
        activity.heartbeat(20)

        detection = detect_phi(
            image_bytes,
            preset=preset,
            llm_endpoint=llm_endpoint,
            llm_model=llm_model,
            llm_api_key=llm_api_key,
            ocr_engine=ocr_engine,
            ner_detector=ner_detector,
        )
        activity.heartbeat(80)

        result_data = {
            "phi_detected": detection.phi_detected,
            "regions_count": detection.regions_count,
            "preset": preset,
            "regions": serialize_phi_regions(detection.regions),
        }

        params: dict = {"preset": preset}
        if llm_model:
            params["llm_model"] = llm_model
        append_event(screenshot, "phi_detection", "auto", params, result_data, input_file=input_file)
        flag_modified(screenshot, "processing_metadata")
        db.commit()

        activity.heartbeat(100)
        return result_data
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Activity: phi_redaction
# ---------------------------------------------------------------------------

@activity.defn
def phi_redaction(screenshot_id: int, method: str = "redbox") -> dict:
    """Redact detected PHI regions in screenshot."""
    from sqlalchemy.orm.attributes import flag_modified

    from screenshot_processor.web.services.preprocessing_service import (
        append_event,
        get_current_input_file,
        get_next_version,
        get_stage_output_path,
        init_preprocessing_metadata,
        redact_phi,
    )

    activity.heartbeat(0)
    db = _get_db()
    try:
        screenshot = db.query(Screenshot).filter(Screenshot.id == screenshot_id).first()
        if not screenshot:
            raise FileNotFoundError(f"Screenshot {screenshot_id} not found")

        pp = init_preprocessing_metadata(screenshot)
        flag_modified(screenshot, "processing_metadata")
        db.commit()

        # Get regions from current PHI detection event
        current_events = pp.get("current_events", {})
        phi_eid = current_events.get("phi_detection")
        if not phi_eid:
            # No PHI detection — nothing to redact
            result_data = {"redacted": False, "regions_redacted": 0, "reason": "no_phi_detection"}
            append_event(
                screenshot, "phi_redaction", "auto", {"method": method}, result_data,
                input_file=get_current_input_file(screenshot, "phi_redaction"),
            )
            flag_modified(screenshot, "processing_metadata")
            db.commit()
            activity.heartbeat(100)
            return result_data

        phi_event = next((e for e in pp["events"] if e["event_id"] == phi_eid), None)
        regions = phi_event.get("result", {}).get("regions", []) if phi_event else []

        input_file = get_current_input_file(screenshot, "phi_redaction")
        image_bytes = Path(input_file).read_bytes()
        activity.heartbeat(30)

        redaction = redact_phi(image_bytes, regions, redaction_method=method)
        activity.heartbeat(70)

        output_file = None
        if redaction.regions_redacted > 0:
            base_path = pp["base_file_path"]
            version = get_next_version(screenshot, "phi_redaction")
            output_path = get_stage_output_path(base_path, "phi_redaction", version)
            output_path.write_bytes(redaction.image_bytes)
            output_file = str(output_path)

        result_data = {
            "redacted": redaction.regions_redacted > 0,
            "regions_redacted": redaction.regions_redacted,
            "method": method,
            "phi_detected": phi_event.get("result", {}).get("phi_detected", False) if phi_event else False,
        }

        append_event(
            screenshot, "phi_redaction", "auto",
            {"method": method, "input_event_id": phi_eid}, result_data,
            output_file=output_file, input_file=input_file,
        )
        flag_modified(screenshot, "processing_metadata")
        db.commit()

        activity.heartbeat(100)
        return result_data
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Activity: ocr_extraction
# ---------------------------------------------------------------------------

@activity.defn
def ocr_extraction(
    screenshot_id: int,
    ocr_method: str = "line_based",
    max_shift: int = 5,
) -> dict:
    """Run OCR processing: grid detection, bar extraction, title/total extraction."""
    from sqlalchemy.orm.attributes import flag_modified

    from screenshot_processor.web.services.preprocessing_service import (
        append_event,
        get_current_input_file,
        init_preprocessing_metadata,
    )
    from screenshot_processor.web.services.processing_service import process_screenshot_sync

    activity.heartbeat(0)
    db = _get_db()
    try:
        screenshot = db.query(Screenshot).filter(Screenshot.id == screenshot_id).first()
        if not screenshot:
            raise FileNotFoundError(f"Screenshot {screenshot_id} not found")

        init_preprocessing_metadata(screenshot)
        flag_modified(screenshot, "processing_metadata")
        db.commit()

        activity.heartbeat(10)
        result = process_screenshot_sync(db, screenshot, processing_method=ocr_method, max_shift=max_shift)
        activity.heartbeat(90)

        result_data = {
            "processing_status": result.get("processing_status", "unknown"),
            "processing_method": result.get("processing_method", ocr_method),
            "extracted_title": result.get("extracted_title"),
            "extracted_total": result.get("extracted_total"),
            "grid_detection_confidence": result.get("grid_detection_confidence", 0),
            "alignment_score": result.get("alignment_score", 0),
            "has_blocking_issues": result.get("has_blocking_issues", False),
            "issues": result.get("issues", []),
        }

        input_file = get_current_input_file(screenshot, "ocr")
        append_event(
            screenshot, "ocr", "auto",
            {"method": ocr_method, "max_shift": max_shift}, result_data,
            input_file=input_file,
        )
        flag_modified(screenshot, "processing_metadata")
        db.commit()

        activity.heartbeat(100)
        return result_data
    finally:
        db.close()
