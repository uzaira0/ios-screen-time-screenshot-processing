"""
Unit tests for processing_service module.

Tests the update_screenshot_from_result helper and the async/sync
processing wrappers with mocked core processing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    AnnotationStatus,
    ProcessingMethod,
    ProcessingStatus,
    Screenshot,
    User,
)
from screenshot_processor.web.services.processing_service import (
    process_screenshot_async,
    process_screenshot_file,
    reprocess_screenshot,
    update_screenshot_from_result,
)


def _make_result(**overrides):
    """Build a processing result dict with sensible defaults."""
    base = {
        "processing_status": "completed",
        "extracted_title": "Instagram",
        "extracted_total": "2h 30m",
        "extracted_hourly_data": {"0": 5, "1": 10},
        "issues": [],
        "has_blocking_issues": False,
        "alignment_score": 0.95,
        "title_y_position": 100,
        "processing_method": "line_based",
        "grid_detection_confidence": 0.9,
        "grid_coords": {
            "upper_left_x": 10,
            "upper_left_y": 20,
            "lower_right_x": 300,
            "lower_right_y": 400,
        },
    }
    base.update(overrides)
    return base


class TestUpdateScreenshotFromResult:
    """Tests for update_screenshot_from_result."""

    def test_sets_basic_fields(self):
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        result = _make_result()
        update_screenshot_from_result(screenshot, result)

        assert screenshot.processing_status == ProcessingStatus.COMPLETED
        assert screenshot.extracted_title == "Instagram"
        assert screenshot.extracted_total == "2h 30m"
        assert screenshot.alignment_score == 0.95
        assert screenshot.processed_at is not None

    def test_sets_grid_coordinates(self):
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        result = _make_result()
        update_screenshot_from_result(screenshot, result)

        assert screenshot.grid_upper_left_x == 10
        assert screenshot.grid_upper_left_y == 20
        assert screenshot.grid_lower_right_x == 300
        assert screenshot.grid_lower_right_y == 400

    def test_sets_processing_method(self):
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        result = _make_result(processing_method="ocr_anchored")
        update_screenshot_from_result(screenshot, result)

        assert screenshot.processing_method == ProcessingMethod.OCR_ANCHORED

    def test_skipped_status_sets_annotation_skipped(self):
        screenshot = Screenshot(
            file_path="/test.png", image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
        )
        result = _make_result(processing_status="skipped")
        update_screenshot_from_result(screenshot, result)

        assert screenshot.annotation_status == AnnotationStatus.SKIPPED

    def test_truncates_long_title(self):
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        long_title = "A" * 600
        result = _make_result(extracted_title=long_title)
        update_screenshot_from_result(screenshot, result)

        assert len(screenshot.extracted_title) == 500

    def test_none_title_stays_none(self):
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        result = _make_result(extracted_title=None)
        update_screenshot_from_result(screenshot, result)

        assert screenshot.extracted_title is None

    def test_no_grid_coords(self):
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        result = _make_result(grid_coords=None)
        update_screenshot_from_result(screenshot, result)

        assert screenshot.grid_upper_left_x is None

    def test_no_processing_method(self):
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        result = _make_result(processing_method=None)
        update_screenshot_from_result(screenshot, result)

        assert screenshot.processing_method is None

    def test_blocking_issues(self):
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        result = _make_result(
            has_blocking_issues=True,
            issues=[{"type": "grid_not_found", "severity": "error"}],
        )
        update_screenshot_from_result(screenshot, result)

        assert screenshot.has_blocking_issues is True
        assert len(screenshot.processing_issues) == 1

    def test_hourly_data_stored(self):
        screenshot = Screenshot(file_path="/test.png", image_type="screen_time")
        data = {"0": 0, "6": 30, "12": 60, "18": 15}
        result = _make_result(extracted_hourly_data=data)
        update_screenshot_from_result(screenshot, result)

        assert screenshot.extracted_hourly_data == data


class TestProcessScreenshotAsync:
    """Tests for process_screenshot_async."""

    @pytest.mark.asyncio
    async def test_blocks_verified_user_reprocess(self, db_session: AsyncSession):
        user = User(username="proc_user", role="annotator", is_active=True)
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        screenshot = Screenshot(
            file_path="/test/proc.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
            verified_by_user_ids=[user.id],
        )
        db_session.add(screenshot)
        await db_session.commit()

        result = await process_screenshot_async(
            db_session, screenshot, current_user_id=user.id
        )
        assert result["success"] is False
        assert result["skipped"] is True
        assert result["skip_reason"] == "verified_by_user"

    @pytest.mark.asyncio
    async def test_allows_reprocess_without_verification(self, db_session: AsyncSession):
        """User who hasn't verified should be able to reprocess."""
        user = User(username="proc_user2", role="annotator", is_active=True)
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        screenshot = Screenshot(
            file_path="/test/proc2.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
            verified_by_user_ids=[999],  # Different user verified
        )
        db_session.add(screenshot)
        await db_session.commit()

        mock_result = _make_result()
        with patch(
            "screenshot_processor.web.services.processing_service.process_screenshot_file",
            return_value=mock_result,
        ):
            result = await process_screenshot_async(
                db_session, screenshot, current_user_id=user.id
            )
        assert result["processing_status"] == "completed"


