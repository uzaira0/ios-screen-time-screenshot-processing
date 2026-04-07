"""File validation utilities."""

from __future__ import annotations

from fastapi import HTTPException, UploadFile, status


def validate_content_type(
    file: UploadFile,
    allowed_types: list[str],
) -> None:
    """Validate file content type.

    Args:
        file: Uploaded file
        allowed_types: List of allowed MIME types

    Raises:
        HTTPException: If content type is not allowed
    """
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{file.content_type}' not allowed. Allowed: {allowed_types}",
        )


async def validate_file_size(
    file: UploadFile,
    max_size_bytes: int,
) -> int:
    """Validate file size.

    Args:
        file: Uploaded file
        max_size_bytes: Maximum allowed size in bytes

    Returns:
        Actual file size in bytes

    Raises:
        HTTPException: If file is too large
    """
    # Read file to get size
    content = await file.read()
    size = len(content)

    # Reset file position for later reading
    await file.seek(0)

    if size > max_size_bytes:
        max_mb = max_size_bytes / (1024 * 1024)
        actual_mb = size / (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large: {actual_mb:.1f}MB (max: {max_mb:.1f}MB)",
        )

    return size
