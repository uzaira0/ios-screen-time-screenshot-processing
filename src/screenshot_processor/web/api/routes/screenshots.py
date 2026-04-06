import asyncio
import base64
import datetime as dt
import hashlib
import logging
import re
import secrets
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, NoReturn

import aiofiles
import cv2
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from fastapi_pagination import PaginatedResponse
from pydantic import BaseModel
from sqlalchemy import String, cast
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.core.generated_constants import PREPROCESSING_STAGES
from screenshot_processor.core.image_utils import convert_dark_mode
from screenshot_processor.web.api.dependencies import CurrentUser, DatabaseSession, get_screenshot_for_update
from screenshot_processor.web.cache import GROUPS_KEY, STATS_KEY, invalidate_stats_and_groups, stats_cache
from screenshot_processor.web.config import get_settings
from screenshot_processor.web.database import (
    EXPORT_CSV_HEADERS,
    AnnotationStatus,
    ApplyPHIRedactionRequest,
    ApplyPHIRedactionResponse,
    BatchItemResult,
    BatchPreprocessRequest,
    BatchPreprocessResponse,
    BatchUploadRequest,
    BatchUploadResponse,
    BrowserUploadItemResult,
    BrowserUploadRequest,
    BrowserUploadResponse,
    ExportRow,
    Group,
    GroupRead,
    InvalidateFromStageRequest,
    ManualCropRequest,
    ManualCropResponse,
    ManualPHIRegionsRequest,
    ManualPHIRegionsResponse,
    NextScreenshotResponse,
    OCRStageRequest,
    PHIDetectionStageRequest,
    PHIRedactionStageRequest,
    PHIRegionRect,
    PHIRegionsResponse,
    PreprocessingDetailsResponse,
    PreprocessingEventLog,
    PreprocessingStageSummary,
    PreprocessingSummary,
    PreprocessRequest,
    ProcessingResultResponse,
    ProcessingStatus,
    ReprocessRequest,
    Screenshot,
    ScreenshotDetail,
    ScreenshotRead,
    ScreenshotUpdate,
    ScreenshotUploadRequest,
    ScreenshotUploadResponse,
    SkipStageRequest,
    StagePreprocessRequest,
    StagePreprocessResponse,
    StageStatus,
    StatsResponse,
    UploadErrorCode,
)
from screenshot_processor.web.rate_limiting import limiter
from screenshot_processor.web.repositories import ScreenshotRepo, ScreenshotRepository
from screenshot_processor.web.services import QueueService, reprocess_screenshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/screenshots", tags=["Screenshots"])


# ============================================================================
# Helper functions
# ============================================================================


async def get_screenshot_or_404(repo: ScreenshotRepository, screenshot_id: int) -> Screenshot:
    """Get screenshot by ID or raise 404."""
    screenshot = await repo.get_by_id(screenshot_id)
    if not screenshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenshot not found")
    return screenshot


async def ensure_ocr_total(screenshot: Screenshot, db: AsyncSession) -> None:
    """Extract and save OCR total if screenshot is missing it."""
    from screenshot_processor.web.services.screenshot_service import ScreenshotService

    await ScreenshotService(db).ensure_ocr_total(screenshot)


async def enrich_screenshot_with_usernames(screenshot: Screenshot, repo: ScreenshotRepository) -> ScreenshotRead:
    """Convert a Screenshot model to ScreenshotRead and populate verified_by_usernames."""
    return await repo.enrich_with_usernames(screenshot)


async def enrich_screenshots_with_usernames(
    screenshots: list[Screenshot], repo: ScreenshotRepository
) -> list[ScreenshotRead]:
    """Convert a list of Screenshot models to ScreenshotRead with verified_by_usernames populated."""
    return await repo.enrich_many_with_usernames(screenshots)


# ============================================================================
# Groups Endpoints (must be before /{screenshot_id} routes to avoid conflicts)
# ============================================================================


@router.get("/groups", response_model=list[GroupRead], tags=["Groups"])
async def list_groups(repo: ScreenshotRepo, _user: CurrentUser):
    """List all groups with screenshot counts by processing_status.

    Results are cached in-memory with a configurable TTL (default 10s).
    """
    cached = stats_cache.get(GROUPS_KEY)
    if cached is not None:
        return cached

    groups = await repo.list_groups()
    stats_cache.set(GROUPS_KEY, groups)
    return groups


