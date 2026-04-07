"""
End-to-end integration tests for the complete screenshot workflow.

Tests the full flow:
1. Upload screenshot via API
2. OCR processing runs and extracts data
3. User annotates the screenshot
4. User verifies the screenshot
5. Export includes only verified/annotated screenshots

Also tests processing status transitions.
"""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    AnnotationStatus,
    ConsensusResult,
    ProcessingStatus,
    Screenshot,
    User,
)
from tests.conftest import auth_headers
# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "images"
TEST_API_KEY = "test_api_key_12345"


def get_test_image_base64() -> str:
    """Load a real test image as base64."""
    test_image = FIXTURES_DIR / "IMG_0806 Cropped.png"
    if test_image.exists():
        return base64.b64encode(test_image.read_bytes()).decode()
    # Fallback to minimal PNG if fixture doesn't exist
    return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


class TestProcessingStatusTransitions:
    """Test that processing status changes correctly through the pipeline."""

    @pytest.mark.asyncio
    async def test_new_screenshot_has_pending_status(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """New screenshot should have processing_status=pending."""
        screenshot = Screenshot(
            file_path="/test/new.png",
            image_type="screen_time",
            uploaded_by_id=test_user.id,
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        assert screenshot.processing_status == ProcessingStatus.PENDING
        assert screenshot.annotation_status == AnnotationStatus.PENDING
        assert screenshot.extracted_title is None
        assert screenshot.extracted_hourly_data is None

    @pytest.mark.asyncio
    async def test_processing_sets_completed_status(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Successful processing should set processing_status=completed."""
        screenshot = Screenshot(
            file_path="/test/to_process.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.PENDING,
            uploaded_by_id=test_user.id,
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        # Simulate successful processing
        screenshot.processing_status = ProcessingStatus.COMPLETED
        screenshot.extracted_title = "Instagram"
        screenshot.extracted_total = "2h 30m"
        screenshot.extracted_hourly_data = {"0": 10, "1": 20, "2": 15}
        await db_session.commit()
        await db_session.refresh(screenshot)

        assert screenshot.processing_status == ProcessingStatus.COMPLETED
        # annotation_status should still be PENDING (not affected by processing)
        assert screenshot.annotation_status == AnnotationStatus.PENDING
        assert screenshot.extracted_title == "Instagram"

    @pytest.mark.asyncio
    async def test_processing_sets_failed_status_on_error(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Failed processing should set processing_status=failed."""
        screenshot = Screenshot(
            file_path="/test/bad_image.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.PENDING,
            uploaded_by_id=test_user.id,
        )
        db_session.add(screenshot)
        await db_session.commit()

        # Simulate failed processing
        screenshot.processing_status = ProcessingStatus.FAILED
        screenshot.has_blocking_issues = True
        screenshot.processing_issues = [
            {"issue_type": "GraphDetectionIssue", "severity": "blocking", "description": "Could not find graph"}
        ]
        await db_session.commit()
        await db_session.refresh(screenshot)

        assert screenshot.processing_status == ProcessingStatus.FAILED
        assert screenshot.has_blocking_issues is True
        # annotation_status still PENDING - user can still try to annotate
        assert screenshot.annotation_status == AnnotationStatus.PENDING

    @pytest.mark.asyncio
    async def test_daily_total_sets_skipped_status(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Daily Total screenshots should have processing_status=skipped and annotation_status=skipped."""
        screenshot = Screenshot(
            file_path="/test/daily_total.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.PENDING,
            uploaded_by_id=test_user.id,
        )
        db_session.add(screenshot)
        await db_session.commit()

        # Simulate Daily Total detection (skipped processing)
        screenshot.processing_status = ProcessingStatus.SKIPPED
        screenshot.annotation_status = AnnotationStatus.SKIPPED  # No annotation needed
        await db_session.commit()
        await db_session.refresh(screenshot)

        assert screenshot.processing_status == ProcessingStatus.SKIPPED
        assert screenshot.annotation_status == AnnotationStatus.SKIPPED


class TestFullWorkflowEndToEnd:
    """End-to-end tests for complete workflow."""

    @pytest.fixture(autouse=True)
    def mock_settings(self, tmp_path):
        """Mock settings for upload API key while preserving real defaults."""
        from screenshot_processor.web.config import get_settings as _real_get_settings

        real_settings = _real_get_settings()

        with patch("screenshot_processor.web.api.routes.screenshots.get_settings") as mock:
            # Copy real settings values, override only what's needed for tests
            mock_instance = MagicMock(spec=type(real_settings))
            for attr in dir(real_settings):
                if not attr.startswith("_"):
                    try:
                        setattr(mock_instance, attr, getattr(real_settings, attr))
                    except (AttributeError, TypeError):
                        pass
            mock_instance.UPLOAD_API_KEY = TEST_API_KEY
            mock_instance.UPLOAD_DIR = str(tmp_path / "uploads")
            mock.return_value = mock_instance
            # Create the upload directory
            (tmp_path / "uploads").mkdir(exist_ok=True)
            yield

    @pytest.mark.skip(reason="Requires PostgreSQL with INSERT ON CONFLICT support")
    @pytest.mark.asyncio
    async def test_full_workflow_upload_to_export(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """
        Test complete workflow: Upload -> Process -> Annotate -> Verify -> Export.

        This test simulates the entire production workflow:
        1. External system uploads screenshot via API
        2. Screenshot is processed (simulated - processing_status set to completed)
        3. User views and annotates the screenshot
        4. User verifies the annotation is correct
        5. Admin exports verified screenshots
        """
        user_headers = auth_headers(test_user.username)

        # Step 1: Upload screenshot
        upload_data = {
            "screenshot": get_test_image_base64(),
            "participant_id": "P001",
            "group_id": "workflow_test",
            "image_type": "screen_time",
        }

        upload_response = await client.post(
            "/api/v1/screenshots/upload",
            headers={"X-API-Key": TEST_API_KEY},
            json=upload_data,
        )
        assert upload_response.status_code == 201
        screenshot_id = upload_response.json()["screenshot_id"]

        # Verify initial state
        result = await db_session.execute(select(Screenshot).where(Screenshot.id == screenshot_id))
        screenshot = result.scalar_one()
        assert screenshot.processing_status == ProcessingStatus.PENDING
        assert screenshot.annotation_status == AnnotationStatus.PENDING
        assert screenshot.current_annotation_count == 0
        assert screenshot.verified_by_user_ids is None or len(screenshot.verified_by_user_ids) == 0

        # Step 2: Simulate OCR processing completed
        screenshot.processing_status = ProcessingStatus.COMPLETED
        screenshot.extracted_title = "Instagram"
        screenshot.extracted_total = "2h 15m"
        # Use valid hourly values (0-60 minutes per hour)
        screenshot.extracted_hourly_data = {str(i): float(min(i * 5, 60)) for i in range(24)}
        await db_session.commit()
        await db_session.refresh(screenshot)

        assert screenshot.processing_status == ProcessingStatus.COMPLETED
        assert screenshot.annotation_status == AnnotationStatus.PENDING  # Still pending

        # Step 3: User annotates
        annotation_data = {
            "screenshot_id": screenshot_id,
            "hourly_values": {str(i): min(i * 5, 60) for i in range(24)},  # Valid 0-60 minute values
            "extracted_title": "Instagram",
            "extracted_total": "2h 15m",
        }

        annotation_response = await client.post(
            "/api/v1/annotations/",
            headers=user_headers,
            json=annotation_data,
        )
        assert annotation_response.status_code == 201

        await db_session.refresh(screenshot)
        assert screenshot.current_annotation_count == 1
        # annotation_status stays PENDING per implementation
        assert screenshot.annotation_status == AnnotationStatus.PENDING
        # Not verified yet
        assert screenshot.verified_by_user_ids is None or len(screenshot.verified_by_user_ids) == 0

        # Step 4: User verifies
        verify_response = await client.post(
            f"/api/v1/screenshots/{screenshot_id}/verify",
            headers=user_headers,
        )
        assert verify_response.status_code == 200

        await db_session.refresh(screenshot)
        assert test_user.id in screenshot.verified_by_user_ids

        # Step 5: Export verified screenshots
        export_response = await client.get(
            "/api/v1/screenshots/export/json?verified_only=true&has_annotations=true",
            headers=user_headers,
        )
        assert export_response.status_code == 200
        export_data = export_response.json()

        assert export_data["total_screenshots"] == 1
        exported_screenshot = export_data["screenshots"][0]
        assert exported_screenshot["id"] == screenshot_id
        assert exported_screenshot["is_verified"] is True
        assert exported_screenshot["annotation_count"] == 1
        assert len(exported_screenshot["annotations"]) == 1

    @pytest.mark.skip(reason="Requires PostgreSQL with INSERT ON CONFLICT support")
    @pytest.mark.asyncio
    async def test_unverified_excluded_from_verified_export(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Unverified screenshots should be excluded from verified_only export."""
        user_headers = auth_headers(test_user.username)

        # Upload and process
        upload_data = {
            "screenshot": get_test_image_base64(),
            "participant_id": "P002",
            "group_id": "export_test",
            "image_type": "screen_time",
        }

        upload_response = await client.post(
            "/api/v1/screenshots/upload",
            headers={"X-API-Key": TEST_API_KEY},
            json=upload_data,
        )
        assert upload_response.status_code == 201
        screenshot_id = upload_response.json()["screenshot_id"]

        # Simulate processing
        result = await db_session.execute(select(Screenshot).where(Screenshot.id == screenshot_id))
        screenshot = result.scalar_one()
        screenshot.processing_status = ProcessingStatus.COMPLETED
        screenshot.extracted_title = "TikTok"
        await db_session.commit()

        # Annotate but DON'T verify
        annotation_data = {
            "screenshot_id": screenshot_id,
            "hourly_values": {"0": 10},
            "extracted_title": "TikTok",
            "extracted_total": "10m",
        }
        await client.post("/api/v1/annotations/", headers=user_headers, json=annotation_data)

        # Export verified only - should be empty
        export_response = await client.get(
            "/api/v1/screenshots/export/json?verified_only=true",
            headers=user_headers,
        )
        assert export_response.status_code == 200
        assert export_response.json()["total_screenshots"] == 0

        # Export without filter - should include it
        export_all_response = await client.get(
            "/api/v1/screenshots/export/json",
            headers=user_headers,
        )
        assert export_all_response.status_code == 200
        assert export_all_response.json()["total_screenshots"] == 1

    @pytest.mark.asyncio
    async def test_skipped_screenshots_excluded_from_annotation_export(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Daily Total (skipped) screenshots should be excluded from has_annotations export."""
        user_headers = auth_headers(test_user.username)

        # Create a skipped screenshot (Daily Total)
        screenshot = Screenshot(
            file_path="/test/daily_total.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.SKIPPED,
            annotation_status=AnnotationStatus.SKIPPED,
            uploaded_by_id=test_user.id,
        )
        db_session.add(screenshot)
        await db_session.commit()

        # Export with has_annotations - should be empty (skipped screenshots can't be annotated)
        export_response = await client.get(
            "/api/v1/screenshots/export/json?has_annotations=true",
            headers=user_headers,
        )
        assert export_response.status_code == 200
        assert export_response.json()["total_screenshots"] == 0


class TestMultiUserWorkflow:
    """Test workflow with multiple users."""

    @pytest.mark.asyncio
    async def test_multiple_users_annotate_and_verify(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_users: list[User],
        test_screenshot: Screenshot,
    ):
        """Multiple users can annotate and verify the same screenshot."""
        screenshot_id = test_screenshot.id

        # Simulate processing completed
        test_screenshot.processing_status = ProcessingStatus.COMPLETED
        test_screenshot.extracted_title = "YouTube"
        await db_session.commit()

        # Each user annotates
        for i, user in enumerate(multiple_users):
            annotation_data = {
                "screenshot_id": screenshot_id,
                "hourly_values": {"0": 10 + i},
                "extracted_title": "YouTube",
                "extracted_total": f"{10 + i}m",
            }
            response = await client.post(
                "/api/v1/annotations/",
                headers=auth_headers(user.username),
                json=annotation_data,
            )
            assert response.status_code == 201

        # Check annotation count
        await db_session.refresh(test_screenshot)
        assert test_screenshot.current_annotation_count == len(multiple_users)

        # Each user verifies
        for user in multiple_users:
            response = await client.post(
                f"/api/v1/screenshots/{screenshot_id}/verify",
                headers=auth_headers(user.username),
            )
            assert response.status_code == 200

        # Check all users in verified list
        result = await db_session.execute(select(Screenshot).where(Screenshot.id == screenshot_id))
        refreshed = result.scalar_one()
        assert len(refreshed.verified_by_user_ids) == len(multiple_users)

    @pytest.mark.asyncio
    async def test_consensus_calculated_after_multiple_annotations(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
    ):
        """Consensus should be calculated when 2+ users annotate."""
        screenshot_id = test_screenshot.id

        # Create two users
        user1 = User(username="consensus_user1", role="annotator", is_active=True)
        user2 = User(username="consensus_user2", role="annotator", is_active=True)
        db_session.add(user1)
        db_session.add(user2)
        await db_session.commit()
        await db_session.refresh(user1)
        await db_session.refresh(user2)

        # User 1 annotates
        await client.post(
            "/api/v1/annotations/",
            headers=auth_headers(user1.username),
            json={
                "screenshot_id": screenshot_id,
                "hourly_values": {"0": 10, "1": 20},
                "extracted_title": "App",
                "extracted_total": "30m",
            },
        )

        # No consensus yet (only 1 annotation)
        consensus_result = await db_session.execute(
            select(ConsensusResult).where(ConsensusResult.screenshot_id == screenshot_id)
        )
        assert consensus_result.scalar_one_or_none() is None

        # User 2 annotates (same values = consensus)
        await client.post(
            "/api/v1/annotations/",
            headers=auth_headers(user2.username),
            json={
                "screenshot_id": screenshot_id,
                "hourly_values": {"0": 10, "1": 20},  # Same values
                "extracted_title": "App",
                "extracted_total": "30m",
            },
        )

        # Now consensus should exist
        consensus_result = await db_session.execute(
            select(ConsensusResult).where(ConsensusResult.screenshot_id == screenshot_id)
        )
        consensus = consensus_result.scalar_one_or_none()
        assert consensus is not None
        assert consensus.has_consensus is True  # Same values = consensus
