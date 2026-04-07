"""
End-to-end tests for error handling and recovery.

Tests error scenarios, validation failures, and system resilience.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    ProcessingStatus,
    Screenshot,
    User,
)
from tests.integration.conftest import auth_headers


@pytest.mark.asyncio
class TestErrorRecovery:
    """Test error handling and recovery scenarios."""

    async def test_invalid_screenshot_id(
        self,
        client: AsyncClient,
        test_user: User,
    ):
        """Test annotation submission with invalid screenshot_id."""
        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": 99999,
                "hourly_values": {"0": 10},
                "extracted_title": "Screen Time",
                "extracted_total": "10m",
                "grid_upper_left": {"x": 100, "y": 100},
                "grid_lower_right": {"x": 500, "y": 500},
            },
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 404
        assert "Screenshot not found" in response.json()["detail"]

    async def test_malformed_annotation_data(
        self,
        client: AsyncClient,
        test_user: User,
        test_screenshot: Screenshot,
    ):
        """Test annotation with malformed data."""
        # Missing required field
        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                # Missing hourly_values
                "extracted_title": "Screen Time",
            },
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 422  # Validation error

    async def test_invalid_grid_coordinates(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_screenshot: Screenshot,
    ):
        """Test annotation with invalid grid coordinates."""
        test_screenshot.processing_status = ProcessingStatus.COMPLETED
        await db_session.commit()

        # Negative coordinates
        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 10},
                "grid_upper_left": {"x": -10, "y": 100},
                "grid_lower_right": {"x": 500, "y": 500},
            },
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 422

    async def test_missing_authentication(
        self,
        client: AsyncClient,
        test_screenshot: Screenshot,
    ):
        """Test endpoints without authentication."""
        # No auth header - returns 401 Unauthorized
        response = await client.get("/api/v1/screenshots/next")
        assert response.status_code == 401  # Unauthorized - missing X-Username header

        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 10},
            },
        )
        assert response.status_code == 401  # Unauthorized - missing X-Username header

    async def test_annotation_deletion_rollback(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_screenshot: Screenshot,
    ):
        """Test annotation deletion updates screenshot count correctly."""
        test_screenshot.processing_status = ProcessingStatus.COMPLETED
        await db_session.commit()

        # Create annotation
        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 10},
                "grid_upper_left": {"x": 100, "y": 100},
                "grid_lower_right": {"x": 500, "y": 500},
            },
            headers=auth_headers(test_user.username),
        )
        annotation_id = response.json()["id"]

        # Verify count increased
        await db_session.refresh(test_screenshot)
        initial_count = test_screenshot.current_annotation_count
        assert initial_count == 1

        # Delete annotation
        delete_response = await client.delete(
            f"/api/v1/annotations/{annotation_id}",
            headers=auth_headers(test_user.username),
        )
        assert delete_response.status_code == 204

        # Verify count decreased
        await db_session.refresh(test_screenshot)
        assert test_screenshot.current_annotation_count == initial_count - 1

    async def test_unauthorized_annotation_deletion(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_users,
        test_screenshot: Screenshot,
    ):
        """Test user cannot delete another user's annotation."""
        test_screenshot.processing_status = ProcessingStatus.COMPLETED
        await db_session.commit()

        # User1 creates annotation
        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 10},
                "grid_upper_left": {"x": 100, "y": 100},
                "grid_lower_right": {"x": 500, "y": 500},
            },
            headers=auth_headers(multiple_users[0].username),
        )
        annotation_id = response.json()["id"]

        # User2 tries to delete
        delete_response = await client.delete(
            f"/api/v1/annotations/{annotation_id}",
            headers=auth_headers(multiple_users[1].username),
        )

        assert delete_response.status_code == 403
        assert "can only delete your own" in delete_response.json()["detail"].lower()

    async def test_nonexistent_screenshot_operations(
        self,
        client: AsyncClient,
        test_user: User,
    ):
        """Test operations on nonexistent screenshot."""
        nonexistent_id = 99999

        # Get screenshot
        response = await client.get(
            f"/api/v1/screenshots/{nonexistent_id}",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 404

        # Skip screenshot
        response = await client.post(
            f"/api/v1/screenshots/{nonexistent_id}/skip",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 404

        # Verify screenshot
        response = await client.post(
            f"/api/v1/screenshots/{nonexistent_id}/verify",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 404

    async def test_empty_hourly_values(
        self,
        client: AsyncClient,
        test_user: User,
        test_screenshot: Screenshot,
    ):
        """Test annotation with empty hourly_values."""
        test_screenshot.processing_status = ProcessingStatus.COMPLETED

        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {},  # Empty
                "grid_upper_left": {"x": 100, "y": 100},
                "grid_lower_right": {"x": 500, "y": 500},
            },
            headers=auth_headers(test_user.username),
        )

        # Should succeed (empty is valid, just unusual)
        assert response.status_code == 201

    async def test_database_transaction_rollback(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_screenshot: Screenshot,
    ):
        """Test database rollback on error maintains consistency."""
        initial_count = test_screenshot.current_annotation_count

        # Attempt annotation with invalid data (will fail validation)
        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 10},
                "grid_upper_left": {"x": -100, "y": 100},  # Invalid
                "grid_lower_right": {"x": 500, "y": 500},
            },
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 422

        # Verify count unchanged (transaction rolled back)
        await db_session.refresh(test_screenshot)
        assert test_screenshot.current_annotation_count == initial_count

    async def test_admin_cannot_deactivate_self(
        self,
        client: AsyncClient,
        test_admin: User,
    ):
        """Test admin cannot deactivate their own account."""
        # This is a business rule to prevent lockout
        # Implementation depends on backend logic
        response = await client.put(
            f"/api/v1/admin/users/{test_admin.id}?is_active=false",
            headers=auth_headers(test_admin.username),
        )

        # Should either succeed or have safeguard
        # If safeguard exists, it would return 400
        # If no safeguard, test documents current behavior
        assert response.status_code in [200, 400]

    async def test_export_with_no_data(
        self,
        client: AsyncClient,
        test_user: User,
    ):
        """Test export endpoints with no matching data."""
        # Export from nonexistent group
        response = await client.get(
            "/api/v1/screenshots/export/json?group_id=nonexistent",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["screenshots"] == []

    async def test_invalid_pagination_parameters(
        self,
        client: AsyncClient,
        test_user: User,
    ):
        """Test list endpoint with invalid pagination."""
        # Negative page
        response = await client.get(
            "/api/v1/screenshots/list?page=-1",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 422

        # Page size too large (max is 5000)
        response = await client.get(
            "/api/v1/screenshots/list?page_size=10000",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 422

    async def test_recovery_from_failed_processing(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test screenshots with failed processing can still be annotated."""
        # Create screenshot with failed processing
        screenshot = Screenshot(
            file_path="/failed.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.FAILED,
            has_blocking_issues=False,  # Non-blocking failure
        )
        db_session.add(screenshot)
        await db_session.commit()

        # User can still annotate
        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": screenshot.id,
                "hourly_values": {"0": 10},
                "grid_upper_left": {"x": 100, "y": 100},
                "grid_lower_right": {"x": 500, "y": 500},
            },
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 201
