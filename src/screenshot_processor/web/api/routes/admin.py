import asyncio
import logging
from pathlib import Path

import cv2
from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel

from screenshot_processor.core.image_utils import convert_dark_mode
from screenshot_processor.web.api.dependencies import CurrentAdmin
from screenshot_processor.web.cache import invalidate_stats_and_groups
from screenshot_processor.web.database import (
    DeleteGroupResponse,
    ResetTestDataResponse,
    UserStatsRead,
    UserUpdateResponse,
)
from screenshot_processor.web.database.models import UserRole
from screenshot_processor.web.rate_limiting import ADMIN_DESTRUCTIVE_RATE_LIMIT, limiter
from screenshot_processor.web.repositories import AdminRepo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


# ============================================================================
# User Management - Admin Only
# ============================================================================


@router.get("/users", response_model=list[UserStatsRead])
async def get_all_users(repo: AdminRepo, admin: CurrentAdmin):
    """Get all users with their annotation statistics. Admin only.

    Uses a single query with LEFT JOIN to avoid N+1 problem.
    """
    rows = await repo.get_users_with_stats()

    return [
        UserStatsRead(
            id=row.user.id,
            username=row.user.username,
            email=row.user.email,
            role=row.user.role,
            is_active=row.user.is_active,
            created_at=row.user.created_at.isoformat(),
            annotations_count=row.annotations_count,
            avg_time_spent_seconds=row.avg_time_spent_seconds,
        )
        for row in rows
    ]


