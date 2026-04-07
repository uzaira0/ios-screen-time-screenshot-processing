"""Admin operations service.

Extracts admin business logic from routes into a testable service layer.
Database queries are delegated to AdminRepository.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.core.image_utils import convert_dark_mode
from screenshot_processor.web.repositories.admin_repository import AdminRepository

logger = logging.getLogger(__name__)


@dataclass
class UserStats:
    """User with annotation statistics."""

    user: object  # User model instance
    annotations_count: int
    avg_time_spent_seconds: float


@dataclass
class DeleteGroupResult:
    """Result of group deletion."""

    success: bool
    group_id: str
    screenshots_deleted: int
    annotations_deleted: int
    message: str


@dataclass
class RecalculateOcrResult:
    """Result of OCR total recalculation."""

    success: bool
    total_missing: int
    processed: int
    updated: int
    failed: int
    message: str


class AdminService:
    """Service for admin operations.

    Handles:
    - User management and statistics
    - Test data reset
    - Group deletion
    - Bulk OCR recalculation

    Database queries are delegated to AdminRepository.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AdminRepository(db)

    # =========================================================================
    # User Management
    # =========================================================================

    async def get_all_users_with_stats(self) -> list[UserStats]:
        """Get all users with their annotation statistics."""
        rows = await self.repo.get_users_with_stats()

        return [
            UserStats(
                user=row.user,
                annotations_count=row.annotations_count,
                avg_time_spent_seconds=row.avg_time_spent_seconds,
            )
            for row in rows
        ]

    async def get_user_by_id(self, user_id: int):
        """Get user by ID."""
        return await self.repo.get_user_by_id(user_id)

    async def update_user(
        self,
        user,
        is_active: bool | None = None,
        role: str | None = None,
    ):
        """Update user attributes."""
        from screenshot_processor.web.database.models import UserRole
        valid_roles = {r.value for r in UserRole}
        if role is not None and role not in valid_roles:
            raise ValueError("Invalid role")

        return await self.repo.update_user(user, is_active=is_active, role=role)

    # =========================================================================
    # Test Data Reset
    # =========================================================================

    async def reset_test_data(self) -> None:
        """Reset all test data for e2e testing."""
        await self.repo.reset_test_data()

    # =========================================================================
    # Group Management
    # =========================================================================

    async def get_group_by_id(self, group_id: str):
        """Get group by ID."""
        return await self.repo.get_group_by_id(group_id)

    async def delete_group(self, group_id: str) -> DeleteGroupResult:
        """Delete a group and all its screenshots (hard delete)."""
        # Check if group exists
        group = await self.repo.get_group_by_id(group_id)
        if not group:
            raise ValueError(f"Group '{group_id}' not found")

        # Get screenshot IDs
        screenshot_ids = await self.repo.get_screenshot_ids_for_group(group_id)

        # Cascade delete
        counts = await self.repo.delete_group_cascade(group_id, screenshot_ids)

        return DeleteGroupResult(
            success=True,
            group_id=group_id,
            screenshots_deleted=counts.screenshots_deleted,
            annotations_deleted=counts.annotations_deleted,
            message=f"Group '{group_id}' deleted successfully",
        )

    # =========================================================================
    # OCR Recalculation
    # =========================================================================

    async def recalculate_ocr_totals(
        self,
        limit: int = 100,
        group_id: str | None = None,
    ) -> RecalculateOcrResult:
        """Recalculate OCR totals for screenshots missing extracted_total."""
        screenshots = await self.repo.get_screenshots_missing_ocr_total(group_id=group_id, limit=limit)

        from screenshot_processor.core.ocr import find_screenshot_total_usage

        total_missing = len(screenshots)
        processed = 0
        updated = 0
        failed = 0

        for screenshot in screenshots:
            processed += 1
            try:
                file_path = screenshot.file_path
                if not Path(file_path).exists():
                    logger.warning(
                        "Screenshot file not found", extra={"screenshot_id": screenshot.id, "file_path": file_path}
                    )
                    failed += 1
                    continue

                img = cv2.imread(file_path)
                if img is None:
                    logger.warning(
                        "Could not read screenshot image",
                        extra={"screenshot_id": screenshot.id, "file_path": file_path},
                    )
                    failed += 1
                    continue

                img = convert_dark_mode(img)
                total, _ = find_screenshot_total_usage(img)

                if total and total.strip():
                    screenshot.extracted_total = total.strip()
                    updated += 1
                    logger.info(
                        "Extracted OCR total", extra={"screenshot_id": screenshot.id, "extracted_total": total.strip()}
                    )
                else:
                    logger.info("No OCR total found", extra={"screenshot_id": screenshot.id})

            except Exception as e:
                logger.error("Error extracting OCR total", extra={"screenshot_id": screenshot.id, "error": str(e)})
                failed += 1

        await self.repo.db.commit()

        return RecalculateOcrResult(
            success=True,
            total_missing=total_missing,
            processed=processed,
            updated=updated,
            failed=failed,
            message=f"Processed {processed} screenshots: {updated} updated, {failed} failed",
        )

    # =========================================================================
    # Bulk Reprocess
    # =========================================================================

    async def get_screenshot_ids_for_reprocess(
        self,
        group_id: str | None = None,
        limit: int = 1000,
    ) -> list[int]:
        """Get screenshot IDs that need reprocessing."""
        return await self.repo.get_screenshot_ids_for_reprocess(group_id=group_id, limit=limit)
