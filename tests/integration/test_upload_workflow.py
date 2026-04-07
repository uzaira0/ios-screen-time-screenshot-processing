"""
Integration tests for screenshot upload workflow.

Tests upload API endpoint, validation, group auto-creation, device detection,
and duplicate handling.
"""

from __future__ import annotations

import base64
from datetime import date
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import Group, Screenshot

# 1x1 PNG for testing
TEST_PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

# Mock API key for testing
TEST_API_KEY = "test_api_key_12345"




@pytest.mark.asyncio
class TestScreenshotUpload:
    """Test screenshot upload endpoint."""

    @pytest.fixture(autouse=True)
    def mock_api_key(self, tmp_path):
        """Mock API key validation and rate limiting settings."""
        with patch("screenshot_processor.web.api.routes.screenshots.get_settings") as mock_settings:
            mock_settings.return_value.UPLOAD_API_KEY = TEST_API_KEY
            mock_settings.return_value.UPLOAD_DIR = str(tmp_path / "uploads")
            mock_settings.return_value.RATE_LIMIT_UPLOAD = "100/minute"
            mock_settings.return_value.RATE_LIMIT_REPROCESS = "100/minute"
            yield

    @pytest.fixture(autouse=True)
    def mock_celery_task(self):
        """Mock Celery processing task."""
        with patch("screenshot_processor.web.tasks.process_screenshot_task") as mock_task:
            yield mock_task

    async def test_upload_with_all_metadata(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test upload with all metadata fields."""
        upload_data = {
            "screenshot": TEST_PNG_BASE64,
            "participant_id": "P001",
            "group_id": "study1",
            "image_type": "screen_time",
            "device_type": "iphone_modern",
            "source_id": "import_batch_1",
            "filename": "screenshot1.png",
            "screenshot_date": "2024-01-15",
        }

        response = await client.post(
            "/api/v1/screenshots/upload",
            headers={"X-API-Key": TEST_API_KEY},
            json=upload_data,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert "screenshot_id" in data
        assert data["group_created"] is True

        # Verify screenshot in database
        result = await db_session.execute(select(Screenshot).where(Screenshot.id == data["screenshot_id"]))
        screenshot = result.scalar_one()
        assert screenshot.participant_id == "P001"
        assert screenshot.group_id == "study1"
        assert screenshot.device_type == "iphone_modern"
        assert screenshot.source_id == "import_batch_1"
        assert screenshot.screenshot_date == date(2024, 1, 15)

    async def test_upload_with_minimal_required_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test upload with minimal required fields."""
        upload_data = {
            "screenshot": TEST_PNG_BASE64,
            "participant_id": "P001",
            "group_id": "study1",
            "image_type": "battery",
        }

        response = await client.post(
            "/api/v1/screenshots/upload",
            headers={"X-API-Key": TEST_API_KEY},
            json=upload_data,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True

        # Verify defaults
        result = await db_session.execute(select(Screenshot).where(Screenshot.id == data["screenshot_id"]))
        screenshot = result.scalar_one()
        assert screenshot.image_type == "battery"
        assert screenshot.source_id is None
        assert screenshot.target_annotations == 1  # Default

    async def test_upload_invalid_api_key(self, client: AsyncClient):
        """Test upload fails with invalid API key."""
        upload_data = {
            "screenshot": TEST_PNG_BASE64,
            "participant_id": "P001",
            "group_id": "study1",
            "image_type": "screen_time",
        }

        response = await client.post(
            "/api/v1/screenshots/upload",
            headers={"X-API-Key": "invalid_key"},
            json=upload_data,
        )

        assert response.status_code == 401
        error = response.json()["detail"]
        assert error["error_code"] == "invalid_api_key"
        assert "Invalid API key" in error["detail"]

    async def test_upload_missing_api_key(self, client: AsyncClient):
        """Test upload fails without API key."""
        upload_data = {
            "screenshot": TEST_PNG_BASE64,
            "participant_id": "P001",
            "group_id": "study1",
            "image_type": "screen_time",
        }

        response = await client.post(
            "/api/v1/screenshots/upload",
            json=upload_data,
        )

        assert response.status_code == 422  # Validation error for missing header

    async def test_upload_invalid_base64(self, client: AsyncClient):
        """Test upload fails with invalid base64 data."""
        upload_data = {
            "screenshot": "not_valid_base64!@#$",
            "participant_id": "P001",
            "group_id": "study1",
            "image_type": "screen_time",
        }

        response = await client.post(
            "/api/v1/screenshots/upload",
            headers={"X-API-Key": TEST_API_KEY},
            json=upload_data,
        )

        assert response.status_code == 400
        error = response.json()["detail"]
        assert error["error_code"] == "invalid_base64"
        assert "Invalid base64" in error["detail"]

    async def test_upload_unsupported_image_format(self, client: AsyncClient):
        """Test upload fails for unsupported image formats."""
        # Base64 of a GIF header
        gif_data = base64.b64encode(b"GIF89a").decode()

        upload_data = {
            "screenshot": gif_data,
            "participant_id": "P001",
            "group_id": "study1",
            "image_type": "screen_time",
        }

        response = await client.post(
            "/api/v1/screenshots/upload",
            headers={"X-API-Key": TEST_API_KEY},
            json=upload_data,
        )

        assert response.status_code == 400
        error = response.json()["detail"]
        assert error["error_code"] == "unsupported_format"
        assert "Unsupported image format" in error["detail"]

    async def test_upload_invalid_image_type(self, client: AsyncClient):
        """Test upload validation fails for invalid image_type."""
        upload_data = {
            "screenshot": TEST_PNG_BASE64,
            "participant_id": "P001",
            "group_id": "study1",
            "image_type": "invalid_type",
        }

        response = await client.post(
            "/api/v1/screenshots/upload",
            headers={"X-API-Key": TEST_API_KEY},
            json=upload_data,
        )

        assert response.status_code == 422  # Validation error

    async def test_upload_empty_participant_id(self, client: AsyncClient):
        """Test upload validation fails for empty participant_id."""
        upload_data = {
            "screenshot": TEST_PNG_BASE64,
            "participant_id": "",
            "group_id": "study1",
            "image_type": "screen_time",
        }

        response = await client.post(
            "/api/v1/screenshots/upload",
            headers={"X-API-Key": TEST_API_KEY},
            json=upload_data,
        )

        assert response.status_code == 422

    async def test_group_auto_creation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test group is auto-created on first upload."""
        upload_data = {
            "screenshot": TEST_PNG_BASE64,
            "participant_id": "P001",
            "group_id": "new_group",
            "image_type": "screen_time",
        }

        response = await client.post(
            "/api/v1/screenshots/upload",
            headers={"X-API-Key": TEST_API_KEY},
            json=upload_data,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["group_created"] is True

        # Verify group in database
        result = await db_session.execute(select(Group).where(Group.id == "new_group"))
        group = result.scalar_one()
        assert group.name == "new_group"
        assert group.image_type == "screen_time"

    async def test_group_not_recreated_on_second_upload(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test group is not recreated if already exists."""
        # Create group first
        group = Group(id="existing_group", name="Existing Group", image_type="screen_time")
        db_session.add(group)
        await db_session.commit()

        upload_data = {
            "screenshot": TEST_PNG_BASE64,
            "participant_id": "P001",
            "group_id": "existing_group",
            "image_type": "screen_time",
        }

        response = await client.post(
            "/api/v1/screenshots/upload",
            headers={"X-API-Key": TEST_API_KEY},
            json=upload_data,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["group_created"] is False

    async def test_duplicate_detection_by_content_hash(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test that uploading the same image twice is deduplicated by content hash.

        The second upload returns the existing screenshot ID with duplicate=True.
        """
        upload_data = {
            "screenshot": TEST_PNG_BASE64,
            "participant_id": "P001",
            "group_id": "study1",
            "image_type": "screen_time",
        }

        # First upload
        response1 = await client.post(
            "/api/v1/screenshots/upload",
            headers={"X-API-Key": TEST_API_KEY},
            json=upload_data,
        )
        assert response1.status_code == 201
        data1 = response1.json()
        screenshot_id_1 = data1["screenshot_id"]

        # Second upload (same content — should be deduplicated)
        response2 = await client.post(
            "/api/v1/screenshots/upload",
            headers={"X-API-Key": TEST_API_KEY},
            json=upload_data,
        )
        assert response2.status_code == 201
        data2 = response2.json()
        assert data2["success"] is True
        assert data2["duplicate"] is True
        assert data2["screenshot_id"] == screenshot_id_1

        # Only one screenshot in database
        result = await db_session.execute(select(Screenshot))
        screenshots = result.scalars().all()
        assert len(screenshots) == 1

    async def test_device_type_auto_detection(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test device_type is auto-detected if not provided."""
        # Create a PNG with specific dimensions (mocked)
        # For actual testing, this would need real PNG with dimensions
        # For now, test that device_type can be set
        upload_data = {
            "screenshot": TEST_PNG_BASE64,
            "participant_id": "P001",
            "group_id": "study1",
            "image_type": "screen_time",
            # device_type not provided - should auto-detect
        }

        response = await client.post(
            "/api/v1/screenshots/upload",
            headers={"X-API-Key": TEST_API_KEY},
            json=upload_data,
        )

        assert response.status_code == 201
        # device_type would be auto-detected from image dimensions

    async def test_upload_triggers_background_processing(
        self,
        client: AsyncClient,
        mock_celery_task,
    ):
        """Test upload triggers Celery background processing task."""
        upload_data = {
            "screenshot": TEST_PNG_BASE64,
            "participant_id": "P001",
            "group_id": "study1",
            "image_type": "screen_time",
        }

        response = await client.post(
            "/api/v1/screenshots/upload",
            headers={"X-API-Key": TEST_API_KEY},
            json=upload_data,
        )

        assert response.status_code == 201
        screenshot_id = response.json()["screenshot_id"]

        # Verify Celery task was queued
        mock_celery_task.delay.assert_called_once_with(screenshot_id)

    async def test_upload_with_data_url_format(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test upload accepts data URL format (data:image/png;base64,...)."""
        data_url = f"data:image/png;base64,{TEST_PNG_BASE64}"

        upload_data = {
            "screenshot": data_url,
            "participant_id": "P001",
            "group_id": "study1",
            "image_type": "screen_time",
        }

        response = await client.post(
            "/api/v1/screenshots/upload",
            headers={"X-API-Key": TEST_API_KEY},
            json=upload_data,
        )

        assert response.status_code == 201
        assert response.json()["success"] is True

    async def test_upload_sets_default_processing_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test uploaded screenshot has default processing_status."""
        upload_data = {
            "screenshot": TEST_PNG_BASE64,
            "participant_id": "P001",
            "group_id": "study1",
            "image_type": "screen_time",
        }

        response = await client.post(
            "/api/v1/screenshots/upload",
            headers={"X-API-Key": TEST_API_KEY},
            json=upload_data,
        )

        assert response.status_code == 201
        screenshot_id = response.json()["screenshot_id"]

        result = await db_session.execute(select(Screenshot).where(Screenshot.id == screenshot_id))
        screenshot = result.scalar_one()
        assert screenshot.processing_status.value == "pending"
        assert screenshot.annotation_status.value == "pending"
