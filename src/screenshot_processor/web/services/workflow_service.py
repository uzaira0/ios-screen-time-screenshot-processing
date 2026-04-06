"""Workflow service — helpers for creating workflows and querying status.

Used by API routes to replace Celery task dispatch.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.workflows.engine.models import (
    ActivityExecution,
    WorkflowExecution,
)
from screenshot_processor.workflows.engine.types import ActivityStatus, WorkflowStatus

if TYPE_CHECKING:
    from screenshot_processor.web.database.schemas import PreprocessingSummary

logger = logging.getLogger(__name__)

# Activity lists per workflow type
PREPROCESSING_ACTIVITIES = ["device_detection", "cropping", "phi_detection"]
REDACTION_ACTIVITIES = ["phi_redaction", "ocr"]


async def create_preprocessing_workflow(
    db: AsyncSession,
    screenshot_id: int,
) -> WorkflowExecution:
    """Create a PreprocessingWorkflow with its 3 activities."""
    wf = WorkflowExecution(
        screenshot_id=screenshot_id,
        workflow_type="PreprocessingWorkflow",
        status=WorkflowStatus.PENDING,
    )
    db.add(wf)
    await db.flush()  # Get wf.id

    for activity_name in PREPROCESSING_ACTIVITIES:
        db.add(ActivityExecution(
            workflow_id=wf.id,
            activity_name=activity_name,
            status=ActivityStatus.PENDING,
            attempt=1,
        ))

    await db.flush()
    return wf


async def create_redaction_workflow(
    db: AsyncSession,
    screenshot_id: int,
) -> WorkflowExecution:
    """Create a RedactionWorkflow with its 2 activities."""
    wf = WorkflowExecution(
        screenshot_id=screenshot_id,
        workflow_type="RedactionWorkflow",
        status=WorkflowStatus.PENDING,
    )
    db.add(wf)
    await db.flush()

    for activity_name in REDACTION_ACTIVITIES:
        db.add(ActivityExecution(
            workflow_id=wf.id,
            activity_name=activity_name,
            status=ActivityStatus.PENDING,
            attempt=1,
        ))

    await db.flush()
    return wf


async def create_preprocessing_workflows_batch(
    db: AsyncSession,
    screenshot_ids: list[int],
) -> list[int]:
    """Bulk-create PreprocessingWorkflows for multiple screenshots. Returns workflow IDs."""
    wf_ids = []
    for sid in screenshot_ids:
        wf = await create_preprocessing_workflow(db, sid)
        wf_ids.append(wf.id)
    return wf_ids


async def create_redaction_workflows_batch(
    db: AsyncSession,
    screenshot_ids: list[int],
) -> list[int]:
    """Bulk-create RedactionWorkflows for multiple screenshots. Returns workflow IDs."""
    wf_ids = []
    for sid in screenshot_ids:
        wf = await create_redaction_workflow(db, sid)
        wf_ids.append(wf.id)
    return wf_ids


async def get_workflow_status(
    db: AsyncSession,
    screenshot_id: int,
    workflow_type: str,
) -> dict | None:
    """Get the latest workflow status and activity statuses for a screenshot."""
    result = await db.execute(
        select(WorkflowExecution)
        .where(WorkflowExecution.screenshot_id == screenshot_id)
        .where(WorkflowExecution.workflow_type == workflow_type)
        .order_by(WorkflowExecution.created_at.desc())
        .limit(1)
    )
    wf = result.scalar_one_or_none()
    if not wf:
        return None

    activities_result = await db.execute(
        select(ActivityExecution)
        .where(ActivityExecution.workflow_id == wf.id)
        .order_by(ActivityExecution.id)
    )
    activities = activities_result.scalars().all()

    return {
        "workflow_id": wf.id,
        "status": wf.status,
        "current_activity": wf.current_activity,
        "created_at": wf.created_at.isoformat() if wf.created_at else None,
        "activities": {
            act.activity_name: {
                "status": act.status,
                "attempt": act.attempt,
                "progress_pct": act.progress_pct,
                "error_message": act.error_message,
                "result_json": act.result_json,
            }
            for act in activities
        },
    }


async def get_preprocessing_summary_from_workflows(
    db: AsyncSession,
    group_id: str,
) -> dict:
    """Build a PreprocessingSummary-compatible dict from workflow/activity tables.

    Returns counts per stage per status, matching the shape the frontend expects.
    """
    from screenshot_processor.web.database.models import Screenshot

    # Get screenshot IDs for this group
    screenshot_ids_result = await db.execute(
        select(Screenshot.id).where(Screenshot.group_id == group_id)
    )
    screenshot_ids = [r[0] for r in screenshot_ids_result.all()]
    total = len(screenshot_ids)

    if not screenshot_ids:
        empty_stage = {"completed": 0, "pending": 0, "skipped": 0, "invalidated": 0, "running": 0, "failed": 0, "cancelled": 0, "exceptions": 0}
        return {
            "total": 0,
            "device_detection": {**empty_stage},
            "cropping": {**empty_stage},
            "phi_detection": {**empty_stage},
            "phi_redaction": {**empty_stage},
            "ocr": {**empty_stage},
        }

    # Query activity statuses grouped by activity_name and status
    # Join through workflow_execution to filter by screenshot_ids
    # Use the LATEST workflow per screenshot (highest ID)
    from sqlalchemy import and_
    from sqlalchemy.orm import aliased

    # Subquery: latest workflow_id per screenshot
    latest_wf = (
        select(
            WorkflowExecution.screenshot_id,
            func.max(WorkflowExecution.id).label("max_wf_id"),
        )
        .where(WorkflowExecution.screenshot_id.in_(screenshot_ids))
        .group_by(WorkflowExecution.screenshot_id)
        .subquery()
    )

    # Activity counts for latest workflows
    counts_result = await db.execute(
        select(
            ActivityExecution.activity_name,
            ActivityExecution.status,
            func.count().label("cnt"),
        )
        .join(WorkflowExecution, ActivityExecution.workflow_id == WorkflowExecution.id)
        .join(
            latest_wf,
            and_(
                WorkflowExecution.screenshot_id == latest_wf.c.screenshot_id,
                WorkflowExecution.id == latest_wf.c.max_wf_id,
            ),
        )
        .group_by(ActivityExecution.activity_name, ActivityExecution.status)
    )

    # Build summary dict
    all_stages = ["device_detection", "cropping", "phi_detection", "phi_redaction", "ocr"]
    summary: dict = {"total": total}
    for stage in all_stages:
        summary[stage] = {"completed": 0, "pending": 0, "skipped": 0, "invalidated": 0, "running": 0, "failed": 0, "cancelled": 0, "exceptions": 0}

    for row in counts_result.all():
        activity_name, status, count = row
        if activity_name in summary and status in summary[activity_name]:
            summary[activity_name][status] = count

    # Screenshots without any workflow yet count as "pending" for all stages
    screenshots_with_workflow = set()
    wf_result = await db.execute(
        select(WorkflowExecution.screenshot_id)
        .where(WorkflowExecution.screenshot_id.in_(screenshot_ids))
        .distinct()
    )
    screenshots_with_workflow = {r[0] for r in wf_result.all()}
    no_workflow_count = total - len(screenshots_with_workflow)
    if no_workflow_count > 0:
        for stage in all_stages:
            summary[stage]["pending"] += no_workflow_count

    return summary


async def cancel_workflow(db: AsyncSession, workflow_id: int) -> None:
    """Cancel a running workflow and its pending activities."""
    wf = await db.get(WorkflowExecution, workflow_id)
    if not wf:
        return

    wf.status = WorkflowStatus.CANCELLED

    # Cancel pending activities
    activities_result = await db.execute(
        select(ActivityExecution)
        .where(ActivityExecution.workflow_id == workflow_id)
        .where(ActivityExecution.status == ActivityStatus.PENDING)
    )
    for act in activities_result.scalars().all():
        act.status = ActivityStatus.SKIPPED

    await db.flush()
