"""
Integration tests for Upload API endpoints.

Tests the screenshot upload functionality:
- POST /screenshots/upload - Upload a single screenshot
- POST /screenshots/upload/batch - Upload multiple screenshots

These tests verify that:
1. Uploads are persisted to the database
2. Duplicate uploads clear and reprocess existing data
3. Groups are auto-created if they don't exist
4. Proper error handling for invalid data
"""

from __future__ import annotations

import base64
import os

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    Annotation,
    Group,
    ProcessingStatus,
    Screenshot,
    User,
)
from tests.conftest import auth_headers
def api_key_header() -> dict[str, str]:
    """Create API key header for uploads."""
    # Use the same default as Settings.UPLOAD_API_KEY
    api_key = os.environ.get("UPLOAD_API_KEY", "dev-upload-key-change-in-production")
    return {"X-API-Key": api_key}


def create_minimal_png() -> str:
    """Create a minimal valid PNG image as base64.

    This is a tiny 1x1 red PNG image.
    """
    # Minimal 1x1 red PNG (67 bytes)
    png_bytes = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk header
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # 1x1 dimensions
        0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,  # 8-bit RGB
        0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,  # IDAT chunk header
        0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,  # Compressed data
        0x00, 0x00, 0x03, 0x00, 0x01, 0x00, 0x18, 0xDD,  # Checksum
        0x8D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45,  # IEND chunk header
        0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,              # IEND CRC
    ])
    return base64.b64encode(png_bytes).decode("ascii")


# Note: These tests require UPLOAD_API_KEY to be set and the upload directory to exist.
# In CI, these may need to be adjusted or skipped.


