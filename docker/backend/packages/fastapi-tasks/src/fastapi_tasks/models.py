"""Task-related models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class TaskStatus(StrEnum):
    """Task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskInfo(BaseModel):
    """Information about a background task."""

    task_id: str
    name: str
    status: TaskStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: Any | None = None
    error: str | None = None

    @property
    def is_finished(self) -> bool:
        """Check if task has finished (success or failure)."""
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
