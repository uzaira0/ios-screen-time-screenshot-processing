"""
Integration tests for GET /screenshots/{id}/stage-image endpoint.

Tests the stage-image endpoint that serves output files from
specific preprocessing pipeline stages.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import Screenshot, User
from tests.conftest import auth_headers
@pytest.mark.asyncio
class TestGetStageImage:
    """Test GET /screenshots/{id}/stage-image endpoint."""

    async def _create_screenshot_with_preprocessing(
        self,
        db_session: AsyncSession,
        user: User,
        file_path: str,
        preprocessing: dict | None = None,
    ) -> Screenshot:
        """Helper to create a screenshot with preprocessing metadata."""
        screenshot = Screenshot(
            file_path=file_path,
            image_type="screen_time",
            annotation_status="pending",
            processing_status="completed",
            target_annotations=2,
            current_annotation_count=0,
            uploaded_by_id=user.id,
            processing_metadata={"preprocessing": preprocessing} if preprocessing else None,
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)
        return screenshot

    async def test_invalid_stage_returns_400(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_screenshot: Screenshot,
    ):
        """Should reject invalid stage names."""
        response = await client.get(
            f"/api/v1/screenshots/{test_screenshot.id}/stage-image",
            params={"stage": "not_a_real_stage"},
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 400
        assert "Invalid stage" in response.json()["detail"]

    async def test_valid_stage_names_accepted(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """All 4 pipeline stages should be accepted (may 404 due to missing file)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = Path(tmpdir) / "test.png"
            img_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

            screenshot = await self._create_screenshot_with_preprocessing(
                db_session,
                test_user,
                str(img_path),
                {"base_file_path": str(img_path), "events": [], "current_events": {}, "stage_status": {}},
            )

            with patch("screenshot_processor.web.api.routes.screenshots.get_settings") as mock_settings:
                mock_settings.return_value.UPLOAD_DIR = tmpdir

                for stage in ["device_detection", "cropping", "phi_detection", "phi_redaction"]:
                    response = await client.get(
                        f"/api/v1/screenshots/{screenshot.id}/stage-image",
                        params={"stage": stage},
                        headers=auth_headers(test_user.username),
                    )
                    # Should not be 400 — stage name is valid
                    assert response.status_code != 400, f"Stage '{stage}' rejected as invalid"

    async def test_returns_stage_output_file(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Should serve the output_file of the current event for the requested stage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir) / "original.png"
            crop_path = Path(tmpdir) / "original_crop_v1.png"
            base_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
            crop_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"CROPPED")

            screenshot = await self._create_screenshot_with_preprocessing(
                db_session,
                test_user,
                str(base_path),
                {
                    "base_file_path": str(base_path),
                    "events": [
                        {
                            "event_id": 1,
                            "stage": "cropping",
                            "timestamp": "2025-01-01T00:00:00Z",
                            "source": "auto",
                            "params": {},
                            "result": {"was_cropped": True},
                            "output_file": str(crop_path),
                            "input_file": str(base_path),
                        },
                    ],
                    "current_events": {"cropping": 1},
                    "stage_status": {"cropping": "completed"},
                },
            )

            with patch("screenshot_processor.web.api.routes.screenshots.get_settings") as mock_settings:
                mock_settings.return_value.UPLOAD_DIR = tmpdir

                response = await client.get(
                    f"/api/v1/screenshots/{screenshot.id}/stage-image",
                    params={"stage": "cropping"},
                    headers=auth_headers(test_user.username),
                )
                assert response.status_code == 200
                assert b"CROPPED" in response.content

    async def test_falls_back_to_input_file(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """When no output_file, should fall back to input_file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir) / "original.png"
            base_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"BASE")

            screenshot = await self._create_screenshot_with_preprocessing(
                db_session,
                test_user,
                str(base_path),
                {
                    "base_file_path": str(base_path),
                    "events": [
                        {
                            "event_id": 1,
                            "stage": "cropping",
                            "timestamp": "2025-01-01T00:00:00Z",
                            "source": "auto",
                            "params": {},
                            "result": {"was_cropped": False},
                            "output_file": None,
                            "input_file": str(base_path),
                        },
                    ],
                    "current_events": {"cropping": 1},
                    "stage_status": {"cropping": "completed"},
                },
            )

            with patch("screenshot_processor.web.api.routes.screenshots.get_settings") as mock_settings:
                mock_settings.return_value.UPLOAD_DIR = tmpdir

                response = await client.get(
                    f"/api/v1/screenshots/{screenshot.id}/stage-image",
                    params={"stage": "cropping"},
                    headers=auth_headers(test_user.username),
                )
                assert response.status_code == 200
                assert b"BASE" in response.content

    async def test_falls_back_to_base_file_path(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """When no current event for stage, should fall back to base_file_path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir) / "original.png"
            base_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"ORIGINAL")

            screenshot = await self._create_screenshot_with_preprocessing(
                db_session,
                test_user,
                str(base_path),
                {
                    "base_file_path": str(base_path),
                    "events": [],
                    "current_events": {},
                    "stage_status": {},
                },
            )

            with patch("screenshot_processor.web.api.routes.screenshots.get_settings") as mock_settings:
                mock_settings.return_value.UPLOAD_DIR = tmpdir

                response = await client.get(
                    f"/api/v1/screenshots/{screenshot.id}/stage-image",
                    params={"stage": "cropping"},
                    headers=auth_headers(test_user.username),
                )
                assert response.status_code == 200
                assert b"ORIGINAL" in response.content

    async def test_path_traversal_blocked(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Should block access to files outside the upload directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            outside_path = "/etc/passwd"
            base_path = Path(tmpdir) / "original.png"
            base_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

            screenshot = await self._create_screenshot_with_preprocessing(
                db_session,
                test_user,
                str(base_path),
                {
                    "base_file_path": str(base_path),
                    "events": [
                        {
                            "event_id": 1,
                            "stage": "cropping",
                            "timestamp": "2025-01-01T00:00:00Z",
                            "source": "auto",
                            "params": {},
                            "result": {},
                            "output_file": outside_path,
                            "input_file": str(base_path),
                        },
                    ],
                    "current_events": {"cropping": 1},
                    "stage_status": {},
                },
            )

            with patch("screenshot_processor.web.api.routes.screenshots.get_settings") as mock_settings:
                mock_settings.return_value.UPLOAD_DIR = tmpdir

                response = await client.get(
                    f"/api/v1/screenshots/{screenshot.id}/stage-image",
                    params={"stage": "cropping"},
                    headers=auth_headers(test_user.username),
                )
                assert response.status_code == 403
                assert "Access denied" in response.json()["detail"]

    async def test_screenshot_not_found_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Should return 404 for nonexistent screenshot."""
        response = await client.get(
            "/api/v1/screenshots/99999/stage-image",
            params={"stage": "cropping"},
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 404

    async def test_missing_file_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Should return 404 when the file doesn't exist on disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent = Path(tmpdir) / "does_not_exist.png"

            screenshot = await self._create_screenshot_with_preprocessing(
                db_session,
                test_user,
                str(nonexistent),
                {
                    "base_file_path": str(nonexistent),
                    "events": [],
                    "current_events": {},
                    "stage_status": {},
                },
            )

            with patch("screenshot_processor.web.api.routes.screenshots.get_settings") as mock_settings:
                mock_settings.return_value.UPLOAD_DIR = tmpdir

                response = await client.get(
                    f"/api/v1/screenshots/{screenshot.id}/stage-image",
                    params={"stage": "cropping"},
                    headers=auth_headers(test_user.username),
                )
                assert response.status_code == 404
                assert "Image not found" in response.json()["detail"]

    async def test_stage_query_param_required(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_screenshot: Screenshot,
    ):
        """Should return 422 when stage parameter is missing."""
        response = await client.get(
            f"/api/v1/screenshots/{test_screenshot.id}/stage-image",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 422
