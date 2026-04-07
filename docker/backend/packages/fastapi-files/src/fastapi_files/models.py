"""File-related models."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel


class FileInfo(BaseModel):
    """Information about an uploaded file."""

    original_name: str
    stored_name: str
    path: str
    size: int
    content_type: str | None
    uploaded_at: datetime

    @property
    def as_path(self) -> Path:
        """Get the file path as a Path object."""
        return Path(self.path)
