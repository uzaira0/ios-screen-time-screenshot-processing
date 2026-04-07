"""API routes for iPad screenshot cropper service."""

from __future__ import annotations

import io
from typing import Annotated

import cv2
import numpy as np
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from .. import __version__
from ..core import (
    SUPPORTED_PROFILES,
    DeviceModel,
    ImageProcessingError,
    ScreenshotCropper,
)
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

router = APIRouter(prefix="/api/v1")

# Global cropper instance
cropper = ScreenshotCropper()


def _device_to_info(device) -> DeviceInfo:
    """Convert DeviceProfile to DeviceInfo schema."""
    return DeviceInfo(
        model=device.model.value,
        uncropped_width=device.uncropped_dimensions.width,
        uncropped_height=device.uncropped_dimensions.height,
        cropped_width=device.cropped_dimensions.width,
        cropped_height=device.cropped_dimensions.height,
    )


@router.post("/crop", response_model=CropResponse, responses={400: {"model": ErrorResponse}})
async def crop_screenshot(
    file: Annotated[UploadFile, File(description="Screenshot image to crop")],
    return_image: bool = False,
) -> CropResponse | StreamingResponse:
    """Crop an iPad screenshot.

    Args:
        file: Screenshot image file
        return_image: If True, return the cropped image instead of JSON

    Returns:
        CropResponse with cropping results or StreamingResponse with image
    """
    try:
        # Read image
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image file")

        # Crop the screenshot
        result = cropper.crop_screenshot(img)

        if return_image:
            # Encode image to PNG
            success, buffer = cv2.imencode(".png", result.cropped_image)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to encode image")

            return StreamingResponse(
                io.BytesIO(buffer.tobytes()),
                media_type="image/png",
                headers={
                    "X-Device-Model": result.device.model.value,
                    "X-Was-Patched": str(result.was_patched),
                    "X-Original-Dimensions": f"{result.original_dimensions[0]}x{result.original_dimensions[1]}",
                    "X-Cropped-Dimensions": f"{result.cropped_dimensions[0]}x{result.cropped_dimensions[1]}",
                },
            )

        return CropResponse(
            success=True,
            device=_device_to_info(result.device),
            was_patched=result.was_patched,
            original_dimensions=result.original_dimensions,
            cropped_dimensions=result.cropped_dimensions,
            message=f"Successfully cropped {result.device.model.value} screenshot",
        )

    except ImageProcessingError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post(
    "/detect-device", response_model=DetectDeviceResponse, responses={400: {"model": ErrorResponse}}
)
async def detect_device(
    file: Annotated[UploadFile, File(description="Screenshot image to analyze")],
) -> DetectDeviceResponse:
    """Detect device type from screenshot image.

    Args:
        file: Screenshot image file

    Returns:
        DetectDeviceResponse with device information
    """
    try:
        # Read image
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image file")

        # Detect device
        device = cropper.detect_device(img)

        return DetectDeviceResponse(
            device=_device_to_info(device),
            is_supported=device.model != DeviceModel.UNKNOWN,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post(
    "/should-process",
    response_model=ProcessingCheckResponse,
    responses={400: {"model": ErrorResponse}},
)
async def should_process(
    file: Annotated[UploadFile, File(description="Screenshot image to check")],
) -> ProcessingCheckResponse:
    """Check if an image should be processed.

    Args:
        file: Screenshot image file

    Returns:
        ProcessingCheckResponse with decision and reason
    """
    try:
        # Read image
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image file")

        # Check if should process
        check = cropper.should_process_image(img)

        return ProcessingCheckResponse(
            should_process=check.should_process,
            reason=check.reason,
            device=_device_to_info(check.device) if check.device else None,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get("/device-profiles", response_model=DeviceProfilesResponse)
async def get_device_profiles() -> DeviceProfilesResponse:
    """Get list of supported device profiles.

    Returns:
        DeviceProfilesResponse with all supported profiles
    """
    profiles = []
    for profile in SUPPORTED_PROFILES:
        profiles.append(
            DeviceProfileSchema(
                model=profile.model.value,
                uncropped_dimensions=(
                    profile.uncropped_dimensions.width,
                    profile.uncropped_dimensions.height,
                ),
                cropped_dimensions=(
                    profile.cropped_dimensions.width,
                    profile.cropped_dimensions.height,
                ),
                crop_region={
                    "x": profile.crop_x,
                    "y": profile.crop_y,
                    "width": profile.crop_width,
                    "height": profile.crop_height,
                },
            )
        )

    return DeviceProfilesResponse(profiles=profiles, count=len(profiles))


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint.

    Returns:
        HealthResponse with service status
    """
    # Check if assets can be loaded
    assets_loaded = True
    try:
        from ..core.patch import ImagePatcher

        patcher = ImagePatcher()
        _ = patcher._get_asset_path("bottom_patch_image.png")
    except Exception:
        assets_loaded = False

    return HealthResponse(
        status="healthy" if assets_loaded else "unhealthy",
        version=__version__,
        assets_loaded=assets_loaded,
    )
