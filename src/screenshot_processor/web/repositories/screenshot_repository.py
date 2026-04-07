"""Repository for Screenshot database operations.

This module extracts database queries from routes into a dedicated class,
providing a clean separation between HTTP handling and data access.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import String, and_, case, cast, delete, extract, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database import (
    Annotation,
    AnnotationStatus,
    ConsensusResult,
    Group,
    GroupRead,
    ProcessingStatus,
    Screenshot,
    ScreenshotRead,
    User,
    UserQueueState,
)


@dataclass
class ScreenshotStats:
    """Statistics about screenshots in the system."""

    total: int
    pending_annotation: int
    completed_annotation: int
    pending_processing: int
    auto_processed: int
    failed: int
    skipped: int
    total_annotations: int
    with_consensus: int
    with_disagreements: int
    users_active: int


@dataclass
class PaginatedResult:
    """Result of a paginated query."""

    items: list[Screenshot]
    total: int
    has_next: bool
    has_prev: bool


class ScreenshotRepository:
    """Repository for Screenshot database operations.

    This class encapsulates all database queries related to screenshots,
    providing a clean interface for the route handlers.

    Usage:
        repo = ScreenshotRepository(db)
        screenshot = await repo.get_by_id(123)
        screenshots = await repo.list_with_filters(group_id="abc", page=1)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, screenshot_id: int) -> Screenshot | None:
        """Get a screenshot by ID.

        Returns None if not found (caller decides whether to raise 404).
        """
        result = await self.db.execute(select(Screenshot).where(Screenshot.id == screenshot_id))
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, screenshot_id: int) -> Screenshot | None:
        """Get a screenshot with row lock for safe concurrent updates.

        Use this when modifying fields that could be updated concurrently
        (e.g., verified_by_user_ids, annotation counts).
        """
        result = await self.db.execute(select(Screenshot).where(Screenshot.id == screenshot_id).with_for_update())
        return result.scalar_one_or_none()

    async def get_by_id_for_update_nowait(self, screenshot_id: int) -> Screenshot | None:
        """Get a screenshot with row lock using NOWAIT.

        Returns the screenshot if the lock is acquired, or raises
        sqlalchemy.exc.OperationalError if the row is already locked
        by another transaction (concurrent processing).
        """
        result = await self.db.execute(
            select(Screenshot).where(Screenshot.id == screenshot_id).with_for_update(nowait=True)
        )
        return result.scalar_one_or_none()

    async def get_usernames_for_ids(self, user_ids: Sequence[int]) -> dict[int, str]:
        """Get username mapping for a list of user IDs.

        Returns a dict mapping user_id -> username.
        """
        if not user_ids:
            return {}

        result = await self.db.execute(select(User.id, User.username).where(User.id.in_(user_ids)))
        return {row.id: row.username for row in result.all()}

    async def enrich_with_usernames(self, screenshot: Screenshot) -> ScreenshotRead:
        """Convert Screenshot to ScreenshotRead with verified_by_usernames populated."""
        data = ScreenshotRead.model_validate(screenshot)

        if screenshot.verified_by_user_ids:
            user_map = await self.get_usernames_for_ids(screenshot.verified_by_user_ids)
            data.verified_by_usernames = [user_map.get(uid, f"User {uid}") for uid in screenshot.verified_by_user_ids]

        return data

    async def enrich_many_with_usernames(self, screenshots: Sequence[Screenshot]) -> list[ScreenshotRead]:
        """Convert list of Screenshots to ScreenshotRead with usernames populated."""
        if not screenshots:
            return []

        # Collect all unique user IDs
        all_user_ids: set[int] = set()
        for s in screenshots:
            if s.verified_by_user_ids:
                all_user_ids.update(s.verified_by_user_ids)

        # Fetch all usernames in one query
        user_map = await self.get_usernames_for_ids(list(all_user_ids))

        # Enrich each screenshot
        enriched = []
        for s in screenshots:
            data = ScreenshotRead.model_validate(s)
            if s.verified_by_user_ids:
                data.verified_by_usernames = [user_map.get(uid, f"User {uid}") for uid in s.verified_by_user_ids]
            enriched.append(data)

        return enriched

    # Shared SQL WHERE predicate for "needs attention" screenshots.
    # Used by needs_attention_conditions() (ORM filter), list_groups(), and get_group().
    # Single source of truth — change here to update all three.
    _NEEDS_ATTENTION_WHERE_SQL = """
        s.processing_status = 'COMPLETED'
        AND (
          -- Bar/OCR total mismatch (excludes seconds-only like "9s")
          (s.extracted_hourly_data IS NOT NULL AND s.extracted_total IS NOT NULL
           AND ((regexp_match(s.extracted_total, '(\\d+)\\s*h'))[1] IS NOT NULL
                OR (regexp_match(s.extracted_total, '(\\d+)\\s*m'))[1] IS NOT NULL)
           AND ABS(
             (SELECT COALESCE(SUM(value::numeric), 0)
              FROM json_each_text(s.extracted_hourly_data::json)
              WHERE key ~ '^\\d+$')
             - (
               COALESCE((regexp_match(s.extracted_total, '(\\d+)\\s*h'))[1]::int * 60, 0) +
               COALESCE((regexp_match(s.extracted_total, '(\\d+)\\s*m'))[1]::int, 0)
             )
           ) >= 1)
          OR
          -- Missing title
          ((s.extracted_title IS NULL OR s.extracted_title = '')
           AND s.extracted_hourly_data IS NOT NULL)
        )
    """

    @staticmethod
    def needs_attention_conditions() -> list:
        """Build SQLAlchemy conditions for the "needs attention" filter.

        Matches COMPLETED screenshots that have any of:
        - Bar total differs from OCR total by >= 1 minute (excluding seconds-only totals)
        - Missing/empty extracted_title (app name not detected)

        Does NOT add a processing_status filter — callers should add their own
        if needed, to avoid silent conflicts with user-supplied status filters.
        """
        from sqlalchemy import text as sa_text

        # Subquery: bar/OCR total mismatch (excludes seconds-only totals like "9s")
        bar_mismatch_subq = select(Screenshot.id).where(
            Screenshot.processing_status == ProcessingStatus.COMPLETED,
            Screenshot.extracted_hourly_data.isnot(None),
            Screenshot.extracted_total.isnot(None),
            # Guard: at least one of h/m must be present (excludes "9s" seconds-only)
            sa_text("""
                ((regexp_match(screenshots.extracted_total, '(\\d+)\\s*h'))[1] IS NOT NULL
                 OR (regexp_match(screenshots.extracted_total, '(\\d+)\\s*m'))[1] IS NOT NULL)
            """),
            sa_text("""
                ABS(
                    (SELECT COALESCE(SUM(value::numeric), 0)
                     FROM json_each_text(screenshots.extracted_hourly_data::json)
                     WHERE key ~ '^\\d+$')
                    - (
                      COALESCE((regexp_match(screenshots.extracted_total, '(\\d+)\\s*h'))[1]::int * 60, 0) +
                      COALESCE((regexp_match(screenshots.extracted_total, '(\\d+)\\s*m'))[1]::int, 0)
                    )
                ) >= 1
            """),
        )

        return [
            or_(
                # Bar/OCR total mismatch
                Screenshot.id.in_(bar_mismatch_subq),
                # Missing title (name not detected) — needs manual entry
                and_(
                    or_(Screenshot.extracted_title.is_(None), Screenshot.extracted_title == ""),
                    Screenshot.extracted_hourly_data.isnot(None),
                    Screenshot.processing_status == ProcessingStatus.COMPLETED,
                ),
            ),
        ]

    async def list_with_filters(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        group_id: str | None = None,
        processing_status: str | None = None,
        verified_by_me: bool | None = None,
        verified_by_others: bool | None = None,
        current_user_id: int | None = None,
        search: str | None = None,
        totals_mismatch: bool | None = None,
        sort_by: str = "id",
        sort_order: str = "asc",
    ) -> PaginatedResult:
        """List screenshots with comprehensive filtering and pagination.

        Args:
            page: Page number (1-indexed)
            page_size: Items per page
            group_id: Filter by group ID
            processing_status: Filter by processing status
            verified_by_me: Filter by current user's verification (True=verified by me, False=not verified by me).
                            Requires current_user_id to be set.
            verified_by_others: Filter for screenshots verified by others but not current user (True only).
                            Requires current_user_id to be set.
            current_user_id: The current user's ID for user-specific filtering
            search: Search by ID, participant_id, or extracted_title
            sort_by: Sort field (id, uploaded_at, processing_status)
            sort_order: Sort direction (asc, desc)

        Returns:
            PaginatedResult with items, total count, and pagination info
        """
        stmt = select(Screenshot)
        count_stmt = select(func.count(Screenshot.id))

        conditions = []

        # Group filter
        if group_id:
            conditions.append(Screenshot.group_id == group_id)

        # Processing status filter
        if processing_status:
            conditions.append(Screenshot.processing_status == processing_status)

        # Helper to check if user ID is in verified_by_user_ids array
        # Uses PostgreSQL JSONB containment operator for index-friendly lookups
        def user_in_verified_list(user_id: int):
            from sqlalchemy import literal
            from sqlalchemy.dialects.postgresql import JSONB

            return cast(Screenshot.verified_by_user_ids, JSONB).op("@>")(cast(literal(f"[{user_id}]"), JSONB))

        def has_verifications():
            return and_(
                Screenshot.verified_by_user_ids.isnot(None),
                cast(Screenshot.verified_by_user_ids, String) != "null",
                cast(Screenshot.verified_by_user_ids, String) != "[]",
            )

        # User-specific verified filter
        if verified_by_me is not None and current_user_id is not None:
            if verified_by_me is True:
                # Verified BY ME: my user ID is in the verified_by_user_ids array
                conditions.append(user_in_verified_list(current_user_id))
            else:
                # NOT verified by me: my user ID is NOT in the array (or array is null/empty)
                conditions.append(
                    or_(
                        ~has_verifications(),
                        ~user_in_verified_list(current_user_id),
                    )
                )

        # Verified by others filter (verified by someone, but not by current user)
        if verified_by_others is True and current_user_id is not None:
            # Has verifications AND current user is NOT in the list
            conditions.append(has_verifications())
            conditions.append(~user_in_verified_list(current_user_id))

        # Search filter
        if search:
            search_term = f"%{search}%"
            conditions.append(
                or_(
                    cast(Screenshot.id, String).like(search_term),
                    Screenshot.participant_id.ilike(search_term),
                    Screenshot.extracted_title.ilike(search_term),
                )
            )

        # Totals mismatch / needs-attention filter (server-side SQL)
        if totals_mismatch is True:
            conditions.extend(self.needs_attention_conditions())

        # Apply conditions
        if conditions:
            stmt = stmt.where(and_(*conditions))
            count_stmt = count_stmt.where(and_(*conditions))

        # Get total count
        result = await self.db.execute(count_stmt)
        total = result.scalar_one()

        # Sorting
        sort_column = Screenshot.id
        if sort_by == "uploaded_at":
            sort_column = Screenshot.uploaded_at
        elif sort_by == "processing_status":
            sort_column = Screenshot.processing_status

        if sort_order == "desc":
            stmt = stmt.order_by(sort_column.desc())
        else:
            stmt = stmt.order_by(sort_column.asc())

        # Pagination
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)

        result = await self.db.execute(stmt)
        screenshots = list(result.scalars().all())

        return PaginatedResult(
            items=screenshots,
            total=total,
            has_next=offset + len(screenshots) < total,
            has_prev=page > 1,
        )

    async def get_stats(self) -> ScreenshotStats:
        """Get comprehensive screenshot statistics.

        Uses conditional aggregation to minimize database round trips.
        Combined into 2 queries (screenshots+annotations+consensus, users).
        """
        # Query 1: All screenshot, annotation, and consensus stats in one shot
        # Uses scalar subqueries for annotation count and consensus stats
        # to avoid JOINs that would multiply rows
        combined_stmt = select(
            func.count(Screenshot.id).label("total"),
            func.count(
                case((Screenshot.annotation_status == AnnotationStatus.PENDING, 1))
            ).label("pending_annotation"),
            func.count(
                case((Screenshot.current_annotation_count >= Screenshot.target_annotations, 1))
            ).label("completed_annotation"),
            func.count(case((Screenshot.processing_status == ProcessingStatus.PENDING, 1))).label("pending_processing"),
            func.count(case((Screenshot.processing_status == ProcessingStatus.COMPLETED, 1))).label("auto_processed"),
            func.count(case((Screenshot.processing_status == ProcessingStatus.FAILED, 1))).label("failed"),
            func.count(case((Screenshot.processing_status == ProcessingStatus.SKIPPED, 1))).label("skipped"),
            # Inline scalar subqueries
            select(func.count(Annotation.id)).scalar_subquery().label("total_annotations"),
            select(
                func.count(case((ConsensusResult.has_consensus == True, 1)))  # noqa: E712
            ).scalar_subquery().label("with_consensus"),
            select(
                func.count(case((ConsensusResult.has_consensus == False, 1)))  # noqa: E712
            ).scalar_subquery().label("with_disagreements"),
            select(func.count(User.id)).where(
                User.is_active == True  # noqa: E712
            ).scalar_subquery().label("users_active"),
        )
        result = await self.db.execute(combined_stmt)
        row = result.one()

        return ScreenshotStats(
            total=row.total,
            pending_annotation=row.pending_annotation,
            completed_annotation=row.completed_annotation,
            pending_processing=row.pending_processing,
            auto_processed=row.auto_processed,
            failed=row.failed,
            skipped=row.skipped,
            total_annotations=row.total_annotations,
            with_consensus=row.with_consensus,
            with_disagreements=row.with_disagreements,
            users_active=row.users_active,
        )

    async def list_groups(self) -> list[GroupRead]:
        """List all groups with screenshot counts by processing status."""
        # Compute processing time in seconds: processed_at - processing_started_at
        processing_time_expr = extract("epoch", Screenshot.processed_at - Screenshot.processing_started_at)
        # Only count processing time for screenshots that have both timestamps
        valid_time_case = case(
            (
                and_(
                    Screenshot.processing_started_at.isnot(None),
                    Screenshot.processed_at.isnot(None),
                ),
                processing_time_expr,
            ),
            else_=None,
        )

        stmt = (
            select(
                Group,
                func.count(Screenshot.id).label("total_count"),
                func.count(case((Screenshot.processing_status == ProcessingStatus.PENDING, 1))).label("pending"),
                func.count(case((Screenshot.processing_status == ProcessingStatus.COMPLETED, 1))).label("completed"),
                func.count(case((Screenshot.processing_status == ProcessingStatus.FAILED, 1))).label("failed"),
                func.count(case((Screenshot.processing_status == ProcessingStatus.SKIPPED, 1))).label("skipped"),
                # Processing time metrics
                func.sum(valid_time_case).label("total_processing_time"),
                func.avg(valid_time_case).label("avg_processing_time"),
                func.min(valid_time_case).label("min_processing_time"),
                func.max(valid_time_case).label("max_processing_time"),
            )
            .outerjoin(Screenshot, Screenshot.group_id == Group.id)
            .group_by(Group.id)
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        # Compute "needs attention" counts per group using shared SQL predicate.
        mismatch_result = await self.db.execute(
            text(f"""
                SELECT s.group_id, COUNT(*) as cnt
                FROM screenshots s
                WHERE {self._NEEDS_ATTENTION_WHERE_SQL}
                GROUP BY s.group_id
            """)
        )
        mismatch_counts: dict[str, int] = {r[0]: r[1] for r in mismatch_result.all()}

        return [
            GroupRead(
                id=row.Group.id,
                name=row.Group.name,
                image_type=row.Group.image_type,
                created_at=row.Group.created_at,
                screenshot_count=row.total_count,
                processing_pending=row.pending,
                processing_completed=row.completed,
                processing_failed=row.failed,
                processing_skipped=row.skipped,
                totals_mismatch_count=mismatch_counts.get(row.Group.id, 0),
                total_processing_time_seconds=float(row.total_processing_time) if row.total_processing_time else None,
                avg_processing_time_seconds=float(row.avg_processing_time) if row.avg_processing_time else None,
                min_processing_time_seconds=float(row.min_processing_time) if row.min_processing_time else None,
                max_processing_time_seconds=float(row.max_processing_time) if row.max_processing_time else None,
            )
            for row in rows
        ]

    async def get_group(self, group_id: str) -> GroupRead | None:
        """Get a single group by ID with screenshot counts."""
        # Compute processing time in seconds: processed_at - processing_started_at
        processing_time_expr = extract("epoch", Screenshot.processed_at - Screenshot.processing_started_at)
        # Only count processing time for screenshots that have both timestamps
        valid_time_case = case(
            (
                and_(
                    Screenshot.processing_started_at.isnot(None),
                    Screenshot.processed_at.isnot(None),
                ),
                processing_time_expr,
            ),
            else_=None,
        )

        stmt = (
            select(
                Group,
                func.count(Screenshot.id).label("total_count"),
                func.count(case((Screenshot.processing_status == ProcessingStatus.PENDING, 1))).label("pending"),
                func.count(case((Screenshot.processing_status == ProcessingStatus.COMPLETED, 1))).label("completed"),
                func.count(case((Screenshot.processing_status == ProcessingStatus.FAILED, 1))).label("failed"),
                func.count(case((Screenshot.processing_status == ProcessingStatus.SKIPPED, 1))).label("skipped"),
                # Processing time metrics
                func.sum(valid_time_case).label("total_processing_time"),
                func.avg(valid_time_case).label("avg_processing_time"),
                func.min(valid_time_case).label("min_processing_time"),
                func.max(valid_time_case).label("max_processing_time"),
            )
            .outerjoin(Screenshot, Screenshot.group_id == Group.id)
            .where(Group.id == group_id)
            .group_by(Group.id)
        )
        result = await self.db.execute(stmt)
        row = result.one_or_none()

        if not row:
            return None

        # Needs-attention count using shared SQL predicate.
        mismatch_result = await self.db.execute(
            text(f"""
                SELECT COUNT(*) FROM screenshots s
                WHERE s.group_id = :gid AND {self._NEEDS_ATTENTION_WHERE_SQL}
            """),
            {"gid": group_id},
        )
        mismatch_count = mismatch_result.scalar_one()

        return GroupRead(
            id=row.Group.id,
            name=row.Group.name,
            image_type=row.Group.image_type,
            created_at=row.Group.created_at,
            screenshot_count=row.total_count,
            processing_pending=row.pending,
            processing_completed=row.completed,
            processing_failed=row.failed,
            processing_skipped=row.skipped,
            totals_mismatch_count=mismatch_count,
            total_processing_time_seconds=float(row.total_processing_time) if row.total_processing_time else None,
            avg_processing_time_seconds=float(row.avg_processing_time) if row.avg_processing_time else None,
            min_processing_time_seconds=float(row.min_processing_time) if row.min_processing_time else None,
            max_processing_time_seconds=float(row.max_processing_time) if row.max_processing_time else None,
        )

    async def get_annotation_count(self, screenshot_id: int) -> int:
        """Get the number of annotations for a screenshot."""
        stmt = select(func.count(Annotation.id)).where(Annotation.screenshot_id == screenshot_id)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def update(self, screenshot: Screenshot, **fields: object) -> Screenshot:
        """Update screenshot fields and commit.

        Args:
            screenshot: The screenshot to update
            **fields: Fields to update

        Returns:
            Updated screenshot
        """
        for field, value in fields.items():
            setattr(screenshot, field, value)

        await self.db.commit()
        await self.db.refresh(screenshot)
        return screenshot

    async def find_by_content_hash(self, content_hash: str) -> Screenshot | None:
        """Find a screenshot by content hash for dedup."""
        result = await self.db.execute(select(Screenshot).where(Screenshot.content_hash == content_hash))
        return result.scalar_one_or_none()

    async def find_potential_duplicate(self, screenshot: Screenshot) -> dict | None:
        """Find a potential semantic duplicate of this screenshot.

        A duplicate is another screenshot with the same:
        - participant_id
        - screenshot_date
        - extracted_title
        - extracted_total

        Returns dict with {id, processing_status} of the duplicate, or None.
        Checks completed and skipped screenshots so the UI can show
        whether the duplicate was already handled.
        """
        # Need all 4 fields to have values to check for duplicates
        if not all(
            [
                screenshot.participant_id,
                screenshot.screenshot_date,
                screenshot.extracted_title,
                screenshot.extracted_total,
            ]
        ):
            return None

        stmt = (
            select(Screenshot.id, Screenshot.processing_status)
            .where(
                and_(
                    Screenshot.id != screenshot.id,
                    Screenshot.participant_id == screenshot.participant_id,
                    Screenshot.screenshot_date == screenshot.screenshot_date,
                    Screenshot.extracted_title == screenshot.extracted_title,
                    Screenshot.extracted_total == screenshot.extracted_total,
                    Screenshot.processing_status.in_(
                        [ProcessingStatus.COMPLETED, ProcessingStatus.SKIPPED]
                    ),
                )
            )
            .order_by(Screenshot.id.asc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return {"id": row[0], "processing_status": row[1].value if row[1] else "completed"}

    # =========================================================================
    # Batch / filtering queries (extracted from routes)
    # =========================================================================

    async def get_by_group(self, group_id: str) -> list[Screenshot]:
        """Get all screenshots in a group.

        Used for batch operations.
        """
        result = await self.db.execute(select(Screenshot).where(Screenshot.group_id == group_id))
        return list(result.scalars().all())

    async def get_preprocessing_metadata_by_group(self, group_id: str) -> list:
        """Get processing_metadata + OCR fields for all screenshots in a group.

        Much lighter than get_by_group — loads only the columns needed for
        preprocessing summary (stage status + OCR mismatch detection).
        """
        result = await self.db.execute(
            select(
                Screenshot.processing_metadata,
                Screenshot.extracted_hourly_data,
                Screenshot.extracted_total,
            ).where(Screenshot.group_id == group_id)
        )
        return list(result.all())

    async def list_basic(
        self,
        *,
        annotation_status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Screenshot]:
        """List screenshots with optional status filter and pagination.

        Simple listing without user-specific or verified filters.
        """
        stmt = select(Screenshot)

        if annotation_status:
            stmt = stmt.where(Screenshot.annotation_status == annotation_status)

        stmt = stmt.offset(skip).limit(limit).order_by(Screenshot.uploaded_at.desc())

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_ids_by_group(
        self,
        group_id: str,
        screenshot_ids: list[int] | None = None,
    ) -> list[int]:
        """Get screenshot IDs in a group, optionally filtered to specific IDs.

        Args:
            group_id: Group to filter by.
            screenshot_ids: If provided, only return IDs that are both in
                this list AND belong to the group.

        Returns:
            List of screenshot IDs.
        """
        if screenshot_ids:
            stmt = select(Screenshot.id).where(
                Screenshot.id.in_(screenshot_ids),
                Screenshot.group_id == group_id,
            )
        else:
            stmt = select(Screenshot.id).where(Screenshot.group_id == group_id).order_by(Screenshot.id)

        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]

    async def get_by_ids_or_group(
        self,
        screenshot_ids: list[int] | None = None,
        group_id: str | None = None,
    ) -> list[Screenshot]:
        """Get screenshots by a list of IDs or by group_id.

        At least one of screenshot_ids or group_id must be provided.

        Returns:
            List of Screenshot objects.
        """
        if screenshot_ids:
            stmt = select(Screenshot).where(Screenshot.id.in_(screenshot_ids))
        elif group_id:
            stmt = select(Screenshot).where(Screenshot.group_id == group_id)
        else:
            raise ValueError("At least one of screenshot_ids or group_id must be provided")

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # =========================================================================
    # Navigation queries (extracted from routes & screenshot_service)
    # =========================================================================

    async def navigate_with_filters(
        self,
        screenshot_id: int,
        direction: str,
        conditions: list,
    ) -> NavigationResult:
        """Navigate screenshots with filter conditions.

        Args:
            screenshot_id: Current screenshot ID for directional navigation.
            direction: "current", "next", or "prev".
            conditions: Pre-built SQLAlchemy filter conditions.

        Returns:
            NavigationResult with screenshot, index, total, and has_next/has_prev.
        """
        # Get the target screenshot based on direction
        if direction == "next":
            stmt = select(Screenshot).where(Screenshot.id > screenshot_id)
            if conditions:
                stmt = stmt.where(and_(*conditions))
            stmt = stmt.order_by(Screenshot.id.asc()).limit(1)
        elif direction == "prev":
            stmt = select(Screenshot).where(Screenshot.id < screenshot_id)
            if conditions:
                stmt = stmt.where(and_(*conditions))
            stmt = stmt.order_by(Screenshot.id.desc()).limit(1)
        else:
            stmt = select(Screenshot).where(Screenshot.id == screenshot_id)
            if conditions:
                stmt = stmt.where(and_(*conditions))

        result = await self.db.execute(stmt)
        screenshot = result.scalar_one_or_none()

        if not screenshot:
            # Only need total count when screenshot not found
            count_stmt = select(func.count(Screenshot.id))
            if conditions:
                count_stmt = count_stmt.where(and_(*conditions))
            result = await self.db.execute(count_stmt)
            total_in_filter = result.scalar_one()
            return NavigationResult(
                screenshot=None,
                current_index=0,
                total_in_filter=total_in_filter,
                has_next=False,
                has_prev=False,
            )

        # Single query: get total count AND count of items before this screenshot
        # has_next/has_prev are derived from current_index and total (no extra queries)
        base_conditions = and_(*conditions) if conditions else True
        combined_stmt = select(
            func.count(Screenshot.id).label("total"),
            func.count(case((Screenshot.id < screenshot.id, 1))).label("before_count"),
        ).where(base_conditions)
        result = await self.db.execute(combined_stmt)
        row = result.one()
        total_in_filter = row.total
        current_index = row.before_count + 1

        return NavigationResult(
            screenshot=screenshot,
            current_index=current_index,
            total_in_filter=total_in_filter,
            has_next=current_index < total_in_filter,
            has_prev=current_index > 1,
        )

    # =========================================================================
    # Content-hash batch queries (extracted from upload routes)
    # =========================================================================

    async def find_existing_by_content_hashes(self, content_hashes: list[str]) -> dict[str, int]:
        """Find screenshots matching any of the given content hashes.

        Returns:
            Dict mapping content_hash -> screenshot_id for existing matches.
        """
        if not content_hashes:
            return {}

        result = await self.db.execute(
            select(Screenshot.content_hash, Screenshot.id).where(Screenshot.content_hash.in_(content_hashes))
        )
        return {row[0]: row[1] for row in result.fetchall()}

    async def find_existing_file_paths(self, file_paths: list[str]) -> set[str]:
        """Find which file_paths already exist in the database.

        Returns:
            Set of file paths that already have screenshot records.
        """
        if not file_paths:
            return set()

        result = await self.db.execute(select(Screenshot.file_path).where(Screenshot.file_path.in_(file_paths)))
        return {row[0] for row in result.fetchall()}

    # =========================================================================
    # Upload duplicate cleanup (extracted from upload routes)
    # =========================================================================

    async def clear_screenshot_related_data(self, screenshot_ids: Sequence[int]) -> None:
        """Clear annotations, consensus results, and queue states for screenshots.

        Used when re-uploading duplicates to ensure a fresh start.
        Does NOT commit — caller is responsible for committing.
        """
        if not screenshot_ids:
            return

        id_list = list(screenshot_ids)
        await self.db.execute(delete(Annotation).where(Annotation.screenshot_id.in_(id_list)))
        await self.db.execute(delete(ConsensusResult).where(ConsensusResult.screenshot_id.in_(id_list)))
        await self.db.execute(delete(UserQueueState).where(UserQueueState.screenshot_id.in_(id_list)))

    async def reset_screenshot_state(self, screenshot_ids: Sequence[int]) -> None:
        """Reset annotation/verification state for screenshots.

        Used after clearing related data for re-uploaded duplicates.
        Does NOT commit — caller is responsible for committing.
        """
        if not screenshot_ids:
            return

        await self.db.execute(
            update(Screenshot)
            .where(Screenshot.id.in_(list(screenshot_ids)))
            .values(
                current_annotation_count=0,
                annotation_status=AnnotationStatus.PENDING,
                has_consensus=False,
                verified_by_user_ids=None,
            )
        )

    # =========================================================================
    # Export queries (extracted from CSV export route)
    # =========================================================================

    async def get_screenshots_with_consensus(self, conditions: list) -> list:
        """Get screenshots joined with consensus results for export.

        Args:
            conditions: Pre-built SQLAlchemy filter conditions.

        Returns:
            List of (Screenshot, ConsensusResult|None) tuples.
        """
        stmt = select(Screenshot, ConsensusResult).outerjoin(
            ConsensusResult, Screenshot.id == ConsensusResult.screenshot_id
        )
        if conditions:
            stmt = stmt.where(and_(*conditions))
        stmt = stmt.order_by(Screenshot.uploaded_at)

        result = await self.db.execute(stmt)
        return list(result.all())

    # =========================================================================
    # Queries extracted from routes (Issue #23)
    # =========================================================================

    async def find_by_file_path(self, file_path: str) -> Screenshot | None:
        """Find a screenshot by its file path.

        Used during upload to detect duplicates by file path.
        """
        result = await self.db.execute(select(Screenshot).where(Screenshot.file_path == file_path))
        return result.scalar_one_or_none()

    async def get_group_by_id(self, group_id: str) -> Group | None:
        """Get a group by its primary key.

        Returns None if the group does not exist.
        """
        result = await self.db.execute(select(Group).where(Group.id == group_id))
        return result.scalar_one_or_none()

    async def upsert_group(self, group_id: str, image_type: str) -> bool:
        """Create a group if it doesn't exist (upsert with ON CONFLICT DO NOTHING).

        Returns True if a new group was created, False if it already existed.
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        insert_stmt = (
            pg_insert(Group)
            .values(id=group_id, name=group_id, image_type=image_type)
            .on_conflict_do_nothing(index_elements=["id"])
        )
        result = await self.db.execute(insert_stmt)
        return result.rowcount > 0  # type: ignore[attr-defined]

    async def soft_delete(self, screenshot: Screenshot) -> str:
        """Soft-delete a screenshot by setting status to DELETED.

        Stores the previous status in processing_metadata for restore.
        Does NOT commit — caller is responsible for committing.

        Returns the previous processing status value.
        """
        from sqlalchemy.orm.attributes import flag_modified

        previous_status = screenshot.processing_status.value
        metadata = dict(screenshot.processing_metadata or {})
        metadata["pre_delete_status"] = previous_status
        screenshot.processing_metadata = metadata
        flag_modified(screenshot, "processing_metadata")
        screenshot.processing_status = ProcessingStatus.DELETED
        return previous_status

    async def restore_from_delete(self, screenshot: Screenshot) -> str:
        """Restore a soft-deleted screenshot to its previous status.

        Does NOT commit — caller is responsible for committing.

        Returns the restored processing status value.
        Raises ValueError if the stored pre_delete_status is invalid.
        """
        from sqlalchemy.orm.attributes import flag_modified

        metadata = dict(screenshot.processing_metadata or {})
        previous_status = metadata.get("pre_delete_status", "completed")

        # Validate status
        screenshot.processing_status = ProcessingStatus(previous_status)

        metadata.pop("pre_delete_status", None)
        screenshot.processing_metadata = metadata if metadata else None
        flag_modified(screenshot, "processing_metadata")
        return previous_status


@dataclass
class NavigationResult:
    """Result of a navigation query."""

    screenshot: Screenshot | None
    current_index: int
    total_in_filter: int
    has_next: bool
    has_prev: bool
