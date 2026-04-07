"""Core module for iOS device detection."""

from .detector import DeviceDetector
from .types import (
    DetectionResult,
    DeviceCategory,
    DeviceFamily,
    Orientation,
    ScreenDimensions,
)
from .exceptions import (
    DetectionError,
    InvalidDimensionsError,
    ProfileNotFoundError,
)

__all__ = [
    "DeviceDetector",
    "DetectionResult",
    "DeviceCategory",
    "DeviceFamily",
    "Orientation",
    "ScreenDimensions",
    "DetectionError",
    "InvalidDimensionsError",
    "ProfileNotFoundError",
]
