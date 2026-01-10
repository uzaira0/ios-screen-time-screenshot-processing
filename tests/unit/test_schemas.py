"""
Unit tests for Pydantic schemas.

Tests schema validation, field constraints, and validation errors.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from screenshot_processor.web.database.schemas import (
    AnnotationBase,
    AnnotationCreate,
    GroupCreate,
    ScreenshotCreate,
    ScreenshotUpdate,
    ScreenshotUploadRequest,
    UserCreate,
    UserUpdate,
)


class TestAnnotationSchemas:
    """Test annotation-related schemas."""

    def test_annotation_base_valid(self):
        """Test AnnotationBase with valid data."""
        data = {
            "hourly_values": {"0": 10, "1": 15, "2": 20},
            "extracted_title": "Screen Time",
            "extracted_total": "45m",
            "grid_upper_left": {"x": 100, "y": 100},
            "grid_lower_right": {"x": 500, "y": 500},
            "time_spent_seconds": 120.5,
            "notes": "Test annotation",
        }
        annotation = AnnotationBase(**data)
        assert annotation.hourly_values == {"0": 10, "1": 15, "2": 20}
        assert annotation.extracted_title == "Screen Time"
        assert annotation.time_spent_seconds == 120.5

    def test_annotation_base_minimal(self):
        """Test AnnotationBase with minimal required fields."""
        data = {"hourly_values": {"0": 10}}
        annotation = AnnotationBase(**data)
        assert annotation.hourly_values == {"0": 10}
        assert annotation.extracted_title is None
        assert annotation.grid_upper_left is None

    def test_annotation_create_valid(self):
        """Test AnnotationCreate with screenshot_id."""
        data = {
            "screenshot_id": 1,
            "hourly_values": {"0": 10},
        }
        annotation = AnnotationCreate(**data)
        assert annotation.screenshot_id == 1
        assert annotation.hourly_values == {"0": 10}

    def test_annotation_grid_validation_missing_x(self):
        """Test grid point validation fails when x is missing."""
        data = {
            "hourly_values": {"0": 10},
            "grid_upper_left": {"y": 100},  # Missing x
        }
        with pytest.raises(ValidationError) as exc_info:
            AnnotationBase(**data)
        # Pydantic 2.x uses "Field required" for missing required fields
        error_str = str(exc_info.value).lower()
        assert "field required" in error_str or "x" in error_str

    def test_annotation_grid_validation_negative_values(self):
        """Test grid point validation fails for negative coordinates."""
        data = {
            "hourly_values": {"0": 10},
            "grid_upper_left": {"x": -10, "y": 100},
        }
        with pytest.raises(ValidationError) as exc_info:
            AnnotationBase(**data)
        # Pydantic 2.x uses "greater than or equal to 0" for ge=0 constraint
        assert "greater than or equal to 0" in str(exc_info.value).lower()

    def test_annotation_time_spent_negative(self):
        """Test time_spent_seconds validation fails for negative values."""
        data = {
            "hourly_values": {"0": 10},
            "time_spent_seconds": -5.0,
        }
        with pytest.raises(ValidationError) as exc_info:
            AnnotationBase(**data)
        # Pydantic validation for ge=0
        assert "greater than or equal to 0" in str(exc_info.value).lower()

    def test_annotation_notes_max_length(self):
        """Test notes field respects max_length constraint."""
        long_notes = "a" * 2001
        data = {
            "hourly_values": {"0": 10},
            "notes": long_notes,
        }
        with pytest.raises(ValidationError) as exc_info:
            AnnotationBase(**data)
        assert "at most 2000 characters" in str(exc_info.value).lower()


class TestScreenshotSchemas:
    """Test screenshot-related schemas."""

    def test_screenshot_create_valid(self):
        """Test ScreenshotCreate with valid data."""
        data = {
            "file_path": "/uploads/test.png",
            "image_type": "screen_time",
            "target_annotations": 2,
        }
        screenshot = ScreenshotCreate(**data)
        assert screenshot.file_path == "/uploads/test.png"
        assert screenshot.image_type == "screen_time"
        assert screenshot.target_annotations == 2

    def test_screenshot_create_default_target(self):
        """Test ScreenshotCreate uses default target_annotations."""
        data = {
            "file_path": "/uploads/test.png",
            "image_type": "screen_time",
        }
        screenshot = ScreenshotCreate(**data)
        assert screenshot.target_annotations == 1

    def test_screenshot_create_target_annotations_minimum(self):
        """Test target_annotations must be >= 1."""
        data = {
            "file_path": "/uploads/test.png",
            "image_type": "screen_time",
            "target_annotations": 0,
        }
        with pytest.raises(ValidationError) as exc_info:
            ScreenshotCreate(**data)
        assert "greater than or equal to 1" in str(exc_info.value).lower()

    def test_screenshot_update_partial(self):
        """Test ScreenshotUpdate allows partial updates."""
        data = {"annotation_status": "annotated"}
        update = ScreenshotUpdate(**data)
        assert update.annotation_status == "annotated"
        assert update.extracted_title is None

    def test_screenshot_update_all_fields(self):
        """Test ScreenshotUpdate with all fields."""
        data = {
            "annotation_status": "verified",
            "target_annotations": 3,
            "extracted_title": "Battery",
        }
        update = ScreenshotUpdate(**data)
        assert update.annotation_status == "verified"
        assert update.target_annotations == 3
        assert update.extracted_title == "Battery"


class TestUserSchemas:
    """Test user-related schemas."""

    def test_user_create_valid(self):
        """Test UserCreate with valid username."""
        data = {"username": "testuser"}
        user = UserCreate(**data)
        assert user.username == "testuser"
        assert user.role == "annotator"  # Default role

    def test_user_create_custom_role(self):
        """Test UserCreate with custom role."""
        data = {"username": "adminuser", "role": "admin"}
        user = UserCreate(**data)
        assert user.role == "admin"

    def test_user_create_username_too_short(self):
        """Test UserCreate fails for username < 3 characters."""
        data = {"username": "ab"}
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(**data)
        assert "at least 3 characters" in str(exc_info.value).lower()

    def test_user_create_username_too_long(self):
        """Test UserCreate fails for username > 100 characters."""
        data = {"username": "a" * 101}
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(**data)
        assert "at most 100 characters" in str(exc_info.value).lower()

    def test_user_update_partial(self):
        """Test UserUpdate allows partial updates."""
        data = {"is_active": False}
        update = UserUpdate(**data)
        assert update.is_active is False
        assert update.role is None
        assert update.email is None

    def test_user_update_all_fields(self):
        """Test UserUpdate with all fields."""
        data = {
            "email": "test@example.com",
            "role": "admin",
            "is_active": True,
        }
        update = UserUpdate(**data)
        assert update.email == "test@example.com"
        assert update.role == "admin"
        assert update.is_active is True


class TestUploadSchemas:
    """Test API upload schemas."""

    def test_screenshot_upload_request_valid(self):
        """Test ScreenshotUploadRequest with valid data."""
        data = {
            "screenshot": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            "participant_id": "P001",
            "group_id": "study1",
            "image_type": "screen_time",
            "device_type": "iphone_modern",
            "source_id": "import_batch_1",
            "screenshot_date": date(2024, 1, 15),
        }
        upload = ScreenshotUploadRequest(**data)
        assert upload.participant_id == "P001"
        assert upload.group_id == "study1"
        assert upload.image_type == "screen_time"
        assert upload.device_type == "iphone_modern"

    def test_screenshot_upload_request_minimal(self):
        """Test ScreenshotUploadRequest with minimal required fields."""
        data = {
            "screenshot": "base64data",
            "participant_id": "P001",
            "group_id": "study1",
            "image_type": "screen_time",
        }
        upload = ScreenshotUploadRequest(**data)
        assert upload.participant_id == "P001"
        assert upload.device_type is None
        assert upload.source_id is None
        assert upload.filename is None

    def test_screenshot_upload_request_invalid_image_type(self):
        """Test ScreenshotUploadRequest fails for invalid image_type."""
        data = {
            "screenshot": "base64data",
            "participant_id": "P001",
            "group_id": "study1",
            "image_type": "invalid_type",
        }
        with pytest.raises(ValidationError) as exc_info:
            ScreenshotUploadRequest(**data)
        # Pydantic 2.x uses "literal_error" for Literal type validation
        error_str = str(exc_info.value).lower()
        assert "literal" in error_str or "battery" in error_str or "screen_time" in error_str

    def test_screenshot_upload_request_empty_participant_id(self):
        """Test ScreenshotUploadRequest fails for empty participant_id."""
        data = {
            "screenshot": "base64data",
            "participant_id": "",
            "group_id": "study1",
            "image_type": "screen_time",
        }
        with pytest.raises(ValidationError) as exc_info:
            ScreenshotUploadRequest(**data)
        assert "at least 1 character" in str(exc_info.value).lower()

    def test_screenshot_upload_request_empty_group_id(self):
        """Test ScreenshotUploadRequest fails for empty group_id."""
        data = {
            "screenshot": "base64data",
            "participant_id": "P001",
            "group_id": "",
            "image_type": "screen_time",
        }
        with pytest.raises(ValidationError) as exc_info:
            ScreenshotUploadRequest(**data)
        assert "at least 1 character" in str(exc_info.value).lower()


class TestGroupSchemas:
    """Test group-related schemas."""

    def test_group_create_valid(self):
        """Test GroupCreate with valid data."""
        data = {
            "id": "study1",
            "name": "Study 1 Participants",
            "image_type": "screen_time",
        }
        group = GroupCreate(**data)
        assert group.id == "study1"
        assert group.name == "Study 1 Participants"
        assert group.image_type == "screen_time"

    def test_group_create_default_image_type(self):
        """Test GroupCreate uses default image_type."""
        data = {
            "id": "study1",
            "name": "Study 1",
        }
        group = GroupCreate(**data)
        assert group.image_type == "screen_time"

    def test_group_create_invalid_image_type(self):
        """Test GroupCreate fails for invalid image_type."""
        data = {
            "id": "study1",
            "name": "Study 1",
            "image_type": "invalid",
        }
        with pytest.raises(ValidationError) as exc_info:
            GroupCreate(**data)
        # Pydantic 2.x uses "literal_error" for Literal type validation
        error_str = str(exc_info.value).lower()
        assert "literal" in error_str or "battery" in error_str or "screen_time" in error_str

    def test_group_create_empty_id(self):
        """Test GroupCreate fails for empty id."""
        data = {
            "id": "",
            "name": "Study 1",
        }
        with pytest.raises(ValidationError) as exc_info:
            GroupCreate(**data)
        assert "at least 1 character" in str(exc_info.value).lower()

    def test_group_create_id_too_long(self):
        """Test GroupCreate fails for id > 100 characters."""
        data = {
            "id": "a" * 101,
            "name": "Study 1",
        }
        with pytest.raises(ValidationError) as exc_info:
            GroupCreate(**data)
        assert "at most 100 characters" in str(exc_info.value).lower()


@pytest.mark.parametrize(
    "image_type,expected_valid",
    [
        ("screen_time", True),
        ("battery", True),
        ("invalid", False),
        ("SCREEN_TIME", False),  # Case sensitive
        ("", False),
    ],
)
def test_image_type_validation(image_type: str, expected_valid: bool):
    """Parametrized test for image_type validation across schemas."""
    data = {
        "screenshot": "base64data",
        "participant_id": "P001",
        "group_id": "study1",
        "image_type": image_type,
    }
    if expected_valid:
        upload = ScreenshotUploadRequest(**data)
        assert upload.image_type == image_type
    else:
        with pytest.raises(ValidationError):
            ScreenshotUploadRequest(**data)
