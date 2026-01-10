"""Core cropping functionality for iPad screenshots."""

from .callbacks import CancellationCheck, LogCallback, ProgressCallback
from .config import AssetConfig, CropDimensions, CropperConfig, ProcessingConfig
from .cropper import CropResult, ProcessingCheck, ScreenshotCropper
from .device_profiles import (
    DEFAULT_DIMENSION_RULES,
    SUPPORTED_PROFILES,
    DeviceDimensions,
    DeviceModel,
    DeviceProfile,
    DimensionRules,
    detect_device_from_dimensions,
    detect_device_from_width,
    is_already_cropped,
    is_landscape_orientation,
    is_valid_aspect_ratio,
)
from .exceptions import (
    AssetNotFoundError,
    CancellationError,
    ConfigurationError,
    CropperError,
    DeviceDetectionError,
    ImageProcessingError,
)
from .patch import ImagePatcher

__all__ = [
    # Main cropper
    "ScreenshotCropper",
    "CropResult",
    "ProcessingCheck",
    # Device profiles
    "DeviceProfile",
    "DeviceModel",
    "DeviceDimensions",
    "DimensionRules",
    "DEFAULT_DIMENSION_RULES",
    "SUPPORTED_PROFILES",
    "detect_device_from_dimensions",
    "detect_device_from_width",
    "is_already_cropped",
    "is_landscape_orientation",
    "is_valid_aspect_ratio",
    # Configuration
    "CropperConfig",
    "CropDimensions",
    "ProcessingConfig",
    "AssetConfig",
    # Patching
    "ImagePatcher",
    # Callbacks
    "ProgressCallback",
    "CancellationCheck",
    "LogCallback",
    # Exceptions
    "CropperError",
    "ConfigurationError",
    "ImageProcessingError",
    "CancellationError",
    "AssetNotFoundError",
    "DeviceDetectionError",
]
