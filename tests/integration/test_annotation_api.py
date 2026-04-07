"""
Integration tests for Annotation API endpoints.

Tests the annotation CRUD workflow:
- POST /annotations/ - Create or update annotation (upsert)
- GET /annotations/history - Get user's annotation history
- GET /annotations/{id} - Get annotation by ID
- PUT /annotations/{id} - Update annotation
- DELETE /annotations/{id} - Delete annotation

These tests verify that annotations are persisted to the
database and that the screenshot's annotation_count is correctly updated.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    Annotation,
    ProcessingStatus,
    Screenshot,
    User,
)
from tests.conftest import auth_headers
@pytest.mark.asyncio
class TestCreateAnnotation:
    """Test POST /annotations/ endpoint."""

    async def test_create_annotation_persists_to_database(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Create annotation MUST persist to database."""
        annotation_data = {
            "screenshot_id": test_screenshot.id,
            "hourly_values": {"0": 10, "1": 20, "5": 30},
            "extracted_title": "Test App",
            "extracted_total": "1h 0m",
        }

        response = await client.post(
            "/api/v1/annotations/",
            json=annotation_data,
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 201
        data = response.json()

        # Verify in DB
        result = await db_session.execute(
            select(Annotation).where(Annotation.id == data["id"])
        )
        annotation = result.scalar_one()

        assert annotation.screenshot_id == test_screenshot.id
        assert annotation.user_id == test_user.id
        assert annotation.hourly_values == {"0": 10, "1": 20, "5": 30}
        assert annotation.extracted_title == "Test App"
        assert annotation.extracted_total == "1h 0m"

    async def test_create_annotation_increments_count(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Creating annotation MUST increment screenshot's annotation count."""
        initial_count = test_screenshot.current_annotation_count

        await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 10},
                "extracted_title": "App",
                "extracted_total": "10m",
            },
            headers=auth_headers(test_user.username),
        )

        # Verify in DB
        await db_session.refresh(test_screenshot)
        assert test_screenshot.current_annotation_count == initial_count + 1

    async def test_create_annotation_with_grid_coordinates(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Create annotation with grid coordinates should persist them."""
        annotation_data = {
            "screenshot_id": test_screenshot.id,
            "hourly_values": {"0": 10},
            "extracted_title": "App",
            "extracted_total": "10m",
            "grid_upper_left": {"x": 100, "y": 200},
            "grid_lower_right": {"x": 500, "y": 600},
        }

        response = await client.post(
            "/api/v1/annotations/",
            json=annotation_data,
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 201
        data = response.json()

        # Verify in DB
        result = await db_session.execute(
            select(Annotation).where(Annotation.id == data["id"])
        )
        annotation = result.scalar_one()

        assert annotation.grid_upper_left == {"x": 100, "y": 200}
        assert annotation.grid_lower_right == {"x": 500, "y": 600}

    async def test_create_annotation_with_time_spent(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Create annotation with time_spent_seconds should persist it."""
        annotation_data = {
            "screenshot_id": test_screenshot.id,
            "hourly_values": {"0": 10},
            "extracted_title": "App",
            "extracted_total": "10m",
            "time_spent_seconds": 45,
        }

        response = await client.post(
            "/api/v1/annotations/",
            json=annotation_data,
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 201
        data = response.json()

        result = await db_session.execute(
            select(Annotation).where(Annotation.id == data["id"])
        )
        annotation = result.scalar_one()
        assert annotation.time_spent_seconds == 45

    async def test_create_annotation_upsert_updates_existing(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Second annotation from same user for same screenshot should update, not create."""
        # First annotation
        first_response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 10},
                "extracted_title": "First Title",
                "extracted_total": "10m",
            },
            headers=auth_headers(test_user.username),
        )
        first_id = first_response.json()["id"]

        # Second annotation (same user, same screenshot)
        second_response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 20},
                "extracted_title": "Updated Title",
                "extracted_total": "20m",
            },
            headers=auth_headers(test_user.username),
        )
        second_id = second_response.json()["id"]

        # Should return same ID (update, not create)
        assert first_id == second_id

        # Verify in DB
        result = await db_session.execute(
            select(Annotation).where(Annotation.id == first_id)
        )
        annotation = result.scalar_one()

        assert annotation.hourly_values == {"0": 20}
        assert annotation.extracted_title == "Updated Title"

        # Count should still be 1
        await db_session.refresh(test_screenshot)
        assert test_screenshot.current_annotation_count == 1

    async def test_create_annotation_different_users_creates_new(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        multiple_users: list[User],
    ):
        """Different users should create separate annotations."""
        annotation_ids = []

        for user in multiple_users[:2]:
            response = await client.post(
                "/api/v1/annotations/",
                json={
                    "screenshot_id": test_screenshot.id,
                    "hourly_values": {"0": 10},
                    "extracted_title": f"From {user.username}",
                    "extracted_total": "10m",
                },
                headers=auth_headers(user.username),
            )
            assert response.status_code == 201
            annotation_ids.append(response.json()["id"])

        # Should have different IDs
        assert annotation_ids[0] != annotation_ids[1]

        # Verify count in DB
        await db_session.refresh(test_screenshot)
        assert test_screenshot.current_annotation_count == 2

    async def test_create_annotation_not_found_screenshot(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Create annotation for non-existent screenshot should fail."""
        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": 999999,
                "hourly_values": {"0": 10},
                "extracted_title": "App",
                "extracted_total": "10m",
            },
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 404

    async def test_create_annotation_requires_auth(
        self,
        client: AsyncClient,
        test_screenshot: Screenshot,
    ):
        """Create annotation should require authentication."""
        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 10},
                "extracted_title": "App",
                "extracted_total": "10m",
            },
        )

        assert response.status_code == 401


