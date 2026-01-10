"""Task execution backends."""

from __future__ import annotations

import asyncio
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from .models import TaskInfo, TaskStatus


class TaskBackend(ABC):
    """Abstract base class for task backends."""

    @abstractmethod
    async def enqueue(
        self,
        func: Callable,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """Enqueue a task for execution.

        Returns:
            Task ID
        """
        ...

    @abstractmethod
    async def get_status(self, task_id: str) -> TaskInfo | None:
        """Get task status by ID."""
        ...


class BackgroundTaskBackend(TaskBackend):
    """Simple in-process background task backend.

    Uses asyncio for async tasks. Suitable for simple cases
    where you don't need distributed task processing.

    Note: Tasks are lost if the process restarts.
    """

    def __init__(self):
        self._tasks: dict[str, TaskInfo] = {}
        self._running: dict[str, asyncio.Task] = {}

    async def enqueue(
        self,
        func: Callable,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """Enqueue a task for background execution."""
        task_id = str(uuid.uuid4())[:12]
        now = datetime.now(timezone.utc)

        # Create task info
        self._tasks[task_id] = TaskInfo(
            task_id=task_id,
            name=func.__name__,
            status=TaskStatus.PENDING,
            created_at=now,
        )

        # Start execution
        if asyncio.iscoroutinefunction(func):
            coro = func(*args, **kwargs)
        else:
            # Wrap sync function
            coro = asyncio.to_thread(func, *args, **kwargs)

        self._running[task_id] = asyncio.create_task(
            self._execute(task_id, coro)
        )

        return task_id

    async def _execute(self, task_id: str, coro: Coroutine) -> None:
        """Execute task and update status."""
        info = self._tasks[task_id]
        info.status = TaskStatus.RUNNING
        info.started_at = datetime.now(timezone.utc)

        try:
            result = await coro
            info.status = TaskStatus.COMPLETED
            info.result = result
        except Exception as e:
            info.status = TaskStatus.FAILED
            info.error = str(e)
        finally:
            info.completed_at = datetime.now(timezone.utc)
            self._running.pop(task_id, None)

    async def get_status(self, task_id: str) -> TaskInfo | None:
        """Get task status by ID."""
        return self._tasks.get(task_id)


class CeleryBackend(TaskBackend):
    """Celery-based distributed task backend.

    Requires celery[redis] to be installed.
    """

    def __init__(self, celery_app):
        """Create Celery backend.

        Args:
            celery_app: Configured Celery application instance
        """
        self._celery = celery_app
        self._task_names: dict[str, str] = {}  # task_id -> task_name

    async def enqueue(
        self,
        func: Callable,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """Enqueue a Celery task."""
        # Get the Celery task by name
        task_name = f"{func.__module__}.{func.__name__}"

        # Send task to Celery
        result = self._celery.send_task(task_name, args=args, kwargs=kwargs)

        self._task_names[result.id] = func.__name__
        return result.id

    async def get_status(self, task_id: str) -> TaskInfo | None:
        """Get task status from Celery."""
        result = self._celery.AsyncResult(task_id)

        if result is None:
            return None

        status_map = {
            "PENDING": TaskStatus.PENDING,
            "STARTED": TaskStatus.RUNNING,
            "SUCCESS": TaskStatus.COMPLETED,
            "FAILURE": TaskStatus.FAILED,
            "REVOKED": TaskStatus.CANCELLED,
        }

        return TaskInfo(
            task_id=task_id,
            name=self._task_names.get(task_id, "unknown"),
            status=status_map.get(result.status, TaskStatus.PENDING),
            created_at=datetime.now(timezone.utc),  # Celery doesn't track this
            result=result.result if result.successful() else None,
            error=str(result.result) if result.failed() else None,
        )
