"""FastAPI web service for iOS device detection."""

from .main import create_app, app
from .routes import router
from .schemas import (
    DetectionRequestSchema,
    DetectionResponseSchema,
    DeviceProfileSchema,
)

__all__ = [
    "create_app",
    "app",
    "router",
    "DetectionRequestSchema",
    "DetectionResponseSchema",
    "DeviceProfileSchema",
]
