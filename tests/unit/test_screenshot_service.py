"""
Unit tests for ScreenshotService.

Tests verification workflow, navigation, and OCR operations
using the in-memory SQLite test database.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    Annotation,
    AnnotationStatus,
    Group,
    ProcessingStatus,
    Screenshot,
    User,
)
from screenshot_processor.web.services.screenshot_service import ScreenshotService


@pytest_asyncio.fixture
async def service(db_session: AsyncSession) -> ScreenshotService:
    return ScreenshotService(db_session)


@pytest_asyncio.fixture
async def user_and_screenshot(db_session: AsyncSession):
    """Create a user and a screen_time screenshot for testing."""
    user = User(username="svc_test_user", role="annotator", is_active=True)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    screenshot = Screenshot(
        file_path="/test/svc_screenshot.png",
        image_type="screen_time",
        annotation_status=AnnotationStatus.PENDING,
        processing_status=ProcessingStatus.COMPLETED,
        target_annotations=2,
        current_annotation_count=0,
        uploaded_by_id=user.id,
    )
    db_session.add(screenshot)
    await db_session.commit()
    await db_session.refresh(screenshot)
    return user, screenshot


class TestVerifyScreenshot:
    """Tests for verify/unverify workflow."""

    @pytest.mark.asyncio
    async def test_verify_adds_user_id(self, db_session, service, user_and_screenshot):
        user, screenshot = user_and_screenshot
        result = await service.verify_screenshot(screenshot, user.id)
        assert user.id in result.verified_by_user_ids

    @pytest.mark.asyncio
    async def test_verify_idempotent(self, db_session, service, user_and_screenshot):
        """Verifying twice should not duplicate the user ID."""
        user, screenshot = user_and_screenshot
        await service.verify_screenshot(screenshot, user.id)
        result = await service.verify_screenshot(screenshot, user.id)
        assert result.verified_by_user_ids.count(user.id) == 1

    @pytest.mark.asyncio
    async def test_verify_multiple_users(self, db_session, service, user_and_screenshot):
        user, screenshot = user_and_screenshot
        user2 = User(username="second_verifier", role="annotator", is_active=True)
        db_session.add(user2)
        await db_session.commit()
        await db_session.refresh(user2)

        await service.verify_screenshot(screenshot, user.id)
        result = await service.verify_screenshot(screenshot, user2.id)
        assert len(result.verified_by_user_ids) == 2

    @pytest.mark.asyncio
    async def test_verify_saves_grid_coords(self, db_session, service, user_and_screenshot):
        user, screenshot = user_and_screenshot
        coords = {
            "upper_left_x": 10,
            "upper_left_y": 20,
            "lower_right_x": 300,
            "lower_right_y": 400,
        }
        result = await service.verify_screenshot(screenshot, user.id, grid_coords=coords)
        assert result.grid_upper_left_x == 10
        assert result.grid_upper_left_y == 20
        assert result.grid_lower_right_x == 300
        assert result.grid_lower_right_y == 400

    @pytest.mark.asyncio
    async def test_verify_partial_grid_coords(self, db_session, service, user_and_screenshot):
        """Only some grid coords provided should update only those."""
        user, screenshot = user_and_screenshot
        coords = {"upper_left_x": 50}
        result = await service.verify_screenshot(screenshot, user.id, grid_coords=coords)
        assert result.grid_upper_left_x == 50
        assert result.grid_upper_left_y is None

    @pytest.mark.asyncio
    async def test_unverify_removes_user_id(self, db_session, service, user_and_screenshot):
        user, screenshot = user_and_screenshot
        await service.verify_screenshot(screenshot, user.id)
        result = await service.unverify_screenshot(screenshot, user.id)
        # When no verifiers remain, verified_by_user_ids should be None
        assert result.verified_by_user_ids is None

    @pytest.mark.asyncio
    async def test_unverify_keeps_other_users(self, db_session, service, user_and_screenshot):
        user, screenshot = user_and_screenshot
        user2 = User(username="other_verifier", role="annotator", is_active=True)
        db_session.add(user2)
        await db_session.commit()
        await db_session.refresh(user2)

        await service.verify_screenshot(screenshot, user.id)
        await service.verify_screenshot(screenshot, user2.id)
        result = await service.unverify_screenshot(screenshot, user.id)
        assert user.id not in result.verified_by_user_ids
        assert user2.id in result.verified_by_user_ids

    @pytest.mark.asyncio
    async def test_unverify_not_verified_is_noop(self, db_session, service, user_and_screenshot):
        """Unverifying when not verified should not crash."""
        user, screenshot = user_and_screenshot
        result = await service.unverify_screenshot(screenshot, user.id)
        assert result.id == screenshot.id


class TestEnsureOcrTotal:
    """Tests for OCR total extraction guard logic."""

    @pytest.mark.asyncio
    async def test_skips_verified_screenshot(self, db_session, service, user_and_screenshot):
        user, screenshot = user_and_screenshot
        screenshot.verified_by_user_ids = [user.id]
        await db_session.commit()

        result = await service.ensure_ocr_total(screenshot)
        assert result is False

    @pytest.mark.asyncio
    async def test_skips_non_screen_time(self, db_session, service):
        screenshot = Screenshot(
            file_path="/test/battery.png",
            image_type="battery",
            processing_status=ProcessingStatus.COMPLETED,
        )
        db_session.add(screenshot)
        await db_session.commit()

        result = await service.ensure_ocr_total(screenshot)
        assert result is False

    @pytest.mark.asyncio
    async def test_skips_already_has_total(self, db_session, service, user_and_screenshot):
        _, screenshot = user_and_screenshot
        screenshot.extracted_total = "3h 15m"
        await db_session.commit()

        result = await service.ensure_ocr_total(screenshot)
        assert result is False

    @pytest.mark.asyncio
    async def test_skips_missing_file(self, db_session, service, user_and_screenshot):
        """Non-existent file path returns False."""
        _, screenshot = user_and_screenshot
        screenshot.file_path = "/nonexistent/path.png"
        await db_session.commit()

        result = await service.ensure_ocr_total(screenshot)
        assert result is False

    @pytest.mark.asyncio
    async def test_extracts_total_successfully(self, db_session, service, user_and_screenshot):
        _, screenshot = user_and_screenshot
        screenshot.extracted_total = None

        with patch(
            "screenshot_processor.web.services.screenshot_service.Path.exists",
            return_value=True,
        ), patch(
            "screenshot_processor.web.services.screenshot_service._sync_extract_ocr_total",
            return_value="2h 30m",
        ):
            result = await service.ensure_ocr_total(screenshot)
        assert result is True
        assert screenshot.extracted_total == "2h 30m"


class TestRecalculateOcrTotal:
    """Tests for recalculate_ocr_total."""

    @pytest.mark.asyncio
    async def test_rejects_non_screen_time(self, db_session, service):
        screenshot = Screenshot(
            file_path="/test/battery.png",
            image_type="battery",
            processing_status=ProcessingStatus.COMPLETED,
        )
        db_session.add(screenshot)
        await db_session.commit()

        success, total, msg = await service.recalculate_ocr_total(screenshot)
        assert success is False
        assert "only applies to screen_time" in msg

    @pytest.mark.asyncio
    async def test_rejects_missing_file(self, db_session, service, user_and_screenshot):
        _, screenshot = user_and_screenshot
        screenshot.file_path = "/nonexistent/file.png"
        await db_session.commit()

        success, total, msg = await service.recalculate_ocr_total(screenshot)
        assert success is False
        assert "not found" in msg


class TestNavigate:
    """Tests for screenshot navigation with filters."""

    @pytest.mark.asyncio
    async def test_navigate_current(self, db_session, service):
        """Navigate to current screenshot."""
        screenshot = Screenshot(
            file_path="/test/nav1.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        result = await service.navigate(screenshot.id, direction="current")
        assert result.screenshot is not None
        assert result.screenshot.id == screenshot.id

    @pytest.mark.asyncio
    async def test_navigate_with_group_filter(self, db_session, service):
        group = Group(id="nav-group", name="Nav Group", image_type="screen_time")
        db_session.add(group)
        await db_session.commit()

        s1 = Screenshot(
            file_path="/test/nav_g1.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
            group_id="nav-group",
        )
        s2 = Screenshot(
            file_path="/test/nav_g2.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
            group_id="nav-group",
        )
        db_session.add_all([s1, s2])
        await db_session.commit()
        await db_session.refresh(s1)

        result = await service.navigate(s1.id, direction="current", group_id="nav-group")
        assert result.total_in_filter == 2

    @pytest.mark.asyncio
    async def test_navigate_with_processing_status_filter(self, db_session, service):
        s1 = Screenshot(
            file_path="/test/nav_status1.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
        )
        s2 = Screenshot(
            file_path="/test/nav_status2.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.FAILED,
        )
        db_session.add_all([s1, s2])
        await db_session.commit()
        await db_session.refresh(s2)

        result = await service.navigate(s2.id, direction="current", processing_status="failed")
        assert result.total_in_filter == 1
