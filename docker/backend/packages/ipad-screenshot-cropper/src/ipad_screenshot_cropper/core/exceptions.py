"""Custom exceptions for iPad screenshot cropper."""

from __future__ import annotations


class CropperError(Exception):
    """Base exception for all cropper errors."""

    pass


class ConfigurationError(CropperError):
    """Invalid configuration."""

    pass


class ImageProcessingError(CropperError):
    """Error during image processing."""

    pass


class CancellationError(CropperError):
    """Operation was cancelled by user."""

    pass


class AssetNotFoundError(CropperError):
    """Required asset file not found."""

    pass


class DeviceDetectionError(CropperError):
    """Error detecting device type from image."""

    pass
