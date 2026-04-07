"""
Unit tests for service layer business logic.

Tests ConsensusService, QueueService, and ProcessingService with mocked dependencies.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    Annotation,
    AnnotationStatus,
    ConsensusResult,
    ProcessingStatus,
    Screenshot,
    User,
)
from screenshot_processor.web.services.consensus_service import (
    ConsensusService,
    ConsensusStrategy,
    DisagreementSeverity,
)
from screenshot_processor.web.services.queue_service import QueueService


class TestConsensusService:
    """Test ConsensusService business logic."""

    def test_classify_disagreement_severity_none(self):
        """Test severity classification for no disagreement."""
        severity = ConsensusService.classify_disagreement_severity(0)
        assert severity == DisagreementSeverity.NONE

    def test_classify_disagreement_severity_minor(self):
        """Test severity classification for minor disagreement."""
        severity = ConsensusService.classify_disagreement_severity(1)
        assert severity == DisagreementSeverity.MINOR

        severity = ConsensusService.classify_disagreement_severity(2)
        assert severity == DisagreementSeverity.MINOR

    def test_classify_disagreement_severity_moderate(self):
        """Test severity classification for moderate disagreement."""
        severity = ConsensusService.classify_disagreement_severity(3)
        assert severity == DisagreementSeverity.MODERATE

        severity = ConsensusService.classify_disagreement_severity(5)
        assert severity == DisagreementSeverity.MODERATE

    def test_classify_disagreement_severity_major(self):
        """Test severity classification for major disagreement."""
        severity = ConsensusService.classify_disagreement_severity(6)
        assert severity == DisagreementSeverity.MAJOR

        severity = ConsensusService.classify_disagreement_severity(100)
        assert severity == DisagreementSeverity.MAJOR

    def test_calculate_consensus_median(self):
        """Test consensus calculation using median strategy."""
        values = [10.0, 15.0, 20.0]
        result = ConsensusService.calculate_consensus_value(values, strategy=ConsensusStrategy.MEDIAN)
        assert result == 15.0

    def test_calculate_consensus_median_even_count(self):
        """Test median with even number of values."""
        values = [10.0, 20.0, 30.0, 40.0]
        result = ConsensusService.calculate_consensus_value(values, strategy=ConsensusStrategy.MEDIAN)
        assert result == 25.0  # Average of middle two

    def test_calculate_consensus_mean(self):
        """Test consensus calculation using mean strategy."""
        values = [10.0, 15.0, 20.0]
        result = ConsensusService.calculate_consensus_value(values, strategy=ConsensusStrategy.MEAN)
        assert result == 15.0

    def test_calculate_consensus_mode(self):
        """Test consensus calculation using mode strategy."""
        values = [10.0, 10.0, 15.0, 20.0]
        result = ConsensusService.calculate_consensus_value(values, strategy=ConsensusStrategy.MODE)
        assert result == 10.0

    def test_calculate_consensus_mode_all_unique(self):
        """Test mode with all unique values returns first value (Python 3.8+ behavior)."""
        values = [10.0, 15.0, 20.0]  # All unique - Python 3.8+ returns first value
        result = ConsensusService.calculate_consensus_value(values, strategy=ConsensusStrategy.MODE)
        # In Python 3.8+, mode returns first value when all values are unique
        assert result == 10.0

    def test_calculate_consensus_empty_values(self):
        """Test consensus with empty values list."""
        values = []
        result = ConsensusService.calculate_consensus_value(values)
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_analyze_consensus_insufficient_annotations(self, db_session: AsyncSession):
        """Test consensus analysis with less than 2 annotations."""
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        db_session.add(screenshot)
        await db_session.commit()

        user = User(username="testuser")
        db_session.add(user)
        await db_session.commit()

        annotation = Annotation(
            screenshot_id=screenshot.id,
            user_id=user.id,
            hourly_values={"0": 10},
        )
        db_session.add(annotation)
        await db_session.commit()

        result = await ConsensusService.analyze_consensus(db_session, screenshot.id)

        assert result is not None
        assert result["has_consensus"] is True
        assert result["total_annotations"] == 1
        assert len(result["disagreements"]) == 0

    @pytest.mark.asyncio
    async def test_analyze_consensus_full_agreement(self, db_session: AsyncSession):
        """Test consensus analysis with full agreement."""
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        db_session.add(screenshot)
        await db_session.commit()

        user1 = User(username="user1")
        user2 = User(username="user2")
        db_session.add_all([user1, user2])
        await db_session.commit()

        annotation1 = Annotation(
            screenshot_id=screenshot.id,
            user_id=user1.id,
            hourly_values={"0": 10, "1": 15},
        )
        annotation2 = Annotation(
            screenshot_id=screenshot.id,
            user_id=user2.id,
            hourly_values={"0": 10, "1": 15},
        )
        db_session.add_all([annotation1, annotation2])
        await db_session.commit()

        result = await ConsensusService.analyze_consensus(db_session, screenshot.id)

        assert result["has_consensus"] is True
        assert result["total_annotations"] == 2
        assert len(result["disagreements"]) == 0
        assert result["consensus_hourly_values"]["0"] == 10.0
        assert result["consensus_hourly_values"]["1"] == 15.0

    @pytest.mark.asyncio
    async def test_analyze_consensus_with_disagreements(self, db_session: AsyncSession):
        """Test consensus analysis with disagreements."""
        # Set threshold to 0 for any difference
        with patch.object(ConsensusService, "DISAGREEMENT_THRESHOLD_MINUTES", 0):
            screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
            db_session.add(screenshot)
            await db_session.commit()

            user1 = User(username="user1")
            user2 = User(username="user2")
            db_session.add_all([user1, user2])
            await db_session.commit()

            annotation1 = Annotation(
                screenshot_id=screenshot.id,
                user_id=user1.id,
                hourly_values={"0": 10, "1": 15},
            )
            annotation2 = Annotation(
                screenshot_id=screenshot.id,
                user_id=user2.id,
                hourly_values={"0": 20, "1": 15},  # 10 min difference in hour 0
            )
            db_session.add_all([annotation1, annotation2])
            await db_session.commit()

            result = await ConsensusService.analyze_consensus(db_session, screenshot.id)

            assert result["has_consensus"] is False
            assert result["has_disagreements"] is True
            assert len(result["disagreements"]) == 1
            assert result["disagreements"][0]["hour"] == "0"
            assert result["disagreements"][0]["max_difference"] == 5.0  # From median

    @pytest.mark.asyncio
    async def test_analyze_consensus_updates_screenshot(self, db_session: AsyncSession):
        """Test consensus analysis updates screenshot.has_consensus."""
        screenshot = Screenshot(
            file_path="/test.png",
            image_type="screen_time",
            has_consensus=None,
        )
        db_session.add(screenshot)
        await db_session.commit()

        user1 = User(username="user1")
        user2 = User(username="user2")
        db_session.add_all([user1, user2])
        await db_session.commit()

        annotation1 = Annotation(
            screenshot_id=screenshot.id,
            user_id=user1.id,
            hourly_values={"0": 10},
        )
        annotation2 = Annotation(
            screenshot_id=screenshot.id,
            user_id=user2.id,
            hourly_values={"0": 10},
        )
        db_session.add_all([annotation1, annotation2])
        await db_session.commit()

        await ConsensusService.analyze_consensus(db_session, screenshot.id)
        await db_session.refresh(screenshot)

        assert screenshot.has_consensus is True

    @pytest.mark.asyncio
    async def test_analyze_consensus_creates_result(self, db_session: AsyncSession):
        """Test consensus analysis creates ConsensusResult."""
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        db_session.add(screenshot)
        await db_session.commit()

        user1 = User(username="user1")
        user2 = User(username="user2")
        db_session.add_all([user1, user2])
        await db_session.commit()

        annotation1 = Annotation(
            screenshot_id=screenshot.id,
            user_id=user1.id,
            hourly_values={"0": 10},
        )
        annotation2 = Annotation(
            screenshot_id=screenshot.id,
            user_id=user2.id,
            hourly_values={"0": 10},
        )
        db_session.add_all([annotation1, annotation2])
        await db_session.commit()

        await ConsensusService.analyze_consensus(db_session, screenshot.id)

        from sqlalchemy import select

        result = await db_session.execute(select(ConsensusResult).where(ConsensusResult.screenshot_id == screenshot.id))
        consensus = result.scalar_one_or_none()

        assert consensus is not None
        assert consensus.has_consensus is True
        assert consensus.consensus_values == {"0": 10.0}

    @pytest.mark.asyncio
    async def test_analyze_consensus_updates_existing_result(self, db_session: AsyncSession):
        """Test consensus analysis updates existing ConsensusResult."""
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        db_session.add(screenshot)
        await db_session.commit()

        # Create existing consensus
        existing_consensus = ConsensusResult(
            screenshot_id=screenshot.id,
            has_consensus=False,
            disagreement_details={"old": "data"},
        )
        db_session.add(existing_consensus)
        await db_session.commit()

        user1 = User(username="user1")
        user2 = User(username="user2")
        db_session.add_all([user1, user2])
        await db_session.commit()

        annotation1 = Annotation(
            screenshot_id=screenshot.id,
            user_id=user1.id,
            hourly_values={"0": 10},
        )
        annotation2 = Annotation(
            screenshot_id=screenshot.id,
            user_id=user2.id,
            hourly_values={"0": 10},
        )
        db_session.add_all([annotation1, annotation2])
        await db_session.commit()

        await ConsensusService.analyze_consensus(db_session, screenshot.id)
        await db_session.refresh(existing_consensus)

        # Should update existing, not create new
        assert existing_consensus.has_consensus is True
        assert "total_disagreements" in existing_consensus.disagreement_details


@pytest.mark.asyncio
class TestQueueService:
    """Test QueueService business logic."""

    async def test_get_next_screenshot_returns_pending(self, db_session: AsyncSession):
        """Test get_next_screenshot returns screenshots needing annotation."""
        user = User(username="testuser")
        db_session.add(user)
        await db_session.commit()

        screenshot1 = Screenshot(
            file_path="/test1.png",
            image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
            target_annotations=2,
            current_annotation_count=0,
        )
        db_session.add(screenshot1)
        await db_session.commit()

        queue_service = QueueService()
        result = await queue_service.get_next_screenshot(db_session, user.id)

        assert result is not None
        assert result.id == screenshot1.id

    async def test_get_next_screenshot_excludes_user_annotations(self, db_session: AsyncSession):
        """Test get_next_screenshot excludes screenshots user already annotated."""
        user = User(username="testuser")
        db_session.add(user)
        await db_session.commit()

        screenshot1 = Screenshot(
            file_path="/test1.png",
            image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
            target_annotations=2,
        )
        screenshot2 = Screenshot(
            file_path="/test2.png",
            image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
            target_annotations=2,
        )
        db_session.add_all([screenshot1, screenshot2])
        await db_session.commit()

        # User already annotated screenshot1
        annotation = Annotation(
            screenshot_id=screenshot1.id,
            user_id=user.id,
            hourly_values={"0": 10},
        )
        db_session.add(annotation)
        await db_session.commit()

        queue_service = QueueService()
        result = await queue_service.get_next_screenshot(db_session, user.id)

        # Should return screenshot2, not screenshot1
        assert result is not None
        assert result.id == screenshot2.id

    async def test_get_next_screenshot_excludes_skipped(self, db_session: AsyncSession):
        """Test get_next_screenshot excludes screenshots user skipped."""
        from screenshot_processor.web.database.models import UserQueueState

        user = User(username="testuser")
        db_session.add(user)
        await db_session.commit()

        screenshot1 = Screenshot(
            file_path="/test1.png",
            image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
            target_annotations=2,
        )
        screenshot2 = Screenshot(
            file_path="/test2.png",
            image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
            target_annotations=2,
        )
        db_session.add_all([screenshot1, screenshot2])
        await db_session.commit()

        # User skipped screenshot1
        queue_state = UserQueueState(
            user_id=user.id,
            screenshot_id=screenshot1.id,
            status="skipped",
        )
        db_session.add(queue_state)
        await db_session.commit()

        queue_service = QueueService()
        result = await queue_service.get_next_screenshot(db_session, user.id)

        assert result is not None
        assert result.id == screenshot2.id

    async def test_get_next_screenshot_filters_by_group(self, db_session: AsyncSession):
        """Test get_next_screenshot filters by group_id."""
        from screenshot_processor.web.database.models import Group

        user = User(username="testuser")
        db_session.add(user)
        await db_session.commit()

        group1 = Group(id="group1", name="Group 1", image_type="screen_time")
        group2 = Group(id="group2", name="Group 2", image_type="screen_time")
        db_session.add_all([group1, group2])
        await db_session.commit()

        screenshot1 = Screenshot(
            file_path="/test1.png",
            image_type="screen_time",
            group_id="group1",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
        )
        screenshot2 = Screenshot(
            file_path="/test2.png",
            image_type="screen_time",
            group_id="group2",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
        )
        db_session.add_all([screenshot1, screenshot2])
        await db_session.commit()

        queue_service = QueueService()
        result = await queue_service.get_next_screenshot(db_session, user.id, group_id="group2")

        assert result is not None
        assert result.id == screenshot2.id

    async def test_get_next_screenshot_filters_by_processing_status(self, db_session: AsyncSession):
        """Test get_next_screenshot filters by processing_status."""
        user = User(username="testuser")
        db_session.add(user)
        await db_session.commit()

        screenshot1 = Screenshot(
            file_path="/test1.png",
            image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
        )
        screenshot2 = Screenshot(
            file_path="/test2.png",
            image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.FAILED,
        )
        db_session.add_all([screenshot1, screenshot2])
        await db_session.commit()

        queue_service = QueueService()
        result = await queue_service.get_next_screenshot(db_session, user.id, processing_status="failed")

        assert result is not None
        assert result.id == screenshot2.id

    async def test_get_next_screenshot_no_results(self, db_session: AsyncSession):
        """Test get_next_screenshot returns None when no screenshots available."""
        user = User(username="testuser")
        db_session.add(user)
        await db_session.commit()

        queue_service = QueueService()
        result = await queue_service.get_next_screenshot(db_session, user.id)

        assert result is None

    async def test_mark_screenshot_skipped_creates_state(self, db_session: AsyncSession):
        """Test mark_screenshot_skipped creates UserQueueState."""
        from sqlalchemy import select

        from screenshot_processor.web.database.models import UserQueueState

        user = User(username="testuser")
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        db_session.add_all([user, screenshot])
        await db_session.commit()

        queue_service = QueueService()
        await queue_service.mark_screenshot_skipped(db_session, user.id, screenshot.id)

        result = await db_session.execute(select(UserQueueState).where(UserQueueState.screenshot_id == screenshot.id))
        state = result.scalar_one_or_none()

        assert state is not None
        assert state.status == "skipped"

    async def test_mark_screenshot_skipped_updates_existing(self, db_session: AsyncSession):
        """Test mark_screenshot_skipped updates existing UserQueueState."""

        from screenshot_processor.web.database.models import UserQueueState

        user = User(username="testuser")
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        db_session.add_all([user, screenshot])
        await db_session.commit()

        # Create existing state
        existing_state = UserQueueState(
            user_id=user.id,
            screenshot_id=screenshot.id,
            status="pending",
        )
        db_session.add(existing_state)
        await db_session.commit()

        queue_service = QueueService()
        await queue_service.mark_screenshot_skipped(db_session, user.id, screenshot.id)
        await db_session.refresh(existing_state)

        assert existing_state.status == "skipped"

    async def test_get_queue_stats(self, db_session: AsyncSession):
        """Test get_queue_stats returns correct statistics."""
        user = User(username="testuser")
        db_session.add(user)
        await db_session.commit()

        # Create mix of screenshots
        screenshot1 = Screenshot(
            file_path="/test1.png",
            image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
        )
        screenshot2 = Screenshot(
            file_path="/test2.png",
            image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.FAILED,
        )
        db_session.add_all([screenshot1, screenshot2])
        await db_session.commit()

        # User completed one annotation
        annotation = Annotation(
            screenshot_id=screenshot1.id,
            user_id=user.id,
            hourly_values={"0": 10},
        )
        db_session.add(annotation)
        await db_session.commit()

        queue_service = QueueService()
        stats = await queue_service.get_queue_stats(db_session, user.id)

        assert stats["user_completed"] == 1
        assert stats["total_remaining"] == 1  # screenshot2 only
        assert stats["auto_processed"] >= 1  # At least screenshot1
        assert stats["failed"] == 1