class TestProcessScreenshotFile:
    """Tests for process_screenshot_file with mocked core processing."""

    @patch("screenshot_processor.web.services.processing_service.ScreenshotProcessingService")
    @patch("screenshot_processor.web.services.processing_service.get_settings")
    def test_manual_grid_coords(self, mock_settings, mock_sps_cls):
        settings = MagicMock()
        settings.USE_FRACTIONAL_HOURLY_VALUES = False
        mock_settings.return_value = settings

        mock_result = MagicMock()
        mock_result.to_dict.return_value = _make_result()
        mock_result.grid_bounds = True
        mock_sps_cls.return_value.process.return_value = mock_result

        coords = {"upper_left_x": 10, "upper_left_y": 20, "lower_right_x": 300, "lower_right_y": 400}
        result = process_screenshot_file("/test.png", "screen_time", grid_coords=coords)

        assert result["processing_status"] == "completed"
        # Manual coords should use MANUAL detection method
        call_kwargs = mock_sps_cls.return_value.process.call_args
        from screenshot_processor.core.interfaces import GridDetectionMethod
        assert call_kwargs.kwargs["detection_method"] == GridDetectionMethod.MANUAL

    @patch("screenshot_processor.web.services.processing_service.ScreenshotProcessingService")
    @patch("screenshot_processor.web.services.processing_service.get_settings")
    def test_specific_method_no_fallback(self, mock_settings, mock_sps_cls):
        settings = MagicMock()
        settings.USE_FRACTIONAL_HOURLY_VALUES = False
        mock_settings.return_value = settings

        mock_result = MagicMock()
        mock_result.to_dict.return_value = _make_result()
        mock_result.grid_bounds = None
        mock_result.processing_status = "completed"
        mock_sps_cls.return_value.process.return_value = mock_result

        process_screenshot_file("/test.png", "screen_time", processing_method="ocr_anchored")

        # Should only call process once (no fallback)
        assert mock_sps_cls.return_value.process.call_count == 1


class TestReprocessScreenshot:
    """Tests for reprocess_screenshot wrapper."""

    @pytest.mark.asyncio
    async def test_delegates_to_process_async(self, db_session: AsyncSession):
        screenshot = Screenshot(
            file_path="/test/reproc.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
        )
        db_session.add(screenshot)
        await db_session.commit()

        mock_result = _make_result()
        with patch(
            "screenshot_processor.web.services.processing_service.process_screenshot_file",
            return_value=mock_result,
        ):
            result = await reprocess_screenshot(db_session, screenshot)
        assert result["processing_status"] == "completed"
