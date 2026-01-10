"""File upload handler."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from .models import FileInfo
from .storage import LocalStorage, StorageBackend
from .validators import validate_content_type, validate_file_size


class FileUploadHandler:
    """Comprehensive file upload handler.

    Example:
        handler = FileUploadHandler(
            allowed_types=["text/csv", "application/json"],
            max_size_mb=50,
            storage_path=Path("./uploads"),
        )

        @app.post("/upload")
        async def upload(file: UploadFile = Depends(handler.validate)):
            info = await handler.save(file)
            return {"path": info.path}
    """

    def __init__(
        self,
        *,
        allowed_types: list[str] | None = None,
        max_size_mb: float = 10,
        storage_path: Path | None = None,
        storage: StorageBackend | None = None,
    ):
        """Create file upload handler.

        Args:
            allowed_types: Allowed MIME types (None = allow all)
            max_size_mb: Maximum file size in MB
            storage_path: Path for local storage (creates LocalStorage)
            storage: Custom storage backend (overrides storage_path)
        """
        self.allowed_types = allowed_types
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)

        if storage:
            self.storage = storage
        elif storage_path:
            self.storage = LocalStorage(storage_path)
        else:
            self.storage = LocalStorage(Path("./uploads"))

    async def validate(self, file: UploadFile) -> UploadFile:
        """Validate uploaded file (use as FastAPI dependency).

        Args:
            file: Uploaded file

        Returns:
            The validated file

        Raises:
            HTTPException: If validation fails
        """
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No filename provided",
            )

        # Validate content type
        if self.allowed_types:
            validate_content_type(file, self.allowed_types)

        # Validate size
        await validate_file_size(file, self.max_size_bytes)

        return file

    async def save(self, file: UploadFile) -> FileInfo:
        """Save uploaded file to storage.

        Args:
            file: Validated uploaded file

        Returns:
            FileInfo with storage details
        """
        content = await file.read()
        await file.seek(0)  # Reset for potential re-reading

        return await self.storage.save(
            content=content,
            original_name=file.filename or "unnamed",
            content_type=file.content_type,
        )

    async def validate_and_save(self, file: UploadFile) -> FileInfo:
        """Validate and save in one step.

        Args:
            file: Uploaded file

        Returns:
            FileInfo with storage details
        """
        await self.validate(file)
        return await self.save(file)
