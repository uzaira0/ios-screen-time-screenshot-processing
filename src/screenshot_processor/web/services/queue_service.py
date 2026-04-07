from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import QueueStateStatus
from ..repositories.queue_repository import QueueRepository

if TYPE_CHECKING:
    from ..database.models import Screenshot

logger = logging.getLogger(__name__)


class QueueService:
    @staticmethod
    async def get_next_screenshot(
        db: AsyncSession,
        user_id: int,
        group_id: str | None = None,
        processing_status: str | None = None,
        browse_mode: bool = False,
    ) -> Screenshot | None:
        """
        Get the next screenshot for annotation.

        MULTI-RATER DESIGN: All users see ALL screenshots. The queue only excludes:
        1. Screenshots this specific user has already annotated/verified
        2. Screenshots this specific user has explicitly skipped

        This ensures every rater can annotate every screenshot for cross-rater consensus.

        Args:
            db: Database session
            user_id: Current user ID
            group_id: Optional group filter
            processing_status: Optional processing status filter
            browse_mode: If True, allows browsing all screenshots including ones
                         the user has already annotated (for review purposes).
        """
        repo = QueueRepository(db)
        screenshot = await repo.get_next_screenshot(
            user_id,
            group_id=group_id,
            processing_status=processing_status,
            browse_mode=browse_mode,
        )

        if screenshot:
            existing_state = await repo.get_queue_state(user_id, screenshot.id)

            if not existing_state:
                try:
                    await repo.create_queue_state(user_id, screenshot.id, QueueStateStatus.PENDING.value)
                    await db.commit()
                except IntegrityError:
                    # Race condition: another request created the entry - this is expected, ignore
                    await db.rollback()
                except Exception as e:
                    # Unexpected error - log and rollback
                    logger.warning("Failed to create queue state", extra={"error": str(e)})
                    await db.rollback()

        return screenshot

    @staticmethod
    async def get_disputed_screenshots(db: AsyncSession, user_id: int) -> list[Screenshot]:
        repo = QueueRepository(db)
        return await repo.get_disputed_screenshots(user_id)

    @staticmethod
    async def mark_screenshot_skipped(db: AsyncSession, user_id: int, screenshot_id: int) -> None:
        repo = QueueRepository(db)
        existing_state = await repo.get_queue_state(user_id, screenshot_id)

        if existing_state:
            existing_state.status = QueueStateStatus.SKIPPED.value
        else:
            await repo.create_queue_state(user_id, screenshot_id, QueueStateStatus.SKIPPED.value)

        await db.commit()

    @staticmethod
    async def unskip_screenshot(db: AsyncSession, user_id: int, screenshot_id: int) -> bool:
        """
        Remove the skipped status from a screenshot for a specific user.

        Returns True if the screenshot was unskipped, False if it wasn't skipped.
        """
        repo = QueueRepository(db)
        existing_state = await repo.get_skipped_queue_state(user_id, screenshot_id)

        if existing_state:
            # Change status back to pending so it can appear in the user's queue again
            existing_state.status = QueueStateStatus.PENDING.value
            await db.commit()
            return True

        return False

    @staticmethod
    async def get_queue_stats(db: AsyncSession, user_id: int) -> dict:
        """
        Get queue statistics for a user.

        MULTI-RATER DESIGN: "remaining" = screenshots this user hasn't annotated yet.
        All users see all screenshots, so remaining count is per-user.
        """
        repo = QueueRepository(db)
        return await repo.get_queue_stats(user_id)