@router.get("/groups/{group_id}", response_model=GroupRead, tags=["Groups"])
async def get_group(group_id: str, repo: ScreenshotRepo, _user: CurrentUser):
    """Get a single group by ID with screenshot counts."""
    group = await repo.get_group(group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    return group


@router.get("/next", response_model=NextScreenshotResponse)
async def get_next_screenshot(
    current_user: CurrentUser,
    db: DatabaseSession,
    repo: ScreenshotRepo,
    group: str | None = Query(None, description="Filter by group ID"),
    processing_status: str | None = Query(
        None, description="Filter by processing status (pending, completed, failed, skipped)"
    ),
    browse: bool = Query(False, description="Enable browse mode to view all matching screenshots"),
):
    queue_service = QueueService()
    # Enable browse mode when explicitly filtering by processing_status
    # This allows viewing all screenshots with that status, including verified ones
    browse_mode = browse or processing_status is not None
    screenshot = await queue_service.get_next_screenshot(
        db, current_user.id, group_id=group, processing_status=processing_status, browse_mode=browse_mode
    )

    stats = await queue_service.get_queue_stats(db, current_user.id)

    if not screenshot:
        return NextScreenshotResponse(
            screenshot=None,
            queue_position=0,
            total_remaining=stats["total_remaining"],
            message="No screenshots available in your queue",
        )

    # Auto-extract OCR total if missing
    await ensure_ocr_total(screenshot, db)

    return NextScreenshotResponse(
        screenshot=await enrich_screenshot_with_usernames(screenshot, repo),
        queue_position=1,
        total_remaining=stats["total_remaining"],
        message=None,
    )


@router.get("/disputed", response_model=list[ScreenshotRead])
async def get_disputed_screenshots(current_user: CurrentUser, db: DatabaseSession, repo: ScreenshotRepo):
    queue_service = QueueService()
    screenshots = await queue_service.get_disputed_screenshots(db, current_user.id)

    return await enrich_screenshots_with_usernames(screenshots, repo)


@router.get("/stats", response_model=StatsResponse)
async def get_screenshot_stats(repo: ScreenshotRepo, current_user: CurrentUser):
    """Get screenshot statistics using consolidated queries.

    Results are cached in-memory with a configurable TTL (default 10s,
    set via STATS_CACHE_TTL_SECONDS env var) to avoid 6+ COUNT queries
    on every page load.
    """
    cached = stats_cache.get(STATS_KEY)
    if cached is not None:
        return cached

    stats = await repo.get_stats()

    avg_annotations = stats.total_annotations / stats.total if stats.total > 0 else 0.0

    response = StatsResponse(
        total_screenshots=stats.total,
        pending_screenshots=stats.pending_annotation,
        completed_screenshots=stats.completed_annotation,
        total_annotations=stats.total_annotations,
        screenshots_with_consensus=stats.with_consensus,
        screenshots_with_disagreements=stats.with_disagreements,
        average_annotations_per_screenshot=avg_annotations,
        users_active=stats.users_active,
        auto_processed=stats.auto_processed,
        pending=stats.pending_processing,
        failed=stats.failed,
        skipped=stats.skipped,
    )
    stats_cache.set(STATS_KEY, response)
    return response


@router.get("/list", response_model=PaginatedResponse[ScreenshotRead])
async def list_screenshots_paginated(
    repo: ScreenshotRepo,
    current_user: CurrentUser,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=5000, description="Items per page"),
    group_id: str | None = Query(None, description="Filter by group ID"),
    processing_status: str | None = Query(None, description="Filter by processing status"),
    verified_by_me: bool | None = Query(
        None, description="Filter by current user's verification (True=verified by me, False=not verified by me)"
    ),
    verified_by_others: bool | None = Query(
        None, description="Filter for screenshots verified by others but not current user (True only)"
    ),
    search: str | None = Query(None, description="Search by ID or participant ID"),
    totals_mismatch: bool | None = Query(
        None, description="Filter for screenshots where bar total differs from OCR total (True=mismatch only)"
    ),
    sort_by: str = Query("id", description="Sort field: id, uploaded_at, processing_status"),
    sort_order: str = Query("asc", description="Sort order: asc, desc"),
):
    """List screenshots with comprehensive filtering and pagination."""
    result = await repo.list_with_filters(
        page=page,
        page_size=page_size,
        group_id=group_id,
        processing_status=processing_status,
        verified_by_me=verified_by_me,
        verified_by_others=verified_by_others,
        current_user_id=current_user.id,
        search=search,
        totals_mismatch=totals_mismatch,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return PaginatedResponse(
        items=await repo.enrich_many_with_usernames(result.items),
        total=result.total,
        page=page,
        page_size=page_size,
    )


@router.get("/preprocessing-summary", response_model=PreprocessingSummary)
async def get_preprocessing_summary(
    repo: ScreenshotRepo,
    current_user: CurrentUser,
    group_id: str = Query(..., description="Group ID"),
):
    """Get per-stage counts for a group's preprocessing pipeline."""
    from screenshot_processor.web.services.preprocessing_service import (
        STAGE_ORDER,
        get_stage_counts_from_metadata,
    )

    rows = await repo.get_preprocessing_metadata_by_group(group_id)

    stage_summaries = {}
    for stage in STAGE_ORDER:
        counts = get_stage_counts_from_metadata(rows, stage)
        stage_summaries[stage] = PreprocessingStageSummary(**counts)

    return PreprocessingSummary(total=len(rows), **stage_summaries)


@router.get("/{screenshot_id}", response_model=ScreenshotDetail)
async def get_screenshot(screenshot_id: int, repo: ScreenshotRepo, current_user: CurrentUser):
    screenshot = await get_screenshot_or_404(repo, screenshot_id)

    annotations_count = screenshot.current_annotation_count
    needs_annotations = max(0, screenshot.target_annotations - annotations_count)

    # Check for potential semantic duplicates
    duplicate_info = await repo.find_potential_duplicate(screenshot)

    screenshot_data = await repo.enrich_with_usernames(screenshot)
    screenshot_data.potential_duplicate_of = duplicate_info["id"] if duplicate_info else None
    screenshot_data.duplicate_status = duplicate_info["processing_status"] if duplicate_info else None

    return ScreenshotDetail(
        **screenshot_data.model_dump(),
        annotations_count=annotations_count,
        needs_annotations=needs_annotations,
    )


@router.patch("/{screenshot_id}", response_model=ScreenshotRead)
async def update_screenshot(
    screenshot_id: int,
    update_data: ScreenshotUpdate,
    db: DatabaseSession,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
):
    """
    Update a screenshot's metadata (e.g., extracted_title).
    """
    screenshot = await get_screenshot_or_404(repo, screenshot_id)

    try:
        # Update only provided fields
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(screenshot, field, value)

        await db.commit()
        await db.refresh(screenshot)

        logger.info("Screenshot updated", extra={"screenshot_id": screenshot_id, "username": current_user.username})
        return await enrich_screenshot_with_usernames(screenshot, repo)

    except Exception as e:
        await db.rollback()
        logger.error("Failed to update screenshot", extra={"screenshot_id": screenshot_id, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update screenshot",
        )


# Old /upload endpoint removed - use the main /upload endpoint below which accepts base64 images


@router.get("/", response_model=list[ScreenshotRead])
async def list_screenshots(
    repo: ScreenshotRepo,
    current_user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status: str | None = Query(None),
):
    screenshots = await repo.list_basic(
        annotation_status=status,
        skip=skip,
        limit=limit,
    )

    return [ScreenshotRead.model_validate(s) for s in screenshots]


@router.post("/{screenshot_id}/skip", status_code=status.HTTP_204_NO_CONTENT)
async def skip_screenshot(screenshot_id: int, db: DatabaseSession, repo: ScreenshotRepo, current_user: CurrentUser):
    """
    Skip a screenshot globally by setting processing_status to 'skipped'.
    This moves it to the skipped category visible on the homepage.
    """
    screenshot = await get_screenshot_or_404(repo, screenshot_id)

    old_status = screenshot.processing_status
    logger.info(
        "Screenshot skip requested",
        extra={"screenshot_id": screenshot_id, "username": current_user.username, "status": str(old_status)},
    )

    # Update the global processing status to skipped
    screenshot.processing_status = ProcessingStatus.SKIPPED
    await db.commit()
    await db.refresh(screenshot)
    invalidate_stats_and_groups()

    logger.info(
        "Screenshot skipped",
        extra={
            "screenshot_id": screenshot_id,
            "username": current_user.username,
            "old_status": str(old_status),
            "new_status": str(screenshot.processing_status),
        },
    )


class UnskipResponse(BaseModel):
    """Response for unskip operation."""

    success: bool
    message: str


@router.post("/{screenshot_id}/unskip", response_model=UnskipResponse)
async def unskip_screenshot(screenshot_id: int, db: DatabaseSession, repo: ScreenshotRepo, current_user: CurrentUser):
    """
    Unskip a screenshot by restoring processing_status to 'completed'.
    """
    screenshot = await get_screenshot_or_404(repo, screenshot_id)

    old_status = screenshot.processing_status
    logger.info(
        "Screenshot unskip requested",
        extra={"screenshot_id": screenshot_id, "username": current_user.username, "status": str(old_status)},
    )

    if screenshot.processing_status != ProcessingStatus.SKIPPED:
        logger.warning("Cannot unskip screenshot", extra={"screenshot_id": screenshot_id, "status": str(old_status)})
        return UnskipResponse(success=False, message="Screenshot is not in skipped status")

    # Restore to completed status
    screenshot.processing_status = ProcessingStatus.COMPLETED
    await db.commit()
    await db.refresh(screenshot)
    invalidate_stats_and_groups()
    logger.info(
        "Screenshot unskipped",
        extra={
            "screenshot_id": screenshot_id,
            "username": current_user.username,
            "old_status": str(old_status),
            "new_status": str(screenshot.processing_status),
        },
    )

    return UnskipResponse(success=True, message="Screenshot has been restored to completed status")


@router.post("/{screenshot_id}/soft-delete")
async def soft_delete_screenshot(
    screenshot_id: int,
    db: DatabaseSession,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
):
    """Soft delete a screenshot by setting processing_status to DELETED."""
    screenshot = await get_screenshot_for_update(repo, screenshot_id)

    if screenshot.processing_status == ProcessingStatus.DELETED:
        return {"success": False, "message": "Screenshot is already deleted"}

    previous_status = await repo.soft_delete(screenshot)

    try:
        await db.commit()
        await db.refresh(screenshot)
        invalidate_stats_and_groups()
    except Exception:
        await db.rollback()
        raise

    return {"success": True, "previous_status": previous_status}


@router.post("/{screenshot_id}/restore")
async def restore_screenshot(
    screenshot_id: int,
    db: DatabaseSession,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
):
    """Restore a soft-deleted screenshot to its previous processing_status."""
    screenshot = await get_screenshot_for_update(repo, screenshot_id)

    if screenshot.processing_status != ProcessingStatus.DELETED:
        raise HTTPException(status_code=400, detail="Screenshot is not deleted")

    try:
        restored_status = await repo.restore_from_delete(screenshot)
    except ValueError:
        metadata = screenshot.processing_metadata or {}
        stored = metadata.get("pre_delete_status", "completed")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Stored pre_delete_status '{stored}' is not a valid status",
        )

    try:
        await db.commit()
        await db.refresh(screenshot)
        invalidate_stats_and_groups()
    except Exception:
        await db.rollback()
        raise

    return {"success": True, "restored_status": restored_status}


class VerifyRequest(BaseModel):
    """Optional grid coordinates to save when verifying."""

    grid_upper_left_x: int | None = None
    grid_upper_left_y: int | None = None
    grid_lower_right_x: int | None = None
    grid_lower_right_y: int | None = None


@router.post("/{screenshot_id}/verify", response_model=ScreenshotRead)
async def verify_screenshot(
    screenshot_id: int,
    db: DatabaseSession,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
    request: VerifyRequest | None = None,
):
    """
    Mark a screenshot as verified by the current user.
    This adds the user's ID to the verified_by_user_ids list without removing the screenshot from the queue.
    Optionally saves the current grid coordinates to freeze them at verification time.
    """
    from sqlalchemy.orm.attributes import flag_modified

    logger.info(
        "Screenshot verify requested",
        extra={"screenshot_id": screenshot_id, "user_id": current_user.id, "username": current_user.username},
    )

    # Use row lock to prevent race condition when multiple users verify simultaneously
    screenshot = await get_screenshot_for_update(repo, screenshot_id)

    try:
        # Initialize list if null - make a copy to avoid mutation issues
        old_verified_ids = list(screenshot.verified_by_user_ids or [])
        logger.info(
            "Screenshot current verified_by_user_ids",
            extra={"screenshot_id": screenshot_id, "verified_by_user_ids": old_verified_ids},
        )

        # Add user if not already verified
        if current_user.id not in old_verified_ids:
            new_verified_ids = [*old_verified_ids, current_user.id]
            # Assign a new list to ensure SQLAlchemy detects the change
            screenshot.verified_by_user_ids = new_verified_ids
            flag_modified(screenshot, "verified_by_user_ids")

        # Save grid coordinates if provided (freeze grid at verification time)
        if request:
            if request.grid_upper_left_x is not None:
                screenshot.grid_upper_left_x = request.grid_upper_left_x
            if request.grid_upper_left_y is not None:
                screenshot.grid_upper_left_y = request.grid_upper_left_y
            if request.grid_lower_right_x is not None:
                screenshot.grid_lower_right_x = request.grid_lower_right_x
            if request.grid_lower_right_y is not None:
                screenshot.grid_lower_right_y = request.grid_lower_right_y

        await db.commit()
        await db.refresh(screenshot)
        logger.info(
            "Screenshot verified",
            extra={
                "screenshot_id": screenshot_id,
                "username": current_user.username,
                "old_verified_ids": old_verified_ids,
                "new_verified_ids": screenshot.verified_by_user_ids,
            },
        )

        return await enrich_screenshot_with_usernames(screenshot, repo)

    except Exception as e:
        await db.rollback()
        logger.error("Failed to verify screenshot", extra={"screenshot_id": screenshot_id, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify screenshot",
        )


@router.delete("/{screenshot_id}/verify", response_model=ScreenshotRead)
async def unverify_screenshot(screenshot_id: int, db: DatabaseSession, repo: ScreenshotRepo, current_user: CurrentUser):
    """
    Remove verification mark from a screenshot for the current user.
    """
    from sqlalchemy.orm.attributes import flag_modified

    logger.info(
        "Screenshot unverify requested",
        extra={"screenshot_id": screenshot_id, "user_id": current_user.id, "username": current_user.username},
    )

    # Use row lock to prevent race condition when multiple users unverify simultaneously
    screenshot = await get_screenshot_for_update(repo, screenshot_id)

    try:
        # Remove user from verified list
        old_verified_ids = list(screenshot.verified_by_user_ids or [])
        logger.info(
            "Screenshot current verified_by_user_ids",
            extra={"screenshot_id": screenshot_id, "verified_by_user_ids": old_verified_ids},
        )

        if current_user.id in old_verified_ids:
            new_verified_ids = [uid for uid in old_verified_ids if uid != current_user.id]
            screenshot.verified_by_user_ids = new_verified_ids if new_verified_ids else None
            flag_modified(screenshot, "verified_by_user_ids")  # Tell SQLAlchemy the field changed
            await db.commit()
            await db.refresh(screenshot)
            logger.info(
                "Screenshot unverified",
                extra={
                    "screenshot_id": screenshot_id,
                    "username": current_user.username,
                    "old_verified_ids": old_verified_ids,
                    "new_verified_ids": screenshot.verified_by_user_ids,
                },
            )
        else:
            logger.warning(
                "User not in verified list",
                extra={
                    "screenshot_id": screenshot_id,
                    "user_id": current_user.id,
                    "verified_by_user_ids": old_verified_ids,
                },
            )

        return await enrich_screenshot_with_usernames(screenshot, repo)

    except Exception as e:
        await db.rollback()
        logger.error("Failed to unverify screenshot", extra={"screenshot_id": screenshot_id, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unverify screenshot",
        )


class NavigationResponse(BaseModel):
    """Response for navigation endpoints."""

    screenshot: ScreenshotRead | None
    current_index: int
    total_in_filter: int
    has_next: bool
    has_prev: bool


@router.get("/{screenshot_id}/navigate", response_model=NavigationResponse)
async def get_screenshot_navigation(
    screenshot_id: int,
    db: DatabaseSession,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
    group_id: str | None = Query(None, description="Filter by group ID"),
    processing_status: str | None = Query(None, description="Filter by processing status"),
    verified_by_me: bool | None = Query(
        None, description="Filter by current user's verification (True=verified by me, False=not verified by me)"
    ),
    verified_by_others: bool | None = Query(
        None, description="Filter for screenshots verified by others but not current user (True only)"
    ),
    totals_mismatch: bool | None = Query(
        None, description="Filter for screenshots where bar total differs from OCR total"
    ),
    direction: str = Query("current", description="Direction: current, next, prev"),
):
    """
    Get a screenshot with navigation context within filtered results.
    Returns the current, next, or previous screenshot based on direction.
    """
    from sqlalchemy import and_, literal, or_
    from sqlalchemy.dialects.postgresql import JSONB

    # Build base conditions for the filtered set
    conditions = []
    if group_id:
        conditions.append(Screenshot.group_id == group_id)
    if processing_status:
        conditions.append(Screenshot.processing_status == processing_status)

    # Helper to check if user ID is in verified_by_user_ids array
    # Column is JSON type, need to cast both sides to JSONB for @> operator
    def user_in_verified_list(user_id: int):
        return cast(Screenshot.verified_by_user_ids, JSONB).op("@>")(cast(literal(f"[{user_id}]"), JSONB))

    def has_verifications():
        return and_(
            Screenshot.verified_by_user_ids.isnot(None),
            cast(Screenshot.verified_by_user_ids, String) != "null",
            cast(Screenshot.verified_by_user_ids, String) != "[]",
        )

    # User-specific verified filter
    if verified_by_me is not None:
        if verified_by_me is True:
            conditions.append(user_in_verified_list(current_user.id))
        else:
            conditions.append(
                or_(
                    ~has_verifications(),
                    ~user_in_verified_list(current_user.id),
                )
            )

    # Verified by others filter (verified by someone, but not by current user)
    if verified_by_others is True:
        conditions.append(has_verifications())
        conditions.append(~user_in_verified_list(current_user.id))

    # Totals mismatch filter (server-side)
    if totals_mismatch is True:
        conditions.extend(repo.needs_attention_conditions())

    nav_result = await repo.navigate_with_filters(screenshot_id, direction, conditions)

    if not nav_result.screenshot:
        return NavigationResponse(
            screenshot=None,
            current_index=nav_result.current_index,
            total_in_filter=nav_result.total_in_filter,
            has_next=nav_result.has_next,
            has_prev=nav_result.has_prev,
        )

    # Auto-extract OCR total if missing
    await ensure_ocr_total(nav_result.screenshot, db)

    return NavigationResponse(
        screenshot=await enrich_screenshot_with_usernames(nav_result.screenshot, repo),
        current_index=nav_result.current_index,
        total_in_filter=nav_result.total_in_filter,
        has_next=nav_result.has_next,
        has_prev=nav_result.has_prev,
    )


@router.get("/{screenshot_id}/image")
async def get_screenshot_image(
    screenshot_id: int,
    repo: ScreenshotRepo,
):
    """Serve screenshot image file.

    No auth required — <img> tags can't send X-Username headers.
    The UI itself is auth-gated; images are not sensitive data.
    """
    screenshot = await get_screenshot_or_404(repo, screenshot_id)

    # Path traversal protection: ensure file is within UPLOAD_DIR
    settings = get_settings()
    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    file_path = Path(screenshot.file_path).resolve()

    # Ensure file is within upload directory
    try:
        file_path.relative_to(upload_dir)
    except ValueError:
        # file_path is not relative to upload_dir - path traversal attempt
        logger.warning(
            "Path traversal attempt detected",
            extra={"screenshot_id": screenshot_id, "file_path": screenshot.file_path, "upload_dir": str(upload_dir)},
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image file not found")

    media_type = "image/png"
    if file_path.suffix.lower() in [".jpg", ".jpeg"]:
        media_type = "image/jpeg"
    elif file_path.suffix.lower() == ".gif":
        media_type = "image/gif"

    return FileResponse(file_path, media_type=media_type)


class RecalculateOcrResponse(BaseModel):
    """Response for OCR recalculation."""

    success: bool
    screenshot_id: int | None = None
    extracted_total: str | None = None
    message: str


@router.post("/{screenshot_id}/recalculate-ocr", response_model=RecalculateOcrResponse)
async def recalculate_ocr_total(
    screenshot_id: int, db: DatabaseSession, repo: ScreenshotRepo, current_user: CurrentUser
):
    """
    Recalculate the OCR total for a specific screenshot.
    Re-runs OCR extraction on the original image to get the total usage time.
    """
    screenshot = await get_screenshot_or_404(repo, screenshot_id)

    if screenshot.image_type != "screen_time":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OCR recalculation only applies to screen_time screenshots",
        )

    try:
        file_path = screenshot.file_path
        if not Path(file_path).exists():
            return RecalculateOcrResponse(
                success=False,
                screenshot_id=screenshot_id,
                extracted_total=None,
                message=f"Image file not found at {file_path}",
            )

        # Run CPU-bound OCR in a thread to avoid blocking the event loop
        def _extract_sync():
            img = cv2.imread(file_path)
            if img is None:
                return None
            from screenshot_processor.core.ocr import find_screenshot_total_usage

            img = convert_dark_mode(img)
            total, _ = find_screenshot_total_usage(img)
            return total

        total = await asyncio.to_thread(_extract_sync)
        if total is None:
            return RecalculateOcrResponse(
                success=False,
                screenshot_id=screenshot_id,
                extracted_total=None,
                message="Could not read image file",
            )

        if total and total.strip():
            screenshot.extracted_total = total.strip()
            await db.commit()
            await db.refresh(screenshot)
            logger.info(
                "Recalculated OCR total", extra={"screenshot_id": screenshot_id, "extracted_total": total.strip()}
            )
            return RecalculateOcrResponse(
                success=True,
                screenshot_id=screenshot_id,
                extracted_total=total.strip(),
                message="OCR total recalculated successfully",
            )
        else:
            return RecalculateOcrResponse(
                success=False,
                screenshot_id=screenshot_id,
                extracted_total=None,
                message="No total found in image",
            )

    except Exception as e:
        await db.rollback()
        logger.error("Error recalculating OCR total", extra={"screenshot_id": screenshot_id, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to recalculate OCR total: {e!s}",
        )


@router.get("/{screenshot_id}/processing-result", response_model=ProcessingResultResponse)
async def get_processing_result(screenshot_id: int, repo: ScreenshotRepo, current_user: CurrentUser):
    screenshot = await get_screenshot_or_404(repo, screenshot_id)

    return ProcessingResultResponse(
        success=screenshot.processing_status not in [ProcessingStatus.PENDING, ProcessingStatus.FAILED],
        processing_status=screenshot.processing_status.value,
        extracted_title=screenshot.extracted_title,
        extracted_total=screenshot.extracted_total,
        extracted_hourly_data=screenshot.extracted_hourly_data,
        issues=screenshot.processing_issues or [],
        has_blocking_issues=screenshot.has_blocking_issues,
        is_daily_total=screenshot.processing_status == ProcessingStatus.SKIPPED,
    )


@router.post("/{screenshot_id}/reprocess", response_model=ProcessingResultResponse)
async def reprocess_screenshot_endpoint(
    screenshot_id: int,
    reprocess_request: ReprocessRequest,
    db: DatabaseSession,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
):
    """
    Reprocess a screenshot with optional grid coordinates and processing method.

    Processing methods:
    - If grid coordinates are provided, uses "manual" method
    - If processing_method="line_based", uses visual line detection (no OCR for grid)
    - Otherwise, uses "ocr_anchored" method (finds "12 AM" and "60" text anchors)
    """
    screenshot = await get_screenshot_or_404(repo, screenshot_id)

    grid_coords = None
    if reprocess_request.grid_upper_left_x is not None and reprocess_request.grid_lower_right_x is not None:
        grid_coords = {
            "upper_left_x": reprocess_request.grid_upper_left_x,
            "upper_left_y": reprocess_request.grid_upper_left_y,
            "lower_right_x": reprocess_request.grid_lower_right_x,
            "lower_right_y": reprocess_request.grid_lower_right_y,
        }

    processing_result = await reprocess_screenshot(
        db,
        screenshot,
        grid_coords=grid_coords,
        processing_method=reprocess_request.processing_method,
        current_user_id=current_user.id,
        max_shift=reprocess_request.max_shift,
    )
    invalidate_stats_and_groups()

    # Handle case where processing_result is None (shouldn't happen, but be defensive)
    if processing_result is None:
        processing_result = {
            "success": False,
            "processing_status": "failed",
            "issues": [
                {
                    "issue_type": "processing_error",
                    "severity": "blocking",
                    "description": "Processing returned no result",
                }
            ],
            "has_blocking_issues": True,
        }

    # Extract grid coordinates from result (populated by line-based/ocr detection)
    # or from the screenshot model (after commit in reprocess_screenshot)
    result_grid_coords = processing_result.get("grid_coords") or {}

    return ProcessingResultResponse(
        success=processing_result.get("success", False),
        processing_status=processing_result.get("processing_status", ProcessingStatus.FAILED.value),
        extracted_title=processing_result.get("extracted_title"),
        extracted_total=processing_result.get("extracted_total"),
        extracted_hourly_data=processing_result.get("extracted_hourly_data"),
        issues=processing_result.get("issues", []),
        has_blocking_issues=processing_result.get("has_blocking_issues", False),
        is_daily_total=processing_result.get("is_daily_total", False),
        alignment_score=processing_result.get("alignment_score"),
        processing_method=processing_result.get("processing_method"),
        grid_detection_confidence=processing_result.get("grid_detection_confidence"),
        # Grid coordinates for frontend overlay
        grid_upper_left_x=result_grid_coords.get("upper_left_x") or screenshot.grid_upper_left_x,
        grid_upper_left_y=result_grid_coords.get("upper_left_y") or screenshot.grid_upper_left_y,
        grid_lower_right_x=result_grid_coords.get("lower_right_x") or screenshot.grid_lower_right_x,
        grid_lower_right_y=result_grid_coords.get("lower_right_y") or screenshot.grid_lower_right_y,
    )


# ============================================================================
# API Upload Endpoint (for external sources like Dagster pipelines)
# ============================================================================


def _resolve_image_path(path_str: str) -> Path:
    """Resolve an image path to an absolute path, prepending UPLOAD_DIR if relative."""
    file_path = Path(path_str)
    if not file_path.is_absolute():
        settings = get_settings()
        upload_dir = Path(settings.UPLOAD_DIR)
        # Avoid double-prepending if path already starts with UPLOAD_DIR
        try:
            file_path.relative_to(upload_dir)
        except ValueError:
            file_path = upload_dir / file_path
    return file_path.resolve()


def sanitize_filename(name: str) -> str:
    """Remove path components and dangerous characters from filename."""
    # Extract just the filename, removing any path components
    name = Path(name).name
    # Replace any non-alphanumeric characters (except dash, underscore, and dot) with underscore
    sanitized = re.sub(r"[^\w\-.]", "_", name)
    # Limit length to prevent filesystem issues
    return sanitized[:100]


def _detect_device_type(width: int, height: int) -> str:
    """Detect device type from image dimensions.

    Uses ios-device-detector package if available for richer detection,
    falls back to simple aspect ratio heuristic.
    """
    try:
        from ios_device_detector import DeviceDetector  # pyright: ignore[reportMissingImports]

        detector = DeviceDetector()
        result = detector.detect_from_dimensions(width, height)
        if result.detected:
            if result.is_ipad:
                return "ipad"
            elif result.is_iphone:
                return "iphone"
    except Exception as e:
        logger.debug(
            "Device detection via ios_device_detector failed, using heuristic fallback", extra={"error": str(e)}
        )

    # Fallback: simple aspect ratio heuristic
    aspect_ratio = height / width if width > 0 else 0

    if aspect_ratio > 2.0:
        return "iphone_modern"  # iPhone X and later (19.5:9)
    elif aspect_ratio > 1.7:
        return "iphone_legacy"  # iPhone 8 and earlier (16:9)
    elif aspect_ratio < 1.5:
        return "ipad"
    else:
        return "unknown"


def _get_image_dimensions(image_data: bytes) -> tuple[int, int]:
    """Get image dimensions from binary data."""
    # PNG signature check
    if image_data[:8] == b"\x89PNG\r\n\x1a\n":
        # PNG: width and height are at bytes 16-24
        width = int.from_bytes(image_data[16:20], "big")
        height = int.from_bytes(image_data[20:24], "big")
        return width, height

    # JPEG signature check
    if image_data[:2] == b"\xff\xd8":
        # JPEG: need to parse markers to find SOF
        i = 2
        while i < len(image_data) - 9:
            if image_data[i] != 0xFF:
                i += 1
                continue
            marker = image_data[i + 1]
            # SOF markers (0xC0-0xCF except 0xC4, 0xC8, 0xCC)
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                height = int.from_bytes(image_data[i + 5 : i + 7], "big")
                width = int.from_bytes(image_data[i + 7 : i + 9], "big")
                return width, height
            # Skip to next marker
            length = int.from_bytes(image_data[i + 2 : i + 4], "big")
            i += 2 + length

    return 0, 0


def _raise_upload_error(
    error_code: "UploadErrorCode",
    detail: str,
    screenshot_index: int | None = None,
) -> NoReturn:
    """Raise an HTTPException with structured upload error response."""
    from screenshot_processor.web.database import UploadErrorCode, UploadErrorResponse

    error_response = UploadErrorResponse(
        error_code=error_code,
        detail=detail,
        screenshot_index=screenshot_index,
    )

    status_map = {
        UploadErrorCode.INVALID_API_KEY: status.HTTP_401_UNAUTHORIZED,
        UploadErrorCode.INVALID_BASE64: status.HTTP_400_BAD_REQUEST,
        UploadErrorCode.UNSUPPORTED_FORMAT: status.HTTP_400_BAD_REQUEST,
        UploadErrorCode.IMAGE_TOO_LARGE: status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        UploadErrorCode.CHECKSUM_MISMATCH: status.HTTP_400_BAD_REQUEST,
        UploadErrorCode.INVALID_CALLBACK_URL: status.HTTP_400_BAD_REQUEST,
        UploadErrorCode.BATCH_TOO_LARGE: status.HTTP_400_BAD_REQUEST,
        UploadErrorCode.RATE_LIMITED: status.HTTP_429_TOO_MANY_REQUESTS,
        UploadErrorCode.STORAGE_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
        UploadErrorCode.DATABASE_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
    }

    raise HTTPException(
        status_code=status_map.get(error_code, status.HTTP_500_INTERNAL_SERVER_ERROR),
        detail=error_response.model_dump(),
    )


def _decode_and_validate_image(
    screenshot_b64: str,
    expected_sha256: str | None = None,
) -> tuple[bytes, str, tuple[int, int]]:
    """Decode base64 image and validate format/checksum.

    Returns:
        Tuple of (image_data, extension, (width, height))

    Raises:
        HTTPException with structured error on failure
    """
    from screenshot_processor.web.database import UploadErrorCode

    # Decode base64
    try:
        if screenshot_b64.startswith("data:"):
            _, encoded = screenshot_b64.split(",", 1)
        else:
            encoded = screenshot_b64
        image_data = base64.b64decode(encoded)
    except Exception as e:
        _raise_upload_error(UploadErrorCode.INVALID_BASE64, f"Invalid base64 image data: {e}")

    # Verify SHA256 checksum if provided
    if expected_sha256:
        actual_sha256 = hashlib.sha256(image_data).hexdigest()
        if actual_sha256.lower() != expected_sha256.lower():
            _raise_upload_error(
                UploadErrorCode.CHECKSUM_MISMATCH,
                f"SHA256 mismatch: expected {expected_sha256}, got {actual_sha256}",
            )

    # Detect image format
    if image_data[:8] == b"\x89PNG\r\n\x1a\n":
        extension = ".png"
    elif image_data[:2] == b"\xff\xd8":
        extension = ".jpg"
    else:
        _raise_upload_error(
            UploadErrorCode.UNSUPPORTED_FORMAT,
            "Unsupported image format. Only PNG and JPEG are supported.",
        )

    # Get dimensions
    width, height = _get_image_dimensions(image_data)

    return image_data, extension, (width, height)


def _validate_callback_url(callback_url: str | None) -> None:
    """Validate callback URL format if provided."""
    from screenshot_processor.web.database import UploadErrorCode

    if callback_url:
        from urllib.parse import urlparse

        try:
            parsed = urlparse(callback_url)
            if parsed.scheme not in ("http", "https"):
                _raise_upload_error(
                    UploadErrorCode.INVALID_CALLBACK_URL,
                    "Callback URL must use http or https scheme",
                )
            if not parsed.netloc:
                _raise_upload_error(
                    UploadErrorCode.INVALID_CALLBACK_URL,
                    "Callback URL must have a valid host",
                )
        except Exception as e:
            _raise_upload_error(
                UploadErrorCode.INVALID_CALLBACK_URL,
                f"Invalid callback URL: {e}",
            )


@dataclass
class UploadContext:
    """Metadata for a single screenshot upload — reduces parameter count."""

    participant_id: str
    group_id: str
    image_type: str
    device_type: str | None = None
    filename: str | None = None
    source_id: str | None = None
    original_filepath: str | None = None
    screenshot_date: dt.datetime | None = None
    callback_url: str | None = None
    idempotency_key: str | None = None
    group_created: bool = False
    preprocess: bool = False


async def _process_single_upload(
    db: AsyncSession,
    repo: ScreenshotRepository,
    image_data: bytes,
    extension: str,
    dimensions: tuple[int, int],
    ctx: UploadContext,
) -> ScreenshotUploadResponse:
    """Process a single screenshot upload and return response with full metadata."""
    import time

    from screenshot_processor.web.database import UploadErrorCode

    timings = {}
    t0 = time.perf_counter()

    width, height = dimensions

    # Auto-detect device type if not provided
    detected_device_type = ctx.device_type
    if not detected_device_type and width > 0 and height > 0:
        detected_device_type = _detect_device_type(width, height)

    # Generate unique filename and content hash for dedup
    # Single blake2b call: truncate for filename, full for dedup
    t1 = time.perf_counter()
    content_hash = hashlib.blake2b(image_data, digest_size=32).hexdigest()
    file_hash = content_hash[:12]
    timings["hash"] = (time.perf_counter() - t1) * 1000

    # Content-hash dedup check
    existing = await repo.find_by_content_hash(content_hash)
    if existing:
        return ScreenshotUploadResponse(
            success=True,
            screenshot_id=existing.id,
            duplicate=True,
            message="Duplicate image detected",
        )

    if ctx.filename:
        safe_filename = sanitize_filename(ctx.filename)
        base_name = Path(safe_filename).stem
        final_filename = f"{ctx.group_id}/{ctx.participant_id}/{base_name}_{file_hash}{extension}"
    else:
        unique_id = str(uuid.uuid4())[:8]
        final_filename = f"{ctx.group_id}/{ctx.participant_id}/{unique_id}_{file_hash}{extension}"

    # Ensure upload directory exists
    settings = get_settings()
    upload_dir = Path(settings.UPLOAD_DIR)
    file_path = upload_dir / final_filename
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Save image file (async for non-blocking I/O)
    t1 = time.perf_counter()
    try:
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(image_data)
    except Exception as e:
        _raise_upload_error(UploadErrorCode.STORAGE_ERROR, f"Failed to save image: {e}")
    timings["file_write"] = (time.perf_counter() - t1) * 1000

    # Create screenshot record (database-agnostic: check-then-insert/update)
    t1 = time.perf_counter()

    is_duplicate = False
    try:
        # Check for existing screenshot with same file_path
        existing_screenshot = await repo.find_by_file_path(str(file_path))

        if existing_screenshot:
            # Update existing record (equivalent to ON CONFLICT DO UPDATE)
            existing_screenshot.processing_status = ProcessingStatus.PENDING
            existing_screenshot.processing_method = None
            existing_screenshot.extracted_title = None
            existing_screenshot.extracted_total = None
            existing_screenshot.extracted_hourly_data = None
            existing_screenshot.grid_upper_left_x = None
            existing_screenshot.grid_upper_left_y = None
            existing_screenshot.grid_lower_right_x = None
            existing_screenshot.grid_lower_right_y = None
            existing_screenshot.device_type = detected_device_type
            existing_screenshot.original_filepath = ctx.original_filepath
            existing_screenshot.screenshot_date = ctx.screenshot_date
            existing_screenshot.processing_metadata = (
                {"callback_url": ctx.callback_url, "reprocessed": True} if ctx.callback_url else {"reprocessed": True}
            )
            screenshot_id = existing_screenshot.id
            is_duplicate = True

            # Clear ALL existing data for fresh start
            await repo.clear_screenshot_related_data([screenshot_id])
            await repo.reset_screenshot_state([screenshot_id])
            logger.info("Duplicate upload: cleared all data, reprocessing", extra={"screenshot_id": screenshot_id})
        else:
            # Insert new screenshot
            new_screenshot = Screenshot(
                file_path=str(file_path),
                image_type=ctx.image_type,
                target_annotations=1,
                annotation_status=AnnotationStatus.PENDING,
                processing_status=ProcessingStatus.PENDING,
                current_annotation_count=0,
                participant_id=ctx.participant_id,
                group_id=ctx.group_id,
                source_id=ctx.source_id,
                device_type=detected_device_type,
                original_filepath=ctx.original_filepath,
                screenshot_date=ctx.screenshot_date,
                processing_metadata={"callback_url": ctx.callback_url} if ctx.callback_url else None,
                content_hash=content_hash,
            )
            db.add(new_screenshot)
            await db.flush()
            screenshot_id = new_screenshot.id

        await db.commit()
        invalidate_stats_and_groups()
    except Exception as e:
        await db.rollback()
        # Clean up saved file
        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            pass  # Best-effort cleanup: DB insert failed, don't mask original error
        _raise_upload_error(UploadErrorCode.DATABASE_ERROR, f"Failed to create screenshot record: {e}")
    timings["db_insert"] = (time.perf_counter() - t1) * 1000

    # Queue background processing via Celery (fire and forget)
    t1 = time.perf_counter()
    processing_queued = False
    preprocessing_queued = False
    try:
        if ctx.preprocess:
            from screenshot_processor.web.tasks import preprocess_screenshot_task

            preprocess_screenshot_task.delay(screenshot_id)  # type: ignore[attr-defined]
            preprocessing_queued = True
            processing_queued = True  # preprocessing chains into OCR processing
        else:
            from screenshot_processor.web.tasks import process_screenshot_task

            process_screenshot_task.delay(screenshot_id)  # type: ignore[attr-defined]
            processing_queued = True
    except Exception as e:
        # processing_queued is already False from line 1315, but be explicit
        processing_queued = False
        logger.error("Failed to queue processing", extra={"screenshot_id": screenshot_id, "error": str(e)})
    timings["celery_queue"] = (time.perf_counter() - t1) * 1000

    total_ms = (time.perf_counter() - t0) * 1000
    if total_ms > 100:  # Log slow uploads at INFO level
        logger.info(
            f"Slow upload {screenshot_id}: total={total_ms:.1f}ms "
            f"(file={timings.get('file_write', 0):.1f}ms db={timings.get('db_insert', 0):.1f}ms)"
        )
    else:
        logger.debug(
            f"Upload {screenshot_id} timing: total={total_ms:.1f}ms "
            f"hash={timings.get('hash', 0):.1f}ms "
            f"file={timings.get('file_write', 0):.1f}ms db={timings.get('db_insert', 0):.1f}ms "
            f"celery={timings.get('celery_queue', 0):.1f}ms"
        )

    return ScreenshotUploadResponse(
        success=True,
        screenshot_id=screenshot_id,
        group_created=ctx.group_created,
        message="Duplicate replaced and requeued for processing" if is_duplicate else None,
        duplicate=is_duplicate,
        file_path=str(file_path),
        file_size_bytes=len(image_data),
        image_dimensions=(width, height) if width > 0 else None,
        device_type_detected=detected_device_type,
        processing_queued=processing_queued,
        preprocessing_queued=preprocessing_queued,
        idempotency_key=ctx.idempotency_key,
    )


@router.post("/upload", response_model=ScreenshotUploadResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(lambda: get_settings().RATE_LIMIT_UPLOAD)
async def upload_screenshot(
    request: Request,
    upload_request: Annotated[ScreenshotUploadRequest, Body()],
    db: DatabaseSession,
    repo: ScreenshotRepo,
    api_key: str = Header(..., alias="X-API-Key", description="API key for upload authorization"),
):
    """
    Upload a screenshot with base64-encoded image data.

    Features:
    - Base64-encoded PNG/JPEG images (max 100 MB)
    - Auto-detection of device type from image dimensions
    - SHA256 checksum verification (optional)
    - Idempotency key for safe retries
    - Callback URL for webhook notifications when processing completes
    - Groups auto-created if they don't exist
    - Duplicate detection by file hash

    Rate limit: 180 requests/minute

    Headers:
        X-API-Key: API key for authorization

    Returns:
        Extended metadata including file path, dimensions, and processing status
    """
    from screenshot_processor.web.database import UploadErrorCode

    settings = get_settings()

    # Validate API key
    if not secrets.compare_digest(api_key.encode(), settings.UPLOAD_API_KEY.encode()):
        _raise_upload_error(UploadErrorCode.INVALID_API_KEY, "Invalid API key")

    # Validate callback URL if provided
    _validate_callback_url(upload_request.callback_url)

    logger.info(
        f"Upload request: group={upload_request.group_id}, participant={upload_request.participant_id}, "
        f"idempotency_key={upload_request.idempotency_key}"
    )

    # Decode and validate image
    image_data, extension, dimensions = _decode_and_validate_image(
        upload_request.screenshot,
        upload_request.sha256,
    )

    # Check/create group - database-agnostic approach
    group_created = False
    existing_group = await repo.get_group_by_id(upload_request.group_id)
    if existing_group is None:
        db.add(
            Group(
                id=upload_request.group_id,
                name=upload_request.group_id,
                image_type=upload_request.image_type,
            )
        )
        try:
            await db.flush()
            group_created = True
        except Exception:
            # Concurrent insert created the group first — safe to continue
            await db.rollback()
            group_created = False

    # Process the upload
    return await _process_single_upload(
        db=db,
        repo=repo,
        image_data=image_data,
        extension=extension,
        dimensions=dimensions,
        ctx=UploadContext(
            participant_id=upload_request.participant_id,
            group_id=upload_request.group_id,
            image_type=upload_request.image_type,
            device_type=upload_request.device_type,
            filename=upload_request.filename,
            source_id=upload_request.source_id,
            original_filepath=upload_request.original_filepath,
            screenshot_date=upload_request.screenshot_date,
            callback_url=upload_request.callback_url,
            idempotency_key=upload_request.idempotency_key,
            group_created=group_created,
            preprocess=upload_request.preprocess,
        ),
    )


@router.post("/upload/batch", response_model=BatchUploadResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(lambda: get_settings().RATE_LIMIT_BATCH_UPLOAD)
async def upload_screenshots_batch(
    request: Request,
    batch_request: Annotated[BatchUploadRequest, Body()],
    db: DatabaseSession,
    repo: ScreenshotRepo,
    api_key: str = Header(..., alias="X-API-Key", description="API key for upload authorization"),
):
    """
    Upload multiple screenshots in a single request.

    Features:
    - Upload up to 60 screenshots per batch
    - All screenshots share the same group_id and image_type
    - Individual SHA256 checksum verification per image
    - Partial success handling - failed items don't block successful ones
    - Callback URL for webhook notification when batch processing completes

    Rate limit: 30 batches/minute (separate from single upload limit)

    Headers:
        X-API-Key: API key for authorization

    Returns:
        Summary of batch results with individual item status
    """
    settings = get_settings()

    # Validate API key
    if not secrets.compare_digest(api_key.encode(), settings.UPLOAD_API_KEY.encode()):
        _raise_upload_error(UploadErrorCode.INVALID_API_KEY, "Invalid API key")

    # Validate callback URL if provided
    _validate_callback_url(batch_request.callback_url)

    logger.info(
        f"Batch upload request: group={batch_request.group_id}, count={len(batch_request.screenshots)}, "
        f"idempotency_key={batch_request.idempotency_key}"
    )

    # Check/create group - must commit before parallel tasks start
    # because each parallel task has its own session and won't see uncommitted changes
    group_created = await repo.upsert_group(batch_request.group_id, batch_request.image_type)
    await db.commit()  # Commit so parallel tasks can see the group

    # Optimized batch processing:
    # 1. Decode/validate all images in parallel
    # 2. Write all files in parallel
    # 3. Single bulk INSERT for all screenshots
    # 4. Queue Celery tasks in bulk
    import time

    t_start = time.perf_counter()
    timings = {}

    settings = get_settings()
    upload_dir = Path(settings.UPLOAD_DIR)

    # Phase 1: Decode and validate all images in parallel
    t1 = time.perf_counter()

    async def decode_item(idx: int, item):
        try:
            image_data, extension, dimensions = _decode_and_validate_image(
                item.screenshot,
                item.sha256,
            )
            return idx, image_data, extension, dimensions, None
        except HTTPException as e:
            return idx, None, None, None, e
        except Exception as e:
            return idx, None, None, None, e

    decode_results = await asyncio.gather(
        *[decode_item(idx, item) for idx, item in enumerate(batch_request.screenshots)]
    )
    timings["decode"] = (time.perf_counter() - t1) * 1000

    # Separate successful decodes from failures
    decoded_items: list[dict] = []
    results: list[BatchItemResult | None] = [None] * len(batch_request.screenshots)

    for idx, image_data, extension, dimensions, error in decode_results:
        if error:
            if isinstance(error, HTTPException):
                error_detail = error.detail if isinstance(error.detail, dict) else {"detail": str(error.detail)}
                raw_error_code = error_detail.get("error_code")
                # Convert string error code to enum if present
                error_code_enum = UploadErrorCode(raw_error_code) if raw_error_code else None
                results[idx] = BatchItemResult(
                    index=idx,
                    success=False,
                    error_code=error_code_enum,
                    error_detail=error_detail.get("detail", str(error.detail)),
                )
            else:
                results[idx] = BatchItemResult(
                    index=idx,
                    success=False,
                    error_code=UploadErrorCode.STORAGE_ERROR,
                    error_detail=str(error),
                )
        else:
            # No error means all values are valid (not None)
            assert image_data is not None
            assert extension is not None
            assert dimensions is not None
            item = batch_request.screenshots[idx]
            width, height = dimensions
            detected_device_type = batch_request.device_type
            if not detected_device_type and width > 0 and height > 0:
                detected_device_type = _detect_device_type(width, height)

            # Generate file path (truncate content hash for filename)
            content_hash = hashlib.blake2b(image_data, digest_size=32).hexdigest()
            file_hash = content_hash[:12]
            if item.filename:
                safe_filename = sanitize_filename(item.filename)
                base_name = Path(safe_filename).stem
                final_filename = f"{batch_request.group_id}/{item.participant_id}/{base_name}_{file_hash}{extension}"
            else:
                unique_id = str(uuid.uuid4())[:8]
                final_filename = f"{batch_request.group_id}/{item.participant_id}/{unique_id}_{file_hash}{extension}"

            file_path = upload_dir / final_filename
            decoded_items.append(
                {
                    "idx": idx,
                    "image_data": image_data,
                    "file_path": file_path,
                    "participant_id": item.participant_id,
                    "source_id": item.source_id,
                    "original_filepath": item.original_filepath,
                    "screenshot_date": item.screenshot_date,
                    "device_type": detected_device_type,
                    "content_hash": content_hash,
                }
            )

    # Content-hash dedup: check which content hashes already exist
    content_hashes = [item["content_hash"] for item in decoded_items]
    existing_hash_map = await repo.find_existing_by_content_hashes(content_hashes)

    # Filter out content-hash duplicates
    non_dup_items = []
    for item_data in decoded_items:
        ch = item_data["content_hash"]
        if ch in existing_hash_map:
            results[item_data["idx"]] = BatchItemResult(
                index=item_data["idx"],
                success=True,
                screenshot_id=existing_hash_map[ch],
                duplicate=True,
            )
        else:
            non_dup_items.append(item_data)
    decoded_items = non_dup_items

    # Phase 2: Write all files in parallel
    t1 = time.perf_counter()

    async def write_file(item_data):
        file_path = item_data["file_path"]
        file_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(item_data["image_data"])
            return item_data["idx"], True, None
        except Exception as e:
            return item_data["idx"], False, str(e)

    write_results = await asyncio.gather(*[write_file(item) for item in decoded_items])
    timings["file_write"] = (time.perf_counter() - t1) * 1000

    # Filter out write failures
    items_to_insert = []
    for idx, success, error in write_results:
        if not success:
            results[idx] = BatchItemResult(
                index=idx,
                success=False,
                error_code=UploadErrorCode.STORAGE_ERROR,
                error_detail=error,
            )
        else:
            # Find the decoded item data
            item_data = next(d for d in decoded_items if d["idx"] == idx)
            items_to_insert.append(item_data)

    # Phase 3: Bulk INSERT all screenshots
    t1 = time.perf_counter()
    inserted_ids = {}
    duplicate_paths: set[str] = set()

    if items_to_insert:
        # Check which paths already exist (for duplicate detection)
        all_paths = [str(item["file_path"]) for item in items_to_insert]
        duplicate_paths = await repo.find_existing_file_paths(all_paths)
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        values = [
            {
                "file_path": str(item["file_path"]),
                "image_type": batch_request.image_type,
                "target_annotations": 1,
                "annotation_status": AnnotationStatus.PENDING,
                "processing_status": ProcessingStatus.PENDING,
                "current_annotation_count": 0,
                "participant_id": item["participant_id"],
                "group_id": batch_request.group_id,
                "source_id": item["source_id"],
                "device_type": item["device_type"],
                "original_filepath": item["original_filepath"],
                "screenshot_date": item["screenshot_date"],
                "content_hash": item["content_hash"],
            }
            for item in items_to_insert
        ]

        # Bulk upsert: ON CONFLICT DO UPDATE to reset and reprocess duplicates
        insert_stmt = (
            pg_insert(Screenshot)
            .values(values)
            .on_conflict_do_update(
                index_elements=["file_path"],
                set_={
                    "processing_status": ProcessingStatus.PENDING,
                    "processing_method": None,
                    "extracted_title": None,
                    "extracted_total": None,
                    "extracted_hourly_data": None,
                    "grid_upper_left_x": None,
                    "grid_upper_left_y": None,
                    "grid_lower_right_x": None,
                    "grid_lower_right_y": None,
                    "processing_metadata": None,
                    "annotation_status": AnnotationStatus.PENDING,
                    "current_annotation_count": 0,
                },
            )
            .returning(Screenshot.id, Screenshot.file_path)
        )

        try:
            result = await db.execute(insert_stmt)
            rows = result.fetchall()

            # Map file_path to id
            for row in rows:
                inserted_ids[row.file_path] = row.id

            # Clear all data for duplicates
            if duplicate_paths:
                dup_ids = [inserted_ids[fp] for fp in duplicate_paths]

                await repo.clear_screenshot_related_data(dup_ids)
                await repo.reset_screenshot_state(dup_ids)
                logger.info(
                    "Batch upload: cleared all data for duplicates, reprocessing",
                    extra={"duplicate_count": len(dup_ids)},
                )

            await db.commit()
            invalidate_stats_and_groups()

        except Exception as e:
            await db.rollback()
            # Mark all as failed
            for item in items_to_insert:
                results[item["idx"]] = BatchItemResult(
                    index=item["idx"],
                    success=False,
                    error_code=UploadErrorCode.DATABASE_ERROR,
                    error_detail=str(e),
                )
            items_to_insert = []

    timings["db_insert"] = (time.perf_counter() - t1) * 1000

    # Phase 4: Queue Celery tasks and build results
    t1 = time.perf_counter()
    screenshot_ids_to_queue = []

    for item in items_to_insert:
        idx = item["idx"]
        fp = str(item["file_path"])
        screenshot_id = inserted_ids.get(fp)
        is_duplicate = fp in duplicate_paths

        if screenshot_id:
            results[idx] = BatchItemResult(
                index=idx,
                success=True,
                screenshot_id=screenshot_id,
                duplicate=is_duplicate,
            )
            # Queue ALL screenshots for processing (including duplicates which are now reset)
            screenshot_ids_to_queue.append(screenshot_id)

    # Queue all Celery tasks at once using group for efficiency
    if screenshot_ids_to_queue:
        try:
            from celery import group

            if batch_request.preprocess:
                from screenshot_processor.web.tasks import preprocess_screenshot_task

                task_group = group(
                    preprocess_screenshot_task.s(sid)
                    for sid in screenshot_ids_to_queue  # type: ignore[attr-defined]
                )
            else:
                from screenshot_processor.web.tasks import process_screenshot_task

                task_group = group(
                    process_screenshot_task.s(sid)
                    for sid in screenshot_ids_to_queue  # type: ignore[attr-defined]
                )
            task_group.apply_async()
        except Exception as e:
            logger.error("Failed to queue processing tasks for batch upload", extra={"error": str(e)})

    timings["celery_queue"] = (time.perf_counter() - t1) * 1000

    total_ms = (time.perf_counter() - t_start) * 1000
    logger.info(
        f"Batch upload timing: total={total_ms:.1f}ms "
        f"decode={timings.get('decode', 0):.1f}ms file={timings.get('file_write', 0):.1f}ms "
        f"db={timings.get('db_insert', 0):.1f}ms celery={timings.get('celery_queue', 0):.1f}ms"
    )

    # Count results (filter out None values first)
    valid_results = [r for r in results if r is not None]
    successful_count = sum(1 for r in valid_results if r.success and not r.duplicate)
    duplicate_count = sum(1 for r in valid_results if r.success and r.duplicate)
    failed_count = sum(1 for r in valid_results if not r.success)

    logger.info(
        f"Batch upload completed: group={batch_request.group_id}, "
        f"success={successful_count}, failed={failed_count}, duplicates={duplicate_count}"
    )

    return BatchUploadResponse(
        success=failed_count == 0,
        total_count=len(batch_request.screenshots),
        successful_count=successful_count,
        failed_count=failed_count,
        duplicate_count=duplicate_count,
        group_created=group_created,
        results=valid_results,  # Already filtered for None
        idempotency_key=batch_request.idempotency_key,
    )


# ============================================================================
# Preprocessing Endpoints
# ============================================================================


@router.get("/{screenshot_id}/preprocessing", response_model=PreprocessingDetailsResponse)
async def get_preprocessing_details(screenshot_id: int, repo: ScreenshotRepo, current_user: CurrentUser):
    """Get preprocessing details for a screenshot from its processing_metadata."""
    screenshot = await get_screenshot_or_404(repo, screenshot_id)

    metadata = screenshot.processing_metadata or {}
    preprocessing = metadata.get("preprocessing")

    if not preprocessing:
        return PreprocessingDetailsResponse(has_preprocessing=False)

    return PreprocessingDetailsResponse(
        has_preprocessing=True,
        device_detection=preprocessing.get("device_detection"),
        cropping=preprocessing.get("cropping"),
        phi_detection=preprocessing.get("phi_detection"),
        phi_redaction=preprocessing.get("phi_redaction"),
        preprocessing_timestamp=preprocessing.get("preprocessing_timestamp"),
        original_file_path=preprocessing.get("original_file_path"),
        preprocessed_file_path=preprocessing.get("preprocessed_file_path"),
        skip_reason=preprocessing.get("skip_reason"),
    )


@router.post("/{screenshot_id}/preprocess", response_model=BatchPreprocessResponse)
async def preprocess_screenshot(
    screenshot_id: int,
    preprocess_request: PreprocessRequest,
    db: DatabaseSession,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
):
    """Queue preprocessing task for a single screenshot."""
    # Verify screenshot exists — concurrent preprocessing is guarded by NOWAIT locks in the Celery task
    await get_screenshot_or_404(repo, screenshot_id)

    try:
        from screenshot_processor.web.tasks import preprocess_screenshot_task

        preprocess_screenshot_task.delay(
            screenshot_id,
            phi_pipeline_preset=preprocess_request.phi_pipeline_preset,
            phi_redaction_method=preprocess_request.phi_redaction_method,
            phi_detection_enabled=preprocess_request.phi_detection_enabled,
            phi_ocr_engine=preprocess_request.phi_ocr_engine,
            phi_ner_detector=preprocess_request.phi_ner_detector,
            run_ocr_after=preprocess_request.run_ocr_after,
        )

        logger.info("Preprocessing queued", extra={"screenshot_id": screenshot_id, "username": current_user.username})
        return BatchPreprocessResponse(
            queued_count=1,
            screenshot_ids=[screenshot_id],
            message=f"Preprocessing queued for screenshot {screenshot_id}",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to queue preprocessing", extra={"screenshot_id": screenshot_id, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue preprocessing: {e}",
        )


@router.post("/preprocess-batch", response_model=BatchPreprocessResponse)
async def preprocess_screenshots_batch(
    batch_request: BatchPreprocessRequest,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
):
    """Queue preprocessing tasks for multiple screenshots in a group."""
    # Get screenshot IDs to process
    screenshot_ids = await repo.get_ids_by_group(
        batch_request.group_id,
        screenshot_ids=batch_request.screenshot_ids,
    )

    if not screenshot_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No screenshots found in group '{batch_request.group_id}'",
        )

    try:
        from celery import group as celery_group

        from screenshot_processor.web.tasks import preprocess_screenshot_task

        task_group = celery_group(
            preprocess_screenshot_task.s(
                sid,
                phi_pipeline_preset=batch_request.phi_pipeline_preset,
                phi_redaction_method=batch_request.phi_redaction_method,
                phi_detection_enabled=batch_request.phi_detection_enabled,
                phi_ocr_engine=batch_request.phi_ocr_engine,
                phi_ner_detector=batch_request.phi_ner_detector,
                run_ocr_after=batch_request.run_ocr_after,
            )
            for sid in screenshot_ids
        )
        task_group.apply_async()

        logger.info(
            f"Batch preprocessing queued: group={batch_request.group_id}, "
            f"count={len(screenshot_ids)}, by={current_user.username}"
        )
        return BatchPreprocessResponse(
            queued_count=len(screenshot_ids),
            screenshot_ids=screenshot_ids,
            message=f"Preprocessing queued for {len(screenshot_ids)} screenshots in group '{batch_request.group_id}'",
        )

    except Exception as e:
        logger.error("Failed to queue batch preprocessing", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue batch preprocessing: {e}",
        )


# ============================================================================
# Composable Pipeline Endpoints (per-stage execution)
# ============================================================================


_STAGE_ORDER = list(PREPROCESSING_STAGES)


async def _get_eligible_screenshot_ids(
    repo: ScreenshotRepository,
    stage: str,
    group_id: str | None,
    screenshot_ids: list[int] | None,
) -> list[int]:
    """Get screenshot IDs eligible for a stage (pending or invalidated).

    A screenshot is only eligible if:
    1. Its status for this stage is pending, invalidated, or failed
    2. ALL prerequisite stages (earlier in the pipeline) are completed
    """
    screenshots = await repo.get_by_ids_or_group(screenshot_ids=screenshot_ids, group_id=group_id)
    if not screenshot_ids and not group_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either screenshot_ids or group_id is required",
        )

    # Determine prerequisite stages
    stage_idx = _STAGE_ORDER.index(stage) if stage in _STAGE_ORDER else 0
    prerequisite_stages = _STAGE_ORDER[:stage_idx]

    eligible = []
    for s in screenshots:
        pp = (s.processing_metadata or {}).get("preprocessing", {})
        statuses = pp.get("stage_status", {})
        stage_status = statuses.get(stage, StageStatus.PENDING)
        if stage_status not in (StageStatus.PENDING, StageStatus.INVALIDATED, StageStatus.FAILED, StageStatus.CANCELLED):
            continue
        # Check all prerequisite stages are completed (or skipped)
        if all(statuses.get(prereq, StageStatus.PENDING) in (StageStatus.COMPLETED, StageStatus.SKIPPED) for prereq in prerequisite_stages):
            eligible.append(s.id)
    return eligible


@router.post("/preprocess-stage/reset", response_model=StagePreprocessResponse)
async def reset_stage(
    request: StagePreprocessRequest,
    db: DatabaseSession,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
):
    """Reset a stage to 'pending' for all completed/failed screenshots in a group.

    Also invalidates all downstream stages. This allows re-running a stage
    that has already completed.
    """
    from sqlalchemy.orm.attributes import flag_modified

    from screenshot_processor.web.services.preprocessing_service import (
        STAGE_ORDER,
        init_preprocessing_metadata,
        invalidate_downstream,
        update_file_path,
    )

    stage = request.stage
    if not stage or stage not in STAGE_ORDER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"stage is required and must be one of: {STAGE_ORDER}",
        )
    screenshots = await repo.get_by_ids_or_group(screenshot_ids=request.screenshot_ids, group_id=request.group_id)
    if not request.screenshot_ids and not request.group_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="group_id or screenshot_ids required")

    reset_ids = []
    for s in screenshots:
        pp = init_preprocessing_metadata(s)
        stage_status = pp.get("stage_status", {}).get(stage, StageStatus.PENDING)
        if stage_status not in (StageStatus.PENDING,):
            pp["stage_status"][stage] = StageStatus.PENDING
            pp["current_events"][stage] = None
            invalidate_downstream(s, stage)
            update_file_path(s)
            flag_modified(s, "processing_metadata")
            reset_ids.append(s.id)

    if reset_ids:
        await db.commit()

    logger.info(
        "Stage reset for screenshots",
        extra={"stage": stage, "count": len(reset_ids), "username": current_user.username},
    )
    return StagePreprocessResponse(
        queued_count=0,
        screenshot_ids=reset_ids,
        stage=stage,
        message=f"Reset {len(reset_ids)} screenshots to pending for {stage}",
    )


@router.post("/preprocess-stage/skip", response_model=StagePreprocessResponse)
async def skip_stage(
    request: SkipStageRequest,
    db: DatabaseSession,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
):
    """Skip or unskip a preprocessing stage for screenshots.

    Skipped stages are treated as completed for prerequisite checks,
    allowing downstream stages to proceed. Does NOT invalidate downstream.
    """
    from sqlalchemy.orm.attributes import flag_modified

    from screenshot_processor.web.services.preprocessing_service import (
        STAGE_ORDER,
        init_preprocessing_metadata,
    )

    stage = request.stage
    if not stage or stage not in STAGE_ORDER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"stage must be one of: {STAGE_ORDER}",
        )
    if not request.screenshot_ids and not request.group_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="group_id or screenshot_ids required")

    screenshots = await repo.get_by_ids_or_group(screenshot_ids=request.screenshot_ids, group_id=request.group_id)

    affected_ids = []
    for s in screenshots:
        # Read current status without initializing metadata (avoid side effects on non-matching screenshots)
        pp = (s.processing_metadata or {}).get("preprocessing", {})
        current = pp.get("stage_status", {}).get(stage, StageStatus.PENDING)

        should_modify = False
        if request.unskip:
            should_modify = current == StageStatus.SKIPPED
        else:
            should_modify = current in (StageStatus.PENDING, StageStatus.INVALIDATED, StageStatus.FAILED, StageStatus.CANCELLED)

        if should_modify:
            # Only initialize metadata for screenshots we're actually modifying
            pp = init_preprocessing_metadata(s)
            new_status = StageStatus.PENDING if request.unskip else StageStatus.SKIPPED
            pp["stage_status"][stage] = new_status
            flag_modified(s, "processing_metadata")
            affected_ids.append(s.id)

    if affected_ids:
        await db.commit()

    action = "unskipped" if request.unskip else "skipped"
    logger.info(
        f"Stage {action}",
        extra={"stage": stage, "count": len(affected_ids), "username": current_user.username},
    )
    return StagePreprocessResponse(
        queued_count=0,
        screenshot_ids=affected_ids,
        stage=stage,
        message=f"{action.capitalize()} {len(affected_ids)} screenshots for {stage}",
    )


