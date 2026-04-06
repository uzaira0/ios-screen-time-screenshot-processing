"""Types matching the Temporal Python SDK interfaces.

Field names, defaults, and semantics are identical to:
- temporalio.common.RetryPolicy
- temporalio.activity.Info
- temporalio.workflow (status enums are implicit in Temporal, explicit here)

When migrating to real Temporal, delete this file and import from temporalio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum
from typing import Sequence


class WorkflowStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActivityStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class RetryPolicy:
    """Mirrors temporalio.common.RetryPolicy exactly."""

    initial_interval: timedelta = field(default_factory=lambda: timedelta(seconds=1))
    backoff_coefficient: float = 2.0
    maximum_interval: timedelta | None = None
    maximum_attempts: int = 0  # 0 = unlimited
    non_retryable_error_types: Sequence[str] | None = None


@dataclass(frozen=True)
class ActivityInfo:
    """Subset of temporalio.activity.Info relevant to our engine."""

    activity_id: str
    activity_type: str
    attempt: int
    workflow_id: str
    workflow_type: str


class NonRetryableError(Exception):
    """Raised by activities to signal permanent failure (no retry).

    Mirrors the pattern in Temporal where certain error types are
    listed in RetryPolicy.non_retryable_error_types.
    """

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message)
        if cause is not None:
            self.__cause__ = cause
