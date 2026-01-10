"""Pydantic schemas for API requests and responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

# Generic type for response data
T = TypeVar("T")


# === API Envelope ===


class APIError(BaseModel):
    """Standard error response."""

    code: str
    message: str
    details: dict[str, Any] | None = None


class APIMeta(BaseModel):
    """Response metadata."""

    request_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str = "1.0.0"


class APIResponse(BaseModel, Generic[T]):
    """Standard API response envelope."""

    success: bool
    data: T | None = None
    error: APIError | None = None
    meta: APIMeta


# === PHI Detection/Removal ===


class BoundingBox(BaseModel):
    """Bounding box coordinates."""

    x: int = Field(..., ge=0, description="X coordinate (pixels)")
    y: int = Field(..., ge=0, description="Y coordinate (pixels)")
    width: int = Field(..., ge=0, description="Width (pixels)")
    height: int = Field(..., ge=0, description="Height (pixels)")


class PHIRegionSchema(BaseModel):
    """Detected PHI region."""

    entity_type: str = Field(..., description="Type of PHI (e.g., PERSON, EMAIL)")
    text: str = Field(..., description="Detected text")
    score: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    bbox: BoundingBox
    source: str = Field(default="presidio", description="Detection source")


class DetectRequest(BaseModel):
    """Request to detect PHI in an image."""

    # File will be uploaded via multipart/form-data
    # This schema is for documentation only
    pass


class DetectResponse(BaseModel):
    """Response from PHI detection."""

    regions: list[PHIRegionSchema]
    total_regions: int
    processing_time_ms: float


class RemoveRequest(BaseModel):
    """Request to remove PHI from an image."""

    regions: list[PHIRegionSchema] = Field(
        ...,
        description="PHI regions to redact (from detect endpoint)",
    )
    method: Literal["redbox", "blackbox", "pixelate"] = Field(
        default="redbox",
        description="Redaction method",
    )


class RemoveResponse(BaseModel):
    """Response from PHI removal."""

    # Image will be returned as bytes
    # This schema is for documentation only
    regions_redacted: int
    processing_time_ms: float


class ProcessRequest(BaseModel):
    """Request to detect and remove PHI in one call."""

    method: Literal["redbox", "blackbox", "pixelate"] = Field(
        default="redbox",
        description="Redaction method",
    )


class ProcessResponse(BaseModel):
    """Response from PHI processing."""

    # Image will be returned as bytes
    # This schema is for documentation only
    regions_detected: int
    regions_redacted: int
    processing_time_ms: float


# === Health Check ===


class HealthResponse(BaseModel):
    """Health check response."""

    status: Literal["healthy", "unhealthy"]
    checks: dict[str, bool]
    version: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# === Configuration ===


class ConfigResponse(BaseModel):
    """Current detector configuration."""

    entities: list[str]
    score_threshold: float
    redaction_methods: list[str]
    ocr_language: str
    custom_patterns_enabled: bool