def _run_sync_stage_batch(stage: str, screenshot_ids: list[int], process_fn) -> None:
    """Run a fast preprocessing stage in a thread with chunked commits.

    Commits every 100 images so the frontend's polling sees progress.
    Runs in a thread to avoid blocking the async event loop (which would
    prevent image serving and other API requests during processing).
    """
    import threading

    def _worker():
        _run_sync_stage_batch_inner(stage, screenshot_ids, process_fn)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


def _run_sync_stage_batch_inner(stage: str, screenshot_ids: list[int], process_fn) -> None:
    """Inner function that does the actual batch processing."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.orm.attributes import flag_modified

    from screenshot_processor.web.config import get_settings
    from screenshot_processor.web.database.models import Screenshot
    from screenshot_processor.web.services.preprocessing_service import (
        append_error_event,
        init_preprocessing_metadata,
        set_stage_running,
    )

    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL.replace("+asyncpg", ""))
    SyncSession = sessionmaker(bind=engine)

    CHUNK_SIZE = 100
    total_processed = 0
    total_chunks = (len(screenshot_ids) + CHUNK_SIZE - 1) // CHUNK_SIZE

    for chunk_idx, chunk_start in enumerate(range(0, len(screenshot_ids), CHUNK_SIZE)):
        chunk_ids = screenshot_ids[chunk_start : chunk_start + CHUNK_SIZE]
        sync_db = SyncSession()
        chunk_count = 0
        try:
            screenshots = sync_db.query(Screenshot).filter(Screenshot.id.in_(chunk_ids)).all()
            for screenshot in screenshots:
                try:
                    init_preprocessing_metadata(screenshot)
                    set_stage_running(screenshot, stage)
                    process_fn(screenshot, stage)
                    flag_modified(screenshot, "processing_metadata")
                    chunk_count += 1
                except Exception as e:
                    logger.warning(f"{stage} failed for {screenshot.id}: {e}")
                    try:
                        # Reset stage status from "running" to "failed" so it doesn't appear stuck
                        pp = screenshot.processing_metadata.get("preprocessing", {})
                        pp.get("stage_status", {})[stage] = "failed"
                        append_error_event(screenshot, stage, "auto", {}, str(e))
                        flag_modified(screenshot, "processing_metadata")
                    except Exception:
                        pass
            sync_db.commit()
            total_processed += chunk_count
            logger.info(
                f"{stage} chunk {chunk_idx + 1}/{total_chunks} committed",
                extra={"chunk": chunk_idx + 1, "chunk_count": chunk_count, "total_so_far": total_processed},
            )
        except Exception as e:
            sync_db.rollback()
            logger.error(f"{stage} chunk {chunk_idx + 1}/{total_chunks} FAILED: {e}")
        finally:
            sync_db.close()

    engine.dispose()
    logger.info(f"{stage} batch completed", extra={"total_processed": total_processed, "total_requested": len(screenshot_ids)})


@router.post("/preprocess-stage/device-detection", response_model=StagePreprocessResponse)
async def run_device_detection_stage(
    request: StagePreprocessRequest,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
):
    """Run device detection in background with chunked commits for live progress."""
    ids = await _get_eligible_screenshot_ids(repo, "device_detection", request.group_id, request.screenshot_ids)
    if not ids:
        return StagePreprocessResponse(
            queued_count=0,
            screenshot_ids=[],
            stage="device_detection",
            message="No eligible screenshots for device detection",
        )

    from screenshot_processor.web.services.preprocessing_service import (
        append_event,
        detect_device,
        get_current_input_file,
    )

    def _process_device(screenshot, stage):
        input_file = get_current_input_file(screenshot, stage)
        device = detect_device(input_file)
        result_data = {
            "detected": device.detected,
            "device_category": device.device_category,
            "device_model": device.device_model,
            "confidence": device.confidence,
            "is_ipad": device.is_ipad,
            "is_iphone": device.is_iphone,
            "orientation": device.orientation,
            "width": device.width,
            "height": device.height,
        }
        if device.detected:
            if device.is_ipad:
                screenshot.device_type = "ipad"
            elif device.is_iphone:
                screenshot.device_type = "iphone"
        append_event(screenshot, stage, "auto", {}, result_data, input_file=input_file)

    background_tasks.add_task(_run_sync_stage_batch, "device_detection", ids, _process_device)

    return StagePreprocessResponse(
        queued_count=len(ids),
        screenshot_ids=ids,
        stage="device_detection",
        message=f"Device detection queued for {len(ids)} screenshots",
    )


@router.post("/preprocess-stage/cropping", response_model=StagePreprocessResponse)
async def run_cropping_stage(
    request: StagePreprocessRequest,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
):
    """Run cropping in background with chunked commits for live progress."""
    ids = await _get_eligible_screenshot_ids(repo, "cropping", request.group_id, request.screenshot_ids)
    if not ids:
        return StagePreprocessResponse(
            queued_count=0,
            screenshot_ids=[],
            stage="cropping",
            message="No eligible screenshots for cropping",
        )

    from screenshot_processor.web.services.preprocessing_service import (
        append_event,
        crop_screenshot_if_ipad,
        detect_device,
        get_current_input_file,
        get_next_version,
        get_stage_output_path,
        init_preprocessing_metadata,
    )

    def _process_crop(screenshot, stage):
        from pathlib import Path

        import cv2
        import numpy as np

        input_file = get_current_input_file(screenshot, stage)
        image_bytes = Path(input_file).read_bytes()
        device = detect_device(input_file)
        cropped_bytes, was_cropped, was_patched, crop_had_error = crop_screenshot_if_ipad(image_bytes, device)

        result_data = {
            "was_cropped": was_cropped,
            "was_patched": was_patched,
            "had_error": crop_had_error,
            "is_ipad": device.is_ipad,
        }

        # Store dimensions (required by CroppingTab UI)
        if was_cropped and device:
            result_data["original_dimensions"] = [device.width, device.height]
            arr = np.frombuffer(cropped_bytes, np.uint8)
            cropped_img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
            if cropped_img is not None:
                result_data["cropped_dimensions"] = [cropped_img.shape[1], cropped_img.shape[0]]
        elif device and device.width > 0:
            result_data["original_dimensions"] = [device.width, device.height]
            result_data["cropped_dimensions"] = [device.width, device.height]

        output_file = None
        if was_cropped:
            version = get_next_version(screenshot, stage)
            base = init_preprocessing_metadata(screenshot).get("base_file_path", screenshot.file_path)
            output_path = get_stage_output_path(base, stage, version)
            output_path.write_bytes(cropped_bytes)
            output_file = str(output_path)

        append_event(screenshot, stage, "auto", {}, result_data, output_file=output_file, input_file=input_file)

    background_tasks.add_task(_run_sync_stage_batch, "cropping", ids, _process_crop)

    return StagePreprocessResponse(
        queued_count=len(ids),
        screenshot_ids=ids,
        stage="cropping",
        message=f"Cropping queued for {len(ids)} screenshots",
    )


@router.post("/preprocess-stage/phi-detection", response_model=StagePreprocessResponse)
async def run_phi_detection_stage(
    request: PHIDetectionStageRequest,
    db: DatabaseSession,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
):
    """Queue PHI detection for a batch of screenshots."""
    ids = await _get_eligible_screenshot_ids(repo, "phi_detection", request.group_id, request.screenshot_ids)
    if not ids:
        return StagePreprocessResponse(
            queued_count=0,
            screenshot_ids=[],
            stage="phi_detection",
            message="No eligible screenshots for PHI detection",
        )

    from screenshot_processor.web.tasks import phi_detection_task

    task_results = [
        phi_detection_task.apply_async(
            args=[sid],
            kwargs={
                "preset": request.phi_pipeline_preset,
                "ocr_engine": request.phi_ocr_engine,
                "ner_detector": request.phi_ner_detector,
                "llm_endpoint": request.llm_endpoint,
                "llm_model": request.llm_model,
                "llm_api_key": request.llm_api_key,
            },
        )
        for sid in ids
    ]
    task_ids = [r.id for r in task_results]

    logger.info("PHI detection queued", extra={"count": len(ids), "username": current_user.username})
    return StagePreprocessResponse(
        queued_count=len(ids),
        screenshot_ids=ids,
        stage="phi_detection",
        message=f"PHI detection queued for {len(ids)} screenshots",
        task_ids=task_ids,
    )


@router.post("/preprocess-stage/phi-detection/cancel", response_model=StagePreprocessResponse)
async def cancel_phi_detection_stage(
    request: StagePreprocessRequest,
    db: DatabaseSession,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
):
    """Revoke queued/running PHI detection tasks and reset affected screenshots to pending.

    Accepts task_ids (from the original dispatch response) to revoke specific tasks.
    Also resets any screenshots in the group that are still marked 'running' back to
    'pending' so they can be re-queued.
    """
    from sqlalchemy.orm.attributes import flag_modified

    from screenshot_processor.web.celery_app import celery_app
    from screenshot_processor.web.services.preprocessing_service import (
        init_preprocessing_metadata,
    )

    # Step 1: Find and revoke/kill phi_detection tasks specifically.
    # Do NOT use celery_app.control.purge() — it destroys ALL queued tasks across all stages.
    killed_ids: list[str] = []
    revoked_ids: list[str] = []
    try:
        inspector = celery_app.control.inspect(timeout=2.0)
        # Revoke queued (reserved) PHI tasks — prevents them from starting
        reserved = inspector.reserved() or {}
        for worker_tasks in reserved.values():
            for task in worker_tasks:
                if "phi_detection_task" in task.get("name", ""):
                    revoked_ids.append(task["id"])
        if revoked_ids:
            celery_app.control.revoke(revoked_ids)
        # Kill actively running PHI tasks
        active = inspector.active() or {}
        for worker_tasks in active.values():
            for task in worker_tasks:
                if "phi_detection_task" in task.get("name", ""):
                    killed_ids.append(task["id"])
        if killed_ids:
            celery_app.control.revoke(killed_ids, terminate=True, signal="SIGKILL")
            logger.info(
                "Active PHI detection tasks killed",
                extra={"count": len(killed_ids), "username": current_user.username},
            )
    except Exception as e:
        logger.warning("Failed to inspect/kill active tasks", extra={"error": str(e)})

    # Step 3: Mark all pending/running phi_detection screenshots as "cancelled"
    # so that any task that somehow still executes will discard its results.
    # Note: "cancelled" is distinct from "invalidated" (which means upstream re-run).
    reset_ids: list[int] = []
    if request.group_id or request.screenshot_ids:
        screenshots = await repo.get_by_ids_or_group(
            screenshot_ids=request.screenshot_ids, group_id=request.group_id
        )
        for s in screenshots:
            pp = init_preprocessing_metadata(s)
            status = pp.get("stage_status", {}).get("phi_detection")
            if status in (StageStatus.PENDING, StageStatus.RUNNING):
                pp["stage_status"]["phi_detection"] = StageStatus.CANCELLED
                pp["current_events"]["phi_detection"] = None
                flag_modified(s, "processing_metadata")
                reset_ids.append(s.id)
        if reset_ids:
            await db.commit()

    return StagePreprocessResponse(
        queued_count=0,
        screenshot_ids=reset_ids,
        stage="phi_detection",
        message=f"Cancelled: revoked {len(revoked_ids)} queued + killed {len(killed_ids)} active tasks, reset {len(reset_ids)} screenshots",
    )


# ---------------------------------------------------------------------------
# PHI text whitelist
# ---------------------------------------------------------------------------


class PHIWhitelistResponse(BaseModel):
    whitelist: list[str]


class PHIWhitelistTextRequest(BaseModel):
    text: str


@router.get("/phi-text-whitelist", response_model=PHIWhitelistResponse)
async def get_phi_whitelist(current_user: CurrentUser):
    """Return the current PHI text whitelist."""
    from screenshot_processor.web.services.preprocessing.phi import load_phi_whitelist

    return PHIWhitelistResponse(whitelist=load_phi_whitelist())


@router.post("/phi-text-whitelist", response_model=PHIWhitelistResponse)
async def add_to_phi_whitelist(request_body: PHIWhitelistTextRequest, current_user: CurrentUser):
    """Add a text string to the PHI whitelist so it is never flagged again."""
    from screenshot_processor.web.services.preprocessing.phi import add_to_phi_whitelist as _add

    updated = _add(request_body.text)
    return PHIWhitelistResponse(whitelist=updated)


@router.delete("/phi-text-whitelist", response_model=PHIWhitelistResponse)
async def remove_from_phi_whitelist(request_body: PHIWhitelistTextRequest, current_user: CurrentUser):
    """Remove a text string from the PHI whitelist."""
    from screenshot_processor.web.services.preprocessing.phi import remove_from_phi_whitelist as _remove

    updated = _remove(request_body.text)
    return PHIWhitelistResponse(whitelist=updated)


@router.post("/preprocess-stage/phi-redaction", response_model=StagePreprocessResponse)
async def run_phi_redaction_stage(
    request: PHIRedactionStageRequest,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
):
    """Queue PHI redaction for a batch of screenshots."""
    ids = await _get_eligible_screenshot_ids(repo, "phi_redaction", request.group_id, request.screenshot_ids)
    if not ids:
        return StagePreprocessResponse(
            queued_count=0,
            screenshot_ids=[],
            stage="phi_redaction",
            message="No eligible screenshots for PHI redaction",
        )

    from celery import group as celery_group

    from screenshot_processor.web.tasks import phi_redaction_task

    task_group = celery_group(phi_redaction_task.s(sid, method=request.phi_redaction_method) for sid in ids)
    task_group.apply_async()

    logger.info("PHI redaction queued", extra={"count": len(ids), "username": current_user.username})
    return StagePreprocessResponse(
        queued_count=len(ids),
        screenshot_ids=ids,
        stage="phi_redaction",
        message=f"PHI redaction queued for {len(ids)} screenshots",
    )


@router.post("/preprocess-stage/ocr", response_model=StagePreprocessResponse)
async def run_ocr_stage(
    request: OCRStageRequest,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
):
    """Queue batch OCR processing (grid detection + title/total + hourly extraction)."""
    ids = await _get_eligible_screenshot_ids(repo, "ocr", request.group_id, request.screenshot_ids)
    if not ids:
        return StagePreprocessResponse(
            queued_count=0,
            screenshot_ids=[],
            stage="ocr",
            message="No eligible screenshots for OCR processing",
        )

    from celery import group as celery_group

    from screenshot_processor.web.tasks import ocr_stage_task

    task_group = celery_group(
        ocr_stage_task.s(sid, ocr_method=request.ocr_method, max_shift=request.max_shift) for sid in ids
    )
    task_group.apply_async()

    logger.info(
        "OCR processing queued",
        extra={"count": len(ids), "method": request.ocr_method, "username": current_user.username},
    )
    return StagePreprocessResponse(
        queued_count=len(ids),
        screenshot_ids=ids,
        stage="ocr",
        message=f"OCR processing queued for {len(ids)} screenshots",
    )


@router.post("/{screenshot_id}/invalidate-from-stage", response_model=StagePreprocessResponse)
async def invalidate_from_stage(
    screenshot_id: int,
    request: InvalidateFromStageRequest,
    db: DatabaseSession,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
):
    """Manually invalidate downstream stages for a screenshot."""
    from sqlalchemy.orm.attributes import flag_modified

    from screenshot_processor.web.services.preprocessing_service import (
        STAGE_ORDER,
        init_preprocessing_metadata,
        invalidate_downstream,
        update_file_path,
    )

    screenshot = await get_screenshot_or_404(repo, screenshot_id)

    if request.stage not in STAGE_ORDER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid stage: {request.stage}. Must be one of: {STAGE_ORDER}",
        )

    pp = init_preprocessing_metadata(screenshot)
    # Invalidate the named stage itself
    pp["stage_status"][request.stage] = StageStatus.INVALIDATED
    pp["current_events"][request.stage] = None
    # Invalidate all downstream stages
    invalidate_downstream(screenshot, request.stage)
    update_file_path(screenshot)
    flag_modified(screenshot, "processing_metadata")
    await db.commit()

    return StagePreprocessResponse(
        queued_count=0,
        screenshot_ids=[screenshot_id],
        stage=request.stage,
        message=f"Downstream stages invalidated from {request.stage}",
    )


@router.get("/{screenshot_id}/preprocessing-events", response_model=PreprocessingEventLog)
async def get_preprocessing_events(
    screenshot_id: int,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
):
    """Get the full preprocessing event log for a screenshot."""
    screenshot = await get_screenshot_or_404(repo, screenshot_id)

    pp = (screenshot.processing_metadata or {}).get("preprocessing", {})
    return PreprocessingEventLog(
        screenshot_id=screenshot_id,
        base_file_path=pp.get("base_file_path", screenshot.file_path),
        stage_status=pp.get("stage_status", {}),
        current_events=pp.get("current_events", {}),
        events=pp.get("events", []),
    )


# ============================================================================
# Browser Upload (Phase 2) — multipart/form-data, CurrentUser auth
# ============================================================================


@router.post("/upload/browser", response_model=BrowserUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_browser(
    request: Request,
    current_user: CurrentUser,
    db: DatabaseSession,
    repo: ScreenshotRepo,
    metadata: str = Form(..., description="JSON string of BrowserUploadRequest"),
    files: list[UploadFile] = File(..., description="Image files"),
):
    """
    Upload screenshots from browser with multipart/form-data.

    Uses X-Username auth (CurrentUser), NOT X-API-Key.
    Accepts metadata as a JSON string plus one or more image files.
    Does not queue Celery tasks — user triggers stages manually.
    """
    import json

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from screenshot_processor.web.services.preprocessing_service import init_preprocessing_metadata

    # Parse metadata JSON
    try:
        meta = BrowserUploadRequest.model_validate(json.loads(metadata))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid metadata: {e}")

    if len(files) != len(meta.items):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File count ({len(files)}) does not match items count ({len(meta.items)})",
        )

    settings = get_settings()
    upload_dir = Path(settings.UPLOAD_DIR)

    # Ensure group exists (upsert)
    await repo.upsert_group(meta.group_id, meta.image_type)

    results: list[BrowserUploadItemResult] = []
    successful = 0
    failed = 0

    for i, (item, upload_file) in enumerate(zip(meta.items, files, strict=False)):
        try:
            # Read file content
            file_data = await upload_file.read()
            if not file_data:
                results.append(BrowserUploadItemResult(index=i, success=False, error="Empty file"))
                failed += 1
                continue

            # Validate image format
            if file_data[:8] == b"\x89PNG\r\n\x1a\n":
                ext = ".png"
            elif file_data[:2] == b"\xff\xd8":
                ext = ".jpg"
            else:
                results.append(
                    BrowserUploadItemResult(index=i, success=False, error="Unsupported format (PNG/JPEG only)")
                )
                failed += 1
                continue

            # Compute hash for unique filename and content dedup
            content_hash = hashlib.blake2b(file_data, digest_size=32).hexdigest()
            file_hash = content_hash[:12]

            # Content-hash dedup check
            existing = await repo.find_by_content_hash(content_hash)
            if existing:
                results.append(BrowserUploadItemResult(index=i, success=True, screenshot_id=existing.id))
                successful += 1
                continue

            safe_name = sanitize_filename(item.filename)
            base_name = Path(safe_name).stem
            final_filename = f"{meta.group_id}/{item.participant_id}/{base_name}_{file_hash}{ext}"

            file_path = upload_dir / final_filename
            file_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(file_path, "wb") as f:
                await f.write(file_data)

            # Get dimensions and detect device
            width, height = _get_image_dimensions(file_data)
            detected_device = _detect_device_type(width, height) if width > 0 else None

            # Use a savepoint so a single file's DB failure doesn't poison
            # the session and cascade-fail all remaining files in the batch.
            async with db.begin_nested():
                # Create screenshot record (upsert on file_path)
                insert_stmt = (
                    pg_insert(Screenshot)
                    .values(
                        file_path=str(file_path),
                        image_type=meta.image_type,
                        target_annotations=1,
                        annotation_status=AnnotationStatus.PENDING,
                        processing_status=ProcessingStatus.PENDING,
                        current_annotation_count=0,
                        participant_id=item.participant_id,
                        group_id=meta.group_id,
                        device_type=detected_device,
                        original_filepath=item.original_filepath,
                        screenshot_date=item.screenshot_date,
                        uploaded_by_id=current_user.id,
                        content_hash=content_hash,
                    )
                    .on_conflict_do_update(
                        index_elements=["file_path"],
                        set_={
                            "processing_status": ProcessingStatus.PENDING,
                            "annotation_status": AnnotationStatus.PENDING,
                            "device_type": detected_device,
                            "original_filepath": item.original_filepath,
                            "screenshot_date": item.screenshot_date,
                            "processing_metadata": None,
                            "extracted_title": None,
                            "extracted_total": None,
                            "extracted_hourly_data": None,
                            "current_annotation_count": 0,
                        },
                    )
                    .returning(Screenshot.id)
                )
                result = await db.execute(insert_stmt)
                screenshot_id = result.fetchone()[0]
                await db.flush()

                # Initialize preprocessing metadata (no Celery tasks)
                from sqlalchemy.orm.attributes import flag_modified as _flag_modified

                screenshot = await get_screenshot_or_404(repo, screenshot_id)
                init_preprocessing_metadata(screenshot)
                _flag_modified(screenshot, "processing_metadata")
                await db.flush()

            results.append(BrowserUploadItemResult(index=i, success=True, screenshot_id=screenshot_id))
            successful += 1

        except Exception as e:
            logger.error("Browser upload item failed", extra={"item_index": i, "error": str(e)})
            results.append(BrowserUploadItemResult(index=i, success=False, error=str(e)))
            failed += 1

    await db.commit()
    if successful > 0:
        invalidate_stats_and_groups()

    return BrowserUploadResponse(
        total=len(files),
        successful=successful,
        failed=failed,
        results=results,
    )


# ============================================================================
# Manual Crop (Phase 3) — synchronous crop with event log
# ============================================================================


@router.get("/{screenshot_id}/original-image")
async def get_original_image(
    screenshot_id: int,
    repo: ScreenshotRepo,
):
    """Serve the immutable original image (base_file_path) for crop editing."""
    screenshot = await get_screenshot_or_404(repo, screenshot_id)

    pp = (screenshot.processing_metadata or {}).get("preprocessing", {})
    base_path = pp.get("base_file_path", screenshot.file_path)

    # Resolve relative to CWD (same approach as /image endpoint)
    file_path = Path(base_path).resolve()

    # Path traversal protection
    settings = get_settings()
    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    try:
        file_path.relative_to(upload_dir)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Original image not found")

    media_type = "image/png" if file_path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(str(file_path), media_type=media_type)


@router.get("/{screenshot_id}/stage-image")
async def get_stage_image(
    screenshot_id: int,
    repo: ScreenshotRepo,
    stage: str = Query(..., description="Stage whose output to serve (e.g. 'cropping')"),
):
    """Serve the output image of a specific preprocessing stage.

    Walks the event log to find the current event for the given stage and
    serves its output_file.  Falls back to the stage's input_file, then to
    base_file_path.
    """
    VALID_STAGES = {"device_detection", "cropping", "phi_detection", "phi_redaction"}
    if stage not in VALID_STAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid stage '{stage}'. Must be one of: {', '.join(sorted(VALID_STAGES))}",
        )

    screenshot = await get_screenshot_or_404(repo, screenshot_id)

    pp = (screenshot.processing_metadata or {}).get("preprocessing", {})
    base_path = pp.get("base_file_path", screenshot.file_path)
    current_events = pp.get("current_events", {})
    events = pp.get("events", [])

    target_path = base_path  # ultimate fallback

    eid = current_events.get(stage)
    if eid:
        ev = next((e for e in events if e.get("event_id") == eid), None)
        if ev:
            if ev.get("output_file"):
                target_path = ev["output_file"]
            elif ev.get("input_file"):
                target_path = ev["input_file"]

    file_path = Path(target_path).resolve()

    settings = get_settings()
    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    try:
        file_path.relative_to(upload_dir)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image not found for stage '{stage}'",
        )

    media_type = "image/png" if file_path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(str(file_path), media_type=media_type)


@router.post("/{screenshot_id}/manual-crop", response_model=ManualCropResponse)
async def manual_crop(
    screenshot_id: int,
    crop_request: ManualCropRequest,
    db: DatabaseSession,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
):
    """
    Apply a manual crop to a screenshot.

    Crops the original image and records an event in the preprocessing log.
    Automatically invalidates phi_detection and phi_redaction downstream.
    CPU-bound OpenCV work runs in a thread to avoid blocking the event loop.
    """
    from screenshot_processor.web.services.preprocessing_service import (
        append_event,
        get_next_version,
        get_stage_output_path,
        init_preprocessing_metadata,
    )

    screenshot = await get_screenshot_for_update(repo, screenshot_id)
    pp = init_preprocessing_metadata(screenshot)
    base_path = pp.get("base_file_path", screenshot.file_path)

    # Resolve relative paths
    resolved_base = str(_resolve_image_path(base_path))

    # Read image in a thread to avoid blocking the event loop
    img = await asyncio.to_thread(cv2.imread, resolved_base)
    if img is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not read original image")

    h_img, w_img = img.shape[:2]

    # Validate crop within image bounds
    if crop_request.right > w_img or crop_request.bottom > h_img:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Crop region ({crop_request.right}x{crop_request.bottom}) exceeds image dimensions ({w_img}x{h_img})",
        )

    # Crop and save in a thread
    version = get_next_version(screenshot, "cropping")
    output_path = get_stage_output_path(base_path, "cropping", version)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _crop_and_save() -> tuple[int, int]:
        cropped = img[crop_request.top : crop_request.bottom, crop_request.left : crop_request.right]
        cv2.imwrite(str(output_path), cropped)
        return cropped.shape[1], cropped.shape[0]  # w, h

    crop_w, crop_h = await asyncio.to_thread(_crop_and_save)

    # Record event
    event_id = append_event(
        screenshot,
        "cropping",
        "manual",
        params={
            "left": crop_request.left,
            "top": crop_request.top,
            "right": crop_request.right,
            "bottom": crop_request.bottom,
            "user": current_user.username,
        },
        result={
            "was_cropped": True,
            "manual": True,
            "original_dimensions": [w_img, h_img],
            "cropped_dimensions": [crop_w, crop_h],
        },
        output_file=str(output_path),
        input_file=base_path,
    )

    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(screenshot, "processing_metadata")
    await db.commit()

    return ManualCropResponse(
        success=True,
        event_id=event_id,
        output_file=str(output_path),
        width=crop_w,
        height=crop_h,
        message=f"Manual crop applied ({crop_w}x{crop_h}). PHI stages invalidated.",
    )


# ============================================================================
# PHI Region Management (Phase 4)
# ============================================================================


@router.get("/{screenshot_id}/phi-regions", response_model=PHIRegionsResponse)
async def get_phi_regions(
    screenshot_id: int,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
):
    """Get current PHI regions from the phi_detection event."""
    screenshot = await get_screenshot_or_404(repo, screenshot_id)

    pp = (screenshot.processing_metadata or {}).get("preprocessing", {})
    current_events = pp.get("current_events", {})
    events = pp.get("events", [])

    phi_eid = current_events.get("phi_detection")
    if not phi_eid:
        return PHIRegionsResponse(regions=[], source=None, event_id=None)

    event = next((e for e in events if e["event_id"] == phi_eid), None)
    if not event:
        return PHIRegionsResponse(regions=[], source=None, event_id=None)

    result = event.get("result", {})
    raw_regions = result.get("regions", [])

    regions = []
    for r in raw_regions:
        if isinstance(r, dict):
            # Normalize from various formats (auto-detection vs manual)
            bbox = r.get("bbox", {})
            if isinstance(bbox, dict):
                regions.append(
                    PHIRegionRect(
                        x=int(bbox.get("x", r.get("x", 0))),
                        y=int(bbox.get("y", r.get("y", 0))),
                        w=max(1, int(bbox.get("width", bbox.get("w", r.get("w", 1))))),
                        h=max(1, int(bbox.get("height", bbox.get("h", r.get("h", 1))))),
                        label=r.get("label", r.get("type", r.get("entity_type", "OTHER"))),
                        source=r.get("source", event.get("source", "auto")),
                        confidence=float(r.get("confidence", r.get("score", 0.0))),
                        text=r.get("text", ""),
                    )
                )
            else:
                # Already in flat format
                regions.append(
                    PHIRegionRect(
                        x=int(r.get("x", 0)),
                        y=int(r.get("y", 0)),
                        w=max(1, int(r.get("w", 1))),
                        h=max(1, int(r.get("h", 1))),
                        label=r.get("label", "OTHER"),
                        source=r.get("source", "auto"),
                        confidence=float(r.get("confidence", 0.0)),
                        text=r.get("text", ""),
                    )
                )

    # PERSON-only: drop any stored region whose label is not a person-name variant.
    # This retroactively cleans up old detections (EMAIL, PHONE, etc.) without reprocessing.
    from screenshot_processor.web.services.preprocessing.phi import _PERSON_LABELS

    _LABEL_NORM = {"PERSON_NAME": "PERSON", "IPAD_OWNER": "PERSON", "OTHER": "PERSON"}
    cleaned: list[PHIRegionRect] = []
    for r in regions:
        if r.label.upper() not in _PERSON_LABELS:
            continue
        # Normalize label to PERSON
        normalized_label = _LABEL_NORM.get(r.label.upper(), r.label.upper())
        cleaned.append(r.model_copy(update={"label": normalized_label}))
    regions = cleaned

    # Apply whitelist filter at read time so whitelisted text is hidden immediately
    # across all screenshots without requiring re-detection.
    from screenshot_processor.web.services.preprocessing.phi import load_phi_whitelist

    whitelist: set[str] = set(load_phi_whitelist())
    if whitelist:
        regions = [r for r in regions if r.text.strip().lower() not in whitelist]

    return PHIRegionsResponse(
        regions=regions,
        source=event.get("source", "auto"),
        event_id=phi_eid,
    )


@router.put("/{screenshot_id}/phi-regions", response_model=ManualPHIRegionsResponse)
async def save_phi_regions(
    screenshot_id: int,
    request_body: ManualPHIRegionsRequest,
    db: DatabaseSession,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
):
    """Save manually-adjusted PHI regions. Invalidates phi_redaction downstream."""
    from sqlalchemy.orm.attributes import flag_modified

    from screenshot_processor.web.services.preprocessing_service import (
        append_event,
        get_current_input_file,
        init_preprocessing_metadata,
    )

    screenshot = await get_screenshot_for_update(repo, screenshot_id)
    init_preprocessing_metadata(screenshot)

    input_file = get_current_input_file(screenshot, "phi_detection")

    regions_dicts = [r.model_dump() for r in request_body.regions]

    event_id = append_event(
        screenshot,
        "phi_detection",
        "manual",
        params={
            "preset": request_body.preset,
            "user": current_user.username,
        },
        result={
            "phi_detected": len(request_body.regions) > 0,
            "regions_count": len(request_body.regions),
            "regions": regions_dicts,
            "preset": request_body.preset,
            "reviewed": True,
        },
        input_file=input_file,
    )

    flag_modified(screenshot, "processing_metadata")
    await db.commit()

    return ManualPHIRegionsResponse(
        success=True,
        event_id=event_id,
        regions_count=len(request_body.regions),
        message=f"Saved {len(request_body.regions)} PHI region(s). Redaction stage invalidated.",
    )


@router.post("/{screenshot_id}/apply-redaction", response_model=ApplyPHIRedactionResponse)
async def apply_redaction(
    screenshot_id: int,
    request_body: ApplyPHIRedactionRequest,
    db: DatabaseSession,
    repo: ScreenshotRepo,
    current_user: CurrentUser,
):
    """Apply PHI redaction to confirmed regions."""
    from sqlalchemy.orm.attributes import flag_modified

    from screenshot_processor.web.services.preprocessing_service import (
        append_event,
        get_current_input_file,
        get_next_version,
        get_stage_output_path,
        init_preprocessing_metadata,
        redact_phi,
    )

    screenshot = await get_screenshot_for_update(repo, screenshot_id)
    pp = init_preprocessing_metadata(screenshot)

    input_file = get_current_input_file(screenshot, "phi_redaction")

    # Resolve relative paths
    input_path = _resolve_image_path(input_file)
    if not input_path.exists():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Input image not found")

    # Read input image without blocking the event loop
    async with aiofiles.open(input_path, "rb") as f:
        image_bytes = await f.read()

    # Convert regions to format expected by redact_phi
    phi_regions_for_redact = [
        {
            "bbox": {"x": r.x, "y": r.y, "width": r.w, "height": r.h},
            "type": r.label,
            "text": r.text,
            "confidence": r.confidence,
            "source": r.source,
        }
        for r in request_body.regions
    ]

    # Run CPU-bound redaction in a thread
    redaction_result = await asyncio.to_thread(
        redact_phi, image_bytes, phi_regions_for_redact, request_body.redaction_method
    )

    # Save redacted image
    base_path = pp.get("base_file_path", screenshot.file_path)
    version = get_next_version(screenshot, "phi_redaction")
    output_path = get_stage_output_path(base_path, "phi_redaction", version)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(output_path, "wb") as f:
        await f.write(redaction_result.image_bytes)

    event_id = append_event(
        screenshot,
        "phi_redaction",
        "manual",
        params={
            "method": request_body.redaction_method,
            "user": current_user.username,
            "regions_count": len(request_body.regions),
        },
        result={
            "redacted": redaction_result.regions_redacted > 0,
            "regions_redacted": redaction_result.regions_redacted,
            "method": request_body.redaction_method,
            "phi_detected": len(request_body.regions) > 0,
        },
        output_file=str(output_path),
        input_file=input_file,
    )

    flag_modified(screenshot, "processing_metadata")
    await db.commit()

    return ApplyPHIRedactionResponse(
        success=True,
        event_id=event_id,
        regions_redacted=redaction_result.regions_redacted,
        output_file=str(output_path),
        message=f"Redacted {redaction_result.regions_redacted} region(s) using {request_body.redaction_method}.",
    )


# ============================================================================
# Export Endpoints - Available to all authenticated users
# ============================================================================


def _build_export_conditions(
    group_id: str | None,
    verified_only: bool,
    has_annotations: bool,
    processing_status: str | None,
    image_type: str | None = None,
) -> list:
    """Build SQLAlchemy filter conditions shared by JSON and CSV export endpoints."""
    conditions = []
    if group_id:
        conditions.append(Screenshot.group_id == group_id)
    if image_type:
        conditions.append(Screenshot.image_type == image_type)
    if verified_only:
        conditions.append(Screenshot.verified_by_user_ids.isnot(None))
        conditions.append(cast(Screenshot.verified_by_user_ids, String) != "null")
        conditions.append(cast(Screenshot.verified_by_user_ids, String) != "[]")
    if has_annotations:
        conditions.append(Screenshot.current_annotation_count > 0)
    if processing_status:
        conditions.append(Screenshot.processing_status == processing_status)
    return conditions


@router.get("/export/json", tags=["Export"])
async def export_consensus_json(
    repo: ScreenshotRepo,
    current_user: CurrentUser,
    group_id: str | None = Query(None, description="Filter by group ID"),
    image_type: str | None = Query(None, description="Filter by image type (screen_time, battery)"),
    verified_only: bool = Query(False, description="Only export verified screenshots"),
    has_annotations: bool = Query(False, description="Only export screenshots with annotations"),
    processing_status: str | None = Query(None, description="Filter by processing status"),
):
    """Export consensus data as JSON."""
    from datetime import datetime, timezone

    conditions = _build_export_conditions(group_id, verified_only, has_annotations, processing_status, image_type)
    rows = await repo.get_screenshots_with_consensus(conditions)

    screenshots_data = []
    for screenshot, consensus in rows:
        hourly_values = {}
        if screenshot.extracted_hourly_data:
            hourly_values = screenshot.extracted_hourly_data

        screenshot_dict = {
            "id": screenshot.id,
            "file_path": screenshot.file_path,
            "participant_id": screenshot.participant_id,
            "group_id": screenshot.group_id,
            "image_type": screenshot.image_type,
            "device_type": getattr(screenshot, "device_type", None),
            "source_id": getattr(screenshot, "source_id", None),
            "screenshot_date": str(screenshot.screenshot_date) if screenshot.screenshot_date else None,
            "processing_status": screenshot.processing_status.value
            if hasattr(screenshot.processing_status, "value")
            else screenshot.processing_status,
            "extracted_title": screenshot.extracted_title,
            "extracted_total": screenshot.extracted_total,
            "hourly_values": hourly_values,
            "consensus": None,
        }

        if consensus:
            screenshot_dict["consensus"] = {
                "has_consensus": consensus.has_consensus,
                "consensus_values": consensus.consensus_values,
                "disagreement_details": consensus.disagreement_details,
            }

        screenshots_data.append(screenshot_dict)

    response = {
        "export_timestamp": datetime.now(timezone.utc).isoformat(),
        "exported_by": current_user.username,
        "total_screenshots": len(screenshots_data),
        "screenshots": screenshots_data,
    }
    if group_id:
        response["group_id"] = group_id

    return response


@router.get("/export/csv", tags=["Export"])
async def export_consensus_csv(
    repo: ScreenshotRepo,
    current_user: CurrentUser,
    group_id: str | None = Query(None, description="Filter by group ID"),
    image_type: str | None = Query(None, description="Filter by image type (screen_time, battery)"),
    verified_only: bool = Query(False, description="Only export screenshots verified by at least one user"),
    has_annotations: bool = Query(False, description="Only export screenshots with at least one annotation"),
    processing_status: str | None = Query(None, description="Filter by processing status (completed, failed, etc.)"),
):
    """
    Export consensus data as CSV.

    Returns CSV with screenshot info, consensus values, and hourly data.
    Available to all authenticated users.

    Filters:
    - group_id: Filter by group
    - verified_only: Only include screenshots that have been verified by at least one user
    - has_annotations: Only include screenshots with at least one annotation
    - processing_status: Filter by OCR processing status (completed, failed, pending, skipped)
    """
    import csv
    import io
    from datetime import datetime, timezone

    from fastapi.responses import StreamingResponse

    logger.info(
        f"User {current_user.username} exported consensus data "
        f"(CSV, group={group_id}, image_type={image_type}, verified_only={verified_only}, has_annotations={has_annotations})"
    )

    conditions = _build_export_conditions(group_id, verified_only, has_annotations, processing_status, image_type)
    rows = await repo.get_screenshots_with_consensus(conditions)

    output = io.StringIO()
    csv_writer = csv.writer(output)

    # Header from single source of truth (schemas.py EXPORT_CSV_HEADERS)
    csv_writer.writerow(EXPORT_CSV_HEADERS)

    for screenshot, consensus in rows:
        hourly_values = [""] * 24
        computed_total = ""
        disagreement_count = 0

        # Use extracted_* fields directly - dispute resolution updates these in place
        hourly_data_source = screenshot.extracted_hourly_data
        title = screenshot.extracted_title or ""
        ocr_total = screenshot.extracted_total or ""

        if hourly_data_source:
            total_minutes = 0
            for hour_str, value in hourly_data_source.items():
                try:
                    hour_idx = int(hour_str)
                    if 0 <= hour_idx < 24:
                        hourly_values[hour_idx] = str(value) if value is not None else ""
                        if value is not None:
                            total_minutes += float(value)
                except (ValueError, TypeError) as e:
                    logger.warning(
                        "Skipping invalid hourly value during CSV export",
                        extra={"hour": hour_str, "value": value, "error": str(e)},
                    )
            hours = int(total_minutes // 60)
            mins = int(total_minutes % 60)
            computed_total = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"

        # Count disagreements if consensus exists
        if consensus and consensus.disagreement_details:
            disagreement_count = sum(
                1
                for details in consensus.disagreement_details.values()
                if isinstance(details, dict) and details.get("has_disagreement", False)
            )

        verified_ids = screenshot.verified_by_user_ids or []
        hourly_dict = {f"hour_{i}": hourly_values[i] for i in range(24)}

        # Build typed row via ExportRow — validates all fields exist
        row = ExportRow(
            screenshot_id=screenshot.id,
            filename=screenshot.file_path.split("/")[-1] if screenshot.file_path else "",
            original_filepath=screenshot.original_filepath or "",
            group_id=screenshot.group_id or "",
            participant_id=screenshot.participant_id or "",
            image_type=screenshot.image_type,
            screenshot_date=screenshot.screenshot_date.isoformat() if screenshot.screenshot_date else "",
            uploaded_at=screenshot.uploaded_at.isoformat(),
            processing_status=screenshot.processing_status.value if screenshot.processing_status else "",
            is_verified="Yes" if verified_ids else "No",
            verified_by_count=len(verified_ids),
            annotation_count=screenshot.current_annotation_count,
            has_consensus="Yes" if screenshot.has_consensus else "No",
            title=title,
            ocr_total=ocr_total,
            computed_total=computed_total,
            disagreement_count=disagreement_count,
            **hourly_dict,
        )

        # Write in field-definition order (matches EXPORT_CSV_HEADERS)
        csv_writer.writerow(list(row.model_dump().values()))

    output.seek(0)
    filename = f"export_{group_id or 'all'}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    # UTF-8 BOM so Excel on Windows opens with correct encoding
    csv_content = "\ufeff" + output.getvalue()
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/schema", response_model=list[str], tags=["Export"])
async def get_export_column_schema(current_user: CurrentUser):
    """Return the canonical export column headers.

    This endpoint is the single source of truth for export column names.
    WASM/Tauri clients use this to build client-side CSV exports with
    identical column schema to the server CSV export.
    """
    return EXPORT_CSV_HEADERS
