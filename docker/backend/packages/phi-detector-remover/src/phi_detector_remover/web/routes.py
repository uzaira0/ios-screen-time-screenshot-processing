"""API routes for PHI detection and removal."""

from __future__ import annotations

import time
import uuid
from io import BytesIO

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from phi_detector_remover.core.detector import PHIDetector, PHIRegion
from phi_detector_remover.core.remover import PHIRemover, RedactionMethod
from phi_detector_remover.web.schemas import (
    APIMeta,
    APIResponse,
    BoundingBox,
    ConfigResponse,
    DetectResponse,
    HealthResponse,
    PHIRegionSchema,
    ProcessResponse,
)

router = APIRouter(prefix="/api/v1", tags=["phi"])

# Global instances (in production, use dependency injection)
detector = PHIDetector()


def _region_to_schema(region: PHIRegion) -> PHIRegionSchema:
    """Convert PHIRegion to Pydantic schema."""
    return PHIRegionSchema(
        entity_type=region.entity_type,
        text=region.text,
        score=region.score,
        bbox=BoundingBox(
            x=region.bbox[0],
            y=region.bbox[1],
            width=region.bbox[2],
            height=region.bbox[3],
        ),
        source=region.source,
    )


def _schema_to_region(schema: PHIRegionSchema) -> PHIRegion:
    """Convert Pydantic schema to PHIRegion."""
    return PHIRegion(
        entity_type=schema.entity_type,
        text=schema.text,
        score=schema.score,
        bbox=(schema.bbox.x, schema.bbox.y, schema.bbox.width, schema.bbox.height),
        source=schema.source,
    )


@router.post("/detect", response_model=APIResponse[DetectResponse])
async def detect_phi(file: UploadFile = File(...)) -> APIResponse[DetectResponse]:
    """Detect PHI regions in an uploaded image.

    Args:
        file: Image file (PNG, JPG, etc.)

    Returns:
        List of detected PHI regions with bounding boxes

    Raises:
        HTTPException: If image processing fails
    """
    request_id = str(uuid.uuid4())
    start_time = time.time()

    try:
        # Read image bytes
        image_bytes = await file.read()

        # Detect PHI
        regions = detector.detect_in_image(image_bytes)

        # Convert to schemas
        region_schemas = [_region_to_schema(r) for r in regions]

        processing_time_ms = (time.time() - start_time) * 1000

        return APIResponse(
            success=True,
            data=DetectResponse(
                regions=region_schemas,
                total_regions=len(region_schemas),
                processing_time_ms=processing_time_ms,
            ),
            meta=APIMeta(request_id=request_id),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/remove")
async def remove_phi(
    file: UploadFile = File(...),
    regions: str = Form(...),  # JSON string of regions
    method: str = Form(default="redbox"),
) -> StreamingResponse:
    """Remove PHI from an image given detected regions.

    Args:
        file: Image file (PNG, JPG, etc.)
        regions: JSON array of PHI regions to redact
        method: Redaction method (redbox, blackbox, pixelate)

    Returns:
        Redacted image as PNG

    Raises:
        HTTPException: If image processing fails
    """
    try:
        # Read image bytes
        image_bytes = await file.read()

        # Parse regions JSON
        import json

        regions_data = json.loads(regions)
        region_schemas = [PHIRegionSchema(**r) for r in regions_data]
        region_objects = [_schema_to_region(s) for s in region_schemas]

        # Remove PHI
        remover = PHIRemover(method=method)
        redacted_bytes = remover.remove(image_bytes, region_objects)

        # Return as streaming response
        return StreamingResponse(
            BytesIO(redacted_bytes),
            media_type="image/png",
            headers={
                "Content-Disposition": "attachment; filename=redacted.png",
            },
        )

    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process")
async def process_image(
    file: UploadFile = File(...),
    method: str = Form(default="redbox"),
) -> StreamingResponse:
    """Detect and remove PHI in one call.

    Args:
        file: Image file (PNG, JPG, etc.)
        method: Redaction method (redbox, blackbox, pixelate)

    Returns:
        Redacted image as PNG

    Raises:
        HTTPException: If image processing fails
    """
    try:
        # Read image bytes
        image_bytes = await file.read()

        # Detect PHI
        regions = detector.detect_in_image(image_bytes)

        # Remove PHI
        remover = PHIRemover(method=method)
        redacted_bytes = remover.remove(image_bytes, regions)

        # Return as streaming response
        return StreamingResponse(
            BytesIO(redacted_bytes),
            media_type="image/png",
            headers={
                "Content-Disposition": "attachment; filename=redacted.png",
                "X-Regions-Detected": str(len(regions)),
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint.

    Returns:
        Health status and system checks
    """
    checks = {
        "detector": True,
        "tesseract": False,
        "presidio": True,
    }

    # Check Tesseract
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        checks["tesseract"] = True
    except Exception:
        checks["tesseract"] = False

    status = "healthy" if all(checks.values()) else "unhealthy"

    return HealthResponse(
        status=status,
        checks=checks,
        version="1.0.0",
    )


@router.get("/config", response_model=APIResponse[ConfigResponse])
async def get_config() -> APIResponse[ConfigResponse]:
    """Get current detector configuration.

    Returns:
        Current configuration settings
    """
    request_id = str(uuid.uuid4())

    return APIResponse(
        success=True,
        data=ConfigResponse(
            entities=detector.config.presidio.entities,
            score_threshold=detector.config.presidio.score_threshold,
            redaction_methods=["redbox", "blackbox", "pixelate"],
            ocr_language=detector.config.ocr.language,
            custom_patterns_enabled=detector.config.custom_patterns.enabled,
        ),
        meta=APIMeta(request_id=request_id),
    )
