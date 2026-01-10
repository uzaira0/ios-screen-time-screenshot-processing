"""HTTP client for iOS device detection service."""

from .client import (
    DeviceDetectorClient,
    AsyncDeviceDetectorClient,
    DetectionResult,
    DeviceProfile,
)

__all__ = [
    "DeviceDetectorClient",
    "AsyncDeviceDetectorClient",
    "DetectionResult",
    "DeviceProfile",
]
