"""Repository for Consensus database operations."""

from __future__ import annotations

from sqlalchemy import String, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from screenshot_processor.web.database.models import (
    Annotation,
    ConsensusResult,
    Group,
    Screenshot,
    User,
)


class ConsensusRepository:
    """Repository for Consensus and verification tier operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_consensus_result(self, screenshot_id: int) -> ConsensusResult | None:
        """Get consensus result for a screenshot."""
        result = await self.db.execute(select(ConsensusResult).where(ConsensusResult.screenshot_id == screenshot_id))
        return result.scalar_one_or_none()

    async def get_or_create_consensus_result(self, screenshot_id: int) -> ConsensusResult:
        """Get or create consensus result for a screenshot."""
        existing = await self.get_consensus_result(screenshot_id)
        if existing:
            return existing

        new_result = ConsensusResult(screenshot_id=screenshot_id)
        self.db.add(new_result)
        await self.db.flush()
        return new_result

    async def update_consensus_result(
        self,
        screenshot_id: int,
        has_consensus: bool,
        consensus_values: dict | None = None,
    ) -> ConsensusResult:
        """Update or create consensus result."""
        result = await self.get_or_create_consensus_result(screenshot_id)
        result.has_consensus = has_consensus
        result.consensus_values = consensus_values
        return result

    async def get_verified_screenshots_in_group(self, group_id: str) -> list[Screenshot]:
        """Get all verified screenshots in a group with their annotations and users."""
        # Note: JSON columns can have SQL NULL or JSON null (literal "null" string)
        result = await self.db.execute(
            select(Screenshot)
            .options(selectinload(Screenshot.annotations).selectinload(Annotation.user))
            .where(
                Screenshot.group_id == group_id,
                Screenshot.verified_by_user_ids.isnot(None),
                cast(Screenshot.verified_by_user_ids, String) != "null",
                cast(Screenshot.verified_by_user_ids, String) != "[]",
            )
            .order_by(Screenshot.screenshot_date, Screenshot.id)
        )
        return list(result.scalars().all())

    async def get_all_groups_with_counts(self) -> list[dict]:
        """Get all groups with total screenshot counts in a single query.

        Returns a list of dicts with keys: group, total_screenshots.
        Eliminates the N+1 query pattern of calling get_group_screenshot_count per group.
        """
        stmt = (
            select(
                Group,
                func.count(Screenshot.id).label("total_screenshots"),
            )
            .outerjoin(Screenshot, Screenshot.group_id == Group.id)
            .group_by(Group.id)
            .order_by(Group.name)
        )
        result = await self.db.execute(stmt)
        rows = result.all()
        return [
            {
                "group": row.Group,
                "total_screenshots": row.total_screenshots,
            }
            for row in rows
        ]

    async def get_screenshot_with_annotations(self, screenshot_id: int) -> Screenshot | None:
        """Get screenshot with annotations and users eagerly loaded."""
        result = await self.db.execute(
            select(Screenshot)
            .options(
                selectinload(Screenshot.annotations).selectinload(Annotation.user),
                selectinload(Screenshot.resolved_by),
            )
            .where(Screenshot.id == screenshot_id)
        )
        return result.scalar_one_or_none()

    async def get_users_by_ids(self, user_ids: list[int]) -> list:
        """Get users by their IDs."""
        result = await self.db.execute(select(User).where(User.id.in_(user_ids)))
        return list(result.scalars().all())

    async def get_group_by_id(self, group_id: str) -> Group | None:
        """Get group by ID."""
        result = await self.db.execute(select(Group).where(Group.id == group_id))
        return result.scalar_one_or_none()

    async def get_screenshot_with_annotations_for_update(self, screenshot_id: int) -> Screenshot | None:
        """Get screenshot with annotations eagerly loaded and row lock.

        Used by consensus analysis to prevent race conditions when
        multiple annotations are submitted concurrently.
        """
        result = await self.db.execute(
            select(Screenshot)
            .options(selectinload(Screenshot.annotations))
            .where(Screenshot.id == screenshot_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_consensus_counts(self) -> dict:
        """Get consensus-related counts for the summary endpoint (single query)."""
        stmt = select(
            func.count(
                case((ConsensusResult.has_consensus == True, 1))  # noqa: E712
            ).label("total_with_consensus"),
            func.count(
                case((ConsensusResult.has_consensus == False, 1))  # noqa: E712
            ).label("total_with_disagreements"),
            select(func.count(Screenshot.id)).where(
                Screenshot.current_annotation_count >= Screenshot.target_annotations
            ).scalar_subquery().label("total_completed"),
        )
        result = await self.db.execute(stmt)
        row = result.one()

        return {
            "total_with_consensus": row.total_with_consensus,
            "total_with_disagreements": row.total_with_disagreements,
            "total_completed": row.total_completed,
        }

    async def get_consensus_summary_stats(self) -> dict:
        """Get summary statistics for consensus analysis (single query)."""
        stmt = select(
            select(func.count(Screenshot.id)).scalar_subquery().label("total_screenshots"),
            func.count(ConsensusResult.id).label("with_consensus"),
            func.count(
                case((ConsensusResult.has_consensus == False, 1))  # noqa: E712
            ).label("with_disagreements"),
            # disagreement_count column doesn't exist — count disagreement rows instead
            func.count(
                case((ConsensusResult.has_consensus == False, 1))  # noqa: E712
            ).label("total_disagreements"),
        )
        result = await self.db.execute(stmt)
        row = result.one()

        return {
            "total_screenshots": row.total_screenshots,
            "screenshots_with_consensus": row.with_consensus,
            "screenshots_with_disagreements": row.with_disagreements,
            "total_disagreements": row.total_disagreements,
            "avg_disagreements_per_screenshot": (
                row.total_disagreements / row.with_disagreements if row.with_disagreements > 0 else 0
            ),
        }
