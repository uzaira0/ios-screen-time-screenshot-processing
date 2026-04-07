"""
Unit tests for SQLAlchemy models.

Tests model relationships, enum fields, defaults, and constraints.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from screenshot_processor.web.database.models import (
    Annotation,
    AnnotationStatus,
    ConsensusResult,
    Group,
    ProcessingIssue,
    ProcessingStatus,
    Screenshot,
    User,
    UserQueueState,
)


@pytest.mark.asyncio
class TestUserModel:
    """Test User model."""

    async def test_user_creation_defaults(self, db_session: AsyncSession):
        """Test User creation with default values."""
        user = User(username="testuser")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.id is not None
        assert user.username == "testuser"
        assert user.role == "annotator"  # Default role
        assert user.is_active is True  # Default active
        assert user.email is None
        assert user.hashed_password is None
        assert isinstance(user.created_at, datetime)

    async def test_user_with_all_fields(self, db_session: AsyncSession):
        """Test User creation with all fields."""
        user = User(
            username="adminuser",
            email="admin@example.com",
            hashed_password="hashed_pw",
            role="admin",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.username == "adminuser"
        assert user.email == "admin@example.com"
        assert user.role == "admin"
        assert user.is_active is True

    async def test_user_username_unique_constraint(self, db_session: AsyncSession):
        """Test username unique constraint."""
        user1 = User(username="duplicate")
        db_session.add(user1)
        await db_session.commit()

        user2 = User(username="duplicate")
        db_session.add(user2)

        with pytest.raises(Exception):  # IntegrityError
            await db_session.commit()
        await db_session.rollback()

    async def test_user_annotations_relationship(self, db_session: AsyncSession):
        """Test User -> Annotations relationship."""
        user = User(username="annotator1")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        screenshot = Screenshot(
            file_path="/test/img.png",
            image_type="screen_time",
            uploaded_by_id=user.id,
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        annotation = Annotation(
            screenshot_id=screenshot.id,
            user_id=user.id,
            hourly_values={"0": 10},
        )
        db_session.add(annotation)
        await db_session.commit()

        # Test relationship with eager loading
        result = await db_session.execute(
            select(User).where(User.id == user.id).options(selectinload(User.annotations))
        )
        fetched_user = result.scalar_one()
        assert len(fetched_user.annotations) == 1
        assert fetched_user.annotations[0].id == annotation.id


@pytest.mark.asyncio
class TestScreenshotModel:
    """Test Screenshot model."""

    async def test_screenshot_creation_defaults(self, db_session: AsyncSession):
        """Test Screenshot creation with default values."""
        screenshot = Screenshot(
            file_path="/uploads/test.png",
            image_type="screen_time",
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        assert screenshot.id is not None
        assert screenshot.annotation_status == AnnotationStatus.PENDING
        assert screenshot.processing_status == ProcessingStatus.PENDING
        assert screenshot.target_annotations == 1
        assert screenshot.current_annotation_count == 0
        assert screenshot.has_consensus is None
        assert screenshot.has_blocking_issues is False
        assert isinstance(screenshot.uploaded_at, datetime)

    async def test_screenshot_with_metadata(self, db_session: AsyncSession):
        """Test Screenshot creation with upload metadata."""
        screenshot = Screenshot(
            file_path="/uploads/P001/screenshot.png",
            image_type="battery",
            participant_id="P001",
            group_id="study1",
            source_id="import_1",
            device_type="iphone_modern",
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        assert screenshot.participant_id == "P001"
        assert screenshot.group_id == "study1"
        assert screenshot.source_id == "import_1"
        assert screenshot.device_type == "iphone_modern"

    async def test_screenshot_enum_fields(self, db_session: AsyncSession):
        """Test Screenshot enum fields work correctly."""
        screenshot = Screenshot(
            file_path="/test.png",
            image_type="screen_time",
            annotation_status=AnnotationStatus.ANNOTATED,
            processing_status=ProcessingStatus.COMPLETED,
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        assert screenshot.annotation_status == AnnotationStatus.ANNOTATED
        assert screenshot.processing_status == ProcessingStatus.COMPLETED
        assert screenshot.annotation_status.value == "annotated"
        assert screenshot.processing_status.value == "completed"

    async def test_screenshot_json_fields(self, db_session: AsyncSession):
        """Test Screenshot JSON fields."""
        screenshot = Screenshot(
            file_path="/test.png",
            image_type="screen_time",
            extracted_hourly_data={"0": 10, "1": 15},
            processing_issues=[{"type": "ocr_error", "severity": "warning"}],
            processing_metadata={"ocr_confidence": 0.85},
            verified_by_user_ids=[1, 2, 3],
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        assert screenshot.extracted_hourly_data == {"0": 10, "1": 15}
        assert len(screenshot.processing_issues) == 1
        assert screenshot.processing_metadata["ocr_confidence"] == 0.85
        assert screenshot.verified_by_user_ids == [1, 2, 3]

    async def test_screenshot_annotations_relationship(self, db_session: AsyncSession):
        """Test Screenshot -> Annotations relationship with cascade delete."""
        # Create two users (unique constraint: screenshot_id + user_id)
        user1 = User(username="testuser1")
        user2 = User(username="testuser2")
        db_session.add_all([user1, user2])
        await db_session.commit()

        screenshot = Screenshot(
            file_path="/test.png",
            image_type="screen_time",
            uploaded_by_id=user1.id,
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        # Each annotation must be from a different user (unique constraint)
        annotation1 = Annotation(
            screenshot_id=screenshot.id,
            user_id=user1.id,
            hourly_values={"0": 10},
        )
        annotation2 = Annotation(
            screenshot_id=screenshot.id,
            user_id=user2.id,
            hourly_values={"1": 15},
        )
        db_session.add_all([annotation1, annotation2])
        await db_session.commit()

        # Test relationship with eager loading
        result = await db_session.execute(
            select(Screenshot).where(Screenshot.id == screenshot.id).options(selectinload(Screenshot.annotations))
        )
        fetched = result.scalar_one()
        assert len(fetched.annotations) == 2

        # Test cascade delete
        await db_session.delete(screenshot)
        await db_session.commit()

        result = await db_session.execute(select(Annotation))
        assert len(result.scalars().all()) == 0

    async def test_screenshot_group_relationship(self, db_session: AsyncSession):
        """Test Screenshot -> Group relationship."""
        group = Group(id="study1", name="Study 1", image_type="screen_time")
        db_session.add(group)
        await db_session.commit()

        screenshot = Screenshot(
            file_path="/test.png",
            image_type="screen_time",
            group_id="study1",
        )
        db_session.add(screenshot)
        await db_session.commit()

        # Test relationship with eager loading
        result = await db_session.execute(
            select(Screenshot).where(Screenshot.id == screenshot.id).options(selectinload(Screenshot.group))
        )
        fetched = result.scalar_one()
        assert fetched.group is not None
        assert fetched.group.id == "study1"
        assert fetched.group.name == "Study 1"


@pytest.mark.asyncio
class TestAnnotationModel:
    """Test Annotation model."""

    async def test_annotation_creation(self, db_session: AsyncSession):
        """Test Annotation creation."""
        user = User(username="annotator")
        db_session.add(user)
        await db_session.commit()

        screenshot = Screenshot(
            file_path="/test.png",
            image_type="screen_time",
        )
        db_session.add(screenshot)
        await db_session.commit()

        annotation = Annotation(
            screenshot_id=screenshot.id,
            user_id=user.id,
            hourly_values={"0": 10, "1": 15, "2": 20},
            extracted_title="Screen Time",
            extracted_total="45m",
            grid_upper_left={"x": 100, "y": 100},
            grid_lower_right={"x": 500, "y": 500},
            time_spent_seconds=120.5,
            notes="Test annotation",
        )
        db_session.add(annotation)
        await db_session.commit()
        await db_session.refresh(annotation)

        assert annotation.id is not None
        assert annotation.hourly_values == {"0": 10, "1": 15, "2": 20}
        assert annotation.extracted_title == "Screen Time"
        assert annotation.time_spent_seconds == 120.5
        assert annotation.status == "submitted"
        assert isinstance(annotation.created_at, datetime)
        assert isinstance(annotation.updated_at, datetime)

    async def test_annotation_relationships(self, db_session: AsyncSession):
        """Test Annotation relationships."""
        user = User(username="annotator")
        db_session.add(user)
        await db_session.commit()

        screenshot = Screenshot(
            file_path="/test.png",
            image_type="screen_time",
        )
        db_session.add(screenshot)
        await db_session.commit()

        annotation = Annotation(
            screenshot_id=screenshot.id,
            user_id=user.id,
            hourly_values={"0": 10},
        )
        db_session.add(annotation)
        await db_session.commit()

        # Test relationships with eager loading
        result = await db_session.execute(
            select(Annotation)
            .where(Annotation.id == annotation.id)
            .options(selectinload(Annotation.user), selectinload(Annotation.screenshot))
        )
        fetched = result.scalar_one()

        # Test user relationship
        assert fetched.user is not None
        assert fetched.user.username == "annotator"

        # Test screenshot relationship
        assert fetched.screenshot is not None
        assert fetched.screenshot.file_path == "/test.png"

    async def test_annotation_cascade_delete(self, db_session: AsyncSession):
        """Test ProcessingIssue cascade delete when Annotation is deleted."""
        user = User(username="annotator")
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        db_session.add_all([user, screenshot])
        await db_session.commit()

        annotation = Annotation(
            screenshot_id=screenshot.id,
            user_id=user.id,
            hourly_values={"0": 10},
        )
        db_session.add(annotation)
        await db_session.commit()
        await db_session.refresh(annotation)

        issue = ProcessingIssue(
            annotation_id=annotation.id,
            issue_type="ocr_error",
            severity="warning",
            description="Low confidence",
        )
        db_session.add(issue)
        await db_session.commit()

        # Delete annotation
        await db_session.delete(annotation)
        await db_session.commit()

        # Issue should be cascade deleted
        result = await db_session.execute(select(ProcessingIssue))
        assert len(result.scalars().all()) == 0


@pytest.mark.asyncio
class TestGroupModel:
    """Test Group model."""

    async def test_group_creation(self, db_session: AsyncSession):
        """Test Group creation."""
        group = Group(
            id="study1",
            name="Study 1 Participants",
            image_type="battery",
        )
        db_session.add(group)
        await db_session.commit()
        await db_session.refresh(group)

        assert group.id == "study1"
        assert group.name == "Study 1 Participants"
        assert group.image_type == "battery"
        assert isinstance(group.created_at, datetime)

    async def test_group_screenshots_relationship(self, db_session: AsyncSession):
        """Test Group -> Screenshots relationship."""
        group = Group(id="study1", name="Study 1", image_type="screen_time")
        db_session.add(group)
        await db_session.commit()

        screenshot1 = Screenshot(
            file_path="/test1.png",
            image_type="screen_time",
            group_id="study1",
        )
        screenshot2 = Screenshot(
            file_path="/test2.png",
            image_type="screen_time",
            group_id="study1",
        )
        db_session.add_all([screenshot1, screenshot2])
        await db_session.commit()

        # Test relationship with eager loading
        result = await db_session.execute(
            select(Group).where(Group.id == "study1").options(selectinload(Group.screenshots))
        )
        fetched = result.scalar_one()
        assert len(fetched.screenshots) == 2


@pytest.mark.asyncio
class TestConsensusResultModel:
    """Test ConsensusResult model."""

    async def test_consensus_result_creation(self, db_session: AsyncSession):
        """Test ConsensusResult creation."""
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        db_session.add(screenshot)
        await db_session.commit()

        consensus = ConsensusResult(
            screenshot_id=screenshot.id,
            has_consensus=True,
            disagreement_details={"total_disagreements": 0, "details": []},
            consensus_values={"0": 10.0, "1": 15.0},
        )
        db_session.add(consensus)
        await db_session.commit()
        await db_session.refresh(consensus)

        assert consensus.has_consensus is True
        assert consensus.consensus_values == {"0": 10.0, "1": 15.0}
        assert isinstance(consensus.calculated_at, datetime)

    async def test_consensus_result_unique_constraint(self, db_session: AsyncSession):
        """Test one consensus result per screenshot."""
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        db_session.add(screenshot)
        await db_session.commit()

        consensus1 = ConsensusResult(
            screenshot_id=screenshot.id,
            has_consensus=True,
            disagreement_details={},
        )
        db_session.add(consensus1)
        await db_session.commit()

        consensus2 = ConsensusResult(
            screenshot_id=screenshot.id,
            has_consensus=False,
            disagreement_details={},
        )
        db_session.add(consensus2)

        with pytest.raises(Exception):  # IntegrityError
            await db_session.commit()
        await db_session.rollback()


@pytest.mark.asyncio
class TestUserQueueStateModel:
    """Test UserQueueState model."""

    async def test_queue_state_creation(self, db_session: AsyncSession):
        """Test UserQueueState creation."""
        user = User(username="testuser")
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        db_session.add_all([user, screenshot])
        await db_session.commit()

        queue_state = UserQueueState(
            user_id=user.id,
            screenshot_id=screenshot.id,
            status="pending",
        )
        db_session.add(queue_state)
        await db_session.commit()
        await db_session.refresh(queue_state)

        assert queue_state.status == "pending"
        assert isinstance(queue_state.last_accessed, datetime)

    async def test_queue_state_relationships(self, db_session: AsyncSession):
        """Test UserQueueState relationships."""
        user = User(username="testuser")
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        db_session.add_all([user, screenshot])
        await db_session.commit()

        queue_state = UserQueueState(
            user_id=user.id,
            screenshot_id=screenshot.id,
            status="skipped",
        )
        db_session.add(queue_state)
        await db_session.commit()
        await db_session.refresh(queue_state)

        assert queue_state.user.username == "testuser"
        assert queue_state.screenshot.file_path == "/test.png"


@pytest.mark.asyncio
class TestProcessingIssueModel:
    """Test ProcessingIssue model."""

    async def test_processing_issue_creation(self, db_session: AsyncSession):
        """Test ProcessingIssue creation."""
        user = User(username="testuser")
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        db_session.add_all([user, screenshot])
        await db_session.commit()

        annotation = Annotation(
            screenshot_id=screenshot.id,
            user_id=user.id,
            hourly_values={"0": 10},
        )
        db_session.add(annotation)
        await db_session.commit()

        issue = ProcessingIssue(
            annotation_id=annotation.id,
            issue_type="ocr_low_confidence",
            severity="warning",
            description="OCR confidence below threshold",
        )
        db_session.add(issue)
        await db_session.commit()
        await db_session.refresh(issue)

        assert issue.issue_type == "ocr_low_confidence"
        assert issue.severity == "warning"
        assert isinstance(issue.created_at, datetime)

    async def test_processing_issue_relationship(self, db_session: AsyncSession):
        """Test ProcessingIssue -> Annotation relationship."""
        user = User(username="testuser")
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        db_session.add_all([user, screenshot])
        await db_session.commit()

        annotation = Annotation(
            screenshot_id=screenshot.id,
            user_id=user.id,
            hourly_values={"0": 10},
        )
        db_session.add(annotation)
        await db_session.commit()

        issue = ProcessingIssue(
            annotation_id=annotation.id,
            issue_type="test_issue",
            severity="error",
            description="Test",
        )
        db_session.add(issue)
        await db_session.commit()
        await db_session.refresh(issue)

        assert issue.annotation is not None
        assert issue.annotation.id == annotation.id
