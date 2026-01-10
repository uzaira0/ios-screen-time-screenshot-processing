"""Web service module for iPad screenshot cropper."""

from .main import app
from .routes import router
from .schemas import (
    CropResponse,
    DetectDeviceResponse,
    DeviceInfo,
    DeviceProfileSchema,
    DeviceProfilesResponse,
    ErrorResponse,
    HealthResponse,
    ProcessingCheckResponse,
)

__all__ = [
    "app",
    "router",
    "CropResponse",
    "DetectDeviceResponse",
    "DeviceInfo",
    "DeviceProfileSchema",
    "DeviceProfilesResponse",
    "ErrorResponse",
    "HealthResponse",
    "ProcessingCheckResponse",
]
