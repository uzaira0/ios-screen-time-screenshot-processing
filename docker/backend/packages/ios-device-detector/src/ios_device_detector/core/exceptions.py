"""Custom exceptions for iOS device detection."""

from __future__ import annotations


class DetectionError(Exception):
    """Base exception for detection errors."""

    pass


class InvalidDimensionsError(DetectionError):
    """Raised when image dimensions are invalid."""

    def __init__(self, width: int, height: int, message: str | None = None) -> None:
        self.width = width
        self.height = height
        msg = message or f"Invalid dimensions: {width}x{height}"
        super().__init__(msg)


class ProfileNotFoundError(DetectionError):
    """Raised when no matching device profile is found."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        super().__init__(f"No device profile found for dimensions: {width}x{height}")


class ImageLoadError(DetectionError):
    """Raised when image cannot be loaded."""

    def __init__(self, filepath: str, cause: Exception | None = None) -> None:
        self.filepath = filepath
        self.cause = cause
        super().__init__(f"Failed to load image: {filepath}")
