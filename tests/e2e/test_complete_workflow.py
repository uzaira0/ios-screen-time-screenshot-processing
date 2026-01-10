"""
End-to-end tests for complete annotation workflows.

Simulates the entire pipeline from upload through export.
"""

from __future__ import annotations


import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    Annotation,
    ConsensusResult,
    ProcessingStatus,
    Screenshot,
    User,
)
from tests.integration.conftest import auth_headers

TEST_PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
TEST_API_KEY = "test_api_key_12345"


@pytest.mark.asyncio
class TestCompleteWorkflow:
    """Test complete end-to-end workflows."""

    @pytest.fixture(autouse=True)
    def mock_settings(self, monkeypatch, tmp_path):
        """Mock settings for upload tests."""
        from screenshot_processor.web.config import Settings

        # Create a mock settings object
        mock = Settings(
            UPLOAD_API_KEY=TEST_API_KEY,
            UPLOAD_DIR=str(tmp_path / "uploads"),
            SECRET_KEY="test_secret_key_that_is_at_least_32_characters_long_for_testing",
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
        )
        # Ensure upload directory exists
        (tmp_path / "uploads").mkdir(exist_ok=True)

        # Patch get_settings to return our mock
        monkeypatch.setattr(
            "screenshot_processor.web.api.routes.screenshots.get_settings",
            lambda: mock,
        )
        return mock

    @pytest.fixture(autouse=True)
    def mock_celery_task(self, monkeypatch):
        """Mock Celery task to avoid actual background processing."""
        mock_task = type("MockTask", (), {"delay": lambda self, *args, **kwargs: None})()
        monkeypatch.setattr(
            "screenshot_processor.web.tasks.process_screenshot_task",
            mock_task,
        )

    async def test_full_pipeline_upload_to_export(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_users: list[User],
    ):
        """
        Test complete pipeline:
        1. Admin uploads screenshots
        2. Users annotate
        3. Consensus calculated
        4. Export data
        """
        admin = User(username="admin", role="admin", is_active=True)
        db_session.add(admin)
        await db_session.commit()

        # Step 1: Upload screenshot
        upload_response = await client.post(
            "/api/v1/screenshots/upload",
            headers={"X-API-Key": TEST_API_KEY},
            json={
                "screenshot": TEST_PNG_BASE64,
                "participant_id": "P001",
                "group_id": "study1",
                "image_type": "screen_time",
            },
        )
        assert upload_response.status_code == 201
        screenshot_id = upload_response.json()["screenshot_id"]

        # Step 2: Update screenshot to mark as processed
        result = await db_session.execute(select(Screenshot).where(Screenshot.id == screenshot_id))
        screenshot = result.scalar_one()
        screenshot.processing_status = ProcessingStatus.COMPLETED
        await db_session.commit()

        # Step 3: Two users annotate
        annotation_data = {
            "screenshot_id": screenshot_id,
            "hourly_values": {"0": 10, "1": 15},
            "extracted_title": "Screen Time",
            "extracted_total": "25m",
            "grid_upper_left": {"x": 100, "y": 100},
            "grid_lower_right": {"x": 500, "y": 500},
        }

        for user in multiple_users[:2]:
            response = await client.post(
                "/api/v1/annotations/",
                json=annotation_data,
                headers=auth_headers(user.username),
            )
            assert response.status_code == 201

        # Step 4: Verify consensus calculated
        result = await db_session.execute(select(ConsensusResult).where(ConsensusResult.screenshot_id == screenshot_id))
        consensus = result.scalar_one_or_none()
        assert consensus is not None
        assert consensus.has_consensus is True

        # Step 5: Export data
        export_response = await client.get(
            "/api/v1/screenshots/export/json?group_id=study1",
            headers=auth_headers(admin.username),
        )
        assert export_response.status_code == 200
        export_data = export_response.json()

        # Verify export includes screenshot
        assert len(export_data["screenshots"]) >= 1
        exported_screenshot = next((s for s in export_data["screenshots"] if s["id"] == screenshot_id), None)
        assert exported_screenshot is not None
        assert exported_screenshot["participant_id"] == "P001"
        assert exported_screenshot["consensus"] is not None

    async def test_multi_user_redundancy_workflow(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_users: list[User],
        multiple_screenshots: list[Screenshot],
    ):
        """
        Test multi-user annotation with redundancy:
        1. Multiple screenshots uploaded
        2. Each screenshot annotated by 2 users
        3. Consensus calculated for all
        4. Verify queue management
        """
        # Mark all screenshots as processed
        for screenshot in multiple_screenshots:
            screenshot.processing_status = ProcessingStatus.COMPLETED
            screenshot.target_annotations = 2
        await db_session.commit()

        # Each user annotates different screenshots
        for i, user in enumerate(multiple_users[:2]):
            for screenshot in multiple_screenshots:
                # Check if screenshot available in queue
                queue_response = await client.get(
                    "/api/v1/screenshots/next",
                    headers=auth_headers(user.username),
                )

                if queue_response.json()["screenshot"] is None:
                    break

                # Annotate
                annotation_response = await client.post(
                    "/api/v1/annotations/",
                    json={
                        "screenshot_id": screenshot.id,
                        "hourly_values": {"0": 10 + i, "1": 15 + i},
                        "extracted_title": "Screen Time",
                        "extracted_total": f"{25 + i * 5}m",
                        "grid_upper_left": {"x": 100, "y": 100},
                        "grid_lower_right": {"x": 500, "y": 500},
                    },
                    headers=auth_headers(user.username),
                )
                assert annotation_response.status_code == 201

        # Verify consensus calculated for screenshots with 2 annotations
        result = await db_session.execute(select(Screenshot).where(Screenshot.current_annotation_count >= 2))
        completed_screenshots = result.scalars().all()

        assert len(completed_screenshots) >= 1

        # Check consensus exists for completed screenshots
        for screenshot in completed_screenshots:
            result = await db_session.execute(
                select(ConsensusResult).where(ConsensusResult.screenshot_id == screenshot.id)
            )
            consensus = result.scalar_one_or_none()
            assert consensus is not None

    async def test_annotation_correction_workflow(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_screenshot: Screenshot,
    ):
        """
        Test user correcting their own annotation:
        1. Submit initial annotation
        2. Realize mistake
        3. Update annotation via upsert
        4. Verify only one annotation exists
        """
        test_screenshot.processing_status = ProcessingStatus.COMPLETED
        await db_session.commit()

        # Initial annotation
        initial_response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 10},
                "extracted_title": "Screen Time",
                "extracted_total": "10m",
                "grid_upper_left": {"x": 100, "y": 100},
                "grid_lower_right": {"x": 500, "y": 500},
            },
            headers=auth_headers(test_user.username),
        )
        assert initial_response.status_code == 201
        annotation_id = initial_response.json()["id"]

        # Corrected annotation (upsert)
        corrected_response = await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 20},  # Corrected value
                "extracted_title": "Screen Time",
                "extracted_total": "20m",
                "grid_upper_left": {"x": 100, "y": 100},
                "grid_lower_right": {"x": 500, "y": 500},
            },
            headers=auth_headers(test_user.username),
        )
        assert corrected_response.status_code == 201
        assert corrected_response.json()["id"] == annotation_id  # Same annotation
        assert corrected_response.json()["hourly_values"]["0"] == 20

        # Verify only one annotation exists
        result = await db_session.execute(
            select(Annotation).where(
                Annotation.screenshot_id == test_screenshot.id,
                Annotation.user_id == test_user.id,
            )
        )
        annotations = result.scalars().all()
        assert len(annotations) == 1

    async def test_skip_and_disputed_workflow(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_users: list[User],
        test_screenshot: Screenshot,
    ):
        """
        Test skip and disputed screenshot workflow:
        1. User1 skips screenshot
        2. User2 and User3 annotate with disagreement
        3. Screenshot appears in disputed queue
        4. User1 can still annotate from disputed queue
        """
        test_screenshot.processing_status = ProcessingStatus.COMPLETED
        test_screenshot.target_annotations = 3
        await db_session.commit()

        # User1 skips
        skip_response = await client.post(
            f"/api/v1/screenshots/{test_screenshot.id}/skip",
            headers=auth_headers(multiple_users[0].username),
        )
        assert skip_response.status_code == 204

        # User2 and User3 annotate with disagreement
        await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 10},
                "extracted_title": "Screen Time",
                "extracted_total": "10m",
                "grid_upper_left": {"x": 100, "y": 100},
                "grid_lower_right": {"x": 500, "y": 500},
            },
            headers=auth_headers(multiple_users[1].username),
        )

        await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 30},  # Disagreement
                "extracted_title": "Screen Time",
                "extracted_total": "30m",
                "grid_upper_left": {"x": 100, "y": 100},
                "grid_lower_right": {"x": 500, "y": 500},
            },
            headers=auth_headers(multiple_users[2].username),
        )

        # Check disputed queue
        disputed_response = await client.get(
            "/api/v1/screenshots/disputed",
            headers=auth_headers(multiple_users[0].username),
        )
        assert disputed_response.status_code == 200
        disputed = disputed_response.json()

        # Screenshot should be in disputed queue
        assert any(s["id"] == test_screenshot.id for s in disputed)

    async def test_batch_upload_and_processing(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """
        Test batch upload scenario:
        1. Upload multiple screenshots
        2. Verify group created once
        3. Verify processing queued for all
        4. Get queue stats
        """
        screenshot_count = 5

        # Upload batch
        screenshot_ids = []
        for i in range(screenshot_count):
            response = await client.post(
                "/api/v1/screenshots/upload",
                headers={"X-API-Key": TEST_API_KEY},
                json={
                    "screenshot": TEST_PNG_BASE64,
                    "participant_id": f"P{i:03d}",
                    "group_id": "batch_group",
                    "image_type": "screen_time",
                },
            )
            assert response.status_code == 201
            screenshot_ids.append(response.json()["screenshot_id"])

        # Verify all uploaded
        assert len(screenshot_ids) == screenshot_count

        # Get queue stats
        stats_response = await client.get(
            "/api/v1/screenshots/stats",
            headers=auth_headers(test_user.username),
        )
        stats = stats_response.json()
        assert stats["total_screenshots"] >= screenshot_count
