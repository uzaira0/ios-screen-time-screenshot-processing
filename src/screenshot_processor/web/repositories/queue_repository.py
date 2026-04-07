"""Repository for queue-related database operations.

This module extracts queue queries from QueueService into a dedicated class,
providing a clean separation between queue business logic and data access.
"""

from __future__ import annotations

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    Annotation,
    ConsensusResult,
    ProcessingStatus,
    QueueStateStatus,
    Screenshot,
    UserQueueState,
)


class QueueRepository:
    """Repository for queue-related database operations.

    Encapsulates all queries related to the annotation queue:
    finding the next screenshot, tracking user progress, and
    gathering queue statistics.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_next_screenshot(
        self,
        user_id: int,
        group_id: str | None = None,
        processing_status: str | None = None,
        browse_mode: bool = False,
    ) -> Screenshot | None:
        """Find the next screenshot for annotation.

        MULTI-RATER DESIGN: All users see ALL screenshots. The queue only excludes:
        1. Screenshots this specific user has already annotated/verified
        2. Screenshots this specific user has explicitly skipped

        Args:
            user_id: Current user ID.
            group_id: Optional group filter.
            processing_status: Optional processing status filter.
            browse_mode: If True, includes screenshots the user has already annotated.

        Returns:
            Next Screenshot or None if queue is empty.
        """
        conditions = []

        # Exclude screenshots this user has already annotated (unless browse mode)
        if not browse_mode:
            subquery_user_annotations = (
                select(Annotation.screenshot_id).where(Annotation.user_id == user_id).scalar_subquery()
            )

            subquery_user_skipped = (
                select(UserQueueState.screenshot_id)
                .where(
                    and_(
                        UserQueueState.user_id == user_id,
                        UserQueueState.status == QueueStateStatus.SKIPPED.value,
                    )
                )
                .scalar_subquery()
            )

            conditions.extend(
                [
                    Screenshot.id.notin_(subquery_user_annotations),
                    Screenshot.id.notin_(subquery_user_skipped),
                ]
            )

        # Add processing_status filter if provided, otherwise show all statuses
        if processing_status:
            conditions.append(Screenshot.processing_status == ProcessingStatus(processing_status))
        else:
            conditions.append(
                Screenshot.processing_status.in_(
                    [
                        ProcessingStatus.PENDING,
                        ProcessingStatus.COMPLETED,
                        ProcessingStatus.FAILED,
                        ProcessingStatus.SKIPPED,
                    ]
                )
            )

        # Add group filter if provided
        if group_id:
            conditions.append(Screenshot.group_id == group_id)

        stmt = (
            select(Screenshot)
            .where(and_(*conditions))
            .order_by(
                Screenshot.processing_status.desc(),
                Screenshot.current_annotation_count.asc(),
                Screenshot.uploaded_at.asc(),
            )
            .limit(1)
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_queue_state(
        self,
        user_id: int,
        screenshot_id: int,
    ) -> UserQueueState | None:
        """Get existing queue state for a user/screenshot pair.

        Returns:
            Existing UserQueueState or None if not found.
        """
        stmt = select(UserQueueState).where(
            and_(
                UserQueueState.user_id == user_id,
                UserQueueState.screenshot_id == screenshot_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def create_queue_state(
        self,
        user_id: int,
        screenshot_id: int,
        queue_status: str = QueueStateStatus.PENDING.value,
    ) -> UserQueueState:
        """Create a new queue state entry.

        Does NOT commit — caller is responsible for committing.
        """
        new_state = UserQueueState(
            user_id=user_id,
            screenshot_id=screenshot_id,
            status=queue_status,
        )
        self.db.add(new_state)
        return new_state

    async def get_disputed_screenshots(self, user_id: int) -> list[Screenshot]:
        """Get disputed screenshots the user hasn't annotated.

        Finds screenshots with consensus disagreements that still need
        annotations and haven't been annotated by this user.

        Returns:
            List of disputed Screenshot objects.
        """
        subquery_user_annotations = (
            select(Annotation.screenshot_id).where(Annotation.user_id == user_id).scalar_subquery()
        )

        stmt = (
            select(Screenshot)
            .join(ConsensusResult)
            .where(
                and_(
                    ConsensusResult.has_consensus == False,  # noqa: E712
                    Screenshot.current_annotation_count < Screenshot.target_annotations,
                    Screenshot.id.notin_(subquery_user_annotations),
                )
            )
            .order_by(Screenshot.uploaded_at.asc())
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_skipped_queue_state(
        self,
        user_id: int,
        screenshot_id: int,
    ) -> UserQueueState | None:
        """Get a skipped queue state for a user/screenshot pair.

        Returns:
            UserQueueState if found with SKIPPED status, else None.
        """
        stmt = select(UserQueueState).where(
            and_(
                UserQueueState.user_id == user_id,
                UserQueueState.screenshot_id == screenshot_id,
                UserQueueState.status == QueueStateStatus.SKIPPED.value,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_queue_stats(self, user_id: int) -> dict:
        """Get queue statistics for a user.

        MULTI-RATER DESIGN: "remaining" = screenshots this user hasn't annotated yet.
        All users see all screenshots, so remaining count is per-user.

        Combined into 2 queries (status counts + remaining, user completed).
        """
        subquery_user_annotations = (
            select(Annotation.screenshot_id).where(Annotation.user_id == user_id).scalar_subquery()
        )

        subquery_user_skipped = (
            select(UserQueueState.screenshot_id)
            .where(
                and_(
                    UserQueueState.user_id == user_id,
                    UserQueueState.status == QueueStateStatus.SKIPPED.value,
                )
            )
            .scalar_subquery()
        )

        non_deleted_statuses = [
            ProcessingStatus.PENDING,
            ProcessingStatus.COMPLETED,
            ProcessingStatus.FAILED,
            ProcessingStatus.SKIPPED,
        ]

        # Query 1: Status counts + remaining + user_completed in one query
        # Uses scalar subqueries to avoid JOINs
        combined_stmt = select(
            func.count(Screenshot.id)
            .filter(Screenshot.processing_status == ProcessingStatus.COMPLETED)
            .label("auto_processed"),
            func.count(Screenshot.id).filter(Screenshot.processing_status == ProcessingStatus.PENDING).label("pending"),
            func.count(Screenshot.id).filter(Screenshot.processing_status == ProcessingStatus.FAILED).label("failed"),
            func.count(Screenshot.id).filter(Screenshot.processing_status == ProcessingStatus.SKIPPED).label("skipped"),
            # Remaining: non-deleted, not annotated by user, not skipped by user
            select(func.count(Screenshot.id)).where(
                and_(
                    Screenshot.processing_status.in_(non_deleted_statuses),
                    Screenshot.id.notin_(subquery_user_annotations),
                    Screenshot.id.notin_(subquery_user_skipped),
                )
            ).scalar_subquery().label("total_remaining"),
            # User completed
            select(func.count(Annotation.id)).where(
                Annotation.user_id == user_id
            ).scalar_subquery().label("user_completed"),
        )
        result = await self.db.execute(combined_stmt)
        row = result.one()

        return {
            "total_remaining": row.total_remaining,
            "user_completed": row.user_completed,
            "auto_processed": row.auto_processed,
            "pending": row.pending,
            "failed": row.failed,
            "skipped": row.skipped,
        }
