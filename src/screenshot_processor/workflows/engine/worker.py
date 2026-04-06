"""WorkflowWorker — polls DB for pending workflows and executes activities.

This is the runtime that replaces Temporal's worker. It:
1. Polls workflow_execution for pending/running workflows
2. For each workflow, finds the next pending activity
3. Executes the activity function with retry logic
4. Updates activity_execution status/progress
5. Checks for signals between activities
6. Marks the workflow as completed when all activities are done

When migrating to Temporal, this file is deleted entirely — Temporal's
worker handles all of this automatically.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from screenshot_processor.workflows.engine.models import (
    ActivityExecution,
    WorkflowAuditEntry,
    WorkflowExecution,
    WorkflowSignal,
)
from screenshot_processor.workflows.engine.registry import (
    get_activity_defn,
    get_workflow_defn,
)
from screenshot_processor.workflows.engine.types import (
    ActivityInfo,
    ActivityStatus,
    NonRetryableError,
    RetryPolicy,
    WorkflowStatus,
)

logger = logging.getLogger(__name__)

# Default retry policy for activities without an explicit one
_DEFAULT_RETRY_POLICY = RetryPolicy()

# Permanent error types (non-retryable by default)
_PERMANENT_ERROR_TYPES: set[str] = {
    "ValueError",
    "KeyError",
    "FileNotFoundError",
    "PermissionError",
    "NonRetryableError",
}


def classify_error(
    error: BaseException,
    *,
    policy: RetryPolicy | None = None,
) -> str:
    """Classify an error as 'transient' or 'permanent'."""
    error_type_name = type(error).__name__

    # NonRetryableError is always permanent
    if isinstance(error, NonRetryableError):
        return "permanent"

    # Check policy-specific non-retryable types
    if policy and policy.non_retryable_error_types:
        if error_type_name in policy.non_retryable_error_types:
            return "permanent"

    # Check built-in permanent types
    if error_type_name in _PERMANENT_ERROR_TYPES:
        return "permanent"

    # Everything else is transient
    return "transient"


def compute_retry_delay(policy: RetryPolicy, *, attempt: int) -> timedelta:
    """Compute the delay before the next retry attempt."""
    delay = policy.initial_interval * (policy.backoff_coefficient ** (attempt - 1))
    if policy.maximum_interval is not None and delay > policy.maximum_interval:
        delay = policy.maximum_interval
    return delay


def should_retry(
    policy: RetryPolicy,
    *,
    attempt: int,
    error_class: str,
) -> bool:
    """Determine if an activity should be retried."""
    if error_class == "permanent":
        return False
    if policy.maximum_attempts > 0 and attempt >= policy.maximum_attempts:
        return False
    return True


def _log_audit(db: Session, workflow_id: int, event: str, *, activity_name: str | None = None, detail: str | None = None, attempt: int | None = None, progress_pct: float | None = None) -> None:
    """Append an entry to the workflow audit log. Never raises."""
    try:
        db.add(WorkflowAuditEntry(
            workflow_id=workflow_id,
            activity_name=activity_name,
            event=event,
            detail=detail,
            attempt=attempt,
            progress_pct=progress_pct,
        ))
        db.commit()
    except Exception:
        db.rollback()


async def execute_activity_with_persistence(
    db: Session,
    activity_row: ActivityExecution,
    *,
    args: list[Any] | None = None,
    retry_policy: RetryPolicy | None = None,
) -> Any:
    """Execute a registered activity, updating the DB row through its lifecycle.

    1. Sets status=running, started_at=now
    2. Sets up activity context (info, heartbeat)
    3. Calls the activity function
    4. On success: status=completed, completed_at=now
    5. On failure: classifies error, sets status=failed with error details

    Raises the original exception after updating the DB row.
    """
    from screenshot_processor.workflows.engine import activity as activity_mod

    policy = retry_policy or _DEFAULT_RETRY_POLICY
    defn = get_activity_defn(activity_row.activity_name)

    # Update status to running
    activity_row.status = ActivityStatus.RUNNING
    activity_row.started_at = datetime.now(UTC)
    db.commit()
    _log_audit(db, activity_row.workflow_id, "started", activity_name=activity_row.activity_name, attempt=activity_row.attempt)

    # Set up activity context
    info = ActivityInfo(
        activity_id=str(activity_row.id),
        activity_type=activity_row.activity_name,
        attempt=activity_row.attempt,
        workflow_id=str(activity_row.workflow_id),
        workflow_type="preprocessing",
    )

    _last_logged_pct = [0.0]

    def _heartbeat(*details: Any) -> None:
        if details and isinstance(details[0], (int, float)):
            pct = float(details[0])
            activity_row.progress_pct = pct
            try:
                db.commit()
            except Exception:
                logger.warning("Failed to persist heartbeat for activity %s", activity_row.activity_name, exc_info=True)
                db.rollback()
            # Log audit at 25% intervals
            if pct - _last_logged_pct[0] >= 25.0:
                _log_audit(db, activity_row.workflow_id, "heartbeat", activity_name=activity_row.activity_name, progress_pct=pct)
                _last_logged_pct[0] = pct

    # Set context variables
    info_token = activity_mod._current_info.set(info)
    hb_token = activity_mod._heartbeat_fn.set(_heartbeat)

    try:
        call_args = args or []
        if defn.is_async:
            result = await defn.fn(*call_args)
        else:
            result = defn.fn(*call_args)

        # Success
        activity_row.status = ActivityStatus.COMPLETED
        activity_row.progress_pct = 100.0
        activity_row.completed_at = datetime.now(UTC)
        db.commit()
        _log_audit(db, activity_row.workflow_id, "completed", activity_name=activity_row.activity_name, attempt=activity_row.attempt, progress_pct=100.0)
        return result

    except Exception as exc:
        error_class = classify_error(exc, policy=policy)
        activity_row.status = ActivityStatus.FAILED
        activity_row.error_message = f"{type(exc).__name__}: {exc}"
        activity_row.error_class = error_class
        activity_row.completed_at = datetime.now(UTC)
        db.commit()
        _log_audit(db, activity_row.workflow_id, "failed", activity_name=activity_row.activity_name, attempt=activity_row.attempt, detail=f"{type(exc).__name__}: {exc}")
        raise

    finally:
        activity_mod._current_info.reset(info_token)
        activity_mod._heartbeat_fn.reset(hb_token)
