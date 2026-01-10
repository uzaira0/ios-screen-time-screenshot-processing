"""Task manager for registering and executing tasks."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from .backends import BackgroundTaskBackend, TaskBackend
from .models import TaskInfo

F = TypeVar("F", bound=Callable)


class TaskManager:
    """Manager for background tasks.

    Example:
        tasks = TaskManager()

        @tasks.task
        async def process_file(file_id: int):
            # Long-running processing
            ...

        # Enqueue task
        task_id = await tasks.enqueue(process_file, file_id=123)

        # Check status
        info = await tasks.get_status(task_id)
    """

    def __init__(self, backend: TaskBackend | None = None):
        """Create task manager.

        Args:
            backend: Task execution backend (default: BackgroundTaskBackend)
        """
        self._backend = backend or BackgroundTaskBackend()
        self._tasks: dict[str, Callable] = {}

    def task(self, func: F) -> F:
        """Decorator to register a task.

        Example:
            @tasks.task
            async def my_task(arg: str):
                ...
        """
        self._tasks[func.__name__] = func
        return func

    async def enqueue(
        self,
        task: Callable | str,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """Enqueue a task for background execution.

        Args:
            task: Task function or name
            *args: Positional arguments for the task
            **kwargs: Keyword arguments for the task

        Returns:
            Task ID for tracking

        Example:
            task_id = await tasks.enqueue(process_file, file_id=123)
            # or
            task_id = await tasks.enqueue("process_file", file_id=123)
        """
        if isinstance(task, str):
            if task not in self._tasks:
                raise ValueError(f"Unknown task: {task}")
            func = self._tasks[task]
        else:
            func = task

        return await self._backend.enqueue(func, *args, **kwargs)

    async def get_status(self, task_id: str) -> TaskInfo | None:
        """Get task status by ID.

        Args:
            task_id: Task ID returned from enqueue()

        Returns:
            TaskInfo or None if not found
        """
        return await self._backend.get_status(task_id)

    def get_task(self, name: str) -> Callable | None:
        """Get a registered task by name."""
        return self._tasks.get(name)

    @property
    def registered_tasks(self) -> list[str]:
        """Get list of registered task names."""
        return list(self._tasks.keys())
