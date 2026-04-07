"""Pydantic schemas for web API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DimensionsSchema(BaseModel):
    """Schema for screen dimensions."""

    width: int = Field(..., gt=0, description="Width in pixels")
    height: int = Field(..., gt=0, description="Height in pixels")


class DetectionRequestSchema(BaseModel):
    """Schema for detection request."""

    width: int = Field(..., gt=0, description="Image width in pixels")
    height: int = Field(..., gt=0, description="Image height in pixels")


class DetectionResponseSchema(BaseModel):
    """Schema for detection response."""

    detected: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    device_model: str
    device_category: str
    device_family: str
    orientation: str
    scale_factor: int
    detected_dimensions: DimensionsSchema | None = None
    expected_dimensions: DimensionsSchema | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BatchDetectionRequestSchema(BaseModel):
    """Schema for batch detection request."""

    dimensions: list[DimensionsSchema]


class BatchDetectionResponseSchema(BaseModel):
    """Schema for batch detection response."""

    results: list[DetectionResponseSchema]
    total: int
    detected_count: int


class DeviceProfileSchema(BaseModel):
    """Schema for device profile information."""

    profile_id: str
    model_name: str
    display_name: str
    category: str
    family: str
    screen_width_points: int
    screen_height_points: int
    scale_factor: int
    screenshot_width: int
    screenshot_height: int
    aspect_ratio: float


class ProfileListResponseSchema(BaseModel):
    """Schema for profile list response."""

    profiles: list[DeviceProfileSchema]
    total: int
    iphone_count: int
    ipad_count: int


class CategoryCheckRequestSchema(BaseModel):
    """Schema for category check request."""

    width: int = Field(..., gt=0)
    height: int = Field(..., gt=0)


class CategoryCheckResponseSchema(BaseModel):
    """Schema for category check response."""

    category: str
    is_iphone: bool
    is_ipad: bool
    is_valid_ios: bool


class HealthCheckSchema(BaseModel):
    """Schema for health check response."""

    status: str
    version: str
    profiles_loaded: int
