#!/usr/bin/env python3
"""One-time migration: convert processing_metadata JSON to workflow/activity execution rows.

Usage:
    python scripts/migrate_preprocessing_metadata.py --dry-run  # preview
    python scripts/migrate_preprocessing_metadata.py             # run migration
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from screenshot_processor.web.database.models import Screenshot
from screenshot_processor.workflows.engine.models import (
    ActivityExecution,
    WorkflowExecution,
)
from screenshot_processor.workflows.engine.types import ActivityStatus, WorkflowStatus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://screenshot:screenshot@localhost:5433/screenshot_annotations",
)
SYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")

PREPROCESSING_STAGES = ["device_detection", "cropping", "phi_detection"]
REDACTION_STAGES = ["phi_redaction", "ocr"]

STATUS_MAP = {
    "completed": ActivityStatus.COMPLETED,
    "pending": ActivityStatus.PENDING,
    "failed": ActivityStatus.FAILED,
    "invalidated": ActivityStatus.PENDING,
    "running": ActivityStatus.PENDING,
    "skipped": ActivityStatus.SKIPPED,
    "cancelled": ActivityStatus.SKIPPED,
}


def migrate(dry_run: bool = False) -> None:
    engine = create_engine(SYNC_DATABASE_URL, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        screenshots = db.query(Screenshot).filter(Screenshot.processing_metadata.isnot(None)).all()
        logger.info("Found %d screenshots with processing_metadata", len(screenshots))

        wf_count = 0
        act_count = 0

        for s in screenshots:
            pp = (s.processing_metadata or {}).get("preprocessing")
            if not pp:
                continue

            stage_status = pp.get("stage_status", {})
            events = pp.get("events", [])
            current_events = pp.get("current_events", {})

            # Check if any preprocessing stages have been run
            has_preprocessing = any(stage_status.get(stage) for stage in PREPROCESSING_STAGES)
            has_redaction = any(stage_status.get(stage) for stage in REDACTION_STAGES)

            if has_preprocessing:
                # Derive workflow status
                all_completed = all(
                    stage_status.get(stage) in ("completed", "skipped")
                    for stage in PREPROCESSING_STAGES
                )
                any_failed = any(stage_status.get(stage) == "failed" for stage in PREPROCESSING_STAGES)
                wf_status = (
                    WorkflowStatus.COMPLETED if all_completed
                    else WorkflowStatus.FAILED if any_failed
                    else WorkflowStatus.PENDING
                )

                wf = WorkflowExecution(
                    screenshot_id=s.id,
                    workflow_type="PreprocessingWorkflow",
                    status=wf_status,
                )
                if not dry_run:
                    db.add(wf)
                    db.flush()
                wf_count += 1

                for stage in PREPROCESSING_STAGES:
                    status = stage_status.get(stage, "pending")
                    mapped_status = STATUS_MAP.get(status, ActivityStatus.PENDING)

                    # Get result from current event
                    result_json = None
                    eid = current_events.get(stage)
                    if eid:
                        event = next((e for e in events if e.get("event_id") == eid), None)
                        if event:
                            result_json = event.get("result")

                    act = ActivityExecution(
                        workflow_id=wf.id if not dry_run else 0,
                        activity_name=stage,
                        status=mapped_status,
                        attempt=1,
                        progress_pct=100.0 if mapped_status == ActivityStatus.COMPLETED else 0.0,
                        result_json=result_json,
                    )
                    if not dry_run:
                        db.add(act)
                    act_count += 1

            if has_redaction:
                all_completed = all(
                    stage_status.get(stage) in ("completed", "skipped")
                    for stage in REDACTION_STAGES
                )
                any_failed = any(stage_status.get(stage) == "failed" for stage in REDACTION_STAGES)
                wf_status = (
                    WorkflowStatus.COMPLETED if all_completed
                    else WorkflowStatus.FAILED if any_failed
                    else WorkflowStatus.PENDING
                )

                wf = WorkflowExecution(
                    screenshot_id=s.id,
                    workflow_type="RedactionWorkflow",
                    status=wf_status,
                )
                if not dry_run:
                    db.add(wf)
                    db.flush()
                wf_count += 1

                for stage in REDACTION_STAGES:
                    status = stage_status.get(stage, "pending")
                    mapped_status = STATUS_MAP.get(status, ActivityStatus.PENDING)

                    result_json = None
                    eid = current_events.get(stage)
                    if eid:
                        event = next((e for e in events if e.get("event_id") == eid), None)
                        if event:
                            result_json = event.get("result")

                    act = ActivityExecution(
                        workflow_id=wf.id if not dry_run else 0,
                        activity_name=stage,
                        status=mapped_status,
                        attempt=1,
                        progress_pct=100.0 if mapped_status == ActivityStatus.COMPLETED else 0.0,
                        result_json=result_json,
                    )
                    if not dry_run:
                        db.add(act)
                    act_count += 1

        if not dry_run:
            db.commit()
            logger.info("Migration complete: %d workflows, %d activities created", wf_count, act_count)
        else:
            logger.info("DRY RUN: would create %d workflows, %d activities", wf_count, act_count)

    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate processing_metadata to workflow tables")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
