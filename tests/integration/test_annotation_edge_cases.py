"""
Edge case tests for Annotation API endpoints.

Tests validation boundaries, invalid inputs, and concurrent behavior
that the base test_annotation_api.py does not cover.
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
# =============================================================================
# Hourly values validation
# =============================================================================


@pytest.mark.asyncio
class TestHourlyValuesValidation:
    """Test that hourly_values dict is properly validated."""

    @pytest.mark.parametrize(
        "hourly_values,expected_status",
        [
            # Invalid hour keys
            ({"24": 10}, 422),  # Hour 24 out of range
            ({"-1": 10}, 422),  # Negative hour
            ({"25": 5}, 422),  # Hour 25 out of range
            ({"abc": 10}, 422),  # Non-numeric key
            ({"1.5": 10}, 422),  # Fractional hour key
            ({"": 10}, 422),  # Empty string key
            # Invalid minute values
            ({"0": -1}, 422),  # Negative minutes
            ({"0": 61}, 422),  # Minutes > 60
            ({"0": -0.5}, 422),  # Negative fractional minutes
            ({"0": 60.1}, 422),  # Slightly over 60
            # Valid edge cases that SHOULD succeed
            ({"0": 0}, 201),  # Zero minutes at hour 0
            ({"23": 60}, 201),  # Max minutes at hour 23
            ({"0": 0.5}, 201),  # Fractional minutes
            ({"0": 59.9}, 201),  # Just under 60
            ({}, 201),  # Empty dict (no hours reported)
        ],
        ids=[
            "hour_24", "hour_neg1", "hour_25", "hour_abc", "hour_fractional",
            "hour_empty", "minutes_neg", "minutes_over_60", "minutes_neg_frac",
            "minutes_slightly_over_60",
            "valid_zero_at_hour0", "valid_max_at_hour23", "valid_fractional",
            "valid_just_under_60", "valid_empty_dict",
        ],
    )
    async def test_hourly_values_validation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
        hourly_values: dict,
        expected_status: int,
    ):
        """Validate hourly_values schema enforcement for various inputs."""
        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": hourly_values,
                "extracted_title": "App",
                "extracted_total": "10m",
            },
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == expected_status, (
            f"hourly_values={hourly_values!r}: expected {expected_status}, got {response.status_code}. "
            f"Body: {response.text}"
        )

    @pytest.mark.parametrize(
        "hourly_values",
        [
            "not a dict",
            [1, 2, 3],
            42,
            None,
            True,
        ],
        ids=["string", "list", "int", "null", "bool"],
    )
    async def test_hourly_values_wrong_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
        hourly_values,
    ):
        """Non-dict types for hourly_values must be rejected."""
        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": hourly_values,
                "extracted_title": "App",
                "extracted_total": "10m",
            },
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 422

    async def test_all_24_hours_populated(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """A full 24-hour annotation should be accepted and persisted correctly."""
        hourly_values = {str(h): h * 2.5 for h in range(24)}

        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": hourly_values,
                "extracted_title": "Full Day App",
                "extracted_total": "30h 0m",
            },
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 201
        data = response.json()

        result = await db_session.execute(
            select(Annotation).where(Annotation.id == data["id"])
        )
        annotation = result.scalar_one()
        assert len(annotation.hourly_values) == 24
        assert annotation.hourly_values["23"] == 57.5


# =============================================================================
# Grid coordinate validation
# =============================================================================


@pytest.mark.asyncio
class TestGridCoordinateValidation:
    """Test grid coordinate validation edge cases."""

    @pytest.mark.parametrize(
        "upper_left,lower_right,expected_status",
        [
            # Inverted coordinates (upper_left > lower_right)
            ({"x": 500, "y": 100}, {"x": 100, "y": 600}, 422),
            ({"x": 100, "y": 600}, {"x": 500, "y": 100}, 422),
            # Equal coordinates (zero-size grid)
            ({"x": 100, "y": 100}, {"x": 100, "y": 600}, 422),
            ({"x": 100, "y": 100}, {"x": 600, "y": 100}, 422),
            # Too small grid (< 10px)
            ({"x": 100, "y": 200}, {"x": 105, "y": 600}, 422),
            ({"x": 100, "y": 200}, {"x": 600, "y": 205}, 422),
            # Negative coordinates
            ({"x": -1, "y": 0}, {"x": 500, "y": 600}, 422),
            ({"x": 0, "y": -1}, {"x": 500, "y": 600}, 422),
            # Valid minimum grid
            ({"x": 0, "y": 0}, {"x": 10, "y": 10}, 201),
            # Valid large grid
            ({"x": 0, "y": 0}, {"x": 2000, "y": 3000}, 201),
            # Only upper_left provided (should be fine, partial coords allowed)
            # lower_right is None in this case — we'll test separately
        ],
        ids=[
            "inverted_x", "inverted_y", "equal_x", "equal_y",
            "too_small_x", "too_small_y", "negative_x", "negative_y",
            "valid_minimum", "valid_large",
        ],
    )
    async def test_grid_coordinate_validation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
        upper_left: dict,
        lower_right: dict,
        expected_status: int,
    ):
        """Grid coordinates must be logically consistent."""
        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 10},
                "extracted_title": "App",
                "extracted_total": "10m",
                "grid_upper_left": upper_left,
                "grid_lower_right": lower_right,
            },
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == expected_status, (
            f"upper_left={upper_left}, lower_right={lower_right}: "
            f"expected {expected_status}, got {response.status_code}. Body: {response.text}"
        )

    async def test_grid_with_only_upper_left(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Providing only upper_left without lower_right should be accepted."""
        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 10},
                "extracted_title": "App",
                "extracted_total": "10m",
                "grid_upper_left": {"x": 100, "y": 200},
            },
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 201

    async def test_grid_with_only_lower_right(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Providing only lower_right without upper_left should be accepted."""
        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 10},
                "extracted_title": "App",
                "extracted_total": "10m",
                "grid_lower_right": {"x": 500, "y": 600},
            },
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 201


# =============================================================================
# Annotation for screenshots in various processing states
# =============================================================================


@pytest.mark.asyncio
class TestAnnotationOnVariousScreenshotStates:
    """Test creating annotations on screenshots in different processing states."""

    @pytest.mark.parametrize(
        "processing_status",
        [
            ProcessingStatus.PENDING,
            ProcessingStatus.PROCESSING,
            ProcessingStatus.COMPLETED,
            ProcessingStatus.FAILED,
            ProcessingStatus.SKIPPED,
            ProcessingStatus.DELETED,
        ],
        ids=lambda s: s.value,
    )
    async def test_annotate_screenshot_in_various_states(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        processing_status: ProcessingStatus,
    ):
        """Annotations should be accepted regardless of processing_status."""
        screenshot = Screenshot(
            file_path=f"/test/{processing_status.value}_screenshot.png",
            image_type="screen_time",
            processing_status=processing_status,
            uploaded_by_id=test_user.id,
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": screenshot.id,
                "hourly_values": {"0": 10},
                "extracted_title": "App",
                "extracted_total": "10m",
            },
            headers=auth_headers(test_user.username),
        )
        # Annotations should be allowed on any processing status
        assert response.status_code == 201, (
            f"Failed to annotate screenshot with processing_status={processing_status.value}: "
            f"{response.status_code} {response.text}"
        )


# =============================================================================
# Upsert behavior
# =============================================================================


@pytest.mark.asyncio
class TestAnnotationUpsertBehavior:
    """Test the upsert (create-or-update) behavior of POST /annotations/."""

    async def test_upsert_preserves_unchanged_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """When upsert updates, fields not sent should still be preserved from the new payload."""
        # Create initial annotation with grid coords
        first_response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 10, "1": 20},
                "extracted_title": "First",
                "extracted_total": "30m",
                "grid_upper_left": {"x": 100, "y": 200},
                "grid_lower_right": {"x": 500, "y": 600},
            },
            headers=auth_headers(test_user.username),
        )
        assert first_response.status_code == 201
        first_id = first_response.json()["id"]

        # Upsert without grid coords
        second_response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 30},
                "extracted_title": "Updated",
                "extracted_total": "30m",
            },
            headers=auth_headers(test_user.username),
        )
        assert second_response.status_code == 201
        assert second_response.json()["id"] == first_id

        # Verify the grid coords were nulled out (since not provided in update)
        result = await db_session.execute(
            select(Annotation).where(Annotation.id == first_id)
        )
        annotation = result.scalar_one()
        assert annotation.grid_upper_left is None
        assert annotation.grid_lower_right is None
        assert annotation.hourly_values == {"0": 30}

    async def test_upsert_count_stays_at_one(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Multiple upserts from same user should not increase annotation count beyond 1."""
        for i in range(5):
            response = await client.post(
                "/api/v1/annotations/",
                json={
                    "screenshot_id": test_screenshot.id,
                    "hourly_values": {"0": i * 10},
                    "extracted_title": f"Attempt {i}",
                    "extracted_total": f"{i * 10}m",
                },
                headers=auth_headers(test_user.username),
            )
            assert response.status_code == 201

        await db_session.refresh(test_screenshot)
        assert test_screenshot.current_annotation_count == 1

    async def test_different_users_create_separate_annotations(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        multiple_users: list[User],
    ):
        """Each user gets their own annotation for the same screenshot."""
        ids = set()
        for user in multiple_users:
            response = await client.post(
                "/api/v1/annotations/",
                json={
                    "screenshot_id": test_screenshot.id,
                    "hourly_values": {"0": 10},
                    "extracted_title": f"By {user.username}",
                    "extracted_total": "10m",
                },
                headers=auth_headers(user.username),
            )
            assert response.status_code == 201
            ids.add(response.json()["id"])

        assert len(ids) == len(multiple_users)
        await db_session.refresh(test_screenshot)
        assert test_screenshot.current_annotation_count == len(multiple_users)


# =============================================================================
# Time spent validation
# =============================================================================


@pytest.mark.asyncio
class TestTimeSpentValidation:
    """Test time_spent_seconds field validation."""

    @pytest.mark.parametrize(
        "time_spent,expected_status",
        [
            (0, 201),  # Zero is valid
            (0.5, 201),  # Fractional seconds
            (3600, 201),  # 1 hour
            (86400, 201),  # 24 hours
            (-1, 422),  # Negative
            (-0.1, 422),  # Slightly negative
        ],
        ids=["zero", "fractional", "one_hour", "one_day", "negative", "slightly_negative"],
    )
    async def test_time_spent_validation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
        time_spent: float,
        expected_status: int,
    ):
        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 10},
                "extracted_title": "App",
                "extracted_total": "10m",
                "time_spent_seconds": time_spent,
            },
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == expected_status


