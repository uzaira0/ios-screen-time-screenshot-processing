"""FastAPI routes for iOS device detection."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..core.detector import DeviceDetector
from ..core.exceptions import InvalidDimensionsError
from ..profiles.registry import get_profile_registry
from .schemas import (
    BatchDetectionRequestSchema,
    BatchDetectionResponseSchema,
    CategoryCheckRequestSchema,
    CategoryCheckResponseSchema,
    DetectionRequestSchema,
    DetectionResponseSchema,
    DeviceProfileSchema,
    DimensionsSchema,
    HealthCheckSchema,
    ProfileListResponseSchema,
)

router = APIRouter(prefix="/api/v1", tags=["detection"])

# Shared detector instance
_detector: DeviceDetector | None = None


def get_detector() -> DeviceDetector:
    """Get or create detector instance."""
    global _detector
    if _detector is None:
        _detector = DeviceDetector()
    return _detector


def _result_to_response(result) -> DetectionResponseSchema:
    """Convert DetectionResult to response schema."""
    return DetectionResponseSchema(
        detected=result.detected,
        confidence=result.confidence,
        device_model=result.device_model,
        device_category=result.device_category.value,
        device_family=result.device_family.value,
        orientation=result.orientation.value,
        scale_factor=result.scale_factor,
        detected_dimensions=DimensionsSchema(
            width=result.detected_dimensions.width,
            height=result.detected_dimensions.height,
        )
        if result.detected_dimensions
        else None,
        expected_dimensions=DimensionsSchema(
            width=result.expected_dimensions.width,
            height=result.expected_dimensions.height,
        )
        if result.expected_dimensions
        else None,
        metadata=result.metadata,
    )


@router.get("/health", response_model=HealthCheckSchema)
async def health_check() -> HealthCheckSchema:
    """Check service health."""
    registry = get_profile_registry()
    profiles = list(registry.get_all_profiles())
    return HealthCheckSchema(
        status="healthy",
        version="1.0.0",
        profiles_loaded=len(profiles),
    )


@router.post("/detect", response_model=DetectionResponseSchema)
async def detect_device(request: DetectionRequestSchema) -> DetectionResponseSchema:
    """Detect iOS device from image dimensions."""
    try:
        detector = get_detector()
        result = detector.detect_from_dimensions(request.width, request.height)
        return _result_to_response(result)
    except InvalidDimensionsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/detect/batch", response_model=BatchDetectionResponseSchema)
async def detect_batch(
    request: BatchDetectionRequestSchema,
) -> BatchDetectionResponseSchema:
    """Detect iOS devices for multiple dimension pairs."""
    try:
        detector = get_detector()
        results = []
        detected_count = 0

        for dims in request.dimensions:
            result = detector.detect_from_dimensions(dims.width, dims.height)
            results.append(_result_to_response(result))
            if result.detected:
                detected_count += 1

        return BatchDetectionResponseSchema(
            results=results,
            total=len(results),
            detected_count=detected_count,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/category", response_model=CategoryCheckResponseSchema)
async def check_category(
    request: CategoryCheckRequestSchema,
) -> CategoryCheckResponseSchema:
    """Quick category check for dimensions."""
    try:
        detector = get_detector()
        result = detector.detect_from_dimensions(request.width, request.height)

        return CategoryCheckResponseSchema(
            category=result.device_category.value,
            is_iphone=result.is_iphone,
            is_ipad=result.is_ipad,
            is_valid_ios=result.detected,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profiles", response_model=ProfileListResponseSchema)
async def list_profiles() -> ProfileListResponseSchema:
    """List all supported device profiles."""
    registry = get_profile_registry()

    profiles = []
    iphone_count = 0
    ipad_count = 0

    for profile in registry.get_all_profiles():
        dims = profile.screenshot_dimensions
        profiles.append(
            DeviceProfileSchema(
                profile_id=profile.profile_id,
                model_name=profile.model_name,
                display_name=profile.display_name,
                category=profile.category.value,
                family=profile.family.value,
                screen_width_points=profile.screen_width_points,
                screen_height_points=profile.screen_height_points,
                scale_factor=profile.scale_factor,
                screenshot_width=dims.width,
                screenshot_height=dims.height,
                aspect_ratio=profile.aspect_ratio,
            )
        )

        if profile.category.value == "iphone":
            iphone_count += 1
        elif profile.category.value == "ipad":
            ipad_count += 1

    return ProfileListResponseSchema(
        profiles=profiles,
        total=len(profiles),
        iphone_count=iphone_count,
        ipad_count=ipad_count,
    )


@router.get("/profiles/{profile_id}", response_model=DeviceProfileSchema)
async def get_profile(profile_id: str) -> DeviceProfileSchema:
    """Get a specific device profile."""
    registry = get_profile_registry()
    profile = registry.get_profile(profile_id)

    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile not found: {profile_id}")

    dims = profile.screenshot_dimensions
    return DeviceProfileSchema(
        profile_id=profile.profile_id,
        model_name=profile.model_name,
        display_name=profile.display_name,
        category=profile.category.value,
        family=profile.family.value,
        screen_width_points=profile.screen_width_points,
        screen_height_points=profile.screen_height_points,
        scale_factor=profile.scale_factor,
        screenshot_width=dims.width,
        screenshot_height=dims.height,
        aspect_ratio=profile.aspect_ratio,
    )
