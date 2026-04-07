"""
Unit tests for AdminService.

Tests user management, group deletion, OCR recalculation,
and bulk reprocess operations.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    Annotation,
    AnnotationStatus,
    Group,
    ProcessingStatus,
    Screenshot,
    User,
)
from screenshot_processor.web.services.admin_service import (
    AdminService,
    DeleteGroupResult,
    RecalculateOcrResult,
    UserStats,
)


@pytest_asyncio.fixture
async def admin_service(db_session: AsyncSession) -> AdminService:
    return AdminService(db_session)


@pytest_asyncio.fixture
async def populated_db(db_session: AsyncSession):
    """Create users and screenshots for admin tests."""
    admin = User(username="admin", role="admin", is_active=True)
    user1 = User(username="worker1", role="annotator", is_active=True)
    user2 = User(username="worker2", role="annotator", is_active=True)
    db_session.add_all([admin, user1, user2])
    await db_session.commit()
    for u in [admin, user1, user2]:
        await db_session.refresh(u)

    group = Group(id="admin-test-group", name="Admin Test", image_type="screen_time")
    db_session.add(group)
    await db_session.commit()

    screenshots = []
    for i in range(3):
        s = Screenshot(
            file_path=f"/admin/test{i}.png",
            image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
            group_id="admin-test-group",
            uploaded_by_id=admin.id,
        )
        db_session.add(s)
        screenshots.append(s)
    await db_session.commit()
    for s in screenshots:
        await db_session.refresh(s)

    return {"admin": admin, "user1": user1, "user2": user2, "group": group, "screenshots": screenshots}


class TestGetAllUsersWithStats:
    """Tests for get_all_users_with_stats."""

    @pytest.mark.asyncio
    async def test_returns_all_users(self, db_session, admin_service, populated_db):
        results = await admin_service.get_all_users_with_stats()
        usernames = [r.user.username for r in results]
        assert "admin" in usernames
        assert "worker1" in usernames

    @pytest.mark.asyncio
    async def test_includes_annotation_counts(self, db_session, admin_service, populated_db):
        # Add annotation for user1
        user1 = populated_db["user1"]
        screenshot = populated_db["screenshots"][0]
        annotation = Annotation(
            screenshot_id=screenshot.id,
            user_id=user1.id,
            hourly_values={"0": 5},
        )
        db_session.add(annotation)
        await db_session.commit()

        results = await admin_service.get_all_users_with_stats()
        user1_stats = [r for r in results if r.user.username == "worker1"][0]
        assert user1_stats.annotations_count == 1

    @pytest.mark.asyncio
    async def test_empty_db(self, db_session, admin_service):
        results = await admin_service.get_all_users_with_stats()
        assert results == []


class TestUpdateUser:
    """Tests for update_user."""

    @pytest.mark.asyncio
    async def test_update_role(self, db_session, admin_service, populated_db):
        user = populated_db["user1"]
        await admin_service.update_user(user, role="admin")
        await db_session.refresh(user)
        assert user.role == "admin"

    @pytest.mark.asyncio
    async def test_update_is_active(self, db_session, admin_service, populated_db):
        user = populated_db["user1"]
        await admin_service.update_user(user, is_active=False)
        await db_session.refresh(user)
        assert user.is_active is False

    @pytest.mark.asyncio
    async def test_invalid_role_raises(self, db_session, admin_service, populated_db):
        user = populated_db["user1"]
        with pytest.raises(ValueError, match="Invalid role"):
            await admin_service.update_user(user, role="superadmin")

    @pytest.mark.asyncio
    async def test_update_both_fields(self, db_session, admin_service, populated_db):
        user = populated_db["user2"]
        await admin_service.update_user(user, role="admin", is_active=False)
        await db_session.refresh(user)
        assert user.role == "admin"
        assert user.is_active is False


class TestGetUserById:
    """Tests for get_user_by_id."""

    @pytest.mark.asyncio
    async def test_existing_user(self, db_session, admin_service, populated_db):
        user = populated_db["user1"]
        result = await admin_service.get_user_by_id(user.id)
        assert result is not None
        assert result.username == "worker1"

    @pytest.mark.asyncio
    async def test_nonexistent_user(self, db_session, admin_service):
        result = await admin_service.get_user_by_id(99999)
        assert result is None


class TestDeleteGroup:
    """Tests for delete_group."""

    @pytest.mark.asyncio
    async def test_delete_existing_group(self, db_session, admin_service, populated_db):
        result = await admin_service.delete_group("admin-test-group")
        assert isinstance(result, DeleteGroupResult)
        assert result.success is True
        assert result.group_id == "admin-test-group"
        assert result.screenshots_deleted == 3

    @pytest.mark.asyncio
    async def test_delete_nonexistent_group_raises(self, db_session, admin_service):
        with pytest.raises(ValueError, match="not found"):
            await admin_service.delete_group("nonexistent-group")

    @pytest.mark.asyncio
    async def test_delete_group_with_annotations(self, db_session, admin_service, populated_db):
        """Deleting a group should cascade-delete annotations too."""
        user = populated_db["user1"]
        screenshot = populated_db["screenshots"][0]
        db_session.add(Annotation(
            screenshot_id=screenshot.id,
            user_id=user.id,
            hourly_values={"0": 5},
        ))
        await db_session.commit()

        result = await admin_service.delete_group("admin-test-group")
        assert result.success is True
        assert result.annotations_deleted >= 1


class TestGetGroupById:
    """Tests for get_group_by_id."""

    @pytest.mark.asyncio
    async def test_existing_group(self, db_session, admin_service, populated_db):
        result = await admin_service.get_group_by_id("admin-test-group")
        assert result is not None
        assert result.name == "Admin Test"

    @pytest.mark.asyncio
    async def test_nonexistent_group(self, db_session, admin_service):
        result = await admin_service.get_group_by_id("does-not-exist")
        assert result is None


class TestRecalculateOcrTotals:
    """Tests for recalculate_ocr_totals."""

    @pytest.mark.asyncio
    async def test_no_missing_totals(self, db_session, admin_service, populated_db):
        """When all screenshots have extracted_total, nothing to do."""
        for s in populated_db["screenshots"]:
            s.extracted_total = "1h 30m"
        await db_session.commit()

        result = await admin_service.recalculate_ocr_totals()
        assert isinstance(result, RecalculateOcrResult)
        assert result.total_missing == 0
        assert result.updated == 0

    @pytest.mark.asyncio
    async def test_missing_file_counts_as_failed(self, db_session, admin_service, populated_db):
        """Screenshots with missing files should increment failed count."""
        # Screenshots have paths like /admin/test0.png which don't exist
        result = await admin_service.recalculate_ocr_totals()
        assert result.failed == result.processed  # All fail because files don't exist

    @pytest.mark.asyncio
    async def test_limit_parameter(self, db_session, admin_service, populated_db):
        result = await admin_service.recalculate_ocr_totals(limit=1)
        assert result.processed <= 1


class TestGetScreenshotIdsForReprocess:
    """Tests for get_screenshot_ids_for_reprocess."""

    @pytest.mark.asyncio
    async def test_returns_ids(self, db_session, admin_service, populated_db):
        ids = await admin_service.get_screenshot_ids_for_reprocess()
        assert isinstance(ids, list)

    @pytest.mark.asyncio
    async def test_with_group_filter(self, db_session, admin_service, populated_db):
        ids = await admin_service.get_screenshot_ids_for_reprocess(group_id="admin-test-group")
        assert isinstance(ids, list)

    @pytest.mark.asyncio
    async def test_with_limit(self, db_session, admin_service, populated_db):
        ids = await admin_service.get_screenshot_ids_for_reprocess(limit=1)
        assert len(ids) <= 1


class TestResetTestData:
    """Tests for reset_test_data."""

    @pytest.mark.asyncio
    async def test_reset_completes(self, db_session, admin_service, populated_db):
        """reset_test_data should not raise."""
        await admin_service.reset_test_data()
        # After reset, data should be cleared
