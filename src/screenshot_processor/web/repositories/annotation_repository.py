"""Repository for Annotation database operations."""

from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from screenshot_processor.web.database.models import Annotation


class AnnotationRepository:
    """Repository for Annotation database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, annotation_id: int) -> Annotation | None:
        """Get annotation by ID."""
        result = await self.db.execute(select(Annotation).where(Annotation.id == annotation_id))
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, annotation_id: int) -> Annotation | None:
        """Get annotation by ID with row lock for safe concurrent updates."""
        result = await self.db.execute(select(Annotation).where(Annotation.id == annotation_id).with_for_update())
        return result.scalar_one_or_none()

    async def get_by_id_with_issues(self, annotation_id: int) -> Annotation | None:
        """Get annotation by ID with issues eagerly loaded."""
        result = await self.db.execute(
            select(Annotation).options(selectinload(Annotation.issues)).where(Annotation.id == annotation_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user_and_screenshot(self, user_id: int, screenshot_id: int) -> Annotation | None:
        """Get annotation by user and screenshot."""
        result = await self.db.execute(
            select(Annotation).where(
                and_(
                    Annotation.screenshot_id == screenshot_id,
                    Annotation.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: int, skip: int = 0, limit: int = 100) -> list[Annotation]:
        """Get annotations by user with pagination."""
        result = await self.db.execute(
            select(Annotation)
            .options(selectinload(Annotation.issues))
            .where(Annotation.user_id == user_id)
            .offset(skip)
            .limit(limit)
            .order_by(Annotation.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_screenshot(self, screenshot_id: int) -> list[Annotation]:
        """Get all annotations for a screenshot."""
        result = await self.db.execute(
            select(Annotation).options(selectinload(Annotation.user)).where(Annotation.screenshot_id == screenshot_id)
        )
        return list(result.scalars().all())

    async def list_by_screenshot_with_users(
        self, screenshot_id: int, user_ids: list[int] | None = None
    ) -> list[Annotation]:
        """Get annotations for a screenshot, optionally filtered by user IDs."""
        stmt = (
            select(Annotation).options(selectinload(Annotation.user)).where(Annotation.screenshot_id == screenshot_id)
        )
        if user_ids:
            stmt = stmt.where(Annotation.user_id.in_(user_ids))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, annotation: Annotation) -> Annotation:
        """Create a new annotation."""
        self.db.add(annotation)
        await self.db.flush()
        return annotation

    async def delete(self, annotation: Annotation) -> None:
        """Delete an annotation."""
        await self.db.delete(annotation)
