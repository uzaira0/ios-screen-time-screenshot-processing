"""
Integration tests for verification tier endpoints.

Tests the consensus verification tier system including:
- GET /consensus/groups - Groups with verification tier breakdown
- GET /consensus/groups/{group_id}/screenshots - Screenshots by tier
- GET /consensus/screenshots/{screenshot_id}/compare - Comparison data
- POST /consensus/screenshots/{screenshot_id}/resolve - Resolve disputes
"""

from __future__ import annotations

import pytest
from tests.conftest import auth_headers
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    Annotation,
    Group,
    Screenshot,
    User,
)


@pytest.mark.asyncio
class TestGroupVerificationTiers:
    """Test the groups verification tier endpoint."""

    async def test_get_groups_empty(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test getting groups when there are no verified screenshots."""
        response = await client.get(
            "/api/v1/consensus/groups",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_groups_with_verified_screenshots(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_group: Group,
    ):
        """Test getting groups with verified screenshots."""
        # Create a screenshot and verify it
        screenshot = Screenshot(
            file_path="/test/verified.png",
            image_type="screen_time",
            annotation_status="pending",
            processing_status="completed",
            target_annotations=2,
            current_annotation_count=0,
            uploaded_by_id=test_user.id,
            group_id=test_group.id,
            verified_by_user_ids=[test_user.id],
        )
        db_session.add(screenshot)

        # Create an annotation
        annotation = Annotation(
            screenshot=screenshot,
            user_id=test_user.id,
            hourly_values={"0": 10, "1": 20},
            extracted_title="Test App",
            extracted_total="30m",
            grid_upper_left={"x": 0, "y": 0},
            grid_lower_right={"x": 100, "y": 100},
        )
        db_session.add(annotation)
        await db_session.commit()

        response = await client.get(
            "/api/v1/consensus/groups",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

        # Find our test group
        test_group_data = next((g for g in data if g["id"] == test_group.id), None)
        assert test_group_data is not None
        assert test_group_data["name"] == test_group.name
        assert test_group_data["single_verified"] == 1
        assert test_group_data["agreed"] == 0
        assert test_group_data["disputed"] == 0
        assert test_group_data["total_verified"] == 1

    async def test_get_groups_with_agreed_screenshots(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_group: Group,
    ):
        """Test groups showing agreed tier when 2+ users agree."""
        # Create two users
        user1 = User(username="user1", role="annotator", is_active=True)
        user2 = User(username="user2", role="annotator", is_active=True)
        db_session.add_all([user1, user2])
        await db_session.commit()

        # Create screenshot verified by both
        screenshot = Screenshot(
            file_path="/test/agreed.png",
            image_type="screen_time",
            annotation_status="pending",
            processing_status="completed",
            target_annotations=2,
            current_annotation_count=0,
            uploaded_by_id=user1.id,
            group_id=test_group.id,
            verified_by_user_ids=[user1.id, user2.id],
        )
        db_session.add(screenshot)
        await db_session.commit()

        # Both users submit identical annotations
        annotation_data = {
            "hourly_values": {"0": 10, "1": 20},
            "extracted_title": "Test App",
            "extracted_total": "30m",
            "grid_upper_left": {"x": 0, "y": 0},
            "grid_lower_right": {"x": 100, "y": 100},
        }

        for user in [user1, user2]:
            ann = Annotation(
                screenshot=screenshot,
                user_id=user.id,
                **annotation_data,
            )
            db_session.add(ann)
        await db_session.commit()

        response = await client.get(
            "/api/v1/consensus/groups",
            headers=auth_headers(user1.username),
        )

        assert response.status_code == 200
        data = response.json()

        test_group_data = next((g for g in data if g["id"] == test_group.id), None)
        assert test_group_data is not None
        assert test_group_data["agreed"] == 1
        assert test_group_data["single_verified"] == 0
        assert test_group_data["disputed"] == 0

    async def test_get_groups_with_disputed_screenshots(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_group: Group,
    ):
        """Test groups showing disputed tier when 2+ users disagree."""
        # Create two users
        user1 = User(username="user1", role="annotator", is_active=True)
        user2 = User(username="user2", role="annotator", is_active=True)
        db_session.add_all([user1, user2])
        await db_session.commit()

        # Create screenshot verified by both
        screenshot = Screenshot(
            file_path="/test/disputed.png",
            image_type="screen_time",
            annotation_status="pending",
            processing_status="completed",
            target_annotations=2,
            current_annotation_count=0,
            uploaded_by_id=user1.id,
            group_id=test_group.id,
            verified_by_user_ids=[user1.id, user2.id],
        )
        db_session.add(screenshot)
        await db_session.commit()

        # Users submit different annotations
        ann1 = Annotation(
            screenshot=screenshot,
            user_id=user1.id,
            hourly_values={"0": 10, "1": 20},
            extracted_title="Test App",
            extracted_total="30m",
            grid_upper_left={"x": 0, "y": 0},
            grid_lower_right={"x": 100, "y": 100},
        )
        ann2 = Annotation(
            screenshot=screenshot,
            user_id=user2.id,
            hourly_values={"0": 50, "1": 60},  # Different values
            extracted_title="Test App",
            extracted_total="110m",
            grid_upper_left={"x": 0, "y": 0},
            grid_lower_right={"x": 100, "y": 100},
        )
        db_session.add_all([ann1, ann2])
        await db_session.commit()

        response = await client.get(
            "/api/v1/consensus/groups",
            headers=auth_headers(user1.username),
        )

        assert response.status_code == 200
        data = response.json()

        test_group_data = next((g for g in data if g["id"] == test_group.id), None)
        assert test_group_data is not None
        assert test_group_data["disputed"] == 1
        assert test_group_data["agreed"] == 0
        assert test_group_data["single_verified"] == 0


@pytest.mark.asyncio
class TestScreenshotsByTier:
    """Test the screenshots by tier endpoint."""

    async def test_get_single_verified_screenshots(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_group: Group,
    ):
        """Test getting single verified screenshots."""
        # Create verified screenshot
        screenshot = Screenshot(
            file_path="/test/single.png",
            image_type="screen_time",
            annotation_status="pending",
            processing_status="completed",
            target_annotations=2,
            current_annotation_count=0,
            uploaded_by_id=test_user.id,
            group_id=test_group.id,
            verified_by_user_ids=[test_user.id],
        )
        db_session.add(screenshot)

        annotation = Annotation(
            screenshot=screenshot,
            user_id=test_user.id,
            hourly_values={"0": 10},
            extracted_title="Test",
            extracted_total="10m",
            grid_upper_left={"x": 0, "y": 0},
            grid_lower_right={"x": 100, "y": 100},
        )
        db_session.add(annotation)
        await db_session.commit()

        response = await client.get(
            f"/api/v1/consensus/groups/{test_group.id}/screenshots",
            params={"tier": "single_verified"},
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == screenshot.id
        assert data[0]["verifier_count"] == 1

    async def test_get_agreed_screenshots(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_group: Group,
    ):
        """Test getting agreed screenshots."""
        user1 = User(username="user1", role="annotator", is_active=True)
        user2 = User(username="user2", role="annotator", is_active=True)
        db_session.add_all([user1, user2])
        await db_session.commit()

        screenshot = Screenshot(
            file_path="/test/agreed.png",
            image_type="screen_time",
            annotation_status="pending",
            processing_status="completed",
            target_annotations=2,
            current_annotation_count=0,
            uploaded_by_id=user1.id,
            group_id=test_group.id,
            verified_by_user_ids=[user1.id, user2.id],
        )
        db_session.add(screenshot)
        await db_session.commit()

        # Identical annotations
        for user in [user1, user2]:
            ann = Annotation(
                screenshot=screenshot,
                user_id=user.id,
                hourly_values={"0": 10},
                extracted_title="Test",
                extracted_total="10m",
                grid_upper_left={"x": 0, "y": 0},
                grid_lower_right={"x": 100, "y": 100},
            )
            db_session.add(ann)
        await db_session.commit()

        response = await client.get(
            f"/api/v1/consensus/groups/{test_group.id}/screenshots",
            params={"tier": "agreed"},
            headers=auth_headers(user1.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["verifier_count"] == 2
        assert data[0]["has_differences"] is False

    async def test_get_disputed_screenshots(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_group: Group,
    ):
        """Test getting disputed screenshots."""
        user1 = User(username="user1", role="annotator", is_active=True)
        user2 = User(username="user2", role="annotator", is_active=True)
        db_session.add_all([user1, user2])
        await db_session.commit()

        screenshot = Screenshot(
            file_path="/test/disputed.png",
            image_type="screen_time",
            annotation_status="pending",
            processing_status="completed",
            target_annotations=2,
            current_annotation_count=0,
            uploaded_by_id=user1.id,
            group_id=test_group.id,
            verified_by_user_ids=[user1.id, user2.id],
        )
        db_session.add(screenshot)
        await db_session.commit()

        # Different annotations
        ann1 = Annotation(
            screenshot=screenshot,
            user_id=user1.id,
            hourly_values={"0": 10},
            extracted_title="Test",
            extracted_total="10m",
            grid_upper_left={"x": 0, "y": 0},
            grid_lower_right={"x": 100, "y": 100},
        )
        ann2 = Annotation(
            screenshot=screenshot,
            user_id=user2.id,
            hourly_values={"0": 99},  # Different
            extracted_title="Test",
            extracted_total="99m",
            grid_upper_left={"x": 0, "y": 0},
            grid_lower_right={"x": 100, "y": 100},
        )
        db_session.add_all([ann1, ann2])
        await db_session.commit()

        response = await client.get(
            f"/api/v1/consensus/groups/{test_group.id}/screenshots",
            params={"tier": "disputed"},
            headers=auth_headers(user1.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["has_differences"] is True

    async def test_get_screenshots_nonexistent_group(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test getting screenshots for nonexistent group."""
        response = await client.get(
            "/api/v1/consensus/groups/nonexistent-group/screenshots",
            params={"tier": "single_verified"},
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 404

    async def test_get_screenshots_empty_tier(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_group: Group,
    ):
        """Test getting screenshots for tier with no data."""
        response = await client.get(
            f"/api/v1/consensus/groups/{test_group.id}/screenshots",
            params={"tier": "disputed"},
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0


@pytest.mark.asyncio
class TestScreenshotComparison:
    """Test the screenshot comparison endpoint."""

    async def test_get_comparison_with_verifiers(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_group: Group,
    ):
        """Test getting comparison data for screenshot with verifiers."""
        user1 = User(username="user1", role="annotator", is_active=True)
        user2 = User(username="user2", role="annotator", is_active=True)
        db_session.add_all([user1, user2])
        await db_session.commit()

        screenshot = Screenshot(
            file_path="/test/compare.png",
            image_type="screen_time",
            annotation_status="pending",
            processing_status="completed",
            target_annotations=2,
            current_annotation_count=0,
            uploaded_by_id=user1.id,
            group_id=test_group.id,
            verified_by_user_ids=[user1.id, user2.id],
        )
        db_session.add(screenshot)
        await db_session.commit()

        # Create annotations with differences
        ann1 = Annotation(
            screenshot=screenshot,
            user_id=user1.id,
            hourly_values={"0": 10, "1": 20},
            extracted_title="App A",
            extracted_total="30m",
            grid_upper_left={"x": 0, "y": 0},
            grid_lower_right={"x": 100, "y": 100},
        )
        ann2 = Annotation(
            screenshot=screenshot,
            user_id=user2.id,
            hourly_values={"0": 15, "1": 20},  # Hour 0 differs
            extracted_title="App A",
            extracted_total="35m",
            grid_upper_left={"x": 0, "y": 0},
            grid_lower_right={"x": 100, "y": 100},
        )
        db_session.add_all([ann1, ann2])
        await db_session.commit()

        response = await client.get(
            f"/api/v1/consensus/screenshots/{screenshot.id}/compare",
            headers=auth_headers(user1.username),
        )

        assert response.status_code == 200
        data = response.json()

        assert data["screenshot_id"] == screenshot.id
        assert data["tier"] == "disputed"
        assert len(data["verifier_annotations"]) == 2
        assert len(data["differences"]) > 0

        # Check difference is for hour 0
        hour_diff = next((d for d in data["differences"] if d["field"] == "hourly_0"), None)
        assert hour_diff is not None
        assert str(user1.id) in hour_diff["values"]
        assert str(user2.id) in hour_diff["values"]

    async def test_get_comparison_agreed_no_differences(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_group: Group,
    ):
        """Test comparison for agreed screenshots has no differences."""
        user1 = User(username="user1", role="annotator", is_active=True)
        user2 = User(username="user2", role="annotator", is_active=True)
        db_session.add_all([user1, user2])
        await db_session.commit()

        screenshot = Screenshot(
            file_path="/test/agreed.png",
            image_type="screen_time",
            annotation_status="pending",
            processing_status="completed",
            target_annotations=2,
            current_annotation_count=0,
            uploaded_by_id=user1.id,
            group_id=test_group.id,
            verified_by_user_ids=[user1.id, user2.id],
        )
        db_session.add(screenshot)
        await db_session.commit()

        # Identical annotations
        for user in [user1, user2]:
            ann = Annotation(
                screenshot=screenshot,
                user_id=user.id,
                hourly_values={"0": 10, "1": 20},
                extracted_title="App",
                extracted_total="30m",
                grid_upper_left={"x": 0, "y": 0},
                grid_lower_right={"x": 100, "y": 100},
            )
            db_session.add(ann)
        await db_session.commit()

        response = await client.get(
            f"/api/v1/consensus/screenshots/{screenshot.id}/compare",
            headers=auth_headers(user1.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tier"] == "agreed"
        assert len(data["differences"]) == 0

    async def test_get_comparison_no_verifiers(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_group: Group,
    ):
        """Test comparison fails for screenshot with no verifiers."""
        screenshot = Screenshot(
            file_path="/test/unverified.png",
            image_type="screen_time",
            annotation_status="pending",
            processing_status="completed",
            target_annotations=2,
            current_annotation_count=0,
            uploaded_by_id=test_user.id,
            group_id=test_group.id,
            verified_by_user_ids=None,  # Not verified
        )
        db_session.add(screenshot)
        await db_session.commit()

        response = await client.get(
            f"/api/v1/consensus/screenshots/{screenshot.id}/compare",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 400
        assert "no verified" in response.json()["detail"].lower()

    async def test_get_comparison_nonexistent_screenshot(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test comparison for nonexistent screenshot."""
        response = await client.get(
            "/api/v1/consensus/screenshots/999999/compare",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 404


@pytest.mark.asyncio
class TestResolveDispute:
    """Test the resolve dispute endpoint."""

    async def test_resolve_dispute_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_group: Group,
    ):
        """Test resolving a disputed screenshot (admin-only)."""
        user1 = User(username="user1", role="annotator", is_active=True)
        user2 = User(username="user2", role="annotator", is_active=True)
        admin_user = User(username="admin_resolver", role="admin", is_active=True)
        db_session.add_all([user1, user2, admin_user])
        await db_session.commit()

        screenshot = Screenshot(
            file_path="/test/resolve.png",
            image_type="screen_time",
            annotation_status="pending",
            processing_status="completed",
            target_annotations=2,
            current_annotation_count=0,
            uploaded_by_id=user1.id,
            group_id=test_group.id,
            verified_by_user_ids=[user1.id, user2.id],
        )
        db_session.add(screenshot)
        await db_session.commit()

        # Create disagreeing annotations
        ann1 = Annotation(
            screenshot=screenshot,
            user_id=user1.id,
            hourly_values={"0": 10},
            extracted_title="App",
            extracted_total="10m",
            grid_upper_left={"x": 0, "y": 0},
            grid_lower_right={"x": 100, "y": 100},
        )
        ann2 = Annotation(
            screenshot=screenshot,
            user_id=user2.id,
            hourly_values={"0": 50},
            extracted_title="App",
            extracted_total="50m",
            grid_upper_left={"x": 0, "y": 0},
            grid_lower_right={"x": 100, "y": 100},
        )
        db_session.add_all([ann1, ann2])
        await db_session.commit()

        # Resolve with agreed values (using admin user)
        response = await client.post(
            f"/api/v1/consensus/screenshots/{screenshot.id}/resolve",
            json={
                "hourly_values": {"0": 30},  # Compromise value
                "extracted_title": "App",
                "extracted_total": "30m",
            },
            headers=auth_headers(admin_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["screenshot_id"] == screenshot.id
        assert data["resolved_by_user_id"] == admin_user.id
        assert data["resolved_by_username"] == admin_user.username

        # The endpoint stores ORIGINAL extracted values in resolved_* fields (for audit/rollback)
        # and updates extracted_* fields with the new resolved values.
        await db_session.refresh(screenshot)
        # New resolved values are in extracted_* fields
        assert screenshot.extracted_hourly_data == {"0": 30}
        assert screenshot.extracted_title == "App"
        assert screenshot.extracted_total == "30m"
        assert screenshot.resolved_at is not None
        assert screenshot.resolved_by_user_id == admin_user.id
        # Original values preserved in resolved_* fields for rollback
        assert screenshot.resolved_hourly_data is None  # Was None before resolve (no prior OCR data)

        # Verify original annotations are preserved (not modified)
        await db_session.refresh(ann1)
        await db_session.refresh(ann2)
        assert ann1.hourly_values["0"] == 10  # Original value preserved
        assert ann2.hourly_values["0"] == 50  # Original value preserved

    async def test_resolve_dispute_single_verifier_fails(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_group: Group,
    ):
        """Test resolving fails for screenshot with single verifier (even for admin)."""
        admin_user = User(username="admin_resolver", role="admin", is_active=True)
        db_session.add(admin_user)
        await db_session.commit()

        screenshot = Screenshot(
            file_path="/test/single.png",
            image_type="screen_time",
            annotation_status="pending",
            processing_status="completed",
            target_annotations=2,
            current_annotation_count=0,
            uploaded_by_id=test_user.id,
            group_id=test_group.id,
            verified_by_user_ids=[test_user.id],  # Only one verifier
        )
        db_session.add(screenshot)
        await db_session.commit()

        response = await client.post(
            f"/api/v1/consensus/screenshots/{screenshot.id}/resolve",
            json={
                "hourly_values": {"0": 30},
            },
            headers=auth_headers(admin_user.username),
        )

        assert response.status_code == 400
        assert "multiple verifiers" in response.json()["detail"].lower()

    async def test_resolve_dispute_nonexistent_screenshot(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test resolving nonexistent screenshot (as admin)."""
        admin_user = User(username="admin_resolver", role="admin", is_active=True)
        db_session.add(admin_user)
        await db_session.commit()

        response = await client.post(
            "/api/v1/consensus/screenshots/999999/resolve",
            json={
                "hourly_values": {"0": 30},
            },
            headers=auth_headers(admin_user.username),
        )

        assert response.status_code == 404

    async def test_resolve_dispute_preserves_original_annotations(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_group: Group,
    ):
        """Test resolution preserves original annotations and stores resolved values separately."""
        user1 = User(username="user1", role="annotator", is_active=True)
        user2 = User(username="user2", role="annotator", is_active=True)
        admin_user = User(username="admin_resolver", role="admin", is_active=True)
        db_session.add_all([user1, user2, admin_user])
        await db_session.commit()

        screenshot = Screenshot(
            file_path="/test/notes.png",
            image_type="screen_time",
            annotation_status="pending",
            processing_status="completed",
            target_annotations=2,
            current_annotation_count=0,
            uploaded_by_id=user1.id,
            group_id=test_group.id,
            verified_by_user_ids=[user1.id, user2.id],
        )
        db_session.add(screenshot)
        await db_session.commit()

        ann1 = Annotation(
            screenshot=screenshot,
            user_id=user1.id,
            hourly_values={"0": 10},
            extracted_title="App",
            extracted_total="10m",
            grid_upper_left={"x": 0, "y": 0},
            grid_lower_right={"x": 100, "y": 100},
            notes="Original note",
        )
        ann2 = Annotation(
            screenshot=screenshot,
            user_id=user2.id,
            hourly_values={"0": 50},
            extracted_title="App",
            extracted_total="50m",
            grid_upper_left={"x": 0, "y": 0},
            grid_lower_right={"x": 100, "y": 100},
        )
        db_session.add_all([ann1, ann2])
        await db_session.commit()

        response = await client.post(
            f"/api/v1/consensus/screenshots/{screenshot.id}/resolve",
            json={
                "hourly_values": {"0": 30},
                "extracted_title": "Resolved App",
                "extracted_total": "30m",
            },
            headers=auth_headers(admin_user.username),
        )

        assert response.status_code == 200

        # Verify original annotations are NOT modified
        await db_session.refresh(ann1)
        await db_session.refresh(ann2)
        assert ann1.hourly_values["0"] == 10  # Original preserved
        assert ann2.hourly_values["0"] == 50  # Original preserved
        assert ann1.notes == "Original note"  # Notes untouched
        assert ann2.notes is None  # Notes untouched

        # The endpoint stores ORIGINAL extracted values in resolved_* fields (for audit/rollback)
        # and updates extracted_* fields with the new resolved values.
        await db_session.refresh(screenshot)
        # New values are in extracted_* fields
        assert screenshot.extracted_hourly_data == {"0": 30}
        assert screenshot.extracted_title == "Resolved App"
        assert screenshot.extracted_total == "30m"
        # Original values preserved in resolved_* fields for rollback
        assert screenshot.resolved_hourly_data is None  # Was None before resolve
        assert screenshot.resolved_at is not None
        assert screenshot.resolved_by_user_id == admin_user.id

    async def test_resolve_dispute_non_admin_forbidden(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_group: Group,
    ):
        """Test that non-admin users cannot resolve disputes."""
        user1 = User(username="user1", role="annotator", is_active=True)
        user2 = User(username="user2", role="annotator", is_active=True)
        db_session.add_all([user1, user2])
        await db_session.commit()

        screenshot = Screenshot(
            file_path="/test/forbidden.png",
            image_type="screen_time",
            annotation_status="pending",
            processing_status="completed",
            target_annotations=2,
            current_annotation_count=0,
            uploaded_by_id=user1.id,
            group_id=test_group.id,
            verified_by_user_ids=[user1.id, user2.id],
        )
        db_session.add(screenshot)
        await db_session.commit()

        # Create annotations
        for user in [user1, user2]:
            ann = Annotation(
                screenshot=screenshot,
                user_id=user.id,
                hourly_values={"0": 10},
                extracted_title="App",
                extracted_total="10m",
                grid_upper_left={"x": 0, "y": 0},
                grid_lower_right={"x": 100, "y": 100},
            )
            db_session.add(ann)
        await db_session.commit()

        # Try to resolve as non-admin
        response = await client.post(
            f"/api/v1/consensus/screenshots/{screenshot.id}/resolve",
            json={
                "hourly_values": {"0": 30},
            },
            headers=auth_headers(user1.username),  # annotator, not admin
        )

        assert response.status_code == 403
        assert "administrators" in response.json()["detail"].lower()


@pytest.mark.asyncio
class TestVerificationTierAuth:
    """Test authentication for verification tier endpoints."""

    async def test_groups_requires_auth(
        self,
        client: AsyncClient,
    ):
        """Test groups endpoint requires authentication."""
        response = await client.get("/api/v1/consensus/groups")

        assert response.status_code == 401

    async def test_screenshots_requires_auth(
        self,
        client: AsyncClient,
    ):
        """Test screenshots endpoint requires authentication."""
        response = await client.get(
            "/api/v1/consensus/groups/test-group/screenshots",
            params={"tier": "single_verified"},
        )

        assert response.status_code == 401

    async def test_comparison_requires_auth(
        self,
        client: AsyncClient,
    ):
        """Test comparison endpoint requires authentication."""
        response = await client.get("/api/v1/consensus/screenshots/1/compare")

        assert response.status_code == 401

    async def test_resolve_requires_auth(
        self,
        client: AsyncClient,
    ):
        """Test resolve endpoint requires authentication."""
        response = await client.post(
            "/api/v1/consensus/screenshots/1/resolve",
            json={"hourly_values": {"0": 30}},
        )

        assert response.status_code == 401


@pytest.mark.asyncio
class TestTierDifferencesDetection:
    """Test the difference detection logic."""

    async def test_hourly_value_differences_detected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_group: Group,
    ):
        """Test hourly value differences are correctly detected."""
        user1 = User(username="user1", role="annotator", is_active=True)
        user2 = User(username="user2", role="annotator", is_active=True)
        db_session.add_all([user1, user2])
        await db_session.commit()

        screenshot = Screenshot(
            file_path="/test/diff.png",
            image_type="screen_time",
            annotation_status="pending",
            processing_status="completed",
            target_annotations=2,
            current_annotation_count=0,
            uploaded_by_id=user1.id,
            group_id=test_group.id,
            verified_by_user_ids=[user1.id, user2.id],
        )
        db_session.add(screenshot)
        await db_session.commit()

        # Difference in hours 0 and 5
        ann1 = Annotation(
            screenshot=screenshot,
            user_id=user1.id,
            hourly_values={"0": 10, "5": 30, "10": 50},
            extracted_title="App",
            extracted_total="90m",
            grid_upper_left={"x": 0, "y": 0},
            grid_lower_right={"x": 100, "y": 100},
        )
        ann2 = Annotation(
            screenshot=screenshot,
            user_id=user2.id,
            hourly_values={"0": 15, "5": 35, "10": 50},  # 0 and 5 differ, 10 same
            extracted_title="App",
            extracted_total="100m",
            grid_upper_left={"x": 0, "y": 0},
            grid_lower_right={"x": 100, "y": 100},
        )
        db_session.add_all([ann1, ann2])
        await db_session.commit()

        response = await client.get(
            f"/api/v1/consensus/screenshots/{screenshot.id}/compare",
            headers=auth_headers(user1.username),
        )

        assert response.status_code == 200
        data = response.json()

        # Should have differences for hours 0 and 5
        diff_fields = [d["field"] for d in data["differences"]]
        assert "hourly_0" in diff_fields
        assert "hourly_5" in diff_fields
        assert "hourly_10" not in diff_fields  # Same value

    async def test_title_differences_detected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_group: Group,
    ):
        """Test title differences are detected."""
        user1 = User(username="user1", role="annotator", is_active=True)
        user2 = User(username="user2", role="annotator", is_active=True)
        db_session.add_all([user1, user2])
        await db_session.commit()

        screenshot = Screenshot(
            file_path="/test/title.png",
            image_type="screen_time",
            annotation_status="pending",
            processing_status="completed",
            target_annotations=2,
            current_annotation_count=0,
            uploaded_by_id=user1.id,
            group_id=test_group.id,
            verified_by_user_ids=[user1.id, user2.id],
        )
        db_session.add(screenshot)
        await db_session.commit()

        ann1 = Annotation(
            screenshot=screenshot,
            user_id=user1.id,
            hourly_values={"0": 10},
            extracted_title="App A",  # Different title
            extracted_total="10m",
            grid_upper_left={"x": 0, "y": 0},
            grid_lower_right={"x": 100, "y": 100},
        )
        ann2 = Annotation(
            screenshot=screenshot,
            user_id=user2.id,
            hourly_values={"0": 10},
            extracted_title="App B",  # Different title
            extracted_total="10m",
            grid_upper_left={"x": 0, "y": 0},
            grid_lower_right={"x": 100, "y": 100},
        )
        db_session.add_all([ann1, ann2])
        await db_session.commit()

        response = await client.get(
            f"/api/v1/consensus/screenshots/{screenshot.id}/compare",
            headers=auth_headers(user1.username),
        )

        assert response.status_code == 200
        data = response.json()

        diff_fields = [d["field"] for d in data["differences"]]
        assert "title" in diff_fields

    async def test_total_differences_detected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_group: Group,
    ):
        """Test total differences are detected."""
        user1 = User(username="user1", role="annotator", is_active=True)
        user2 = User(username="user2", role="annotator", is_active=True)
        db_session.add_all([user1, user2])
        await db_session.commit()

        screenshot = Screenshot(
            file_path="/test/total.png",
            image_type="screen_time",
            annotation_status="pending",
            processing_status="completed",
            target_annotations=2,
            current_annotation_count=0,
            uploaded_by_id=user1.id,
            group_id=test_group.id,
            verified_by_user_ids=[user1.id, user2.id],
        )
        db_session.add(screenshot)
        await db_session.commit()

        ann1 = Annotation(
            screenshot=screenshot,
            user_id=user1.id,
            hourly_values={"0": 10},
            extracted_title="App",
            extracted_total="10m",  # Different total
            grid_upper_left={"x": 0, "y": 0},
            grid_lower_right={"x": 100, "y": 100},
        )
        ann2 = Annotation(
            screenshot=screenshot,
            user_id=user2.id,
            hourly_values={"0": 10},
            extracted_title="App",
            extracted_total="15m",  # Different total
            grid_upper_left={"x": 0, "y": 0},
            grid_lower_right={"x": 100, "y": 100},
        )
        db_session.add_all([ann1, ann2])
        await db_session.commit()

        response = await client.get(
            f"/api/v1/consensus/screenshots/{screenshot.id}/compare",
            headers=auth_headers(user1.username),
        )

        assert response.status_code == 200
        data = response.json()

        diff_fields = [d["field"] for d in data["differences"]]
        assert "total" in diff_fields
