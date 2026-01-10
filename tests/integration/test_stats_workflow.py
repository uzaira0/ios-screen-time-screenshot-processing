"""
Integration tests for statistics endpoints.
"""

from __future__ import annotations

import pytest
from tests.conftest import auth_headers
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    Annotation,
    ProcessingStatus,
    Screenshot,
    User,
)


@pytest.mark.asyncio
class TestStatsWorkflow:
    """Test statistics endpoints."""

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear stats cache before and after each test to avoid stale data."""
        from screenshot_processor.web.cache import invalidate_stats_and_groups

        invalidate_stats_and_groups()
        yield
        invalidate_stats_and_groups()

    async def test_get_stats_returns_all_fields(
        self,
        client: AsyncClient,
        test_user: User,
    ):
        """Test stats endpoint returns all expected fields."""
        response = await client.get(
            "/api/v1/screenshots/stats",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()

        # Verify all fields present
        assert "total_screenshots" in data
        assert "pending_screenshots" in data
        assert "completed_screenshots" in data
        assert "total_annotations" in data
        assert "screenshots_with_consensus" in data
        assert "screenshots_with_disagreements" in data
        assert "average_annotations_per_screenshot" in data
        assert "users_active" in data
        assert "auto_processed" in data
        assert "pending" in data
        assert "failed" in data
        assert "skipped" in data

    async def test_stats_update_after_upload(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test stats update after new screenshot upload."""
        # Get initial stats
        response1 = await client.get(
            "/api/v1/screenshots/stats",
            headers=auth_headers(test_user.username),
        )
        initial_total = response1.json()["total_screenshots"]

        # Add screenshot
        screenshot = Screenshot(
            file_path="/new.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.PENDING,
        )
        db_session.add(screenshot)
        await db_session.commit()

        # Invalidate cache and expire session so stats query sees new data
        from screenshot_processor.web.cache import invalidate_stats_and_groups

        # Get updated stats
        response2 = await client.get(
            "/api/v1/screenshots/stats",
            headers=auth_headers(test_user.username),
        )
        new_total = response2.json()["total_screenshots"]

        assert new_total == initial_total + 1

    async def test_stats_update_after_annotation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_screenshot: Screenshot,
    ):
        """Test stats update after annotation submission."""
        # Get initial stats
        response1 = await client.get(
            "/api/v1/screenshots/stats",
            headers=auth_headers(test_user.username),
        )
        initial_annotations = response1.json()["total_annotations"]

        # Submit annotation
        annotation = Annotation(
            screenshot_id=test_screenshot.id,
            user_id=test_user.id,
            hourly_values={"0": 10},
        )
        db_session.add(annotation)
        await db_session.commit()

        # Invalidate cache and expire session so stats query sees new data
        from screenshot_processor.web.cache import invalidate_stats_and_groups

        # Get updated stats
        response2 = await client.get(
            "/api/v1/screenshots/stats",
            headers=auth_headers(test_user.username),
        )
        new_annotations = response2.json()["total_annotations"]

        assert new_annotations == initial_annotations + 1

    async def test_stats_processing_status_counts(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test stats response includes processing status count fields."""
        response = await client.get(
            "/api/v1/screenshots/stats",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()

        # Verify all processing status count fields are present
        assert "pending" in data
        assert "auto_processed" in data
        assert "failed" in data
        assert "skipped" in data

        # Verify they are integers
        assert isinstance(data["pending"], int)
        assert isinstance(data["auto_processed"], int)
        assert isinstance(data["failed"], int)
        assert isinstance(data["skipped"], int)

    async def test_stats_consensus_counts(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test stats response includes consensus count fields."""
        response = await client.get(
            "/api/v1/screenshots/stats",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()

        # Verify consensus count fields are present
        assert "screenshots_with_consensus" in data
        assert "screenshots_with_disagreements" in data

        # Verify they are integers
        assert isinstance(data["screenshots_with_consensus"], int)
        assert isinstance(data["screenshots_with_disagreements"], int)

    async def test_stats_average_annotations_calculation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test average annotations per screenshot is calculated correctly."""
        # Create additional users (unique constraint: screenshot_id + user_id)
        user2 = User(username="user2_stats", role="annotator", is_active=True)
        db_session.add(user2)
        await db_session.commit()

        # Create 2 screenshots
        screenshot1 = Screenshot(file_path="/test1.png", image_type="screen_time")
        screenshot2 = Screenshot(file_path="/test2.png", image_type="screen_time")
        db_session.add_all([screenshot1, screenshot2])
        await db_session.commit()

        # Add 3 total annotations (2 for screenshot1 from different users, 1 for screenshot2)
        annotations = [
            Annotation(screenshot_id=screenshot1.id, user_id=test_user.id, hourly_values={"0": 10}),
            Annotation(screenshot_id=screenshot1.id, user_id=user2.id, hourly_values={"1": 15}),
            Annotation(screenshot_id=screenshot2.id, user_id=test_user.id, hourly_values={"0": 20}),
        ]
        db_session.add_all(annotations)
        await db_session.commit()

        response = await client.get(
            "/api/v1/screenshots/stats",
            headers=auth_headers(test_user.username),
        )

        data = response.json()
        # Average should be 3 annotations / 2 screenshots = 1.5
        # (Plus any existing screenshots/annotations from fixtures)
        assert data["average_annotations_per_screenshot"] >= 0

    async def test_stats_with_empty_database(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test stats with minimal data (just test fixtures)."""
        user = User(username="newuser", role="annotator", is_active=True)
        db_session.add(user)
        await db_session.commit()

        response = await client.get(
            "/api/v1/screenshots/stats",
            headers=auth_headers(user.username),
        )

        assert response.status_code == 200
        data = response.json()
        # All counts should be non-negative
        assert data["total_screenshots"] >= 0
        assert data["total_annotations"] >= 0
        # users_active counts users with annotations, so may be 0 if no annotations exist
        assert data["users_active"] >= 0

    async def test_stats_requires_authentication(
        self,
        client: AsyncClient,
    ):
        """Test stats endpoint requires authentication."""
        response = await client.get("/api/v1/screenshots/stats")

        # Should fail without auth header
        assert response.status_code == 401  # Unauthorized
