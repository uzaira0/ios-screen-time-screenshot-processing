"""
Integration tests for preprocessing pipeline API endpoints (Phases 2-4).

Endpoints tested:
  Phase 2: POST /screenshots/upload/browser
  Phase 3: GET  /screenshots/{id}/original-image
           POST /screenshots/{id}/manual-crop
  Phase 4: GET  /screenshots/{id}/phi-regions
           PUT  /screenshots/{id}/phi-regions
           POST /screenshots/{id}/apply-redaction

Note: upload/browser uses PostgreSQL INSERT ON CONFLICT and is skipped
on SQLite. The remaining endpoints work with SQLite via direct model setup.
"""

from __future__ import annotations

import io
import json
import struct
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import Group, Screenshot
from tests.conftest import auth_headers

REQUIRES_POSTGRES = pytest.mark.skip(reason="Requires PostgreSQL with INSERT ON CONFLICT support")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def create_minimal_png(width: int = 4, height: int = 4, color: tuple = (255, 0, 0)) -> bytes:
    """Create a minimal valid PNG image in memory (no external deps).

    Returns raw PNG bytes for the given width/height filled with a solid color.
    """

    def _crc32(data: bytes) -> int:
        import zlib
        return zlib.crc32(data) & 0xFFFFFFFF

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", _crc32(c))

    # IHDR
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = _chunk(b"IHDR", ihdr_data)

    # IDAT — uncompressed deflate with filter byte 0 per row
    import zlib

    raw = b""
    for _ in range(height):
        raw += b"\x00"  # filter byte
        for _ in range(width):
            raw += bytes(color)
    compressed = zlib.compress(raw)
    idat = _chunk(b"IDAT", compressed)

    # IEND
    iend = _chunk(b"IEND", b"")

    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend
def _make_preprocessing_metadata(
    file_path: str,
    *,
    events: list[dict[str, Any]] | None = None,
    current_events: dict[str, int | None] | None = None,
    stage_status: dict[str, str] | None = None,
) -> dict:
    """Build a processing_metadata dict with preprocessing sub-key."""
    return {
        "preprocessing": {
            "base_file_path": file_path,
            "events": events or [],
            "current_events": current_events or {},
            "stage_status": stage_status or {
                "device_detection": "pending",
                "cropping": "pending",
                "phi_detection": "pending",
                "phi_redaction": "pending",
            },
        }
    }


@pytest_asyncio.fixture
async def test_group_for_preproc(db_session: AsyncSession) -> Group:
    """Create a group for preprocessing tests."""
    group = Group(id="preproc-test", name="Preproc Test", image_type="screen_time")
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)
    return group


@pytest_asyncio.fixture
async def screenshot_with_image(
    db_session: AsyncSession, test_user, test_group_for_preproc, tmp_path
) -> Screenshot:
    """Create a screenshot backed by a real PNG file on disk."""
    img_bytes = create_minimal_png(100, 200)
    img_file = tmp_path / "test_screenshot.png"
    img_file.write_bytes(img_bytes)

    screenshot = Screenshot(
        file_path=str(img_file),
        image_type="screen_time",
        annotation_status="pending",
        processing_status="pending",
        target_annotations=1,
        current_annotation_count=0,
        uploaded_by_id=test_user.id,
        group_id=test_group_for_preproc.id,
        processing_metadata=_make_preprocessing_metadata(str(img_file)),
    )
    db_session.add(screenshot)
    await db_session.commit()
    await db_session.refresh(screenshot)
    return screenshot


# ===========================================================================
# Phase 2: POST /screenshots/upload/browser
# ===========================================================================


