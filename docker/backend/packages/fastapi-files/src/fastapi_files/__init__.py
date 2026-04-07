"""File upload handling for FastAPI applications.

Example usage:
    from fastapi_files import FileUploadHandler, FileInfo

    handler = FileUploadHandler(
        allowed_types=["text/csv", "application/json"],
        max_size_mb=50,
        storage_path=Path("./uploads"),
    )

    @app.post("/upload")
    async def upload(file: UploadFile = Depends(handler.validate)):
        info = await handler.save(file)
        return {"path": info.path, "size": info.size}
"""

from __future__ import annotations

from .handler import FileUploadHandler
from .models import FileInfo
from .validators import validate_content_type, validate_file_size
from .storage import LocalStorage, StorageBackend

__all__ = [
    "FileUploadHandler",
    "FileInfo",
    "validate_content_type",
    "validate_file_size",
    "LocalStorage",
    "StorageBackend",
]

__version__ = "0.1.0"
