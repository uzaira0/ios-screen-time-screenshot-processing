"""
Integration tests for admin-only endpoints.

Tests user management, role changes, and admin authorization.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import User
from tests.conftest import auth_headers


@pytest.mark.asyncio
class TestAdminWorkflow:
    """Test admin-only endpoints."""

    async def test_get_all_users_as_admin(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin: User,
        test_user: User,
    ):
        """Test admin can get all users with stats."""
        response = await client.get(
            "/api/v1/admin/users",
            headers=auth_headers(test_admin.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2  # At least admin and test_user

        # Check user data structure
        user_data = next((u for u in data if u["username"] == test_user.username), None)
        assert user_data is not None
        assert "id" in user_data
        assert "role" in user_data
        assert "is_active" in user_data
        assert "annotations_count" in user_data
        assert "avg_time_spent_seconds" in user_data

    async def test_get_all_users_non_admin_forbidden(
        self,
        client: AsyncClient,
        test_user: User,
    ):
        """Test non-admin cannot access user management."""
        response = await client.get(
            "/api/v1/admin/users",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 403
        assert "Admin privileges required" in response.json()["detail"]

    async def test_update_user_role_as_admin(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin: User,
        test_user: User,
    ):
        """Test admin can update user role."""
        response = await client.put(
            f"/api/v1/admin/users/{test_user.id}?role=admin",
            headers=auth_headers(test_admin.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "admin"

        # Verify in database
        result = await db_session.execute(select(User).where(User.id == test_user.id))
        user = result.scalar_one()
        assert user.role == "admin"

    async def test_update_user_is_active_as_admin(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin: User,
        test_user: User,
    ):
        """Test admin can deactivate user."""
        response = await client.put(
            f"/api/v1/admin/users/{test_user.id}?is_active=false",
            headers=auth_headers(test_admin.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

        # Verify in database
        await db_session.refresh(test_user)
        assert test_user.is_active is False

    async def test_update_user_invalid_role(
        self,
        client: AsyncClient,
        test_admin: User,
        test_user: User,
    ):
        """Test updating user with invalid role fails."""
        response = await client.put(
            f"/api/v1/admin/users/{test_user.id}?role=invalid_role",
            headers=auth_headers(test_admin.username),
        )

        assert response.status_code == 400
        assert "Invalid role" in response.json()["detail"]

    async def test_update_nonexistent_user(
        self,
        client: AsyncClient,
        test_admin: User,
    ):
        """Test updating nonexistent user returns 404."""
        response = await client.put(
            "/api/v1/admin/users/99999?role=admin",
            headers=auth_headers(test_admin.username),
        )

        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]

    async def test_update_user_non_admin_forbidden(
        self,
        client: AsyncClient,
        test_user: User,
    ):
        """Test non-admin cannot update users."""
        response = await client.put(
            f"/api/v1/admin/users/{test_user.id}?role=admin",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 403

    async def test_admin_user_stats_include_annotations(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin: User,
        test_user: User,
        test_screenshot,
    ):
        """Test user stats include annotation count."""
        from screenshot_processor.web.database.models import Annotation

        # Create annotation
        annotation = Annotation(
            screenshot_id=test_screenshot.id,
            user_id=test_user.id,
            hourly_values={"0": 10},
            time_spent_seconds=120.5,
        )
        db_session.add(annotation)
        await db_session.commit()

        response = await client.get(
            "/api/v1/admin/users",
            headers=auth_headers(test_admin.username),
        )

        assert response.status_code == 200
        data = response.json()

        user_data = next((u for u in data if u["id"] == test_user.id), None)
        assert user_data["annotations_count"] == 1
        assert user_data["avg_time_spent_seconds"] == 120.5

    async def test_update_user_both_role_and_active(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin: User,
        test_user: User,
    ):
        """Test updating both role and is_active simultaneously."""
        response = await client.put(
            f"/api/v1/admin/users/{test_user.id}?role=admin&is_active=false",
            headers=auth_headers(test_admin.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "admin"
        assert data["is_active"] is False

        await db_session.refresh(test_user)
        assert test_user.role == "admin"
        assert test_user.is_active is False