class TestBrowserUpload:
    """Tests for the browser upload endpoint.

    All tests are skipped because the endpoint uses PostgreSQL-specific
    INSERT ON CONFLICT which is unavailable with the SQLite test database.
    """

    @REQUIRES_POSTGRES
    @pytest.mark.asyncio
    async def test_upload_single_file(self, client: AsyncClient, test_user):
        img = create_minimal_png()
        metadata = {
            "group_id": "test-upload-group",
            "image_type": "screen_time",
            "items": [
                {"participant_id": "P001", "filename": "screenshot1.png"}
            ],
        }
        response = await client.post(
            "/api/v1/screenshots/upload/browser",
            data={"metadata": json.dumps(metadata)},
            files=[("files", ("screenshot1.png", io.BytesIO(img), "image/png"))],
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["total"] == 1
        assert body["successful"] == 1
        assert body["failed"] == 0
        assert body["results"][0]["success"] is True

    @REQUIRES_POSTGRES
    @pytest.mark.asyncio
    async def test_upload_file_count_mismatch(self, client: AsyncClient, test_user):
        metadata = {
            "group_id": "test-group",
            "image_type": "screen_time",
            "items": [
                {"participant_id": "P001", "filename": "a.png"},
                {"participant_id": "P002", "filename": "b.png"},
            ],
        }
        img = create_minimal_png()
        response = await client.post(
            "/api/v1/screenshots/upload/browser",
            data={"metadata": json.dumps(metadata)},
            files=[("files", ("a.png", io.BytesIO(img), "image/png"))],
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 400
        assert "count" in response.json()["detail"].lower()

    @REQUIRES_POSTGRES
    @pytest.mark.asyncio
    async def test_upload_invalid_metadata_json(self, client: AsyncClient, test_user):
        img = create_minimal_png()
        response = await client.post(
            "/api/v1/screenshots/upload/browser",
            data={"metadata": "not-valid-json"},
            files=[("files", ("a.png", io.BytesIO(img), "image/png"))],
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 400

    @REQUIRES_POSTGRES
    @pytest.mark.asyncio
    async def test_upload_requires_auth(self, client: AsyncClient):
        """Endpoint requires X-Username header."""
        img = create_minimal_png()
        metadata = {
            "group_id": "g",
            "image_type": "screen_time",
            "items": [{"participant_id": "P", "filename": "a.png"}],
        }
        response = await client.post(
            "/api/v1/screenshots/upload/browser",
            data={"metadata": json.dumps(metadata)},
            files=[("files", ("a.png", io.BytesIO(img), "image/png"))],
        )
        # Should fail without auth
        assert response.status_code in (401, 422)


# ===========================================================================
# Phase 3: GET /screenshots/{id}/original-image
# ===========================================================================


class TestGetOriginalImage:
    @pytest.mark.asyncio
    async def test_serves_original_image(self, client: AsyncClient, test_user, screenshot_with_image, tmp_path):
        """Should return the original PNG file."""
        # Patch UPLOAD_DIR so the path traversal check allows tmp_path
        with patch("screenshot_processor.web.api.routes.screenshots.get_settings") as mock_gs:
            mock_gs.return_value.UPLOAD_DIR = str(tmp_path)
            response = await client.get(
                f"/api/v1/screenshots/{screenshot_with_image.id}/original-image",
                headers=auth_headers(test_user.username),
            )
        assert response.status_code == 200
        assert response.headers["content-type"] in ("image/png", "image/png; charset=utf-8")
        # Verify it's a PNG
        assert response.content[:8] == b"\x89PNG\r\n\x1a\n"

    @pytest.mark.asyncio
    async def test_nonexistent_screenshot(self, client: AsyncClient, test_user):
        response = await client.get(
            "/api/v1/screenshots/99999/original-image",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_file_on_disk(self, client: AsyncClient, test_user, db_session, test_group_for_preproc, tmp_path):
        """Screenshot exists in DB but file doesn't exist on disk."""
        fake_path = str(tmp_path / "nonexistent" / "fake.png")
        screenshot = Screenshot(
            file_path=fake_path,
            image_type="screen_time",
            annotation_status="pending",
            processing_status="pending",
            target_annotations=1,
            current_annotation_count=0,
            uploaded_by_id=test_user.id,
            group_id=test_group_for_preproc.id,
            processing_metadata=_make_preprocessing_metadata(fake_path),
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        # Patch UPLOAD_DIR so the path traversal check allows tmp_path
        with patch("screenshot_processor.web.api.routes.screenshots.get_settings") as mock_gs:
            mock_gs.return_value.UPLOAD_DIR = str(tmp_path)
            response = await client.get(
                f"/api/v1/screenshots/{screenshot.id}/original-image",
                headers=auth_headers(test_user.username),
            )
        assert response.status_code == 404


# ===========================================================================
# Phase 3: POST /screenshots/{id}/manual-crop
# ===========================================================================


class TestManualCrop:
    @pytest.mark.asyncio
    async def test_successful_crop(self, client: AsyncClient, test_user, screenshot_with_image, tmp_path):
        """Crop a 100x200 image to a smaller rectangle."""
        crop = {"left": 10, "top": 20, "right": 90, "bottom": 180}

        # Patch cv2 to avoid real OpenCV dependency in test env
        mock_img = MagicMock()
        mock_img.shape = (200, 100, 3)  # h, w, c
        mock_cropped = MagicMock()
        mock_cropped.shape = (160, 80, 3)  # cropped h=180-20, w=90-10

        with patch("screenshot_processor.web.api.routes.screenshots.cv2") as mock_cv2, \
             patch("screenshot_processor.web.api.routes.screenshots.asyncio") as mock_asyncio:
            mock_cv2.imread.return_value = mock_img
            mock_img.__getitem__ = MagicMock(return_value=mock_cropped)

            # Make asyncio.to_thread call the function directly
            async def fake_to_thread(fn, *args):
                return fn(*args) if callable(fn) else fn

            mock_asyncio.to_thread = AsyncMock(side_effect=fake_to_thread)

            response = await client.post(
                f"/api/v1/screenshots/{screenshot_with_image.id}/manual-crop",
                json=crop,
                headers=auth_headers(test_user.username),
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["event_id"] >= 1
        assert body["width"] == 80
        assert body["height"] == 160
        assert "invalidated" in body["message"].lower()

    @pytest.mark.asyncio
    async def test_crop_invalid_coords_right_le_left(self, client: AsyncClient, test_user, screenshot_with_image):
        """right <= left should fail validation."""
        crop = {"left": 50, "top": 0, "right": 30, "bottom": 100}
        response = await client.post(
            f"/api/v1/screenshots/{screenshot_with_image.id}/manual-crop",
            json=crop,
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_crop_invalid_coords_bottom_le_top(self, client: AsyncClient, test_user, screenshot_with_image):
        """bottom <= top should fail validation."""
        crop = {"left": 0, "top": 100, "right": 50, "bottom": 50}
        response = await client.post(
            f"/api/v1/screenshots/{screenshot_with_image.id}/manual-crop",
            json=crop,
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_crop_exceeds_image_bounds(self, client: AsyncClient, test_user, screenshot_with_image):
        """Crop rectangle larger than the image should return 400."""
        crop = {"left": 0, "top": 0, "right": 5000, "bottom": 5000}

        mock_img = MagicMock()
        mock_img.shape = (200, 100, 3)

        with patch("screenshot_processor.web.api.routes.screenshots.cv2") as mock_cv2, \
             patch("screenshot_processor.web.api.routes.screenshots.asyncio") as mock_asyncio:
            mock_cv2.imread.return_value = mock_img

            async def fake_to_thread(fn, *args):
                return fn(*args) if callable(fn) else fn

            mock_asyncio.to_thread = AsyncMock(side_effect=fake_to_thread)

            response = await client.post(
                f"/api/v1/screenshots/{screenshot_with_image.id}/manual-crop",
                json=crop,
                headers=auth_headers(test_user.username),
            )

        assert response.status_code == 400
        assert "exceeds" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_crop_nonexistent_screenshot(self, client: AsyncClient, test_user):
        crop = {"left": 0, "top": 0, "right": 50, "bottom": 50}
        response = await client.post(
            "/api/v1/screenshots/99999/manual-crop",
            json=crop,
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 404


# ===========================================================================
# Phase 4: GET /screenshots/{id}/phi-regions
# ===========================================================================


class TestGetPHIRegions:
    @pytest.mark.asyncio
    async def test_no_phi_detection_event(self, client: AsyncClient, test_user, screenshot_with_image):
        """When no phi_detection event exists, returns empty regions."""
        response = await client.get(
            f"/api/v1/screenshots/{screenshot_with_image.id}/phi-regions",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["regions"] == []
        assert body["source"] is None
        assert body["event_id"] is None

    @pytest.mark.asyncio
    async def test_returns_regions_from_event(self, client: AsyncClient, test_user, db_session, screenshot_with_image):
        """When phi_detection event has regions, they are returned normalized."""
        # Manually inject a phi_detection event into metadata
        screenshot_with_image.processing_metadata = _make_preprocessing_metadata(
            screenshot_with_image.file_path,
            events=[
                {
                    "event_id": 1,
                    "stage": "phi_detection",
                    "source": "auto",
                    "result": {
                        "phi_detected": True,
                        "regions_count": 2,
                        "regions": [
                            {"bbox": {"x": 10, "y": 20, "width": 100, "height": 50}, "type": "PERSON_NAME", "confidence": 0.95, "text": "John"},
                            {"x": 200, "y": 300, "w": 50, "h": 30, "label": "DATE", "source": "auto", "confidence": 0.8, "text": "2024-01"},
                        ],
                    },
                }
            ],
            current_events={"phi_detection": 1},
            stage_status={"device_detection": "completed", "cropping": "completed", "phi_detection": "completed", "phi_redaction": "pending"},
        )
        await db_session.commit()
        await db_session.refresh(screenshot_with_image)

        response = await client.get(
            f"/api/v1/screenshots/{screenshot_with_image.id}/phi-regions",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["regions"]) == 2
        assert body["source"] == "auto"
        assert body["event_id"] == 1

        # First region: bbox format -> normalized
        r0 = body["regions"][0]
        assert r0["x"] == 10
        assert r0["y"] == 20
        assert r0["w"] == 100
        assert r0["h"] == 50
        assert r0["label"] == "PERSON_NAME"

        # Second region: flat format
        r1 = body["regions"][1]
        assert r1["x"] == 200
        assert r1["y"] == 300
        assert r1["w"] == 50
        assert r1["h"] == 30
        assert r1["label"] == "DATE"

    @pytest.mark.asyncio
    async def test_nonexistent_screenshot(self, client: AsyncClient, test_user):
        response = await client.get(
            "/api/v1/screenshots/99999/phi-regions",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 404


# ===========================================================================
# Phase 4: PUT /screenshots/{id}/phi-regions
# ===========================================================================


class TestSavePHIRegions:
    @pytest.mark.asyncio
    async def test_save_regions(self, client: AsyncClient, test_user, screenshot_with_image):
        """Saving regions should record event and invalidate downstream."""
        payload = {
            "regions": [
                {"x": 10, "y": 20, "w": 100, "h": 50, "label": "PERSON_NAME", "source": "manual", "confidence": 1.0, "text": "John Doe"},
                {"x": 200, "y": 300, "w": 80, "h": 40, "label": "DATE"},
            ],
            "preset": "manual",
        }
        response = await client.put(
            f"/api/v1/screenshots/{screenshot_with_image.id}/phi-regions",
            json=payload,
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["regions_count"] == 2
        assert body["event_id"] >= 1
        assert "invalidated" in body["message"].lower()

    @pytest.mark.asyncio
    async def test_save_empty_regions(self, client: AsyncClient, test_user, screenshot_with_image):
        """Saving zero regions (clearing) should still succeed."""
        payload = {"regions": [], "preset": "manual"}
        response = await client.put(
            f"/api/v1/screenshots/{screenshot_with_image.id}/phi-regions",
            json=payload,
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["regions_count"] == 0

    @pytest.mark.asyncio
    async def test_save_regions_nonexistent_screenshot(self, client: AsyncClient, test_user):
        payload = {"regions": [], "preset": "manual"}
        response = await client.put(
            "/api/v1/screenshots/99999/phi-regions",
            json=payload,
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_save_regions_then_get(self, client: AsyncClient, test_user, screenshot_with_image):
        """Regions saved via PUT should be retrievable via GET."""
        payload = {
            "regions": [
                {"x": 50, "y": 60, "w": 70, "h": 80, "label": "PHONE", "source": "manual", "confidence": 1.0, "text": "555-1234"},
            ],
            "preset": "custom",
        }
        put_resp = await client.put(
            f"/api/v1/screenshots/{screenshot_with_image.id}/phi-regions",
            json=payload,
            headers=auth_headers(test_user.username),
        )
        assert put_resp.status_code == 200

        # Now GET should return the saved regions
        get_resp = await client.get(
            f"/api/v1/screenshots/{screenshot_with_image.id}/phi-regions",
            headers=auth_headers(test_user.username),
        )
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert len(body["regions"]) == 1
        assert body["regions"][0]["x"] == 50
        assert body["regions"][0]["label"] == "PHONE"
        assert body["source"] == "manual"


# ===========================================================================
# Phase 4: POST /screenshots/{id}/apply-redaction
# ===========================================================================


class TestApplyRedaction:
    @pytest.mark.asyncio
    async def test_apply_redaction_success(self, client: AsyncClient, test_user, screenshot_with_image, tmp_path):
        """Apply redaction with mocked redact_phi function."""
        # Give the screenshot a cropping output to serve as input for redaction
        cropped_img = create_minimal_png(80, 160)
        cropped_file = tmp_path / "test_screenshot_crop_v1.png"
        cropped_file.write_bytes(cropped_img)

        payload = {
            "regions": [
                {"x": 10, "y": 20, "w": 30, "h": 40, "label": "PERSON_NAME"},
            ],
            "redaction_method": "redbox",
        }

        # Mock the redact_phi function and aiofiles
        from screenshot_processor.web.services.preprocessing_service import PHIRedactionResult

        mock_result = PHIRedactionResult(
            image_bytes=create_minimal_png(80, 160),
            regions_redacted=1,
            redaction_method="redbox",
        )

        with patch("screenshot_processor.web.api.routes.screenshots.aiofiles") as mock_aiofiles, \
             patch("screenshot_processor.web.api.routes.screenshots.asyncio") as mock_asyncio:

            # Mock aiofiles.open for reading input image
            mock_read_ctx = AsyncMock()
            mock_read_file = AsyncMock()
            mock_read_file.read = AsyncMock(return_value=cropped_img)
            mock_read_ctx.__aenter__ = AsyncMock(return_value=mock_read_file)
            mock_read_ctx.__aexit__ = AsyncMock(return_value=False)

            # Mock aiofiles.open for writing output image
            mock_write_ctx = AsyncMock()
            mock_write_file = AsyncMock()
            mock_write_file.write = AsyncMock()
            mock_write_ctx.__aenter__ = AsyncMock(return_value=mock_write_file)
            mock_write_ctx.__aexit__ = AsyncMock(return_value=False)

            call_count = 0

            def open_side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return mock_read_ctx
                return mock_write_ctx

            mock_aiofiles.open = MagicMock(side_effect=open_side_effect)

            # Make asyncio.to_thread return mock redaction result
            mock_asyncio.to_thread = AsyncMock(return_value=mock_result)

            response = await client.post(
                f"/api/v1/screenshots/{screenshot_with_image.id}/apply-redaction",
                json=payload,
                headers=auth_headers(test_user.username),
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["regions_redacted"] == 1
        assert body["event_id"] >= 1
        assert "redacted" in body["message"].lower()

    @pytest.mark.asyncio
    async def test_apply_redaction_no_regions(self, client: AsyncClient, test_user, screenshot_with_image, tmp_path):
        """Applying redaction with zero regions should still work (no-op redaction)."""
        from screenshot_processor.web.services.preprocessing_service import PHIRedactionResult

        mock_result = PHIRedactionResult(
            image_bytes=create_minimal_png(),
            regions_redacted=0,
            redaction_method="redbox",
        )

        with patch("screenshot_processor.web.api.routes.screenshots.aiofiles") as mock_aiofiles, \
             patch("screenshot_processor.web.api.routes.screenshots.asyncio") as mock_asyncio:

            mock_read_ctx = AsyncMock()
            mock_read_file = AsyncMock()
            mock_read_file.read = AsyncMock(return_value=create_minimal_png())
            mock_read_ctx.__aenter__ = AsyncMock(return_value=mock_read_file)
            mock_read_ctx.__aexit__ = AsyncMock(return_value=False)

            mock_write_ctx = AsyncMock()
            mock_write_file = AsyncMock()
            mock_write_file.write = AsyncMock()
            mock_write_ctx.__aenter__ = AsyncMock(return_value=mock_write_file)
            mock_write_ctx.__aexit__ = AsyncMock(return_value=False)

            call_count = 0

            def open_side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return mock_read_ctx if call_count == 1 else mock_write_ctx

            mock_aiofiles.open = MagicMock(side_effect=open_side_effect)
            mock_asyncio.to_thread = AsyncMock(return_value=mock_result)

            response = await client.post(
                f"/api/v1/screenshots/{screenshot_with_image.id}/apply-redaction",
                json={"regions": [], "redaction_method": "blackbox"},
                headers=auth_headers(test_user.username),
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["regions_redacted"] == 0

    @pytest.mark.asyncio
    async def test_apply_redaction_nonexistent_screenshot(self, client: AsyncClient, test_user):
        payload = {"regions": [], "redaction_method": "redbox"}
        response = await client.post(
            "/api/v1/screenshots/99999/apply-redaction",
            json=payload,
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 404


# ===========================================================================
# Cross-endpoint integration: save regions → get regions → apply redaction
# ===========================================================================


class TestPHIWorkflow:
    @pytest.mark.asyncio
    async def test_full_phi_workflow(self, client: AsyncClient, test_user, screenshot_with_image, tmp_path):
        """Exercise the full PHI workflow: save regions, retrieve, apply redaction."""
        headers = auth_headers(test_user.username)
        sid = screenshot_with_image.id

        # Step 1: Initially no regions
        resp = await client.get(f"/api/v1/screenshots/{sid}/phi-regions", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["regions"] == []

        # Step 2: Save some regions
        regions_payload = {
            "regions": [
                {"x": 10, "y": 20, "w": 100, "h": 50, "label": "PERSON_NAME", "text": "Jane Doe"},
                {"x": 300, "y": 400, "w": 60, "h": 30, "label": "PHONE", "text": "555-0000"},
            ],
            "preset": "manual",
        }
        resp = await client.put(f"/api/v1/screenshots/{sid}/phi-regions", json=regions_payload, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["regions_count"] == 2

        # Step 3: Retrieve saved regions
        resp = await client.get(f"/api/v1/screenshots/{sid}/phi-regions", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["regions"]) == 2
        assert body["source"] == "manual"

        # Step 4: Apply redaction (with mocked redact_phi)
        from screenshot_processor.web.services.preprocessing_service import PHIRedactionResult

        mock_result = PHIRedactionResult(
            image_bytes=create_minimal_png(),
            regions_redacted=2,
            redaction_method="redbox",
        )

        redaction_payload = {
            "regions": regions_payload["regions"],
            "redaction_method": "redbox",
        }

        with patch("screenshot_processor.web.api.routes.screenshots.aiofiles") as mock_aiofiles, \
             patch("screenshot_processor.web.api.routes.screenshots.asyncio") as mock_asyncio:
            mock_read_ctx = AsyncMock()
            mock_read_file = AsyncMock()
            mock_read_file.read = AsyncMock(return_value=create_minimal_png())
            mock_read_ctx.__aenter__ = AsyncMock(return_value=mock_read_file)
            mock_read_ctx.__aexit__ = AsyncMock(return_value=False)

            mock_write_ctx = AsyncMock()
            mock_write_file = AsyncMock()
            mock_write_file.write = AsyncMock()
            mock_write_ctx.__aenter__ = AsyncMock(return_value=mock_write_file)
            mock_write_ctx.__aexit__ = AsyncMock(return_value=False)

            call_count = 0

            def open_side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return mock_read_ctx if call_count == 1 else mock_write_ctx

            mock_aiofiles.open = MagicMock(side_effect=open_side_effect)
            mock_asyncio.to_thread = AsyncMock(return_value=mock_result)

            resp = await client.post(
                f"/api/v1/screenshots/{sid}/apply-redaction",
                json=redaction_payload,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["regions_redacted"] == 2
