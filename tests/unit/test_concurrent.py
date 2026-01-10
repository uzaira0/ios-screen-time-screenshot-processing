"""Tests for concurrent request handling and race condition protection.

These tests verify that the codebase properly handles concurrent operations
using appropriate locking mechanisms (SELECT FOR UPDATE, unique constraints, etc).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from screenshot_processor.web.database.models import (
    Annotation,
    Screenshot,
    UserQueueState,
)


class TestScreenshotLocking:
    """Tests for screenshot row locking."""

    @pytest.mark.asyncio
    async def test_get_screenshot_for_update_uses_for_update(self):
        """get_screenshot_for_update should use SELECT FOR UPDATE via repository."""
        from screenshot_processor.web.api.dependencies import get_screenshot_for_update

        mock_screenshot = MagicMock(spec=Screenshot)
        mock_screenshot.id = 1

        mock_repo = AsyncMock()
        mock_repo.get_by_id_for_update.return_value = mock_screenshot

        result = await get_screenshot_for_update(mock_repo, 1)

        assert result == mock_screenshot
        mock_repo.get_by_id_for_update.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_get_screenshot_for_update_raises_404_when_not_found(self):
        """get_screenshot_for_update should raise 404 when screenshot doesn't exist."""
        from fastapi import HTTPException

        from screenshot_processor.web.api.dependencies import get_screenshot_for_update

        mock_repo = AsyncMock()
        mock_repo.get_by_id_for_update.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_screenshot_for_update(mock_repo, 999)

        assert exc_info.value.status_code == 404
        assert "Screenshot not found" in exc_info.value.detail


class TestUserQueueStateConstraints:
    """Tests for UserQueueState unique constraint handling."""

    def test_unique_constraint_exists_in_model(self):
        """UserQueueState should have unique constraint on (user_id, screenshot_id)."""
        table_args = UserQueueState.__table_args__
        # Find the UniqueConstraint
        from sqlalchemy import UniqueConstraint

        has_constraint = any(
            isinstance(arg, UniqueConstraint) and set(arg.columns.keys()) == {"user_id", "screenshot_id"}
            for arg in table_args
            if isinstance(arg, UniqueConstraint)
        )
        assert has_constraint, "UserQueueState should have unique constraint on (user_id, screenshot_id)"


class TestAnnotationConstraints:
    """Tests for Annotation unique constraint handling."""

    def test_unique_constraint_exists_in_model(self):
        """Annotation should have unique constraint on (screenshot_id, user_id)."""
        table_args = Annotation.__table_args__
        # Find the UniqueConstraint
        from sqlalchemy import UniqueConstraint

        has_constraint = any(
            isinstance(arg, UniqueConstraint) and set(arg.columns.keys()) == {"screenshot_id", "user_id"}
            for arg in table_args
            if isinstance(arg, UniqueConstraint)
        )
        assert has_constraint, "Annotation should have unique constraint on (screenshot_id, user_id)"


class TestBulkReprocessStatusCleanup:
    """Tests for bulk reprocess status cleanup to prevent memory leaks."""

    def test_cleanup_removes_old_completed_entries(self):
        """Cleanup should remove completed entries older than TTL."""
        import time

        from screenshot_processor.web.api.routes.admin import (
            BulkReprocessStatus,
            _BULK_REPROCESS_TTL_SECONDS,
            _bulk_reprocess_status,
            _cleanup_old_reprocess_status,
        )

        # Clear any existing status
        _bulk_reprocess_status.clear()

        # Add a completed entry with old timestamp
        old_timestamp = time.time() - _BULK_REPROCESS_TTL_SECONDS - 100
        _bulk_reprocess_status["test_old"] = BulkReprocessStatus(
            total=10,
            processed=10,
            succeeded=10,
            failed=0,
            in_progress=False,
            completed_at=old_timestamp,
        )

        # Add a completed entry with recent timestamp
        recent_timestamp = time.time() - 60  # 1 minute ago
        _bulk_reprocess_status["test_recent"] = BulkReprocessStatus(
            total=5,
            processed=5,
            succeeded=5,
            failed=0,
            in_progress=False,
            completed_at=recent_timestamp,
        )

        # Add an in-progress entry (should not be cleaned)
        _bulk_reprocess_status["test_in_progress"] = BulkReprocessStatus(
            total=20,
            processed=5,
            succeeded=5,
            failed=0,
            in_progress=True,
            completed_at=None,
        )

        # Run cleanup
        _cleanup_old_reprocess_status()

        # Verify old entry was removed
        assert "test_old" not in _bulk_reprocess_status

        # Verify recent entry was kept
        assert "test_recent" in _bulk_reprocess_status

        # Verify in-progress entry was kept
        assert "test_in_progress" in _bulk_reprocess_status

        # Clean up
        _bulk_reprocess_status.clear()

    def test_cleanup_does_not_remove_in_progress(self):
        """Cleanup should not remove entries that are still in progress."""

        from screenshot_processor.web.api.routes.admin import (
            BulkReprocessStatus,
            _bulk_reprocess_status,
            _cleanup_old_reprocess_status,
        )

        # Clear any existing status
        _bulk_reprocess_status.clear()

        # Add an in-progress entry with no completed_at
        _bulk_reprocess_status["test_running"] = BulkReprocessStatus(
            total=100,
            processed=50,
            succeeded=50,
            failed=0,
            in_progress=True,
            completed_at=None,
        )

        # Run cleanup
        _cleanup_old_reprocess_status()

        # Verify entry was kept
        assert "test_running" in _bulk_reprocess_status

        # Clean up
        _bulk_reprocess_status.clear()


class TestConcurrentAnnotationCreation:
    """Tests for concurrent annotation creation handling."""

    def test_annotation_model_has_screenshot_user_constraint(self):
        """Annotation model should prevent duplicate annotations per user per screenshot."""
        # The constraint prevents two annotations for same screenshot by same user
        table_args = Annotation.__table_args__
        from sqlalchemy import UniqueConstraint

        constraint_found = False
        for arg in table_args:
            if isinstance(arg, UniqueConstraint):
                if "screenshot_id" in arg.columns.keys() and "user_id" in arg.columns.keys():
                    constraint_found = True
                    break

        assert constraint_found, "Annotation should have unique constraint on (screenshot_id, user_id)"
