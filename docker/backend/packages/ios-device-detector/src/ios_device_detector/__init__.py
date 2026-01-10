"""iOS Device Detector - Detect iOS device models from image dimensions.

This package provides device detection from screenshot dimensions with:
- Comprehensive iPhone and iPad device profiles
- Confidence scoring for matches
- Support for portrait and landscape orientations

Example usage (Library):
    >>> from ios_device_detector import DeviceDetector
    >>>
    >>> detector = DeviceDetector()
    >>> result = detector.detect_from_dimensions(1170, 2532)
    >>> print(f"Device: {result.device_model}, Confidence: {result.confidence:.0%}")

Example usage (Service):
    >>> from ios_device_detector.client import DeviceDetectorClient
    >>>
    >>> with DeviceDetectorClient("http://localhost:8000") as client:
    ...     result = client.detect(width=1170, height=2532)
"""

from .core.detector import DeviceDetector
from .core.types import (
    DetectionResult,
    DeviceCategory,
    DeviceFamily,
    Orientation,
    ScreenDimensions,
)
from .core.exceptions import (
    DetectionError,
    InvalidDimensionsError,
    ProfileNotFoundError,
)
from .profiles.registry import DeviceProfile, get_profile_registry

__version__ = "1.0.0"

__all__ = [
    # Main detector
    "DeviceDetector",
    # Types
    "DetectionResult",
    "DeviceCategory",
    "DeviceFamily",
    "Orientation",
    "ScreenDimensions",
    "DeviceProfile",
    # Registry
    "get_profile_registry",
    # Exceptions
    "DetectionError",
    "InvalidDimensionsError",
    "ProfileNotFoundError",
]
