"""
Integration tests for Verification API endpoints.

Tests the screenshot verification workflow:
- POST /screenshots/{id}/verify - Add user to verified_by_user_ids
- DELETE /screenshots/{id}/verify - Remove user from verified_by_user_ids

These tests verify that verified_by_user_ids is persisted
to the database, including proper handling of JSON null vs SQL NULL.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    ProcessingStatus,
    Screenshot,
    User,
)
from tests.conftest import auth_headers
@pytest.mark.asyncio
class TestVerifyScreenshot:
    """Test POST /screenshots/{id}/verify endpoint."""

    async def test_verify_adds_user_to_database(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Verify MUST add user ID to verified_by_user_ids in database."""
        # Verify initial state
        assert test_screenshot.verified_by_user_ids is None or test_screenshot.verified_by_user_ids == []

        # Call API
        response = await client.post(
            f"/api/v1/screenshots/{test_screenshot.id}/verify",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200

        # Verify in DB
        await db_session.refresh(test_screenshot)
        assert test_screenshot.verified_by_user_ids is not None
        assert test_user.id in test_screenshot.verified_by_user_ids

    async def test_verify_is_idempotent(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Verifying twice should not duplicate user in list."""
        # Verify twice
        await client.post(
            f"/api/v1/screenshots/{test_screenshot.id}/verify",
            headers=auth_headers(test_user.username),
        )
        await client.post(
            f"/api/v1/screenshots/{test_screenshot.id}/verify",
            headers=auth_headers(test_user.username),
        )

        # Verify in DB
        await db_session.refresh(test_screenshot)
        assert test_screenshot.verified_by_user_ids.count(test_user.id) == 1

    async def test_verify_multiple_users(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        multiple_users: list[User],
    ):
        """Multiple users can verify the same screenshot."""
        for user in multiple_users:
            response = await client.post(
                f"/api/v1/screenshots/{test_screenshot.id}/verify",
                headers=auth_headers(user.username),
            )
            assert response.status_code == 200

        # Verify in DB
        # Re-fetch from database to get updated data
        result = await db_session.execute(
            select(Screenshot).where(Screenshot.id == test_screenshot.id)
        )
        refreshed = result.scalar_one()

        assert len(refreshed.verified_by_user_ids) == len(multiple_users)
        for user in multiple_users:
            assert user.id in refreshed.verified_by_user_ids

    async def test_verify_saves_grid_coordinates(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Verify with grid coordinates should save them to database."""
        response = await client.post(
            f"/api/v1/screenshots/{test_screenshot.id}/verify",
            json={
                "grid_upper_left_x": 100,
                "grid_upper_left_y": 200,
                "grid_lower_right_x": 500,
                "grid_lower_right_y": 600,
            },
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200

        # Verify in DB
        await db_session.refresh(test_screenshot)
        assert test_screenshot.grid_upper_left_x == 100
        assert test_screenshot.grid_upper_left_y == 200
        assert test_screenshot.grid_lower_right_x == 500
        assert test_screenshot.grid_lower_right_y == 600

    async def test_verify_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Verify should return 404 for non-existent screenshot."""
        response = await client.post(
            "/api/v1/screenshots/999999/verify",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 404

    async def test_verify_requires_auth(
        self,
        client: AsyncClient,
        test_screenshot: Screenshot,
    ):
        """Verify should require authentication."""
        response = await client.post(
            f"/api/v1/screenshots/{test_screenshot.id}/verify"
        )

        assert response.status_code == 401


@pytest.mark.asyncio
class TestUnverifyScreenshot:
    """Test DELETE /screenshots/{id}/verify endpoint.

    These tests verify that unverify removes user from
    verified_by_user_ids in the database, handling JSON null properly.
    """

    async def test_unverify_removes_user_from_database(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Unverify MUST remove user ID from verified_by_user_ids in database."""
        # First verify
        await client.post(
            f"/api/v1/screenshots/{test_screenshot.id}/verify",
            headers=auth_headers(test_user.username),
        )
        await db_session.refresh(test_screenshot)
        assert test_user.id in test_screenshot.verified_by_user_ids

        # Then unverify
        response = await client.delete(
            f"/api/v1/screenshots/{test_screenshot.id}/verify",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200

        # Verify in DB
        await db_session.refresh(test_screenshot)
        assert (
            test_screenshot.verified_by_user_ids is None
            or test_user.id not in test_screenshot.verified_by_user_ids
        )

    async def test_unverify_when_not_verified_is_noop(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Unverify when user hasn't verified should be a no-op."""
        # Ensure not verified
        assert test_screenshot.verified_by_user_ids is None or test_user.id not in test_screenshot.verified_by_user_ids

        response = await client.delete(
            f"/api/v1/screenshots/{test_screenshot.id}/verify",
            headers=auth_headers(test_user.username),
        )

        # Should not fail
        assert response.status_code == 200

    async def test_unverify_preserves_other_users(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        multiple_users: list[User],
    ):
        """Unverify should only remove the requesting user, preserving others."""
        # Have all users verify
        for user in multiple_users:
            await client.post(
                f"/api/v1/screenshots/{test_screenshot.id}/verify",
                headers=auth_headers(user.username),
            )

        # Have first user unverify
        await client.delete(
            f"/api/v1/screenshots/{test_screenshot.id}/verify",
            headers=auth_headers(multiple_users[0].username),
        )

        # Verify in DB
        result = await db_session.execute(
            select(Screenshot).where(Screenshot.id == test_screenshot.id)
        )
        refreshed = result.scalar_one()

        # First user should be removed, others should remain
        assert multiple_users[0].id not in refreshed.verified_by_user_ids
        assert multiple_users[1].id in refreshed.verified_by_user_ids
        assert multiple_users[2].id in refreshed.verified_by_user_ids

    async def test_unverify_last_user_sets_null(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Unverify when last user should set verified_by_user_ids to None."""
        # Verify
        await client.post(
            f"/api/v1/screenshots/{test_screenshot.id}/verify",
            headers=auth_headers(test_user.username),
        )

        # Unverify
        await client.delete(
            f"/api/v1/screenshots/{test_screenshot.id}/verify",
            headers=auth_headers(test_user.username),
        )

        # Verify in DB
        await db_session.refresh(test_screenshot)
        assert test_screenshot.verified_by_user_ids is None


@pytest.mark.asyncio
class TestVerifiedByMeFilter:
    """Test that verified_by_me filter correctly handles JSON null values."""

    async def test_verified_by_me_true_excludes_null(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """verified_by_me=true should exclude screenshots with null verified_by_user_ids."""
        # Create unverified screenshot (null)
        unverified = Screenshot(
            file_path="/test/unverified.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
            verified_by_user_ids=None,
            uploaded_by_id=test_user.id,
        )
        db_session.add(unverified)

        # Create verified screenshot
        verified = Screenshot(
            file_path="/test/verified.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
            verified_by_user_ids=[test_user.id],
            uploaded_by_id=test_user.id,
        )
        db_session.add(verified)
        await db_session.commit()

        response = await client.get(
            "/api/v1/screenshots/list?verified_by_me=true",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["file_path"] == "/test/verified.png"

    async def test_verified_by_me_false_includes_null(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """verified_by_me=false should include screenshots with null verified_by_user_ids."""
        # Create unverified screenshot (null)
        unverified = Screenshot(
            file_path="/test/unverified_for_filter.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
            verified_by_user_ids=None,
            uploaded_by_id=test_user.id,
        )
        db_session.add(unverified)

        # Create verified screenshot
        verified = Screenshot(
            file_path="/test/verified_for_filter.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
            verified_by_user_ids=[test_user.id],
            uploaded_by_id=test_user.id,
        )
        db_session.add(verified)
        await db_session.commit()

        response = await client.get(
            "/api/v1/screenshots/list?verified_by_me=false",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["file_path"] == "/test/unverified_for_filter.png"

    async def test_verified_by_me_excludes_empty_list(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """verified_by_me=true should also exclude empty lists []."""
        # Create screenshot with empty list (possible after all users unverify)
        empty_list = Screenshot(
            file_path="/test/empty_list.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
            verified_by_user_ids=[],  # Empty list, not null
            uploaded_by_id=test_user.id,
        )
        db_session.add(empty_list)

        # Create verified screenshot
        verified = Screenshot(
            file_path="/test/verified_not_empty.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
            verified_by_user_ids=[test_user.id],
            uploaded_by_id=test_user.id,
        )
        db_session.add(verified)
        await db_session.commit()

        response = await client.get(
            "/api/v1/screenshots/list?verified_by_me=true",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["file_path"] == "/test/verified_not_empty.png"


@pytest.mark.asyncio
class TestVerificationPersistenceAcrossSessions:
    """Test that verification persists correctly after database refresh operations."""

    async def test_verify_persists_after_refresh(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Verified status should persist after session refresh."""
        # Create screenshot
        screenshot = Screenshot(
            file_path="/test/persist_test.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
            uploaded_by_id=test_user.id,
        )
        db_session.add(screenshot)
        await db_session.commit()
        screenshot_id = screenshot.id

        # Verify via API
        await client.post(
            f"/api/v1/screenshots/{screenshot_id}/verify",
            headers=auth_headers(test_user.username),
        )

        # Force a new query (simulating new session)
        result = await db_session.execute(
            select(Screenshot).where(Screenshot.id == screenshot_id)
        )
        refreshed_screenshot = result.scalar_one()

        assert refreshed_screenshot.verified_by_user_ids is not None
        assert test_user.id in refreshed_screenshot.verified_by_user_ids

    async def test_unverify_persists_after_refresh(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Unverified status should persist after session refresh."""
        # Create already verified screenshot
        screenshot = Screenshot(
            file_path="/test/unverify_persist.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
            verified_by_user_ids=[test_user.id],
            uploaded_by_id=test_user.id,
        )
        db_session.add(screenshot)
        await db_session.commit()
        screenshot_id = screenshot.id

        # Unverify via API
        await client.delete(
            f"/api/v1/screenshots/{screenshot_id}/verify",
            headers=auth_headers(test_user.username),
        )

        # Force a new query (simulating new session)
        result = await db_session.execute(
            select(Screenshot).where(Screenshot.id == screenshot_id)
        )
        refreshed_screenshot = result.scalar_one()

        assert (
            refreshed_screenshot.verified_by_user_ids is None
            or test_user.id not in refreshed_screenshot.verified_by_user_ids
        )
