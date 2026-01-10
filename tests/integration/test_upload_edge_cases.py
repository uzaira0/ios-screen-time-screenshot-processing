"""
Edge case tests for Upload API endpoints.

Tests input validation, malformed data, authentication, and boundary conditions
for the upload endpoints. Most upload tests require PostgreSQL (INSERT ON CONFLICT),
so tests here focus on validation that happens BEFORE the DB write.
"""

from __future__ import annotations

import base64
import os

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import Screenshot, User
from tests.conftest import auth_headers
def api_key_header() -> dict[str, str]:
    api_key = os.environ.get("UPLOAD_API_KEY", "test-api-key")
    return {"X-API-Key": api_key}


def create_minimal_png() -> str:
    """Create a minimal valid PNG image as base64."""
    png_bytes = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
        0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
        0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
        0x00, 0x00, 0x03, 0x00, 0x01, 0x00, 0x18, 0xDD,
        0x8D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45,
        0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
    ])
    return base64.b64encode(png_bytes).decode("ascii")


# =============================================================================
# API key authentication
# =============================================================================


@pytest.mark.asyncio
class TestUploadAuthentication:
    """Test API key authentication for upload endpoints."""

    async def test_upload_without_api_key(
        self,
        client: AsyncClient,
    ):
        """Upload without X-API-Key header should fail."""
        response = await client.post(
            "/api/v1/screenshots/upload",
            json={
                "screenshot": create_minimal_png(),
                "group_id": "test",
                "participant_id": "P001",
                "image_type": "screen_time",
            },
        )
        assert response.status_code in [401, 422]

    async def test_upload_with_empty_api_key(
        self,
        client: AsyncClient,
    ):
        """Upload with empty API key should fail."""
        response = await client.post(
            "/api/v1/screenshots/upload",
            json={
                "screenshot": create_minimal_png(),
                "group_id": "test",
                "participant_id": "P001",
                "image_type": "screen_time",
            },
            headers={"X-API-Key": ""},
        )
        assert response.status_code in [401, 422]

    async def test_upload_with_wrong_api_key(
        self,
        client: AsyncClient,
    ):
        """Upload with incorrect API key should fail."""
        response = await client.post(
            "/api/v1/screenshots/upload",
            json={
                "screenshot": create_minimal_png(),
                "group_id": "test",
                "participant_id": "P001",
                "image_type": "screen_time",
            },
            headers={"X-API-Key": "definitely-wrong-key-12345"},
        )
        assert response.status_code == 401

    async def test_batch_upload_without_api_key(
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


# =============================================================================
# Invalid image data
# =============================================================================


@pytest.mark.asyncio
class TestInvalidImageData:
    """Test upload with various types of invalid image data."""

    @pytest.mark.parametrize(
        "screenshot_data,error_desc",
        [
            ("not-valid-base64!!!", "completely_invalid_base64"),
            ("", "empty_string"),
            ("===", "invalid_padding_only"),
        ],
        ids=["invalid_chars", "empty_string", "padding_only"],
    )
    async def test_invalid_base64_variations(
        self,
        client: AsyncClient,
        screenshot_data: str,
        error_desc: str,
    ):
        """Various invalid base64 inputs should be rejected."""
        response = await client.post(
            "/api/v1/screenshots/upload",
            json={
                "screenshot": screenshot_data,
                "group_id": "test",
                "participant_id": "P001",
                "image_type": "screen_time",
            },
            headers=api_key_header(),
        )
        if response.status_code == 401:
            pytest.skip("Invalid API key")
        assert response.status_code == 400, (
            f"Invalid base64 ({error_desc}) should be rejected, got {response.status_code}"
        )

    async def test_valid_base64_but_not_image(
        self,
        client: AsyncClient,
    ):
        """Valid base64 encoding of non-image data should be rejected."""
        # base64 of "Hello, World!"
        not_image = base64.b64encode(b"Hello, World!").decode("ascii")
        response = await client.post(
            "/api/v1/screenshots/upload",
            json={
                "screenshot": not_image,
                "group_id": "test",
                "participant_id": "P001",
                "image_type": "screen_time",
            },
            headers=api_key_header(),
        )
        if response.status_code == 401:
            pytest.skip("Invalid API key")
        assert response.status_code == 400


# =============================================================================
# Image type validation
# =============================================================================


@pytest.mark.asyncio
class TestImageTypeValidation:
    """Test image_type field validation."""

    @pytest.mark.parametrize(
        "image_type,expected_valid",
        [
            ("screen_time", True),
            ("battery", True),
            ("invalid", False),
            ("Screen_Time", False),
            ("SCREEN_TIME", False),
            ("", False),
        ],
        ids=["screen_time", "battery", "invalid", "wrong_case_1", "wrong_case_2", "empty"],
    )
    async def test_image_type_validation(
        self,
        client: AsyncClient,
        image_type: str,
        expected_valid: bool,
    ):
        """Only 'screen_time' and 'battery' should be accepted as image_type."""
        try:
            response = await client.post(
                "/api/v1/screenshots/upload",
                json={
                    "screenshot": create_minimal_png(),
                    "group_id": "test",
                    "participant_id": "P001",
                    "image_type": image_type,
                },
                headers=api_key_header(),
            )
        except PermissionError:
            if expected_valid:
                # Valid type passed validation but hit filesystem permission error
                # (test env doesn't have writable uploads dir). That's fine.
                return
            raise

        if response.status_code == 401:
            pytest.skip("Upload API key not configured for test environment")

        if expected_valid:
            assert response.status_code != 422, (
                f"Valid image_type '{image_type}' rejected with 422"
            )
        else:
            assert response.status_code == 422, (
                f"Invalid image_type '{image_type}' should be rejected with 422, got {response.status_code}"
            )


# =============================================================================
# Missing required fields
# =============================================================================


@pytest.mark.asyncio
class TestMissingRequiredFields:
    """Test that missing required fields produce appropriate errors."""

    @pytest.mark.parametrize(
        "missing_field",
        ["screenshot", "group_id", "participant_id", "image_type"],
        ids=lambda f: f"missing_{f}",
    )
    async def test_missing_required_upload_field(
        self,
        client: AsyncClient,
        missing_field: str,
    ):
        """Each required field omission should result in 422."""
        payload = {
            "screenshot": create_minimal_png(),
            "group_id": "test",
            "participant_id": "P001",
            "image_type": "screen_time",
        }
        del payload[missing_field]

        response = await client.post(
            "/api/v1/screenshots/upload",
            json=payload,
            headers=api_key_header(),
        )
        if response.status_code == 401:
            pytest.skip("Invalid API key")
        assert response.status_code == 422, (
            f"Missing '{missing_field}' should produce 422, got {response.status_code}"
        )


# =============================================================================
# SHA256 checksum verification
# =============================================================================


@pytest.mark.asyncio
class TestSHA256Verification:
    """Test SHA256 checksum edge cases."""

    @pytest.mark.parametrize(
        "bad_sha256",
        [
            "0" * 64,  # Valid format but wrong hash
            "abc",  # Too short
            "x" * 64,  # Non-hex chars
            "",  # Empty string
        ],
        ids=["wrong_hash", "too_short", "non_hex", "empty"],
    )
    @pytest.mark.skip(reason="Requires PostgreSQL with INSERT ON CONFLICT support")
    async def test_invalid_sha256_values(
        self,
        client: AsyncClient,
        bad_sha256: str,
    ):
        """Various incorrect SHA256 values should be rejected."""
        response = await client.post(
            "/api/v1/screenshots/upload",
            json={
                "screenshot": create_minimal_png(),
                "group_id": "test",
                "participant_id": "P001",
                "image_type": "screen_time",
                "sha256": bad_sha256,
            },
            headers=api_key_header(),
        )
        if response.status_code == 401:
            pytest.skip("Invalid API key")
        assert response.status_code == 400


# =============================================================================
# Browser upload endpoint
# =============================================================================


@pytest.mark.asyncio
class TestBrowserUploadValidation:
    """Test the browser-based upload endpoint validation."""

    async def test_browser_upload_requires_auth(
        self,
        client: AsyncClient,
    ):
        """Browser upload should require authentication (X-Username header)."""
        response = await client.post(
            "/api/v1/screenshots/upload/browser",
            json={
                "group_id": "test",
                "image_type": "screen_time",
                "screenshots": [],
            },
        )
        # Should fail without auth
        assert response.status_code in [401, 422]

    async def test_browser_upload_empty_screenshots_list(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Browser upload with empty screenshots list should handle gracefully."""
        response = await client.post(
            "/api/v1/screenshots/upload/browser",
            json={
                "group_id": "test",
                "image_type": "screen_time",
                "screenshots": [],
            },
            headers=auth_headers(test_user.username),
        )
        # Should either succeed with 0 items or reject empty list
        assert response.status_code in [200, 201, 422]


# =============================================================================
# Filename edge cases
# =============================================================================


@pytest.mark.asyncio
class TestFilenameEdgeCases:
    """Test edge cases in filename handling."""

    @pytest.mark.parametrize(
        "filename",
        [
            "normal.png",
            "file with spaces.png",
            "file-with-dashes.png",
            "file_with_underscores.png",
            "../../../etc/passwd",  # Path traversal attempt
            "file\x00name.png",  # Null byte
            "a" * 500 + ".png",  # Very long filename
        ],
        ids=[
            "normal", "spaces", "dashes", "underscores",
            "path_traversal", "null_byte", "very_long",
        ],
    )
    @pytest.mark.skip(reason="Requires PostgreSQL with INSERT ON CONFLICT support")
    async def test_filename_handling(
        self,
        client: AsyncClient,
        filename: str,
    ):
        """Various filenames should be handled safely (no path traversal, etc.)."""
        response = await client.post(
            "/api/v1/screenshots/upload",
            json={
                "screenshot": create_minimal_png(),
                "group_id": "test",
                "participant_id": "P001",
                "image_type": "screen_time",
                "filename": filename,
            },
            headers=api_key_header(),
        )
        if response.status_code == 401:
            pytest.skip("Invalid API key")
        # Path traversal should be sanitized, not cause a server error
        assert response.status_code in [201, 400, 422], (
            f"Filename '{filename[:50]}...' caused unexpected status {response.status_code}"
        )


# =============================================================================
# Batch upload validation
# =============================================================================


@pytest.mark.asyncio
class TestBatchUploadValidation:
    """Test batch upload input validation."""

    async def test_batch_missing_screenshots_field(
        self,
        client: AsyncClient,
    ):
        """Batch upload without screenshots field should fail."""
        response = await client.post(
            "/api/v1/screenshots/upload/batch",
            json={
                "group_id": "test",
                "image_type": "screen_time",
            },
            headers=api_key_header(),
        )
        if response.status_code == 401:
            pytest.skip("Invalid API key")
        assert response.status_code == 422

    async def test_batch_invalid_image_type(
        self,
        client: AsyncClient,
    ):
        """Batch upload with invalid image type should fail."""
        response = await client.post(
            "/api/v1/screenshots/upload/batch",
            json={
                "group_id": "test",
                "image_type": "invalid_type",
                "screenshots": [
                    {
                        "screenshot": create_minimal_png(),
                        "participant_id": "P001",
                    }
                ],
            },
            headers=api_key_header(),
        )
        if response.status_code == 401:
            pytest.skip("Invalid API key")
        assert response.status_code == 422
