"""
Auth guard tests for API endpoints.

Verifies that:
1. Unauthenticated requests (no X-Username header) get 401
2. Non-admin users get 403 on admin-only endpoints
3. Admin users CAN access admin endpoints
4. Annotation ownership is enforced (403 for other users' annotations)
5. Auto-create user behavior works correctly
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    Annotation,
    Group,
    Screenshot,
    User,
)
from tests.conftest import auth_headers
# =============================================================================
# Unauthenticated access - all endpoints require auth
# =============================================================================


@pytest.mark.asyncio
class TestUnauthenticatedAccess:
    """All endpoints requiring X-Username header should return 401 without it."""

    @pytest.mark.parametrize(
        "method,path",
        [
            # Screenshot endpoints
            ("GET", "/api/v1/screenshots/next"),
            ("GET", "/api/v1/screenshots/stats"),
            ("GET", "/api/v1/screenshots/list"),
            ("GET", "/api/v1/screenshots/groups"),
            ("GET", "/api/v1/screenshots/1"),
            ("GET", "/api/v1/screenshots/1/navigate?direction=current"),
            ("POST", "/api/v1/screenshots/1/skip"),
            # Annotation endpoints
            ("GET", "/api/v1/annotations/history"),
            ("GET", "/api/v1/annotations/1"),
            ("DELETE", "/api/v1/annotations/1"),
            # Admin endpoints
            ("GET", "/api/v1/admin/users"),
            ("GET", "/api/v1/admin/orphaned-entries"),
            ("POST", "/api/v1/admin/cleanup-orphaned"),
            ("POST", "/api/v1/admin/reset-test-data"),
            ("POST", "/api/v1/admin/bulk-reprocess"),
            # Consensus endpoint
            ("GET", "/api/v1/consensus/1"),
        ],
        ids=[
            "next", "stats", "list", "groups", "get_screenshot",
            "navigate", "skip",
            "annotation_history", "get_annotation", "delete_annotation",
            "admin_users", "admin_orphaned", "admin_cleanup",
            "admin_reset", "admin_bulk_reprocess",
            "consensus",
        ],
    )
    async def test_unauthenticated_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        method: str,
        path: str,
    ):
        """Requests without X-Username header should be rejected with 401."""
        if method == "GET":
            response = await client.get(path)
        elif method == "POST":
            response = await client.post(path)
        elif method == "DELETE":
            response = await client.delete(path)
        elif method == "PUT":
            response = await client.put(path)
        else:
            pytest.fail(f"Unknown method: {method}")

        assert response.status_code == 401, (
            f"{method} {path} without auth: expected 401, got {response.status_code}"
        )

    async def test_create_annotation_unauthenticated(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """POST /annotations/ without auth should return 401."""
        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": 1,
                "hourly_values": {"0": 10},
                "extracted_title": "App",
                "extracted_total": "10m",
            },
        )
        assert response.status_code == 401

    async def test_update_annotation_unauthenticated(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """PUT /annotations/{id} without auth should return 401."""
        response = await client.put(
            "/api/v1/annotations/1",
            json={"hourly_values": {"0": 10}},
        )
        assert response.status_code == 401

    async def test_empty_username_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Empty X-Username header should be rejected."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"X-Username": ""},
        )
        # Should fail - empty username is not valid
        assert response.status_code in (400, 401, 422)


# =============================================================================
# Non-admin users blocked from admin endpoints
# =============================================================================


@pytest.mark.asyncio
class TestNonAdminBlocked:
    """Non-admin users should get 403 on all admin endpoints."""

    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/api/v1/admin/users"),
            ("GET", "/api/v1/admin/orphaned-entries"),
            ("POST", "/api/v1/admin/cleanup-orphaned"),
            ("POST", "/api/v1/admin/reset-test-data"),
            ("POST", "/api/v1/admin/bulk-reprocess"),
        ],
        ids=["users", "orphaned_entries", "cleanup", "reset", "bulk_reprocess"],
    )
    async def test_non_admin_gets_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        method: str,
        path: str,
    ):
        """Annotator role should be denied access to admin endpoints."""
        if method == "GET":
            response = await client.get(path, headers=auth_headers(test_user.username))
        else:
            response = await client.post(path, headers=auth_headers(test_user.username))

        assert response.status_code == 403, (
            f"{method} {path} as non-admin: expected 403, got {response.status_code}"
        )

    async def test_non_admin_cannot_delete_group(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_group: Group,
    ):
        """Non-admin should not be able to delete groups."""
        response = await client.delete(
            f"/api/v1/admin/groups/{test_group.id}",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 403

    async def test_non_admin_cannot_update_user_role(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Non-admin should not be able to change user roles."""
        response = await client.put(
            f"/api/v1/admin/users/{test_user.id}?role=admin",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 403


# =============================================================================
# Admin users have access
# =============================================================================


@pytest.mark.asyncio
class TestAdminAccess:
    """Verify that admin users CAN access admin endpoints."""

    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/api/v1/admin/users"),
            ("GET", "/api/v1/admin/orphaned-entries"),
            ("POST", "/api/v1/admin/cleanup-orphaned"),
            ("POST", "/api/v1/admin/reset-test-data"),
        ],
        ids=["users", "orphaned_entries", "cleanup", "reset"],
    )
    async def test_admin_can_access(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin: User,
        method: str,
        path: str,
    ):
        """Admin should get 200 on admin endpoints."""
        if method == "GET":
            response = await client.get(path, headers=auth_headers(test_admin.username))
        else:
            response = await client.post(path, headers=auth_headers(test_admin.username))

        assert response.status_code == 200, (
            f"{method} {path} as admin: expected 200, got {response.status_code}. "
            f"Body: {response.text}"
        )