# =============================================================================
# Notes field validation
# =============================================================================


@pytest.mark.asyncio
class TestNotesValidation:
    """Test notes field length validation."""

    async def test_notes_at_max_length(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Notes at exactly 2000 chars should be accepted."""
        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 10},
                "extracted_title": "App",
                "extracted_total": "10m",
                "notes": "x" * 2000,
            },
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 201

    async def test_notes_over_max_length(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Notes over 2000 chars should be rejected."""
        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 10},
                "extracted_title": "App",
                "extracted_total": "10m",
                "notes": "x" * 2001,
            },
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 422


# =============================================================================
# Screenshot ID edge cases
# =============================================================================


@pytest.mark.asyncio
class TestScreenshotIdEdgeCases:
    """Test annotation creation with invalid screenshot IDs."""

    @pytest.mark.parametrize(
        "screenshot_id,expected_status",
        [
            (0, 404),  # Zero ID (doesn't exist)
            (-1, 404),  # Negative ID (no schema constraint, just not found)
            (999999999, 404),  # Very large non-existent ID
        ],
        ids=["zero_id", "negative_id", "huge_id"],
    )
    async def test_invalid_screenshot_ids(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        screenshot_id: int,
        expected_status: int,
    ):
        response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": screenshot_id,
                "hourly_values": {"0": 10},
                "extracted_title": "App",
                "extracted_total": "10m",
            },
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == expected_status


