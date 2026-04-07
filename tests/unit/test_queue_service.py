"""
Unit tests for QueueService.

Tests queue navigation, skip/unskip, statistics, and browse mode.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
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
from screenshot_processor.web.services.queue_service import QueueService


@pytest.mark.asyncio
class TestGetNextScreenshot:
    """Tests for get_next_screenshot."""

    async def test_returns_pending_screenshot(self, db_session: AsyncSession):
        user = User(username="q_user1")
        db_session.add(user)
        await db_session.commit()

        screenshot = Screenshot(
            file_path="/queue/s1.png",
            image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
            target_annotations=2,
        )
        db_session.add(screenshot)
        await db_session.commit()

        result = await QueueService.get_next_screenshot(db_session, user.id)
        assert result is not None

    async def test_empty_queue_returns_none(self, db_session: AsyncSession):
        user = User(username="q_empty")
        db_session.add(user)
        await db_session.commit()

        result = await QueueService.get_next_screenshot(db_session, user.id)
        assert result is None

    async def test_excludes_already_annotated(self, db_session: AsyncSession):
        user = User(username="q_annotated")
        db_session.add(user)
        await db_session.commit()

        s1 = Screenshot(
            file_path="/queue/annotated1.png",
            image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
        )
        db_session.add(s1)
        await db_session.commit()

        db_session.add(Annotation(
            screenshot_id=s1.id, user_id=user.id, hourly_values={"0": 5},
        ))
        await db_session.commit()

        result = await QueueService.get_next_screenshot(db_session, user.id)
        assert result is None

    async def test_excludes_skipped_by_user(self, db_session: AsyncSession):
        user = User(username="q_skipped")
        db_session.add(user)
        await db_session.commit()

        s1 = Screenshot(
            file_path="/queue/skipped1.png",
            image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
        )
        db_session.add(s1)
        await db_session.commit()

        db_session.add(UserQueueState(
            user_id=user.id, screenshot_id=s1.id, status="skipped",
        ))
        await db_session.commit()

        result = await QueueService.get_next_screenshot(db_session, user.id)
        assert result is None

    async def test_group_filter(self, db_session: AsyncSession):
        user = User(username="q_group")
        db_session.add(user)
        group = Group(id="q-group-a", name="Group A", image_type="screen_time")
        db_session.add(group)
        await db_session.commit()

        s1 = Screenshot(
            file_path="/queue/ga1.png", image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
            group_id="q-group-a",
        )
        s2 = Screenshot(
            file_path="/queue/no_group.png", image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
        )
        db_session.add_all([s1, s2])
        await db_session.commit()

        result = await QueueService.get_next_screenshot(db_session, user.id, group_id="q-group-a")
        assert result is not None
        assert result.group_id == "q-group-a"

    async def test_processing_status_filter(self, db_session: AsyncSession):
        user = User(username="q_status")
        db_session.add(user)
        await db_session.commit()

        s_completed = Screenshot(
            file_path="/queue/completed.png", image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
        )
        s_failed = Screenshot(
            file_path="/queue/failed.png", image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.FAILED,
        )
        db_session.add_all([s_completed, s_failed])
        await db_session.commit()

        result = await QueueService.get_next_screenshot(
            db_session, user.id, processing_status="failed"
        )
        assert result is not None
        assert result.processing_status == ProcessingStatus.FAILED


@pytest.mark.asyncio
class TestMarkScreenshotSkipped:
    """Tests for mark_screenshot_skipped."""

    async def test_creates_new_skipped_state(self, db_session: AsyncSession):
        user = User(username="q_skip_new")
        screenshot = Screenshot(file_path="/queue/skip_new.png", image_type="screen_time")
        db_session.add_all([user, screenshot])
        await db_session.commit()

        await QueueService.mark_screenshot_skipped(db_session, user.id, screenshot.id)

        row = await db_session.execute(
            select(UserQueueState).where(
                UserQueueState.user_id == user.id,
                UserQueueState.screenshot_id == screenshot.id,
            )
        )
        state = row.scalar_one_or_none()
        assert state is not None
        assert state.status == "skipped"

    async def test_updates_existing_state_to_skipped(self, db_session: AsyncSession):
        user = User(username="q_skip_upd")
        screenshot = Screenshot(file_path="/queue/skip_upd.png", image_type="screen_time")
        db_session.add_all([user, screenshot])
        await db_session.commit()

        db_session.add(UserQueueState(
            user_id=user.id, screenshot_id=screenshot.id, status="pending",
        ))
        await db_session.commit()

        await QueueService.mark_screenshot_skipped(db_session, user.id, screenshot.id)

        row = await db_session.execute(
            select(UserQueueState).where(
                UserQueueState.user_id == user.id,
                UserQueueState.screenshot_id == screenshot.id,
            )
        )
        state = row.scalar_one()
        assert state.status == "skipped"


@pytest.mark.asyncio
class TestUnskipScreenshot:
    """Tests for unskip_screenshot."""

    async def test_unskip_returns_true(self, db_session: AsyncSession):
        user = User(username="q_unskip")
        screenshot = Screenshot(file_path="/queue/unskip.png", image_type="screen_time")
        db_session.add_all([user, screenshot])
        await db_session.commit()

        db_session.add(UserQueueState(
            user_id=user.id, screenshot_id=screenshot.id, status="skipped",
        ))
        await db_session.commit()

        result = await QueueService.unskip_screenshot(db_session, user.id, screenshot.id)
        assert result is True

    async def test_unskip_changes_status_to_pending(self, db_session: AsyncSession):
        user = User(username="q_unskip2")
        screenshot = Screenshot(file_path="/queue/unskip2.png", image_type="screen_time")
        db_session.add_all([user, screenshot])
        await db_session.commit()

        state = UserQueueState(
            user_id=user.id, screenshot_id=screenshot.id, status="skipped",
        )
        db_session.add(state)
        await db_session.commit()

        await QueueService.unskip_screenshot(db_session, user.id, screenshot.id)
        await db_session.refresh(state)
        assert state.status == "pending"

    async def test_unskip_not_skipped_returns_false(self, db_session: AsyncSession):
        user = User(username="q_unskip_no")
        screenshot = Screenshot(file_path="/queue/unskip_no.png", image_type="screen_time")
        db_session.add_all([user, screenshot])
        await db_session.commit()

        result = await QueueService.unskip_screenshot(db_session, user.id, screenshot.id)
        assert result is False


@pytest.mark.asyncio
class TestGetQueueStats:
    """Tests for get_queue_stats."""

    async def test_empty_queue_stats(self, db_session: AsyncSession):
        user = User(username="q_stats_empty")
        db_session.add(user)
        await db_session.commit()

        stats = await QueueService.get_queue_stats(db_session, user.id)
        assert isinstance(stats, dict)
        assert stats["user_completed"] == 0

    async def test_stats_reflect_annotations(self, db_session: AsyncSession):
        user = User(username="q_stats_ann")
        db_session.add(user)
        await db_session.commit()

        s1 = Screenshot(
            file_path="/queue/stats1.png", image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
        )
        s2 = Screenshot(
            file_path="/queue/stats2.png", image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
        )
        db_session.add_all([s1, s2])
        await db_session.commit()

        db_session.add(Annotation(
            screenshot_id=s1.id, user_id=user.id, hourly_values={"0": 10},
        ))
        await db_session.commit()

        stats = await QueueService.get_queue_stats(db_session, user.id)
        assert stats["user_completed"] == 1


@pytest.mark.asyncio
class TestGetDisputedScreenshots:
    """Tests for get_disputed_screenshots."""

    async def test_no_disputes(self, db_session: AsyncSession):
        user = User(username="q_no_dispute")
        db_session.add(user)
        await db_session.commit()

        result = await QueueService.get_disputed_screenshots(db_session, user.id)
        assert result == []