# =============================================================================
# Admin role change edge cases
# =============================================================================


@pytest.mark.asyncio
class TestAdminRoleChanges:
    """Test admin user management edge cases."""

    @pytest.mark.parametrize(
        "role,expected_status",
        [
            ("admin", 200),
            ("annotator", 200),
            ("superuser", 400),
            ("", 400),
            ("Admin", 400),
            ("ADMIN", 400),
        ],
        ids=["admin", "annotator", "superuser", "empty", "wrong_case", "all_caps"],
    )
    async def test_role_change_validation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin: User,
        test_user: User,
        role: str,
        expected_status: int,
    ):
        """Only valid role values should be accepted."""
        response = await client.put(
            f"/api/v1/admin/users/{test_user.id}?role={role}",
            headers=auth_headers(test_admin.username),
        )
        assert response.status_code == expected_status, (
            f"Role '{role}': expected {expected_status}, got {response.status_code}. "
            f"Body: {response.text}"
        )

    async def test_deactivate_and_reactivate_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin: User,
        test_user: User,
    ):
        """Deactivating and reactivating a user should persist correctly."""
        # Deactivate
        response = await client.put(
            f"/api/v1/admin/users/{test_user.id}?is_active=false",
            headers=auth_headers(test_admin.username),
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False

        await db_session.refresh(test_user)
        assert test_user.is_active is False

        # Reactivate
        response = await client.put(
            f"/api/v1/admin/users/{test_user.id}?is_active=true",
            headers=auth_headers(test_admin.username),
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is True

        await db_session.refresh(test_user)
        assert test_user.is_active is True

    async def test_update_nonexistent_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin: User,
    ):
        """Updating a nonexistent user should return 404."""
        response = await client.put(
            "/api/v1/admin/users/999999?role=admin",
            headers=auth_headers(test_admin.username),
        )
        assert response.status_code == 404


# =============================================================================
# Cross-user annotation ownership
# =============================================================================


@pytest.mark.asyncio
class TestAnnotationOwnership:
    """Test that annotation ownership is enforced correctly."""

    async def test_user_cannot_update_others_annotation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        multiple_users: list[User],
    ):
        """User should not be able to update another user's annotation."""
        annotation = Annotation(
            screenshot_id=test_screenshot.id,
            user_id=multiple_users[0].id,
            hourly_values={"0": 10},
            extracted_title="Owner's annotation",
            extracted_total="10m",
        )
        db_session.add(annotation)
        await db_session.commit()

        response = await client.put(
            f"/api/v1/annotations/{annotation.id}",
            json={"extracted_title": "Hacked!"},
            headers=auth_headers(multiple_users[1].username),
        )
        assert response.status_code == 403

        # Verify original value is unchanged
        await db_session.refresh(annotation)
        assert annotation.extracted_title == "Owner's annotation"

    async def test_user_cannot_delete_others_annotation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        multiple_users: list[User],
    ):
        """User should not be able to delete another user's annotation."""
        annotation = Annotation(
            screenshot_id=test_screenshot.id,
            user_id=multiple_users[0].id,
            hourly_values={"0": 10},
            extracted_title="Protected",
            extracted_total="10m",
        )
        db_session.add(annotation)
        await db_session.commit()
        annotation_id = annotation.id

        response = await client.delete(
            f"/api/v1/annotations/{annotation_id}",
            headers=auth_headers(multiple_users[1].username),
        )
        assert response.status_code == 403

        # Verify annotation still exists
        result = await db_session.execute(
            select(Annotation).where(Annotation.id == annotation_id)
        )
        assert result.scalar_one_or_none() is not None

    async def test_admin_can_delete_others_annotation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_admin: User,
        test_user: User,
    ):
        """Admin should be able to delete any user's annotation."""
        annotation = Annotation(
            screenshot_id=test_screenshot.id,
            user_id=test_user.id,
            hourly_values={"0": 10},
            extracted_title="User's annotation",
            extracted_total="10m",
        )
        db_session.add(annotation)
        test_screenshot.current_annotation_count = 1
        await db_session.commit()
        annotation_id = annotation.id

        response = await client.delete(
            f"/api/v1/annotations/{annotation_id}",
            headers=auth_headers(test_admin.username),
        )
        assert response.status_code == 204

        result = await db_session.execute(
            select(Annotation).where(Annotation.id == annotation_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_admin_can_view_others_annotation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_admin: User,
        test_user: User,
    ):
        """Admin should be able to view annotations from other users."""
        annotation = Annotation(
            screenshot_id=test_screenshot.id,
            user_id=test_user.id,
            hourly_values={"0": 10},
            extracted_title="User's annotation",
            extracted_total="10m",
        )
        db_session.add(annotation)
        await db_session.commit()

        response = await client.get(
            f"/api/v1/annotations/{annotation.id}",
            headers=auth_headers(test_admin.username),
        )
        assert response.status_code == 200
        assert response.json()["extracted_title"] == "User's annotation"

    async def test_user_cannot_view_others_annotation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        multiple_users: list[User],
    ):
        """Non-admin user should not be able to view others' annotations."""
        annotation = Annotation(
            screenshot_id=test_screenshot.id,
            user_id=multiple_users[0].id,
            hourly_values={"0": 10},
            extracted_title="Private",
            extracted_total="10m",
        )
        db_session.add(annotation)
        await db_session.commit()

        response = await client.get(
            f"/api/v1/annotations/{annotation.id}",
            headers=auth_headers(multiple_users[1].username),
        )
        assert response.status_code == 403


# =============================================================================
# Auto-create user on first request
# =============================================================================


@pytest.mark.asyncio
class TestAutoCreateUser:
    """Test that users are auto-created on first authenticated request."""

    async def test_new_username_auto_creates_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """First request with a new username should auto-create the user."""
        response = await client.get(
            "/api/v1/screenshots/stats",
            headers=auth_headers("brand-new-user-xyz"),
        )
        assert response.status_code == 200

        result = await db_session.execute(
            select(User).where(User.username == "brand-new-user-xyz")
        )
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.role == "annotator"
        assert user.is_active is True

    async def test_admin_username_gets_admin_role(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Username 'admin' should be auto-created with admin role."""
        response = await client.get(
            "/api/v1/admin/users",
            headers=auth_headers("admin"),
        )
        assert response.status_code == 200

        result = await db_session.execute(
            select(User).where(User.username == "admin")
        )
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.role == "admin"

    async def test_user_persists_across_requests(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Same username on subsequent requests should return the same user."""
        r1 = await client.get(
            "/api/v1/auth/me",
            headers=auth_headers("persist-test"),
        )
        r2 = await client.get(
            "/api/v1/auth/me",
            headers=auth_headers("persist-test"),
        )
        assert r1.json()["id"] == r2.json()["id"]
