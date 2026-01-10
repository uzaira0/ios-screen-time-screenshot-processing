"""
Integration tests for queue and filtering workflows.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    Group,
    ProcessingStatus,
    Screenshot,
    User,
)
from tests.conftest import auth_headers


@pytest.mark.asyncio
class TestQueueWorkflow:
    """Test queue endpoint and filtering."""

    async def test_get_next_screenshot_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_screenshot: Screenshot,
    ):
        """Test getting next screenshot from queue."""
        response = await client.get(
            "/api/v1/screenshots/next",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["screenshot"] is not None
        assert data["screenshot"]["id"] == test_screenshot.id
        assert data["total_remaining"] >= 1

    async def test_get_next_screenshot_empty_queue(
        self,
        client: AsyncClient,
        test_user: User,
    ):
        """Test getting next screenshot when queue is empty."""
        response = await client.get(
            "/api/v1/screenshots/next",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["screenshot"] is None
        assert "No screenshots available" in data["message"]

    async def test_get_next_screenshot_filter_by_group(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test filtering queue by group_id."""
        group1 = Group(id="group1", name="Group 1", image_type="screen_time")
        group2 = Group(id="group2", name="Group 2", image_type="screen_time")
        db_session.add_all([group1, group2])
        await db_session.commit()

        screenshot1 = Screenshot(
            file_path="/test1.png",
            image_type="screen_time",
            group_id="group1",
            processing_status=ProcessingStatus.COMPLETED,
        )
        screenshot2 = Screenshot(
            file_path="/test2.png",
            image_type="screen_time",
            group_id="group2",
            processing_status=ProcessingStatus.COMPLETED,
        )
        db_session.add_all([screenshot1, screenshot2])
        await db_session.commit()

        response = await client.get(
            "/api/v1/screenshots/next?group=group2",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["screenshot"]["id"] == screenshot2.id

    async def test_get_next_screenshot_filter_by_processing_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test filtering queue by processing_status."""
        screenshot1 = Screenshot(
            file_path="/test1.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
        )
        screenshot2 = Screenshot(
            file_path="/test2.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.FAILED,
        )
        db_session.add_all([screenshot1, screenshot2])
        await db_session.commit()

        response = await client.get(
            "/api/v1/screenshots/next?processing_status=failed",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["screenshot"]["id"] == screenshot2.id

    async def test_skip_screenshot(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_screenshot: Screenshot,
    ):
        """Test skipping a screenshot sets processing_status to 'skipped'.

        Note: Globally skipped screenshots are still included in the default queue
        filter (for browse mode). The skip action changes the processing_status
        so it appears in the 'skipped' category on the homepage.
        """
        response = await client.post(
            f"/api/v1/screenshots/{test_screenshot.id}/skip",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 204

        # Verify screenshot now has 'skipped' processing status
        await db_session.refresh(test_screenshot)
        assert test_screenshot.processing_status == ProcessingStatus.SKIPPED

        # Verify skipped screenshot IS NOT returned when filtering for completed only
        response = await client.get(
            "/api/v1/screenshots/next?processing_status=completed",
            headers=auth_headers(test_user.username),
        )
        data = response.json()
        # Should return None since only screenshot is skipped
        assert data["screenshot"] is None

    async def test_get_disputed_screenshots(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test getting disputed screenshots."""
        from screenshot_processor.web.database.models import ConsensusResult

        screenshot = Screenshot(
            file_path="/disputed.png",
            image_type="screen_time",
            target_annotations=3,
        )
        db_session.add(screenshot)
        await db_session.commit()

        consensus = ConsensusResult(
            screenshot_id=screenshot.id,
            has_consensus=False,
            disagreement_details={"details": [{"hour": "0"}]},
        )
        db_session.add(consensus)
        await db_session.commit()

        response = await client.get(
            "/api/v1/screenshots/disputed",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(s["id"] == screenshot.id for s in data)

    async def test_list_screenshots_paginated(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test paginated screenshot list."""
        # Create multiple screenshots
        for i in range(5):
            screenshot = Screenshot(
                file_path=f"/test{i}.png",
                image_type="screen_time",
            )
            db_session.add(screenshot)
        await db_session.commit()

        response = await client.get(
            "/api/v1/screenshots/list?page=1&page_size=3",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        assert data["total"] >= 5
        assert data["page"] == 1
        assert data["has_next"] is True

    async def test_list_screenshots_filter_by_group(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test filtering screenshot list by group."""
        group = Group(id="testgroup", name="Test Group", image_type="screen_time")
        db_session.add(group)
        await db_session.commit()

        screenshot1 = Screenshot(
            file_path="/test1.png",
            image_type="screen_time",
            group_id="testgroup",
        )
        screenshot2 = Screenshot(
            file_path="/test2.png",
            image_type="screen_time",
            group_id=None,
        )
        db_session.add_all([screenshot1, screenshot2])
        await db_session.commit()

        response = await client.get(
            "/api/v1/screenshots/list?group_id=testgroup",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert all(item["group_id"] == "testgroup" for item in data["items"])