@pytest.mark.asyncio
class TestSingleUpload:
    """Test POST /screenshots/upload endpoint."""

    @pytest.mark.skip(reason="Requires PostgreSQL with INSERT ON CONFLICT support")
    async def test_upload_creates_screenshot(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Upload should create a screenshot in the database."""
        upload_data = {
            "screenshot": create_minimal_png(),
            "group_id": "test-upload-group",
            "participant_id": "P001",
            "image_type": "screen_time",
        }

        response = await client.post(
            "/api/v1/screenshots/upload",
            json=upload_data,
            headers=api_key_header(),
        )

        if response.status_code == 401:
            pytest.skip("Invalid API key - set UPLOAD_API_KEY environment variable")

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["screenshot_id"] is not None

        # Verify in DB
        result = await db_session.execute(
            select(Screenshot).where(Screenshot.id == data["screenshot_id"])
        )
        screenshot = result.scalar_one()
        assert screenshot.participant_id == "P001"
        assert screenshot.group_id == "test-upload-group"

    @pytest.mark.skip(reason="Requires PostgreSQL with INSERT ON CONFLICT support")
    async def test_upload_creates_group_if_not_exists(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Upload should auto-create group if it doesn't exist."""
        new_group_id = "auto-created-group"

        # Verify group doesn't exist
        result = await db_session.execute(
            select(Group).where(Group.id == new_group_id)
        )
        assert result.scalar_one_or_none() is None

        upload_data = {
            "screenshot": create_minimal_png(),
            "group_id": new_group_id,
            "participant_id": "P001",
            "image_type": "screen_time",
        }

        response = await client.post(
            "/api/v1/screenshots/upload",
            json=upload_data,
            headers=api_key_header(),
        )

        if response.status_code == 401:
            pytest.skip("Invalid API key")

        assert response.status_code == 201
        data = response.json()
        assert data["group_created"] is True

        # Verify group created
        result = await db_session.execute(
            select(Group).where(Group.id == new_group_id)
        )
        group = result.scalar_one()
        assert group.name == new_group_id

    async def test_upload_requires_api_key(
        self,
        client: AsyncClient,
    ):
        """Upload without API key should fail."""
        response = await client.post(
            "/api/v1/screenshots/upload",
            json={
                "screenshot": create_minimal_png(),
                "group_id": "test",
                "participant_id": "P001",
                "image_type": "screen_time",
            },
        )

        # Should fail without API key header
        assert response.status_code in [401, 422]

    async def test_upload_invalid_base64(
        self,
        client: AsyncClient,
    ):
        """Upload with invalid base64 should fail."""
        response = await client.post(
            "/api/v1/screenshots/upload",
            json={
                "screenshot": "not-valid-base64!!!",
                "group_id": "test",
                "participant_id": "P001",
                "image_type": "screen_time",
            },
            headers=api_key_header(),
        )

        if response.status_code == 401:
            pytest.skip("Invalid API key")

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error_code"] == "invalid_base64"


@pytest.mark.asyncio
class TestDuplicateUpload:
    """Test duplicate upload handling."""

    @pytest.mark.skip(reason="Requires PostgreSQL with INSERT ON CONFLICT support")
    async def test_duplicate_clears_existing_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Duplicate upload should clear existing annotations and reprocess."""
        # First upload
        upload_data = {
            "screenshot": create_minimal_png(),
            "group_id": "duplicate-test-group",
            "participant_id": "P001",
            "image_type": "screen_time",
            "filename": "duplicate_test.png",
        }

        response1 = await client.post(
            "/api/v1/screenshots/upload",
            json=upload_data,
            headers=api_key_header(),
        )

        if response1.status_code == 401:
            pytest.skip("Invalid API key")

        screenshot_id = response1.json()["screenshot_id"]

        # Add annotation to the screenshot
        result = await db_session.execute(
            select(Screenshot).where(Screenshot.id == screenshot_id)
        )
        screenshot = result.scalar_one()

        annotation = Annotation(
            screenshot_id=screenshot_id,
            user_id=test_user.id,
            hourly_values={"0": 10},
            extracted_title="Test",
            extracted_total="10m",
        )
        db_session.add(annotation)
        screenshot.current_annotation_count = 1
        screenshot.verified_by_user_ids = [test_user.id]
        await db_session.commit()

        # Duplicate upload (same file path should trigger duplicate detection)
        response2 = await client.post(
            "/api/v1/screenshots/upload",
            json=upload_data,
            headers=api_key_header(),
        )

        assert response2.status_code == 201
        data = response2.json()
        assert data["duplicate"] is True

        # Verify data cleared
        result = await db_session.execute(
            select(Screenshot).where(Screenshot.id == screenshot_id)
        )
        refreshed = result.scalar_one()

        # Annotation count should be reset
        assert refreshed.current_annotation_count == 0
        # Verification should be cleared
        assert refreshed.verified_by_user_ids is None
        # Processing status should be reset to pending
        assert refreshed.processing_status == ProcessingStatus.PENDING

        # Annotations should be deleted
        result = await db_session.execute(
            select(Annotation).where(Annotation.screenshot_id == screenshot_id)
        )
        assert result.scalars().all() == []


@pytest.mark.asyncio
class TestBatchUpload:
    """Test POST /screenshots/upload/batch endpoint."""

    @pytest.mark.skip(reason="Requires PostgreSQL with INSERT ON CONFLICT support")
    async def test_batch_upload_creates_multiple(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Batch upload should create multiple screenshots."""
        batch_data = {
            "group_id": "batch-test-group",
            "image_type": "screen_time",
            "screenshots": [
                {
                    "screenshot": create_minimal_png(),
                    "participant_id": "P001",
                    "filename": "batch1.png",
                },
                {
                    "screenshot": create_minimal_png(),
                    "participant_id": "P002",
                    "filename": "batch2.png",
                },
            ],
        }

        response = await client.post(
            "/api/v1/screenshots/upload/batch",
            json=batch_data,
            headers=api_key_header(),
        )

        if response.status_code == 401:
            pytest.skip("Invalid API key")

        assert response.status_code == 201
        data = response.json()
        assert data["total_count"] == 2
        assert data["successful_count"] == 2
        assert data["failed_count"] == 0

    @pytest.mark.skip(reason="Requires PostgreSQL with INSERT ON CONFLICT support")
    async def test_batch_upload_partial_failure(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Batch upload should handle partial failures gracefully."""
        batch_data = {
            "group_id": "batch-partial-group",
            "image_type": "screen_time",
            "screenshots": [
                {
                    "screenshot": create_minimal_png(),  # Valid
                    "participant_id": "P001",
                },
                {
                    "screenshot": "invalid-base64!!!",  # Invalid
                    "participant_id": "P002",
                },
            ],
        }

        response = await client.post(
            "/api/v1/screenshots/upload/batch",
            json=batch_data,
            headers=api_key_header(),
        )

        if response.status_code == 401:
            pytest.skip("Invalid API key")

        assert response.status_code == 201
        data = response.json()
        assert data["successful_count"] == 1
        assert data["failed_count"] == 1

        # Check individual results
        success_result = next(r for r in data["results"] if r["success"])
        failure_result = next(r for r in data["results"] if not r["success"])

        assert success_result["index"] == 0
        assert failure_result["index"] == 1
        assert failure_result["error_code"] == "INVALID_BASE64"

    async def test_batch_upload_requires_api_key(
        self,
        client: AsyncClient,
    ):
        """Batch upload without API key should fail."""
        response = await client.post(
            "/api/v1/screenshots/upload/batch",
            json={
                "group_id": "test",
                "image_type": "screen_time",
                "screenshots": [],
            },
        )

        assert response.status_code in [401, 422]


@pytest.mark.asyncio
class TestUploadMetadata:
    """Test that upload correctly stores metadata."""

    @pytest.mark.skip(reason="Requires PostgreSQL with INSERT ON CONFLICT support")
    async def test_upload_stores_device_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Upload should store device_type in database."""
        upload_data = {
            "screenshot": create_minimal_png(),
            "group_id": "metadata-test",
            "participant_id": "P001",
            "image_type": "screen_time",
            "device_type": "iphone_modern",
        }

        response = await client.post(
            "/api/v1/screenshots/upload",
            json=upload_data,
            headers=api_key_header(),
        )

        if response.status_code == 401:
            pytest.skip("Invalid API key")

        assert response.status_code == 201
        screenshot_id = response.json()["screenshot_id"]

        result = await db_session.execute(
            select(Screenshot).where(Screenshot.id == screenshot_id)
        )
        screenshot = result.scalar_one()
        assert screenshot.device_type == "iphone_modern"

    @pytest.mark.skip(reason="Requires PostgreSQL with INSERT ON CONFLICT support")
    async def test_upload_stores_original_filepath(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Upload should store original_filepath in database."""
        upload_data = {
            "screenshot": create_minimal_png(),
            "group_id": "metadata-test",
            "participant_id": "P001",
            "image_type": "screen_time",
            "original_filepath": "/Users/participant/Screenshots/screen.png",
        }

        response = await client.post(
            "/api/v1/screenshots/upload",
            json=upload_data,
            headers=api_key_header(),
        )

        if response.status_code == 401:
            pytest.skip("Invalid API key")

        assert response.status_code == 201
        screenshot_id = response.json()["screenshot_id"]

        result = await db_session.execute(
            select(Screenshot).where(Screenshot.id == screenshot_id)
        )
        screenshot = result.scalar_one()
        assert screenshot.original_filepath == "/Users/participant/Screenshots/screen.png"

    @pytest.mark.skip(reason="Requires PostgreSQL with INSERT ON CONFLICT support")
    async def test_upload_auto_detects_device_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Upload without device_type should auto-detect from dimensions."""
        upload_data = {
            "screenshot": create_minimal_png(),
            "group_id": "autodetect-test",
            "participant_id": "P001",
            "image_type": "screen_time",
            # No device_type provided - should be auto-detected
        }

        response = await client.post(
            "/api/v1/screenshots/upload",
            json=upload_data,
            headers=api_key_header(),
        )

        if response.status_code == 401:
            pytest.skip("Invalid API key")

        assert response.status_code == 201
        data = response.json()
        # Device type should be detected (though 1x1 image may return "unknown")
        assert data["device_type_detected"] is not None


@pytest.mark.asyncio
class TestUploadSHA256Verification:
    """Test SHA256 checksum verification on upload."""

    @pytest.mark.skip(reason="Requires PostgreSQL with INSERT ON CONFLICT support")
    async def test_upload_with_correct_sha256(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Upload with correct SHA256 should succeed."""
        import hashlib

        png_b64 = create_minimal_png()
        png_bytes = base64.b64decode(png_b64)
        correct_sha256 = hashlib.sha256(png_bytes).hexdigest()

        upload_data = {
            "screenshot": png_b64,
            "group_id": "sha256-test",
            "participant_id": "P001",
            "image_type": "screen_time",
            "sha256": correct_sha256,
        }

        response = await client.post(
            "/api/v1/screenshots/upload",
            json=upload_data,
            headers=api_key_header(),
        )

        if response.status_code == 401:
            pytest.skip("Invalid API key")

        assert response.status_code == 201

    @pytest.mark.skip(reason="Requires PostgreSQL with INSERT ON CONFLICT support")
    async def test_upload_with_incorrect_sha256(
        self,
        client: AsyncClient,
    ):
        """Upload with incorrect SHA256 should fail."""
        upload_data = {
            "screenshot": create_minimal_png(),
            "group_id": "sha256-fail-test",
            "participant_id": "P001",
            "image_type": "screen_time",
            "sha256": "incorrect_hash_value_that_does_not_match",
        }

        response = await client.post(
            "/api/v1/screenshots/upload",
            json=upload_data,
            headers=api_key_header(),
        )

        if response.status_code == 401:
            pytest.skip("Invalid API key")

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error_code"] == "CHECKSUM_MISMATCH"