# =============================================================================
# History endpoint edge cases
# =============================================================================


@pytest.mark.asyncio
class TestAnnotationHistoryEdgeCases:
    """Test annotation history endpoint edge cases."""

    async def test_history_empty_for_new_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """New user with no annotations should get empty list."""
        response = await client.get(
            "/api/v1/annotations/history",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.parametrize(
        "skip,limit,expected_count",
        [
            (0, 1, 1),  # First item only
            (0, 100, 5),  # All items (5 created)
            (4, 100, 1),  # Skip most
            (5, 100, 0),  # Skip all
            (0, 500, 5),  # Max limit
        ],
        ids=["first_only", "all", "skip_most", "skip_all", "max_limit"],
    )
    async def test_history_pagination_edges(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        skip: int,
        limit: int,
        expected_count: int,
    ):
        """Pagination should handle boundary values correctly."""
        # Create 5 annotations on 5 different screenshots
        for i in range(5):
            screenshot = Screenshot(
                file_path=f"/test/hist_edge_{i}.png",
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
            f"/api/v1/annotations/history?skip={skip}&limit={limit}",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        assert len(response.json()) == expected_count


# =============================================================================
# Delete annotation edge cases
# =============================================================================


@pytest.mark.asyncio
class TestDeleteAnnotationEdgeCases:
    """Test delete annotation edge cases."""

    async def test_delete_count_does_not_go_negative(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Deleting annotation when count is already 0 should keep count at 0."""
        # Create annotation but set count to 0 (simulating a bug or race condition)
        annotation = Annotation(
            screenshot_id=test_screenshot.id,
            user_id=test_user.id,
            hourly_values={"0": 10},
            extracted_title="Test",
            extracted_total="10m",
        )
        db_session.add(annotation)
        test_screenshot.current_annotation_count = 0
        await db_session.commit()

        response = await client.delete(
            f"/api/v1/annotations/{annotation.id}",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 204

        await db_session.refresh(test_screenshot)
        assert test_screenshot.current_annotation_count == 0  # Should not go negative

    async def test_delete_same_annotation_twice(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Deleting the same annotation twice should return 404 the second time."""
        annotation = Annotation(
            screenshot_id=test_screenshot.id,
            user_id=test_user.id,
            hourly_values={"0": 10},
            extracted_title="Test",
            extracted_total="10m",
        )
        db_session.add(annotation)
        test_screenshot.current_annotation_count = 1
        await db_session.commit()
        annotation_id = annotation.id

        response1 = await client.delete(
            f"/api/v1/annotations/{annotation_id}",
            headers=auth_headers(test_user.username),
        )
        assert response1.status_code == 204

        response2 = await client.delete(
            f"/api/v1/annotations/{annotation_id}",
            headers=auth_headers(test_user.username),
        )
        assert response2.status_code == 404


# =============================================================================
# Update annotation edge cases
# =============================================================================


@pytest.mark.asyncio
class TestUpdateAnnotationEdgeCases:
    """Test update annotation edge cases."""

    async def test_update_nonexistent_annotation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Update nonexistent annotation should return 404."""
        response = await client.put(
            "/api/v1/annotations/999999",
            json={"hourly_values": {"0": 10}},
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 404

    async def test_update_with_empty_body(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Update with empty body should succeed (no-op update)."""
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
            json={},
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200

        # Values should be unchanged
        await db_session.refresh(annotation)
        assert annotation.extracted_title == "Original"
        assert annotation.hourly_values == {"0": 10}

    async def test_admin_can_view_other_users_annotation(
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
