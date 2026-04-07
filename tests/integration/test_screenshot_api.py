"""
Integration tests for Screenshot API endpoints.

Tests the core screenshot management endpoints:
- GET /screenshots/next - Get next screenshot to annotate
- GET /screenshots/{id} - Get screenshot by ID
- GET /screenshots/list - List screenshots with filters
- GET /screenshots/{id}/navigate - Navigate between screenshots
- POST /screenshots/{id}/skip - Skip a screenshot (sets processing_status to SKIPPED)
- POST /screenshots/{id}/unskip - Unskip a screenshot
- POST /screenshots/{id}/soft-delete - Soft delete a screenshot
- POST /screenshots/{id}/restore - Restore a soft-deleted screenshot

These tests verify that database state is actually persisted,
not just that the API returns the right response.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    Group,
    ProcessingStatus,
    Screenshot,
    User,
)
from tests.conftest import auth_headers
@pytest.mark.asyncio
class TestGetNextScreenshot:
    """Test GET /screenshots/next endpoint."""

    async def test_get_next_returns_screenshot(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Next endpoint should return a screenshot when available."""
        response = await client.get(
            "/api/v1/screenshots/next",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["screenshot"] is not None
        assert data["screenshot"]["id"] == test_screenshot.id

    async def test_get_next_returns_null_when_empty(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Next endpoint should return null when no screenshots available."""
        response = await client.get(
            "/api/v1/screenshots/next",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["screenshot"] is None
        assert data["message"] == "No screenshots available in your queue"

    async def test_get_next_with_group_filter(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_group: Group,
    ):
        """Next endpoint should filter by group."""
        # Create screenshots in test group
        screenshot = Screenshot(
            file_path="/test/group_screenshot.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
            group_id=test_group.id,
            uploaded_by_id=test_user.id,
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        response = await client.get(
            f"/api/v1/screenshots/next?group={test_group.id}",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["screenshot"] is not None
        assert data["screenshot"]["group_id"] == test_group.id

    async def test_get_next_with_processing_status_filter(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Next endpoint should filter by processing_status."""
        # Create a skipped screenshot
        screenshot = Screenshot(
            file_path="/test/skipped.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.SKIPPED,
            uploaded_by_id=test_user.id,
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        response = await client.get(
            "/api/v1/screenshots/next?processing_status=skipped",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["screenshot"] is not None
        assert data["screenshot"]["processing_status"] == "skipped"

    async def test_get_next_requires_auth(
        self,
        client: AsyncClient,
    ):
        """Next endpoint should require authentication."""
        response = await client.get("/api/v1/screenshots/next")

        assert response.status_code == 401


@pytest.mark.asyncio
class TestGetScreenshot:
    """Test GET /screenshots/{id} endpoint."""

    async def test_get_screenshot_by_id(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Should return screenshot details by ID."""
        response = await client.get(
            f"/api/v1/screenshots/{test_screenshot.id}",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_screenshot.id
        assert data["file_path"] == test_screenshot.file_path

    async def test_get_screenshot_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Should return 404 for non-existent screenshot."""
        response = await client.get(
            "/api/v1/screenshots/999999",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 404

    async def test_get_screenshot_requires_auth(
        self,
        client: AsyncClient,
        test_screenshot: Screenshot,
    ):
        """Should require authentication."""
        response = await client.get(f"/api/v1/screenshots/{test_screenshot.id}")

        assert response.status_code == 401


@pytest.mark.asyncio
class TestListScreenshots:
    """Test GET /screenshots/list endpoint."""

    async def test_list_returns_all_screenshots(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_screenshots: list[Screenshot],
        test_user: User,
    ):
        """Should return all screenshots with pagination."""
        response = await client.get(
            "/api/v1/screenshots/list",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == len(multiple_screenshots)
        assert len(data["items"]) == len(multiple_screenshots)

    async def test_list_with_group_filter(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_screenshots: list[Screenshot],
        test_user: User,
        test_group: Group,
    ):
        """Should filter by group_id."""
        response = await client.get(
            f"/api/v1/screenshots/list?group_id={test_group.id}",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        # All screenshots in multiple_screenshots fixture have test_group.id
        assert data["total"] == len(multiple_screenshots)

    async def test_list_with_processing_status_filter(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Should filter by processing_status."""
        # Create screenshots with different statuses
        for status in [ProcessingStatus.COMPLETED, ProcessingStatus.SKIPPED]:
            screenshot = Screenshot(
                file_path=f"/test/{status.value}.png",
                image_type="screen_time",
                processing_status=status,
                uploaded_by_id=test_user.id,
            )
            db_session.add(screenshot)
        await db_session.commit()

        response = await client.get(
            "/api/v1/screenshots/list?processing_status=skipped",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["processing_status"] == "skipped"

    async def test_list_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_screenshots: list[Screenshot],
        test_user: User,
    ):
        """Should handle pagination correctly."""
        response = await client.get(
            "/api/v1/screenshots/list?page=1&page_size=2",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert data["has_next"] is True


@pytest.mark.asyncio
class TestSkipScreenshot:
    """Test POST /screenshots/{id}/skip endpoint.

    These tests verify that processing_status is persisted
    to the database, not just that the API returns 204.
    """

    async def test_skip_persists_to_database(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Skip endpoint MUST persist processing_status=SKIPPED to database."""
        # Verify initial state
        assert test_screenshot.processing_status == ProcessingStatus.COMPLETED

        # Call API
        response = await client.post(
            f"/api/v1/screenshots/{test_screenshot.id}/skip",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 204

        # Verify in DB
        await db_session.refresh(test_screenshot)
        assert test_screenshot.processing_status == ProcessingStatus.SKIPPED

    async def test_skip_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Skip should return 404 for non-existent screenshot."""
        response = await client.post(
            "/api/v1/screenshots/999999/skip",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 404

    async def test_skip_requires_auth(
        self,
        client: AsyncClient,
        test_screenshot: Screenshot,
    ):
        """Skip should require authentication."""
        response = await client.post(
            f"/api/v1/screenshots/{test_screenshot.id}/skip"
        )

        assert response.status_code == 401


@pytest.mark.asyncio
class TestUnskipScreenshot:
    """Test POST /screenshots/{id}/unskip endpoint."""

    async def test_unskip_persists_to_database(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Unskip endpoint MUST persist processing_status=COMPLETED to database."""
        # Create a skipped screenshot
        screenshot = Screenshot(
            file_path="/test/skipped_for_unskip.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.SKIPPED,
            uploaded_by_id=test_user.id,
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        # Call API
        response = await client.post(
            f"/api/v1/screenshots/{screenshot.id}/unskip",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify in DB
        await db_session.refresh(screenshot)
        assert screenshot.processing_status == ProcessingStatus.COMPLETED

    async def test_unskip_non_skipped_fails(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Unskip should fail for non-skipped screenshot."""
        # test_screenshot has COMPLETED status
        response = await client.post(
            f"/api/v1/screenshots/{test_screenshot.id}/unskip",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not in skipped status" in data["message"]


@pytest.mark.asyncio
class TestSoftDeleteScreenshot:
    """Test POST /screenshots/{id}/soft-delete endpoint."""

    async def test_soft_delete_persists_to_database(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Soft delete MUST persist processing_status=DELETED to database."""
        original_status = test_screenshot.processing_status

        response = await client.post(
            f"/api/v1/screenshots/{test_screenshot.id}/soft-delete",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["previous_status"] == original_status.value

        # Verify in DB
        await db_session.refresh(test_screenshot)
        assert test_screenshot.processing_status == ProcessingStatus.DELETED
        # Verify pre_delete_status is stored in metadata
        assert test_screenshot.processing_metadata is not None
        assert test_screenshot.processing_metadata["pre_delete_status"] == original_status.value

    async def test_soft_delete_already_deleted(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Soft delete should fail if already deleted."""
        screenshot = Screenshot(
            file_path="/test/deleted.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.DELETED,
            uploaded_by_id=test_user.id,
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        response = await client.post(
            f"/api/v1/screenshots/{screenshot.id}/soft-delete",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "already deleted" in data["message"]


@pytest.mark.asyncio
class TestRestoreScreenshot:
    """Test POST /screenshots/{id}/restore endpoint."""

    async def test_restore_persists_to_database(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Restore MUST persist original processing_status to database."""
        # Create and soft-delete a screenshot
        screenshot = Screenshot(
            file_path="/test/to_restore.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.SKIPPED,
            uploaded_by_id=test_user.id,
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        # Soft delete first
        await client.post(
            f"/api/v1/screenshots/{screenshot.id}/soft-delete",
            headers=auth_headers(test_user.username),
        )
        await db_session.refresh(screenshot)
        assert screenshot.processing_status == ProcessingStatus.DELETED

        # Restore
        response = await client.post(
            f"/api/v1/screenshots/{screenshot.id}/restore",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200

        # Verify in DB
        await db_session.refresh(screenshot)
        assert screenshot.processing_status == ProcessingStatus.SKIPPED

    async def test_restore_non_deleted_fails(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Restore should fail for non-deleted screenshot."""
        response = await client.post(
            f"/api/v1/screenshots/{test_screenshot.id}/restore",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 400
        assert "not deleted" in response.json()["detail"]


@pytest.mark.asyncio
class TestNavigateScreenshot:
    """Test GET /screenshots/{id}/navigate endpoint."""

    async def test_navigate_returns_current(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_screenshots: list[Screenshot],
        test_user: User,
    ):
        """Navigate with direction=current returns the specified screenshot."""
        target = multiple_screenshots[2]

        response = await client.get(
            f"/api/v1/screenshots/{target.id}/navigate?direction=current",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["screenshot"]["id"] == target.id

    async def test_navigate_next(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_screenshots: list[Screenshot],
        test_user: User,
    ):
        """Navigate with direction=next returns the next screenshot."""
        # Sort by ID to find relationships
        sorted_screenshots = sorted(multiple_screenshots, key=lambda s: s.id)
        current = sorted_screenshots[0]
        expected_next = sorted_screenshots[1]

        response = await client.get(
            f"/api/v1/screenshots/{current.id}/navigate?direction=next",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["screenshot"]["id"] == expected_next.id

    async def test_navigate_prev(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_screenshots: list[Screenshot],
        test_user: User,
    ):
        """Navigate with direction=prev returns the previous screenshot."""
        sorted_screenshots = sorted(multiple_screenshots, key=lambda s: s.id)
        current = sorted_screenshots[2]
        expected_prev = sorted_screenshots[1]

        response = await client.get(
            f"/api/v1/screenshots/{current.id}/navigate?direction=prev",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["screenshot"]["id"] == expected_prev.id

    async def test_navigate_next_at_end_returns_null(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_screenshots: list[Screenshot],
        test_user: User,
    ):
        """Navigate next at end of list returns null screenshot."""
        sorted_screenshots = sorted(multiple_screenshots, key=lambda s: s.id)
        last = sorted_screenshots[-1]

        response = await client.get(
            f"/api/v1/screenshots/{last.id}/navigate?direction=next",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["screenshot"] is None
        assert data["has_next"] is False

    async def test_navigate_with_filter(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_group: Group,
    ):
        """Navigate should respect filters."""
        # Create screenshots in different groups
        for i in range(3):
            screenshot = Screenshot(
                file_path=f"/test/group_nav_{i}.png",
                image_type="screen_time",
                processing_status=ProcessingStatus.COMPLETED,
                group_id=test_group.id,
                uploaded_by_id=test_user.id,
            )
            db_session.add(screenshot)
        await db_session.commit()

        # Get first screenshot in group
        result = await db_session.execute(
            select(Screenshot)
            .where(Screenshot.group_id == test_group.id)
            .order_by(Screenshot.id)
        )
        first = result.scalars().first()

        response = await client.get(
            f"/api/v1/screenshots/{first.id}/navigate?direction=current&group_id={test_group.id}",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_in_filter"] == 3


@pytest.mark.asyncio
class TestScreenshotStats:
    """Test GET /screenshots/stats endpoint."""

    async def test_stats_returns_counts(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_screenshots: list[Screenshot],
        test_user: User,
    ):
        """Stats endpoint should return screenshot counts."""
        response = await client.get(
            "/api/v1/screenshots/stats",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_screenshots" in data
        assert "pending_screenshots" in data
        assert "completed_screenshots" in data
        assert data["total_screenshots"] >= len(multiple_screenshots)
