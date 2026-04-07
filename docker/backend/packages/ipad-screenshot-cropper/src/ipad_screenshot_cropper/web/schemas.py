"""Pydantic schemas for web API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DeviceInfo(BaseModel):
    """Device information."""

    model: str = Field(..., description="Device model name")
    uncropped_width: int = Field(..., description="Expected uncropped width")
    uncropped_height: int = Field(..., description="Expected uncropped height")
    cropped_width: int = Field(..., description="Expected cropped width")
    cropped_height: int = Field(..., description="Expected cropped height")


class CropResponse(BaseModel):
    """Response from crop endpoint."""

    success: bool = Field(..., description="Whether cropping succeeded")
    device: DeviceInfo = Field(..., description="Detected device information")
    was_patched: bool = Field(..., description="Whether image was patched")
    original_dimensions: tuple[int, int] = Field(
        ..., description="Original image dimensions (width, height)"
    )
    cropped_dimensions: tuple[int, int] = Field(
        ..., description="Cropped image dimensions (width, height)"
    )
    message: str | None = Field(None, description="Additional information")


class DetectDeviceResponse(BaseModel):
    """Response from detect-device endpoint."""

    device: DeviceInfo = Field(..., description="Detected device information")
    is_supported: bool = Field(..., description="Whether device is supported")


class ProcessingCheckResponse(BaseModel):
    """Response from should-process endpoint."""

    should_process: bool = Field(..., description="Whether image should be processed")
    reason: str = Field(..., description="Reason for the decision")
    device: DeviceInfo | None = Field(None, description="Detected device (if applicable)")


class DeviceProfileSchema(BaseModel):
    """Device profile information."""

    model: str = Field(..., description="Device model name")
    uncropped_dimensions: tuple[int, int] = Field(
        ..., description="Expected uncropped dimensions (width, height)"
    )
    cropped_dimensions: tuple[int, int] = Field(
        ..., description="Expected cropped dimensions (width, height)"
    )
    crop_region: dict[str, int] = Field(..., description="Crop region coordinates")


class DeviceProfilesResponse(BaseModel):
    """Response from device-profiles endpoint."""

    profiles: list[DeviceProfileSchema] = Field(
        ..., description="List of supported device profiles"
    )
    count: int = Field(..., description="Number of supported profiles")


class HealthResponse(BaseModel):
    """Health check response."""

    status: Literal["healthy", "unhealthy"] = Field(..., description="Service health status")
    version: str = Field(..., description="Service version")
    assets_loaded: bool = Field(..., description="Whether assets are accessible")


class ErrorResponse(BaseModel):
    """Error response."""

    error: str = Field(..., description="Error message")
    detail: str | None = Field(None, description="Additional error details")
