"""File storage backends."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import aiofiles

from .models import FileInfo


class StorageBackend(Protocol):
    """Protocol for file storage backends."""

    async def save(
        self,
        content: bytes,
        original_name: str,
        content_type: str | None,
    ) -> FileInfo:
        """Save file content and return file info."""
        ...

    async def delete(self, path: str) -> bool:
        """Delete a file. Returns True if deleted."""
        ...

    async def exists(self, path: str) -> bool:
        """Check if file exists."""
        ...


class LocalStorage:
    """Local filesystem storage backend.

    Example:
        storage = LocalStorage(Path("./uploads"))
        info = await storage.save(content, "data.csv", "text/csv")
    """

    def __init__(
        self,
        base_path: Path,
        *,
        create_dirs: bool = True,
        use_date_subdirs: bool = True,
    ):
        """Create local storage backend.

        Args:
            base_path: Base directory for file storage
            create_dirs: Create directories if they don't exist
            use_date_subdirs: Organize files in YYYY/MM/DD subdirectories
        """
        self.base_path = Path(base_path)
        self.use_date_subdirs = use_date_subdirs

        if create_dirs:
            self.base_path.mkdir(parents=True, exist_ok=True)

    def _generate_stored_name(self, original_name: str) -> str:
        """Generate a unique stored filename."""
        suffix = Path(original_name).suffix
        unique_id = uuid.uuid4().hex[:12]
        return f"{unique_id}{suffix}"

    def _get_storage_dir(self) -> Path:
        """Get the storage directory (with date subdir if enabled)."""
        if self.use_date_subdirs:
            now = datetime.now(timezone.utc)
            return self.base_path / f"{now.year}" / f"{now.month:02d}" / f"{now.day:02d}"
        return self.base_path

    async def save(
        self,
        content: bytes,
        original_name: str,
        content_type: str | None = None,
    ) -> FileInfo:
        """Save file to local storage.

        Args:
            content: File content as bytes
            original_name: Original filename
            content_type: MIME content type

        Returns:
            FileInfo with storage details
        """
        storage_dir = self._get_storage_dir()
        storage_dir.mkdir(parents=True, exist_ok=True)

        stored_name = self._generate_stored_name(original_name)
        file_path = storage_dir / stored_name

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        return FileInfo(
            original_name=original_name,
            stored_name=stored_name,
            path=str(file_path),
            size=len(content),
            content_type=content_type,
            uploaded_at=datetime.now(timezone.utc),
        )

    async def delete(self, path: str) -> bool:
        """Delete a file from storage."""
        file_path = Path(path)
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    async def exists(self, path: str) -> bool:
        """Check if file exists."""
        return Path(path).exists()