@pytest.mark.asyncio
class TestGetAnnotationHistory:
    """Test GET /annotations/history endpoint."""

    async def test_history_returns_user_annotations(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """History should return only the current user's annotations."""
        # Create annotation
        annotation = Annotation(
            screenshot_id=test_screenshot.id,
            user_id=test_user.id,
            hourly_values={"0": 10},
            extracted_title="Test",
            extracted_total="10m",
        )
        db_session.add(annotation)
        await db_session.commit()

        response = await client.get(
            "/api/v1/annotations/history",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        # Should contain annotation for this user
        annotation_ids = [a["id"] for a in data]
        assert annotation.id in annotation_ids

    async def test_history_excludes_other_users(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        multiple_users: list[User],
    ):
        """History should NOT include other users' annotations."""
        # Create annotations from multiple users
        for i, user in enumerate(multiple_users):
            annotation = Annotation(
                screenshot_id=test_screenshot.id,
                user_id=user.id,
                hourly_values={"0": i * 10},
                extracted_title=f"User {i}",
                extracted_total=f"{i * 10}m",
            )
            db_session.add(annotation)
        await db_session.commit()

        # Get history for first user only
        response = await client.get(
            "/api/v1/annotations/history",
            headers=auth_headers(multiple_users[0].username),
        )

        assert response.status_code == 200
        data = response.json()
        # Should only contain first user's annotation
        assert len(data) == 1
        assert data[0]["user_id"] == multiple_users[0].id

    async def test_history_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """History should support pagination."""
        # Create multiple screenshots and annotations
        for i in range(5):
            screenshot = Screenshot(
                file_path=f"/test/history_{i}.png",
                image_type="screen_time",
                processing_status=ProcessingStatus.COMPLETED,
                uploaded_by_id=test_user.id,
            )
            db_session.add(screenshot)
            await db_session.flush()
            annotation = Annotation(
                screenshot_id=screenshot.id,
                user_id=test_user.id,
                hourly_values={"0": i},
                extracted_title=f"App {i}",
                extracted_total=f"{i}m",
            )
            db_session.add(annotation)
        await db_session.commit()

        response = await client.get(
            "/api/v1/annotations/history?skip=0&limit=2",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2


@pytest.mark.asyncio
class TestGetAnnotation:
    """Test GET /annotations/{id} endpoint."""

    async def test_get_annotation_by_id(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Should return annotation details by ID."""
        annotation = Annotation(
            screenshot_id=test_screenshot.id,
            user_id=test_user.id,
            hourly_values={"0": 10, "1": 20},
            extracted_title="Test App",
            extracted_total="30m",
        )
        db_session.add(annotation)
        await db_session.commit()

        response = await client.get(
            f"/api/v1/annotations/{annotation.id}",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == annotation.id
        assert data["hourly_values"] == {"0": 10, "1": 20}
        assert data["extracted_title"] == "Test App"

    async def test_get_annotation_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Should return 404 for non-existent annotation."""
        response = await client.get(
            "/api/v1/annotations/999999",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 404

    async def test_get_annotation_forbidden_for_other_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        multiple_users: list[User],
    ):
        """Non-admin users should not see other users' annotations."""
        # Create annotation by first user
        annotation = Annotation(
            screenshot_id=test_screenshot.id,
            user_id=multiple_users[0].id,
            hourly_values={"0": 10},
            extracted_title="Test",
            extracted_total="10m",
        )
        db_session.add(annotation)
        await db_session.commit()

        # Second user tries to access
        response = await client.get(
            f"/api/v1/annotations/{annotation.id}",
            headers=auth_headers(multiple_users[1].username),
        )

        assert response.status_code == 403


@pytest.mark.asyncio
class TestUpdateAnnotation:
    """Test PUT /annotations/{id} endpoint."""

    async def test_update_annotation_persists_to_database(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Update annotation MUST persist changes to database."""
        annotation = Annotation(
            screenshot_id=test_screenshot.id,
            user_id=test_user.id,
            hourly_values={"0": 10},
            extracted_title="Original",
            extracted_total="10m",
        )
        db_session.add(annotation)
        await db_session.commit()

        response = await client.put(
            f"/api/v1/annotations/{annotation.id}",
            json={
                "hourly_values": {"0": 20, "1": 30},
                "extracted_title": "Updated",
            },
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200

        # Verify in DB
        await db_session.refresh(annotation)
        assert annotation.hourly_values == {"0": 20, "1": 30}
        assert annotation.extracted_title == "Updated"

    async def test_update_annotation_forbidden_for_other_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        multiple_users: list[User],
    ):
        """Users should not be able to update others' annotations."""
        # Create annotation by first user
        annotation = Annotation(
            screenshot_id=test_screenshot.id,
            user_id=multiple_users[0].id,
            hourly_values={"0": 10},
            extracted_title="Original",
            extracted_total="10m",
        )
        db_session.add(annotation)
        await db_session.commit()

        # Second user tries to update
        response = await client.put(
            f"/api/v1/annotations/{annotation.id}",
            json={"hourly_values": {"0": 99}},
            headers=auth_headers(multiple_users[1].username),
        )

        assert response.status_code == 403


@pytest.mark.asyncio
class TestDeleteAnnotation:
    """Test DELETE /annotations/{id} endpoint."""

    async def test_delete_annotation_removes_from_database(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Delete annotation MUST remove it from database."""
        annotation = Annotation(
            screenshot_id=test_screenshot.id,
            user_id=test_user.id,
            hourly_values={"0": 10},
            extracted_title="To Delete",
            extracted_total="10m",
        )
        db_session.add(annotation)
        test_screenshot.current_annotation_count = 1
        await db_session.commit()
        annotation_id = annotation.id

        response = await client.delete(
            f"/api/v1/annotations/{annotation_id}",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 204

        # Verify in DB
        result = await db_session.execute(
            select(Annotation).where(Annotation.id == annotation_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_delete_annotation_decrements_count(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Deleting annotation MUST decrement screenshot's annotation count."""
        annotation = Annotation(
            screenshot_id=test_screenshot.id,
            user_id=test_user.id,
            hourly_values={"0": 10},
            extracted_title="To Delete",
            extracted_total="10m",
        )
        db_session.add(annotation)
        test_screenshot.current_annotation_count = 1
        await db_session.commit()

        await client.delete(
            f"/api/v1/annotations/{annotation.id}",
            headers=auth_headers(test_user.username),
        )

        # Verify in DB
        await db_session.refresh(test_screenshot)
        assert test_screenshot.current_annotation_count == 0

    async def test_delete_annotation_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Delete non-existent annotation should return 404."""
        response = await client.delete(
            "/api/v1/annotations/999999",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 404

    async def test_delete_annotation_forbidden_for_other_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        multiple_users: list[User],
    ):
        """Users should not be able to delete others' annotations."""
        # Create annotation by first user
        annotation = Annotation(
            screenshot_id=test_screenshot.id,
            user_id=multiple_users[0].id,
            hourly_values={"0": 10},
            extracted_title="Other user's",
            extracted_total="10m",
        )
        db_session.add(annotation)
        await db_session.commit()

        # Second user tries to delete
        response = await client.delete(
            f"/api/v1/annotations/{annotation.id}",
            headers=auth_headers(multiple_users[1].username),
        )

        assert response.status_code == 403

        # Annotation should still exist
        result = await db_session.execute(
            select(Annotation).where(Annotation.id == annotation.id)
        )
        assert result.scalar_one_or_none() is not None
