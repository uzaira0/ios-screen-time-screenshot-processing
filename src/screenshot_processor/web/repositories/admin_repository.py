"""Repository for Admin database operations.

This module extracts database queries from admin routes and services into a
dedicated class, providing a clean separation between HTTP/business logic
and data access.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, func, not_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    Annotation,
    AnnotationStatus,
    ConsensusResult,
    Group,
    ProcessingStatus,
    Screenshot,
    User,
    UserQueueState,
)


@dataclass
class UserWithStats:
    """User row joined with annotation statistics."""

    user: User
    annotations_count: int
    avg_time_spent_seconds: float


@dataclass
class GroupDeleteCounts:
    """Counts of rows deleted during a group cascade delete."""

    screenshot_ids: list[int]
    screenshots_deleted: int
    annotations_deleted: int
    consensus_deleted: int
    queue_states_deleted: int


@dataclass
class OrphanedCounts:
    """Counts of orphaned entries in the database."""

    orphaned_annotations: int
    orphaned_consensus: int
    orphaned_queue_states: int
    screenshots_without_group: int


@dataclass
class CleanupCounts:
    """Counts of orphaned entries deleted during cleanup."""

    deleted_annotations: int
    deleted_consensus: int
    deleted_queue_states: int


@dataclass
class StuckScreenshotCounts:
    """Counts of stuck screenshots by status."""

    pending_count: int
    processing_count: int


class AdminRepository:
    """Repository for admin-specific database operations.

    This class encapsulates all database queries used by admin routes,
    providing a clean interface for the route handlers and service layer.

    Usage:
        repo = AdminRepository(db)
        users = await repo.get_users_with_stats()
        user = await repo.get_user_by_id(123)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # User Management
    # =========================================================================

    async def get_users_with_stats(self) -> list[UserWithStats]:
        """Get all users with their annotation count and avg time stats.

        Uses a single query with LEFT JOIN to avoid N+1 problem.
        """
        stmt = (
            select(
                User,
                func.count(Annotation.id).label("annotations_count"),
                func.coalesce(func.avg(Annotation.time_spent_seconds), 0).label("avg_time"),
            )
            .outerjoin(Annotation, Annotation.user_id == User.id)
            .group_by(User.id)
            .order_by(User.created_at.desc())
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        return [
            UserWithStats(
                user=row.User,
                annotations_count=row.annotations_count,
                avg_time_spent_seconds=round(float(row.avg_time), 2),
            )
            for row in rows
        ]

    async def get_user_by_id(self, user_id: int) -> User | None:
        """Get a single user by ID."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def update_user(
        self,
        user: User,
        *,
        is_active: bool | None = None,
        role: str | None = None,
    ) -> User:
        """Update user fields, commit, and return the refreshed user."""
        if is_active is not None:
            user.is_active = is_active
        if role is not None:
            user.role = role

        await self.db.commit()
        await self.db.refresh(user)
        return user

    # =========================================================================
    # Test Data Reset
    # =========================================================================

    async def reset_test_data(self) -> None:
        """Delete all queue states and annotations, reset screenshot counters."""
        # Clear all user queue states
        await self.db.execute(delete(UserQueueState))

        # Clear all annotations
        await self.db.execute(delete(Annotation))

        # Bulk reset screenshot annotation counts
        await self.db.execute(
            update(Screenshot).values(
                current_annotation_count=0,
                annotation_status=AnnotationStatus.PENDING,
                has_consensus=False,
                verified_by_user_ids=None,
            )
        )

        await self.db.commit()

    # =========================================================================
    # Group Management
    # =========================================================================

    async def get_group_by_id(self, group_id: str) -> Group | None:
        """Get a group by ID."""
        result = await self.db.execute(select(Group).where(Group.id == group_id))
        return result.scalar_one_or_none()

    async def get_screenshot_ids_for_group(self, group_id: str) -> list[int]:
        """Get all screenshot IDs belonging to a group."""
        result = await self.db.execute(select(Screenshot.id).where(Screenshot.group_id == group_id))
        return [row[0] for row in result.fetchall()]

    async def delete_group_cascade(self, group_id: str, screenshot_ids: list[int]) -> GroupDeleteCounts:
        """Delete a group and all related DB rows (annotations, consensus, queue states, screenshots).

        File system cleanup should be handled by the caller.

        Args:
            group_id: The group ID to delete.
            screenshot_ids: Pre-fetched screenshot IDs for the group.

        Returns:
            GroupDeleteCounts with row counts for each table.
        """
        annotations_deleted = 0
        consensus_deleted = 0
        queue_states_deleted = 0

        if screenshot_ids:
            # Delete annotations
            result = await self.db.execute(delete(Annotation).where(Annotation.screenshot_id.in_(screenshot_ids)))
            annotations_deleted = result.rowcount

            # Delete consensus results
            result = await self.db.execute(
                delete(ConsensusResult).where(ConsensusResult.screenshot_id.in_(screenshot_ids))
            )
            consensus_deleted = result.rowcount

            # Delete user queue states
            result = await self.db.execute(
                delete(UserQueueState).where(UserQueueState.screenshot_id.in_(screenshot_ids))
            )
            queue_states_deleted = result.rowcount

            # Delete screenshots
            await self.db.execute(delete(Screenshot).where(Screenshot.group_id == group_id))

        # Delete the group itself
        await self.db.execute(delete(Group).where(Group.id == group_id))

        await self.db.commit()

        return GroupDeleteCounts(
            screenshot_ids=screenshot_ids,
            screenshots_deleted=len(screenshot_ids),
            annotations_deleted=annotations_deleted,
            consensus_deleted=consensus_deleted,
            queue_states_deleted=queue_states_deleted,
        )

    # =========================================================================
    # OCR Total Recalculation
    # =========================================================================

    async def get_screenshots_missing_ocr_total(
        self,
        *,
        group_id: str | None = None,
        limit: int = 100,
    ) -> list[Screenshot]:
        """Get screen_time screenshots that are missing extracted_total."""
        query = select(Screenshot).where(
            Screenshot.image_type == "screen_time",
            or_(
                Screenshot.extracted_total.is_(None),
                Screenshot.extracted_total == "",
            ),
        )

        if group_id:
            query = query.where(Screenshot.group_id == group_id)

        query = query.limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # =========================================================================
    # Bulk Reprocess
    # =========================================================================

    async def get_screenshot_ids_for_reprocess(
        self,
        *,
        group_id: str | None = None,
        limit: int = 1000,
    ) -> list[int]:
        """Get screen_time screenshot IDs eligible for reprocessing."""
        query = select(Screenshot.id).where(
            Screenshot.image_type == "screen_time",
        )

        if group_id:
            query = query.where(Screenshot.group_id == group_id)

        query = query.limit(limit)

        result = await self.db.execute(query)
        return [row[0] for row in result.fetchall()]

    # =========================================================================
    # Retry Stuck Screenshots
    # =========================================================================

    async def count_stuck_screenshots(
        self,
        *,
        group_id: str | None = None,
    ) -> StuckScreenshotCounts:
        """Count screenshots stuck in PENDING or PROCESSING status."""
        pending_query = select(func.count(Screenshot.id)).where(
            Screenshot.processing_status == ProcessingStatus.PENDING,
        )
        processing_query = select(func.count(Screenshot.id)).where(
            Screenshot.processing_status == ProcessingStatus.PROCESSING,
        )

        if group_id:
            pending_query = pending_query.where(Screenshot.group_id == group_id)
            processing_query = processing_query.where(Screenshot.group_id == group_id)

        pending_result = await self.db.execute(pending_query)
        pending_count = pending_result.scalar() or 0

        processing_result = await self.db.execute(processing_query)
        processing_count = processing_result.scalar() or 0

        return StuckScreenshotCounts(
            pending_count=pending_count,
            processing_count=processing_count,
        )

    async def mark_processing_as_failed(
        self,
        *,
        group_id: str | None = None,
    ) -> int:
        """Mark all PROCESSING screenshots as FAILED. Returns number of rows updated."""
        update_query = (
            update(Screenshot)
            .where(Screenshot.processing_status == ProcessingStatus.PROCESSING)
            .values(
                processing_status=ProcessingStatus.FAILED,
                processing_issues=["Marked as failed by admin: stuck in PROCESSING status"],
                processed_at=datetime.now(timezone.utc),
            )
        )
        if group_id:
            update_query = update_query.where(Screenshot.group_id == group_id)

        result = await self.db.execute(update_query)
        await self.db.commit()
        return result.rowcount

    async def get_pending_screenshot_ids(
        self,
        *,
        group_id: str | None = None,
    ) -> list[int]:
        """Get IDs of all PENDING screenshots."""
        ids_query = select(Screenshot.id).where(
            Screenshot.processing_status == ProcessingStatus.PENDING,
        )
        if group_id:
            ids_query = ids_query.where(Screenshot.group_id == group_id)

        result = await self.db.execute(ids_query)
        return [row[0] for row in result.fetchall()]

    # =========================================================================
    # Orphaned Entry Detection & Cleanup
    # =========================================================================

    async def find_orphaned_entries(self) -> OrphanedCounts:
        """Find orphaned database entries referencing non-existent screenshots."""
        screenshot_ids_subquery = select(Screenshot.id)

        orphaned_annotations_result = await self.db.execute(
            select(func.count(Annotation.id)).where(not_(Annotation.screenshot_id.in_(screenshot_ids_subquery)))
        )
        orphaned_annotations = orphaned_annotations_result.scalar() or 0

        orphaned_consensus_result = await self.db.execute(
            select(func.count(ConsensusResult.id)).where(
                not_(ConsensusResult.screenshot_id.in_(screenshot_ids_subquery))
            )
        )
        orphaned_consensus = orphaned_consensus_result.scalar() or 0

        orphaned_queue_result = await self.db.execute(
            select(func.count(UserQueueState.id)).where(not_(UserQueueState.screenshot_id.in_(screenshot_ids_subquery)))
        )
        orphaned_queue_states = orphaned_queue_result.scalar() or 0

        screenshots_no_group_result = await self.db.execute(
            select(func.count(Screenshot.id)).where(Screenshot.group_id.is_(None))
        )
        screenshots_without_group = screenshots_no_group_result.scalar() or 0

        return OrphanedCounts(
            orphaned_annotations=orphaned_annotations,
            orphaned_consensus=orphaned_consensus,
            orphaned_queue_states=orphaned_queue_states,
            screenshots_without_group=screenshots_without_group,
        )

    async def cleanup_orphaned_entries(self) -> CleanupCounts:
        """Delete orphaned entries and commit. Returns counts of deleted rows."""
        screenshot_ids_subquery = select(Screenshot.id)

        result1 = await self.db.execute(
            delete(Annotation).where(not_(Annotation.screenshot_id.in_(screenshot_ids_subquery)))
        )
        deleted_annotations = result1.rowcount

        result2 = await self.db.execute(
            delete(ConsensusResult).where(not_(ConsensusResult.screenshot_id.in_(screenshot_ids_subquery)))
        )
        deleted_consensus = result2.rowcount

        result3 = await self.db.execute(
            delete(UserQueueState).where(not_(UserQueueState.screenshot_id.in_(screenshot_ids_subquery)))
        )
        deleted_queue_states = result3.rowcount

        await self.db.commit()

        return CleanupCounts(
            deleted_annotations=deleted_annotations,
            deleted_consensus=deleted_consensus,
            deleted_queue_states=deleted_queue_states,
        )

    # =========================================================================
    # Stale UserQueueState Cleanup
    # =========================================================================

    async def cleanup_stale_queue_states(self) -> int:
        """Delete UserQueueState rows for screenshots that are completed or deleted.

        These queue state entries are no longer useful once the screenshot has
        finished processing (completed) or been soft-deleted.

        Returns:
            Number of deleted rows.
        """
        completed_or_deleted = select(Screenshot.id).where(
            Screenshot.processing_status.in_([ProcessingStatus.COMPLETED, ProcessingStatus.DELETED])
        )

        result = await self.db.execute(
            delete(UserQueueState).where(UserQueueState.screenshot_id.in_(completed_or_deleted))
        )
        deleted = result.rowcount or 0
        return deleted
