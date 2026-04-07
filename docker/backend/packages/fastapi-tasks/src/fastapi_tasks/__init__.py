"""Background task utilities for FastAPI.

Supports multiple backends:
- FastAPI BackgroundTasks (built-in, simple)
- Celery (distributed, reliable)
- ARQ (async, Redis-based)

Example usage:
    from fastapi_tasks import TaskManager, BackgroundTask

    tasks = TaskManager()

    @tasks.task
    async def process_file(file_id: int):
        ...

    @app.post("/files")
    async def upload(file: UploadFile, background_tasks: BackgroundTasks):
        file_id = await save_file(file)
        await tasks.enqueue("process_file", file_id=file_id)
        return {"file_id": file_id}
"""

from __future__ import annotations

from .manager import TaskManager
from .models import TaskInfo, TaskStatus
from .backends import BackgroundTaskBackend, CeleryBackend

__all__ = [
    "TaskManager",
    "TaskInfo",
    "TaskStatus",
    "BackgroundTaskBackend",
    "CeleryBackend",
]

__version__ = "0.1.0"