@router.put("/users/{user_id}", response_model=UserUpdateResponse)
async def update_user(
    user_id: int,
    repo: AdminRepo,
    admin: CurrentAdmin,
    is_active: bool | None = None,
    role: str | None = None,
):
    """Update user status or role. Admin only."""
    user = await repo.get_user_by_id(user_id)

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    try:
        old_role = user.role
        old_active = user.is_active

        valid_roles = {r.value for r in UserRole}
        if role is not None and role not in valid_roles:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")

        user = await repo.update_user(user, is_active=is_active, role=role)

        # Audit logging
        if role is not None and role != old_role:
            logger.info(
                "Admin changed user role",
                extra={
                    "audit": True,
                    "admin_username": admin.username,
                    "username": user.username,
                    "old_role": str(old_role),
                    "new_role": role,
                },
            )
        if is_active is not None and is_active != old_active:
            status_str = "activated" if is_active else "deactivated"
            logger.info(
                "Admin changed user status",
                extra={
                    "audit": True,
                    "admin_username": admin.username,
                    "username": user.username,
                    "action": status_str,
                },
            )

        return UserUpdateResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
        )

    except HTTPException:
        raise
    except Exception as e:
        await repo.db.rollback()
        logger.error("Failed to update user", extra={"user_id": user_id, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user",
        )


# ============================================================================
# Test Data Reset - Admin Only (for e2e tests)
# ============================================================================


@router.post("/reset-test-data", response_model=ResetTestDataResponse)
@limiter.limit(ADMIN_DESTRUCTIVE_RATE_LIMIT)
async def reset_test_data(request: Request, repo: AdminRepo, admin: CurrentAdmin):
    """
    Reset test data for e2e testing.
    Clears user queue states and annotations to allow fresh test runs.
    Admin only.
    """
    try:
        await repo.reset_test_data()
        invalidate_stats_and_groups()

        logger.info("Admin reset test data", extra={"audit": True, "admin_username": admin.username})

        return ResetTestDataResponse(success=True, message="Test data reset successfully")

    except Exception as e:
        await repo.db.rollback()
        logger.error("Failed to reset test data", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset test data: {e!s}",
        )


# ============================================================================
# Group Management - Admin Only
# ============================================================================


@router.delete("/groups/{group_id}", response_model=DeleteGroupResponse)
@limiter.limit(ADMIN_DESTRUCTIVE_RATE_LIMIT)
async def delete_group(
    request: Request,
    group_id: str,
    repo: AdminRepo,
    admin: CurrentAdmin,
):
    """
    Delete a group and all its screenshots (hard delete).
    This is a destructive operation that permanently removes:
    - All screenshots in the group
    - All annotations for those screenshots
    - The group itself

    Admin only.
    """
    try:
        # Check if group exists
        group = await repo.get_group_by_id(group_id)

        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Group '{group_id}' not found",
            )

        # Get screenshot IDs first
        screenshot_ids = await repo.get_screenshot_ids_for_group(group_id)

        # Cascade delete all DB rows
        counts = await repo.delete_group_cascade(group_id, screenshot_ids)
        invalidate_stats_and_groups()

        logger.info(
            "Admin deleted group",
            extra={
                "audit": True,
                "admin_username": admin.username,
                "group_id": group_id,
                "screenshots_deleted": counts.screenshots_deleted,
                "annotations_deleted": counts.annotations_deleted,
            },
        )

        return DeleteGroupResponse(
            success=True,
            group_id=group_id,
            screenshots_deleted=counts.screenshots_deleted,
            annotations_deleted=counts.annotations_deleted,
            message=f"Group '{group_id}' deleted successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        await repo.db.rollback()
        logger.error("Failed to delete group", extra={"group_id": group_id, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete group: {e!s}",
        )


# ============================================================================
# OCR Total Recalculation - Admin Only
# ============================================================================


class RecalculateOcrTotalResponse(BaseModel):
    success: bool
    total_missing: int
    processed: int
    updated: int
    failed: int
    message: str


@router.post("/recalculate-ocr-totals", response_model=RecalculateOcrTotalResponse)
async def recalculate_ocr_totals(
    repo: AdminRepo,
    admin: CurrentAdmin,
    limit: int = Query(default=100, ge=1, le=1000, description="Max screenshots to process"),
    group_id: str | None = Query(default=None, description="Filter by group ID"),
):
    """
    Recalculate OCR totals for screen_time screenshots that are missing extracted_total.
    This runs OCR on the original image to extract the total usage time.

    Admin only.
    """
    try:
        screenshots = await repo.get_screenshots_missing_ocr_total(group_id=group_id, limit=limit)

        total_missing = len(screenshots)
        processed = 0
        updated = 0
        failed = 0

        def _extract_ocr_total_sync(file_path: str) -> str | None:
            """CPU-bound OCR extraction — runs in a thread to avoid blocking the event loop."""
            from screenshot_processor.core.ocr import find_screenshot_total_usage

            if not Path(file_path).exists():
                return None

            img = cv2.imread(file_path)
            if img is None:
                return None

            img = convert_dark_mode(img)
            total, _ = find_screenshot_total_usage(img)
            return total

        # Process in chunks with concurrent OCR + periodic commits to bound memory
        CHUNK_SIZE = 50
        sem = asyncio.Semaphore(8)

        async def process_one(screenshot):
            async with sem:
                try:
                    total = await asyncio.to_thread(_extract_ocr_total_sync, screenshot.file_path)
                    return screenshot, total
                except Exception as e:
                    raise RuntimeError(f"screenshot_id={screenshot.id}") from e

        for chunk_start in range(0, len(screenshots), CHUNK_SIZE):
            chunk = screenshots[chunk_start : chunk_start + CHUNK_SIZE]

            results = await asyncio.gather(
                *[process_one(s) for s in chunk],
                return_exceptions=True,
            )

            for result in results:
                processed += 1
                if isinstance(result, BaseException):
                    logger.error(
                        "Error extracting OCR total",
                        extra={"error": str(result.__cause__ or result), "context": str(result)},
                    )
                    failed += 1
                    continue

                screenshot, total = result
                if total is None:
                    logger.warning(
                        "Screenshot file not found or unreadable",
                        extra={"screenshot_id": screenshot.id, "file_path": screenshot.file_path},
                    )
                    failed += 1
                    continue

                if total and total.strip():
                    screenshot.extracted_total = total.strip()
                    updated += 1
                    logger.info("Extracted OCR total", extra={"screenshot_id": screenshot.id, "extracted_total": total.strip()})
                else:
                    logger.info("No OCR total found", extra={"screenshot_id": screenshot.id})

            # Commit + free ORM identity map after each chunk
            await repo.db.commit()
            repo.db.expire_all()

        logger.info(
            "Admin recalculated OCR totals",
            extra={
                "audit": True,
                "admin_username": admin.username,
                "processed": processed,
                "updated": updated,
                "failed": failed,
            },
        )

        return RecalculateOcrTotalResponse(
            success=True,
            total_missing=total_missing,
            processed=processed,
            updated=updated,
            failed=failed,
            message=f"Processed {processed} screenshots: {updated} updated, {failed} failed",
        )

    except Exception as e:
        await repo.db.rollback()
        logger.error("Failed to recalculate OCR totals", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to recalculate OCR totals: {e!s}",
        )


# ============================================================================
# Bulk Reprocess - Admin Only
# ============================================================================


class BulkReprocessResponse(BaseModel):
    success: bool
    queued: int
    message: str


@router.post("/bulk-reprocess", response_model=BulkReprocessResponse)
@limiter.limit(ADMIN_DESTRUCTIVE_RATE_LIMIT)
async def bulk_reprocess_screenshots(
    request: Request,
    repo: AdminRepo,
    admin: CurrentAdmin,
    group_id: str | None = Query(default=None, description="Filter by group ID"),
    processing_method: str | None = Query(default=None, description="Processing method: 'ocr' or 'line_based'", pattern="^(ocr|line_based)$"),
    max_shift: int = Query(default=5, ge=0, le=10, description="Max pixels to shift grid for optimization"),
    limit: int = Query(default=1000, ge=1, le=5000, description="Max screenshots to reprocess"),
):
    """
    Queue screenshots for reprocessing via workflow workers.

    This will reprocess all screen_time screenshots in the specified group
    (or all groups if not specified) using the updated processing code.
    Uses workflow engine for background processing to avoid blocking the API.

    Admin only.
    """
    try:
        screenshot_ids = await repo.get_screenshot_ids_for_reprocess(group_id=group_id, limit=limit)

        if not screenshot_ids:
            return BulkReprocessResponse(
                success=True,
                queued=0,
                message="No screenshots found to reprocess",
            )

        # Queue workflows for each screenshot
        from screenshot_processor.web.services.workflow_service import create_redaction_workflows_batch

        await create_redaction_workflows_batch(db, screenshot_ids)
        await db.commit()

        logger.info(
            "Admin queued bulk reprocess via workflow engine",
            extra={
                "audit": True,
                "admin_username": admin.username,
                "count": len(screenshot_ids),
                "group_id": group_id,
                "processing_method": processing_method,
                "max_shift": max_shift,
            },
        )

        return BulkReprocessResponse(
            success=True,
            queued=len(screenshot_ids),
            message=f"Queued {len(screenshot_ids)} screenshots for reprocessing (max_shift={max_shift})",
        )

    except Exception as e:
        logger.error("Failed to queue bulk reprocess", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue bulk reprocess: {e!s}",
        )


# ============================================================================
# Retry Stuck Screenshots - Admin Only
# ============================================================================


class RetryStuckResponse(BaseModel):
    success: bool
    pending_count: int
    processing_count: int
    requeued: int
    marked_failed: int
    message: str


@router.post("/retry-stuck", response_model=RetryStuckResponse)
@limiter.limit(ADMIN_DESTRUCTIVE_RATE_LIMIT)
async def retry_stuck_screenshots(
    request: Request,
    repo: AdminRepo,
    admin: CurrentAdmin,
    group_id: str | None = Query(default=None, description="Filter by group ID"),
    mark_processing_as_failed: bool = Query(
        default=True,
        description="Mark screenshots stuck in PROCESSING as FAILED before requeuing PENDING ones",
    ),
):
    """
    Retry screenshots stuck in PENDING or PROCESSING status.

    This endpoint:
    1. Optionally marks all PROCESSING screenshots as FAILED (they're stuck/orphaned)
    2. Requeues all PENDING screenshots for processing via workflow engine

    Use this when screenshots are stuck and not being processed by workflow workers.
    Admin only.
    """
    try:
        # Count current stuck screenshots
        stuck_counts = await repo.count_stuck_screenshots(group_id=group_id)

        marked_failed = 0

        # Step 1: Mark PROCESSING screenshots as FAILED (they're orphaned)
        if mark_processing_as_failed and stuck_counts.processing_count > 0:
            marked_failed = await repo.mark_processing_as_failed(group_id=group_id)
            logger.info("Marked stuck PROCESSING screenshots as FAILED", extra={"count": marked_failed})

        # Step 2: Get all PENDING screenshot IDs and requeue them
        screenshot_ids = await repo.get_pending_screenshot_ids(group_id=group_id)

        requeued = 0
        if screenshot_ids:
            from screenshot_processor.web.services.workflow_service import create_preprocessing_workflows_batch

            await create_preprocessing_workflows_batch(db, screenshot_ids)
            await db.commit()
            requeued = len(screenshot_ids)

            logger.info("Requeued PENDING screenshots via workflow engine", extra={"count": requeued})

        logger.info(
            "Admin retried stuck screenshots",
            extra={
                "audit": True,
                "admin_username": admin.username,
                "group_id": group_id,
                "pending_count": stuck_counts.pending_count,
                "processing_count": stuck_counts.processing_count,
                "marked_failed": marked_failed,
                "requeued": requeued,
            },
        )

        return RetryStuckResponse(
            success=True,
            pending_count=stuck_counts.pending_count,
            processing_count=stuck_counts.processing_count,
            requeued=requeued,
            marked_failed=marked_failed,
            message=f"Marked {marked_failed} as failed, requeued {requeued} pending screenshots",
        )

    except Exception as e:
        await repo.db.rollback()
        logger.error("Failed to retry stuck screenshots", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retry stuck screenshots: {e!s}",
        )


# ============================================================================
# Database Cleanup - Admin Only
# ============================================================================


class OrphanedEntriesResponse(BaseModel):
    orphaned_annotations: int
    orphaned_consensus: int
    orphaned_queue_states: int
    screenshots_without_group: int


class CleanupResponse(BaseModel):
    success: bool
    deleted_annotations: int
    deleted_consensus: int
    deleted_queue_states: int
    message: str


@router.get("/orphaned-entries", response_model=OrphanedEntriesResponse)
async def find_orphaned_entries(repo: AdminRepo, admin: CurrentAdmin):
    """
    Find orphaned database entries that reference non-existent screenshots.
    Admin only.
    """
    counts = await repo.find_orphaned_entries()

    return OrphanedEntriesResponse(
        orphaned_annotations=counts.orphaned_annotations,
        orphaned_consensus=counts.orphaned_consensus,
        orphaned_queue_states=counts.orphaned_queue_states,
        screenshots_without_group=counts.screenshots_without_group,
    )


@router.post("/cleanup-orphaned", response_model=CleanupResponse)
@limiter.limit(ADMIN_DESTRUCTIVE_RATE_LIMIT)
async def cleanup_orphaned_entries(request: Request, repo: AdminRepo, admin: CurrentAdmin):
    """
    Delete orphaned database entries that reference non-existent screenshots.
    Admin only.
    """
    try:
        counts = await repo.cleanup_orphaned_entries()

        logger.info(
            "Admin cleaned up orphaned entries",
            extra={
                "audit": True,
                "admin_username": admin.username,
                "deleted_annotations": counts.deleted_annotations,
                "deleted_consensus": counts.deleted_consensus,
                "deleted_queue_states": counts.deleted_queue_states,
            },
        )

        return CleanupResponse(
            success=True,
            deleted_annotations=counts.deleted_annotations,
            deleted_consensus=counts.deleted_consensus,
            deleted_queue_states=counts.deleted_queue_states,
            message=f"Cleaned up {counts.deleted_annotations + counts.deleted_consensus + counts.deleted_queue_states} orphaned entries",
        )

    except Exception as e:
        await repo.db.rollback()
        logger.error("Failed to cleanup orphaned entries", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup: {e!s}",
        )


# ============================================================================
# Stale Queue State Cleanup - Admin Only
# ============================================================================


class StaleQueueCleanupResponse(BaseModel):
    success: bool
    deleted_queue_states: int
    message: str


@router.post("/cleanup-stale-queue-states", response_model=StaleQueueCleanupResponse)
@limiter.limit(ADMIN_DESTRUCTIVE_RATE_LIMIT)
async def cleanup_stale_queue_states(request: Request, repo: AdminRepo, admin: CurrentAdmin):
    """
    Delete UserQueueState rows for screenshots that are completed or deleted.

    These stale entries accumulate over time and are no longer needed once the
    associated screenshot has been fully processed or soft-deleted.

    Admin only.
    """
    try:
        deleted = await repo.cleanup_stale_queue_states()
        await repo.db.commit()

        logger.info(
            "Admin cleaned up stale queue states",
            extra={
                "audit": True,
                "admin_username": admin.username,
                "deleted_queue_states": deleted,
            },
        )

        return StaleQueueCleanupResponse(
            success=True,
            deleted_queue_states=deleted,
            message=f"Cleaned up {deleted} stale UserQueueState entries",
        )

    except Exception as e:
        await repo.db.rollback()
        logger.error("Failed to cleanup stale queue states", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup stale queue states: {e!s}",
        )
