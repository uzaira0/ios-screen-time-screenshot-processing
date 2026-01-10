# pyright: reportPossiblyUnboundVariable=false
"""Snapshot tests for API schemas, OCR output patterns, config shapes, and error responses.

These tests verify that serialized schema shapes and processing outputs remain
stable over time. They use inline expected dictionaries rather than external
snapshot files, making regressions immediately visible in diffs.
"""

from __future__ import annotations

import datetime
import json

import pytest

# ---------------------------------------------------------------------------
# Guard imports so the suite degrades gracefully when optional deps are missing
# ---------------------------------------------------------------------------
try:
    from pydantic import ValidationError

    from screenshot_processor.web.database.schemas import (
        AnnotationCreate,
        AnnotationRead,
        AnnotationUpsert,
        AnnotationWithIssues,
        ApplyPHIRedactionRequest,
        ApplyPHIRedactionResponse,
        BatchItemResult,
        BatchPreprocessResponse,
        BatchUploadResponse,
        BrowserUploadResponse,
        ConsensusAnalysis,
        ConsensusResultRead,
        DeleteGroupResponse,
        DisagreementDetail,
        FieldDifference,
        GroupRead,
        GroupVerificationSummary,
        HealthCheckResponse,
        ManualCropRequest,
        ManualCropResponse,
        ManualPHIRegionsRequest,
        ManualPHIRegionsResponse,
        NavigationResponse,
        NextScreenshotResponse,
        PasswordRequiredResponse,
        PHIRegionRect,
        PHIRegionsResponse,
        Point,
        PreprocessingDetailsResponse,
        PreprocessingEvent,
        PreprocessingEventLog,
        PreprocessingStageSummary,
        PreprocessingSummary,
        ProcessingIssue,
        ProcessingIssueCreate,
        ProcessingIssueRead,
        ProcessingResultResponse,
        RecalculateOcrResponse,
        RecalculateOcrTotalResponse,
        ReprocessRequest,
        ResetTestDataResponse,
        ResolveDisputeRequest,
        ResolveDisputeResponse,
        RootResponse,
        ScreenshotComparison,
        ScreenshotDetail,
        ScreenshotRead,
        ScreenshotTierItem,
        ScreenshotUploadResponse,
        StagePreprocessResponse,
        StatsResponse,
        Token,
        TokenData,
        UploadErrorCode,
        UploadErrorResponse,
        UserRead,
        UserStatsRead,
        UserUpdateResponse,
        VerificationTier,
        VerifierAnnotation,
    )

    HAS_SCHEMAS = True
except ImportError:
    HAS_SCHEMAS = False

try:
    from screenshot_processor.web.database.models import (
        AnnotationStatus as AnnotationStatusEnum,
        OCREngineType,
        ProcessingMethod as ProcessingMethodEnum,
        ProcessingStatus as ProcessingStatusEnum,
        QueueStateStatus as QueueStateStatusEnum,
        SubmissionStatus as SubmissionStatusEnum,
        UserRole as UserRoleEnum,
    )

    HAS_ENUMS = True
except ImportError:
    HAS_ENUMS = False

try:
    from screenshot_processor.web.database.schemas import (
        IssueSeverity,
        IssueType,
    )

    HAS_SCHEMA_ENUMS = True
except ImportError:
    HAS_SCHEMA_ENUMS = False

try:
    from screenshot_processor.core.ocr import (
        _extract_time_from_text,
        _normalize_ocr_digits,
        is_daily_total_page,
    )

    HAS_OCR = True
except ImportError:
    HAS_OCR = False

try:
    from screenshot_processor.core.config import (
        ImageProcessingConfig,
        OCRConfig,
    )

    HAS_CONFIG = True
except ImportError:
    HAS_CONFIG = False

try:
    from screenshot_processor.core.models import (
        ImageType,
        LineExtractionMode,
        PageMarkerWord,
        PageType,
    )

    HAS_CORE_MODELS = True
except ImportError:
    HAS_CORE_MODELS = False

try:
    from screenshot_processor.web.websocket.manager import WebSocketEvent

    HAS_WS = True
except ImportError:
    HAS_WS = False

# ============================================================================
# 1. API Schema Serialization Snapshots
# ============================================================================

_NOW = datetime.datetime(2025, 6, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestScreenshotReadSnapshot:
    """ScreenshotRead serialization must match a known shape."""

    def _make_screenshot(self, **overrides) -> ScreenshotRead:
        defaults = dict(
            id=42,
            file_path="uploads/group1/img_001.png",
            image_type="screen_time",
            annotation_status="pending",
            target_annotations=2,
            current_annotation_count=0,
            has_consensus=None,
            uploaded_at=_NOW,
            processing_status="pending",
            uploaded_by_id=1,
        )
        defaults.update(overrides)
        return ScreenshotRead(**defaults)

    def test_minimal_screenshot_read_shape(self):
        """A minimal ScreenshotRead must contain all required keys."""
        obj = self._make_screenshot()
        data = json.loads(obj.model_dump_json())

        expected_keys = {
            "id",
            "file_path",
            "image_type",
            "annotation_status",
            "target_annotations",
            "current_annotation_count",
            "has_consensus",
            "uploaded_at",
            "processing_status",
            "extracted_title",
            "extracted_total",
            "extracted_hourly_data",
            "processing_time_seconds",
            "alignment_score",
            "alignment_score_status",
            "processing_method",
            "grid_detection_confidence",
            "processing_issues",
            "has_blocking_issues",
            "title_y_position",
            "grid_upper_left_x",
            "grid_upper_left_y",
            "grid_lower_right_x",
            "grid_lower_right_y",
            "participant_id",
            "group_id",
            "source_id",
            "device_type",
            "original_filepath",
            "screenshot_date",
            "verified_by_user_ids",
            "verified_by_usernames",
            "resolved_hourly_data",
            "resolved_title",
            "resolved_total",
            "resolved_at",
            "resolved_by_user_id",
            "potential_duplicate_of",
            "processing_metadata",
            "content_hash",
            "processed_at",
            "uploaded_by_id",
        }
        assert expected_keys.issubset(set(data.keys())), (
            f"Missing keys: {expected_keys - set(data.keys())}"
        )

    def test_screenshot_read_default_values(self):
        """Default nullable fields must serialize to None / expected defaults."""
        obj = self._make_screenshot()
        data = obj.model_dump()

        assert data["extracted_title"] is None
        assert data["extracted_total"] is None
        assert data["extracted_hourly_data"] is None
        assert data["has_blocking_issues"] is False
        assert data["alignment_score"] is None
        assert data["processing_method"] is None

    def test_screenshot_read_with_grid_coords(self):
        """Grid coordinate fields serialize as flat integers."""
        obj = self._make_screenshot(
            grid_upper_left_x=100,
            grid_upper_left_y=200,
            grid_lower_right_x=500,
            grid_lower_right_y=400,
        )
        data = obj.model_dump()

        assert data["grid_upper_left_x"] == 100
        assert data["grid_upper_left_y"] == 200
        assert data["grid_lower_right_x"] == 500
        assert data["grid_lower_right_y"] == 400

    def test_alignment_score_status_computed_field(self):
        """alignment_score_status computed field returns expected structure."""
        good = self._make_screenshot(alignment_score=0.92)
        assert good.alignment_score_status == {
            "status": "good",
            "description": "Excellent alignment - grid boundaries match well with the bar graph.",
            "action": None,
        }

        warning = self._make_screenshot(alignment_score=0.55)
        assert warning.alignment_score_status["status"] == "warning"

        poor = self._make_screenshot(alignment_score=0.3)
        assert poor.alignment_score_status["status"] == "poor"

        none_score = self._make_screenshot(alignment_score=None)
        assert none_score.alignment_score_status is None

    def test_alignment_score_acceptable_status(self):
        """Alignment score between 0.7 and 0.85 gives acceptable status."""
        obj = self._make_screenshot(alignment_score=0.75)
        status = obj.alignment_score_status
        assert status["status"] == "acceptable"
        assert status["action"] is not None

    def test_screenshot_read_with_all_optional_fields(self):
        """ScreenshotRead with all optional fields populated serializes correctly."""
        obj = self._make_screenshot(
            extracted_title="Safari",
            extracted_total="2h 30m",
            extracted_hourly_data={str(i): i * 2 for i in range(24)},
            processing_method="line_based",
            grid_detection_confidence=0.95,
            alignment_score=0.88,
            participant_id="P001",
            group_id="study1",
            source_id="src1",
            device_type="iPhone",
            screenshot_date="2025-06-15",
            content_hash="abc123",
            processing_metadata={"stage": "completed"},
        )
        data = obj.model_dump()
        assert data["extracted_title"] == "Safari"
        assert data["extracted_total"] == "2h 30m"
        assert len(data["extracted_hourly_data"]) == 24
        assert data["processing_method"] == "line_based"
        assert data["participant_id"] == "P001"

    def test_screenshot_detail_extends_read(self):
        """ScreenshotDetail extends ScreenshotRead with extra fields."""
        obj = ScreenshotDetail(
            id=1,
            file_path="test.png",
            image_type="screen_time",
            annotation_status="pending",
            target_annotations=2,
            current_annotation_count=0,
            has_consensus=None,
            uploaded_at=_NOW,
            processing_status="pending",
            uploaded_by_id=1,
            annotations_count=3,
            needs_annotations=1,
        )
        data = obj.model_dump()
        assert data["annotations_count"] == 3
        assert data["needs_annotations"] == 1
        # Should have all ScreenshotRead keys too
        assert "extracted_title" in data


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestAnnotationSchemaSnapshots:
    """Annotation schema serialization snapshots."""

    def test_annotation_create_shape(self):
        """AnnotationCreate accepts nested Point objects and hourly values."""
        obj = AnnotationCreate(
            screenshot_id=1,
            hourly_values={"0": 10, "1": 20, "23": 5},
            extracted_title="Safari",
            extracted_total="2h 30m",
            grid_upper_left=Point(x=100, y=200),
            grid_lower_right=Point(x=500, y=400),
        )
        data = obj.model_dump()

        assert data["screenshot_id"] == 1
        assert data["hourly_values"] == {"0": 10, "1": 20, "23": 5}
        assert data["grid_upper_left"] == {"x": 100, "y": 200}
        assert data["grid_lower_right"] == {"x": 500, "y": 400}
        assert data["extracted_title"] == "Safari"
        assert data["extracted_total"] == "2h 30m"

    def test_annotation_read_shape(self):
        """AnnotationRead includes DB metadata fields."""
        obj = AnnotationRead(
            id=7,
            screenshot_id=1,
            user_id=3,
            status="pending",
            hourly_values={str(i): 0 for i in range(24)},
            created_at=_NOW,
            updated_at=_NOW,
        )
        data = obj.model_dump()

        expected_keys = {
            "id", "screenshot_id", "user_id", "status",
            "hourly_values", "extracted_title", "extracted_total",
            "grid_upper_left", "grid_lower_right",
            "time_spent_seconds", "notes",
            "created_at", "updated_at",
        }
        assert expected_keys.issubset(set(data.keys()))
        assert data["status"] == "pending"
        assert len(data["hourly_values"]) == 24

    def test_annotation_upsert_shape(self):
        """AnnotationUpsert has same base fields as AnnotationCreate."""
        obj = AnnotationUpsert(
            screenshot_id=5,
            hourly_values={"0": 10},
        )
        data = obj.model_dump()
        assert data["screenshot_id"] == 5
        assert data["hourly_values"] == {"0": 10}
        assert data["extracted_title"] is None

    def test_annotation_with_issues_shape(self):
        """AnnotationWithIssues extends AnnotationRead with issues list."""
        obj = AnnotationWithIssues(
            id=1, screenshot_id=1, user_id=1, status="submitted",
            hourly_values={"0": 10}, created_at=_NOW, updated_at=_NOW,
            issues=[
                ProcessingIssueRead(
                    id=1, annotation_id=1, issue_type="alignment_warning",
                    severity="non_blocking", description="Slight misalignment",
                    created_at=_NOW,
                ),
            ],
        )
        data = obj.model_dump()
        assert len(data["issues"]) == 1
        assert data["issues"][0]["issue_type"] == "alignment_warning"

    def test_annotation_create_fractional_minutes(self):
        """Annotation hourly values can contain fractional minutes."""
        obj = AnnotationCreate(
            screenshot_id=1,
            hourly_values={"0": 10.5, "1": 20.3},
        )
        data = obj.model_dump()
        assert data["hourly_values"]["0"] == 10.5

    def test_annotation_create_with_notes(self):
        """AnnotationCreate can have notes and time_spent_seconds."""
        obj = AnnotationCreate(
            screenshot_id=1,
            hourly_values={"0": 10},
            notes="Difficult to read",
            time_spent_seconds=45.5,
        )
        data = obj.model_dump()
        assert data["notes"] == "Difficult to read"
        assert data["time_spent_seconds"] == 45.5


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestGroupReadSnapshot:
    """GroupRead serialization snapshot."""

    def test_group_read_shape(self):
        obj = GroupRead(
            id="study-2025",
            name="Study Group 2025",
            image_type="screen_time",
            created_at=_NOW,
            screenshot_count=50,
            processing_pending=10,
            processing_completed=35,
            processing_failed=3,
            processing_skipped=2,
        )
        data = obj.model_dump()

        expected = {
            "id": "study-2025",
            "name": "Study Group 2025",
            "image_type": "screen_time",
            "screenshot_count": 50,
            "processing_pending": 10,
            "processing_completed": 35,
            "processing_failed": 3,
            "processing_skipped": 2,
            "processing_deleted": 0,
            "total_processing_time_seconds": None,
            "avg_processing_time_seconds": None,
            "min_processing_time_seconds": None,
            "max_processing_time_seconds": None,
        }
        for key, val in expected.items():
            assert data[key] == val, f"Mismatch on {key}: {data[key]} != {val}"

    def test_group_read_with_processing_times(self):
        """GroupRead with processing time stats."""
        obj = GroupRead(
            id="g1", name="G1", image_type="screen_time", created_at=_NOW,
            screenshot_count=10, processing_completed=10,
            total_processing_time_seconds=120.5,
            avg_processing_time_seconds=12.05,
            min_processing_time_seconds=5.0,
            max_processing_time_seconds=25.0,
        )
        data = obj.model_dump()
        assert data["total_processing_time_seconds"] == 120.5
        assert data["avg_processing_time_seconds"] == 12.05


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestStatsResponseSnapshot:
    """StatsResponse serialization snapshot."""

    def test_stats_response_shape(self):
        obj = StatsResponse(
            total_screenshots=100,
            pending_screenshots=20,
            completed_screenshots=75,
            total_annotations=200,
            screenshots_with_consensus=60,
            screenshots_with_disagreements=5,
            average_annotations_per_screenshot=2.0,
            users_active=8,
            auto_processed=50,
            pending=20,
            failed=3,
            skipped=2,
            deleted=0,
        )
        data = obj.model_dump()

        expected = {
            "total_screenshots": 100,
            "pending_screenshots": 20,
            "completed_screenshots": 75,
            "total_annotations": 200,
            "screenshots_with_consensus": 60,
            "screenshots_with_disagreements": 5,
            "average_annotations_per_screenshot": 2.0,
            "users_active": 8,
            "auto_processed": 50,
            "pending": 20,
            "failed": 3,
            "skipped": 2,
            "deleted": 0,
        }
        assert data == expected


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestUserReadSnapshot:
    """UserRead serialization snapshot."""

    def test_user_read_shape(self):
        obj = UserRead(
            id=1, username="testuser", email="test@example.com",
            role="annotator", is_active=True, created_at=_NOW,
        )
        data = obj.model_dump()
        expected_keys = {"id", "username", "email", "role", "is_active", "created_at"}
        assert expected_keys.issubset(set(data.keys()))
        assert data["username"] == "testuser"
        assert data["role"] == "annotator"

    def test_user_read_admin_role(self):
        obj = UserRead(
            id=2, username="admin", role="admin", is_active=True, created_at=_NOW,
        )
        assert obj.role == "admin"

    def test_user_read_nullable_email(self):
        obj = UserRead(
            id=3, username="nomail", role="annotator", is_active=True, created_at=_NOW,
        )
        assert obj.email is None


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestUserStatsReadSnapshot:
    """UserStatsRead serialization snapshot."""

    def test_user_stats_read_shape(self):
        obj = UserStatsRead(
            id=1, username="annotator1", role="annotator", is_active=True,
            created_at="2025-01-01T00:00:00Z", annotations_count=50,
            avg_time_spent_seconds=23.5,
        )
        data = obj.model_dump()
        assert data["annotations_count"] == 50
        assert data["avg_time_spent_seconds"] == 23.5
        assert data["email"] is None


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestConsensusAnalysisSnapshot:
    """ConsensusAnalysis serialization snapshot."""

    def test_consensus_analysis_shape(self):
        obj = ConsensusAnalysis(
            screenshot_id=1, has_consensus=True, total_annotations=3,
            disagreements=[], consensus_hourly_values={"0": 10.0, "1": 15.0},
            calculated_at=_NOW,
        )
        data = obj.model_dump()
        assert data["screenshot_id"] == 1
        assert data["has_consensus"] is True
        assert data["total_annotations"] == 3
        assert data["disagreements"] == []
        assert data["consensus_hourly_values"]["0"] == 10.0

    def test_consensus_analysis_with_disagreements(self):
        detail = DisagreementDetail(
            hour="3", values=[10.0, 25.0], median=17.5,
            has_disagreement=True, max_difference=15.0,
        )
        obj = ConsensusAnalysis(
            screenshot_id=1, has_consensus=False, total_annotations=2,
            disagreements=[detail], calculated_at=_NOW,
        )
        data = obj.model_dump()
        assert len(data["disagreements"]) == 1
        assert data["disagreements"][0]["max_difference"] == 15.0

    def test_consensus_result_read_shape(self):
        obj = ConsensusResultRead(
            id=1, screenshot_id=1, has_consensus=True,
            disagreement_details=[], consensus_values={"0": 10.0},
            calculated_at=_NOW,
        )
        data = obj.model_dump()
        assert "id" in data
        assert "calculated_at" in data


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestPreprocessingSummarySnapshot:
    """PreprocessingSummary serialization snapshot."""

    def test_preprocessing_summary_shape(self):
        stage = PreprocessingStageSummary(completed=5, pending=3, invalidated=1)
        obj = PreprocessingSummary(
            total=10,
            device_detection=stage,
            cropping=PreprocessingStageSummary(completed=10),
            phi_detection=PreprocessingStageSummary(pending=10),
            phi_redaction=PreprocessingStageSummary(),
            ocr=PreprocessingStageSummary(failed=2, exceptions=1),
        )
        data = obj.model_dump()
        assert data["total"] == 10
        assert data["device_detection"]["completed"] == 5
        assert data["ocr"]["failed"] == 2
        assert data["ocr"]["exceptions"] == 1
        assert data["phi_redaction"]["completed"] == 0

    def test_preprocessing_stage_defaults(self):
        """All PreprocessingStageSummary defaults are zero."""
        stage = PreprocessingStageSummary()
        data = stage.model_dump()
        for key in ["completed", "pending", "invalidated", "running", "failed", "exceptions"]:
            assert data[key] == 0, f"{key} should default to 0"


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestGroupVerificationSummarySnapshot:
    """GroupVerificationSummary serialization snapshot."""

    def test_group_verification_summary_shape(self):
        obj = GroupVerificationSummary(
            id="study1", name="Study 1", image_type="screen_time",
            single_verified=10, agreed=5, disputed=2,
            total_verified=17, total_screenshots=50,
        )
        data = obj.model_dump()
        expected_keys = {
            "id", "name", "image_type", "single_verified", "agreed",
            "disputed", "total_verified", "total_screenshots",
        }
        assert expected_keys.issubset(set(data.keys()))
        assert data["single_verified"] == 10
        assert data["total_verified"] == 17

    def test_group_verification_summary_defaults(self):
        obj = GroupVerificationSummary(
            id="g1", name="G1", image_type="screen_time",
        )
        assert obj.single_verified == 0
        assert obj.agreed == 0
        assert obj.disputed == 0


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestNavigationAndQueueSnapshots:
    """Navigation and queue response snapshots."""

    def test_next_screenshot_response_shape(self):
        obj = NextScreenshotResponse(
            screenshot=None, queue_position=0, total_remaining=0,
            message="No screenshots available",
        )
        data = obj.model_dump()
        assert data["screenshot"] is None
        assert data["queue_position"] == 0
        assert data["message"] == "No screenshots available"

    def test_navigation_response_shape(self):
        obj = NavigationResponse(
            screenshot=None, current_index=0, total_in_filter=10,
            has_next=True, has_prev=False,
        )
        data = obj.model_dump()
        assert data["has_next"] is True
        assert data["has_prev"] is False
        assert data["total_in_filter"] == 10


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestUploadResponseSnapshots:
    """Upload response schema snapshots."""

    def test_screenshot_upload_response_shape(self):
        obj = ScreenshotUploadResponse(
            success=True, screenshot_id=42, group_created=True,
            message="Uploaded", file_path="uploads/test.png",
            file_size_bytes=1024, processing_queued=True,
        )
        data = obj.model_dump()
        assert data["success"] is True
        assert data["screenshot_id"] == 42
        assert data["group_created"] is True
        assert data["duplicate"] is False

    def test_batch_upload_response_shape(self):
        obj = BatchUploadResponse(
            success=True, total_count=3, successful_count=2,
            failed_count=1, duplicate_count=0, group_created=True,
            results=[
                BatchItemResult(index=0, success=True, screenshot_id=1),
                BatchItemResult(index=1, success=True, screenshot_id=2),
                BatchItemResult(index=2, success=False, error_code="invalid_base64", error_detail="Bad data"),
            ],
        )
        data = obj.model_dump()
        assert data["total_count"] == 3
        assert data["successful_count"] == 2
        assert len(data["results"]) == 3

    def test_upload_error_response_shape(self):
        obj = UploadErrorResponse(
            error_code="checksum_mismatch",
            detail="SHA256 does not match",
            screenshot_index=2,
        )
        data = obj.model_dump()
        assert data["success"] is False
        assert data["error_code"] == "checksum_mismatch"
        assert data["screenshot_index"] == 2


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestProcessingResultSnapshots:
    """Processing result response snapshots."""

    def test_processing_result_success_shape(self):
        obj = ProcessingResultResponse(
            success=True, processing_status="completed",
            extracted_title="Safari", extracted_total="2h 30m",
            extracted_hourly_data={str(i): i for i in range(24)},
            alignment_score=0.92, processing_method="line_based",
            grid_detection_confidence=0.95,
            grid_upper_left_x=100, grid_upper_left_y=200,
            grid_lower_right_x=500, grid_lower_right_y=400,
        )
        data = obj.model_dump()
        assert data["success"] is True
        assert data["is_daily_total"] is False
        assert data["skipped"] is False
        assert len(data["extracted_hourly_data"]) == 24

    def test_processing_result_skipped_shape(self):
        obj = ProcessingResultResponse(
            success=True, processing_status="completed",
            skipped=True, skip_reason="Already verified",
        )
        data = obj.model_dump()
        assert data["skipped"] is True
        assert data["skip_reason"] == "Already verified"

    def test_processing_result_daily_total(self):
        obj = ProcessingResultResponse(
            success=True, processing_status="skipped",
            is_daily_total=True, message="Daily Total page detected",
        )
        data = obj.model_dump()
        assert data["is_daily_total"] is True

    def test_reprocess_request_defaults(self):
        obj = ReprocessRequest()
        data = obj.model_dump()
        assert data["max_shift"] == 5
        assert data["processing_method"] is None


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestPHISchemaSnapshots:
    """PHI region and redaction schema snapshots."""

    def test_phi_region_rect_shape(self):
        obj = PHIRegionRect(x=10, y=20, w=100, h=50, label="NAME", source="auto", confidence=0.95)
        data = obj.model_dump()
        assert data["x"] == 10
        assert data["label"] == "NAME"
        assert data["source"] == "auto"

    def test_phi_region_rect_defaults(self):
        obj = PHIRegionRect(x=0, y=0, w=1, h=1)
        assert obj.label == "OTHER"
        assert obj.source == "manual"
        assert obj.confidence == 1.0
        assert obj.text == ""

    def test_manual_phi_regions_response_shape(self):
        obj = ManualPHIRegionsResponse(
            success=True, event_id=5, regions_count=3, message="Saved",
        )
        data = obj.model_dump()
        assert data["success"] is True
        assert data["regions_count"] == 3

    def test_apply_phi_redaction_response_shape(self):
        obj = ApplyPHIRedactionResponse(
            success=True, event_id=6, regions_redacted=2,
            output_file="redacted.png", message="Redacted",
        )
        data = obj.model_dump()
        assert data["regions_redacted"] == 2


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestDisputeResolutionSnapshots:
    """Dispute resolution schema snapshots."""

    def test_resolve_dispute_response_shape(self):
        obj = ResolveDisputeResponse(
            success=True, screenshot_id=1, message="Resolved",
            resolved_at=_NOW, resolved_by_user_id=5, resolved_by_username="admin",
        )
        data = obj.model_dump()
        assert data["success"] is True
        assert data["resolved_by_username"] == "admin"

    def test_screenshot_comparison_shape(self):
        obj = ScreenshotComparison(
            screenshot_id=1, file_path="test.png", group_id="g1",
            participant_id="P001", screenshot_date=None, tier="disputed",
            verifier_annotations=[
                VerifierAnnotation(
                    user_id=1, username="user1", hourly_values={"0": 10},
                    verified_at=_NOW,
                ),
            ],
            differences=[
                FieldDifference(field="hourly_0", values={"1": 10, "2": 15}),
            ],
        )
        data = obj.model_dump()
        assert data["tier"] == "disputed"
        assert len(data["differences"]) == 1

    def test_verification_tier_shape(self):
        obj = VerificationTier(tier="agreed", count=10, color="green")
        data = obj.model_dump()
        assert data["tier"] == "agreed"
        assert data["color"] == "green"

    def test_screenshot_tier_item_shape(self):
        obj = ScreenshotTierItem(
            id=1, file_path="test.png", participant_id="P001",
            screenshot_date=None, verifier_count=2, has_differences=False,
        )
        data = obj.model_dump()
        assert data["verifier_count"] == 2
        assert data["has_differences"] is False


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestAdminSchemaSnapshots:
    """Admin-specific schema snapshots."""

    def test_delete_group_response_shape(self):
        obj = DeleteGroupResponse(
            success=True, group_id="study1",
            screenshots_deleted=50, annotations_deleted=120,
            message="Group deleted",
        )
        data = obj.model_dump()
        assert data["screenshots_deleted"] == 50
        assert data["annotations_deleted"] == 120

    def test_reset_test_data_response_shape(self):
        obj = ResetTestDataResponse(success=True, message="Test data reset")
        data = obj.model_dump()
        assert data["success"] is True

    def test_user_update_response_shape(self):
        obj = UserUpdateResponse(
            id=1, username="user1", role="admin", is_active=True,
        )
        data = obj.model_dump()
        assert data["role"] == "admin"

    def test_recalculate_ocr_response_shape(self):
        obj = RecalculateOcrResponse(
            success=True, screenshot_id=1,
            extracted_total="3h 15m", message="Recalculated",
        )
        data = obj.model_dump()
        assert data["extracted_total"] == "3h 15m"


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestHealthAndRootSnapshots:
    """Health check and root response snapshots."""

    def test_root_response_shape(self):
        obj = RootResponse(
            message="Screenshot Annotation API",
            version="1.0.0", docs="/docs", redoc="/redoc",
        )
        data = obj.model_dump()
        assert set(data.keys()) == {"message", "version", "docs", "redoc"}

    def test_health_check_response_shape(self):
        obj = HealthCheckResponse(
            status="healthy",
            checks={"database": True, "redis": True, "storage": True},
        )
        data = obj.model_dump()
        assert data["status"] == "healthy"
        assert data["checks"]["database"] is True

    def test_token_shape(self):
        obj = Token(access_token="abc123", token_type="bearer")
        data = obj.model_dump()
        assert data["token_type"] == "bearer"

    def test_token_data_shape(self):
        obj = TokenData(username="user1", user_id=42)
        data = obj.model_dump()
        assert data["username"] == "user1"


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestPreprocessingEventSnapshots:
    """Preprocessing event log schema snapshots."""

    def test_preprocessing_event_shape(self):
        obj = PreprocessingEvent(
            event_id=1, stage="device_detection",
            timestamp="2025-06-15T12:00:00Z", source="auto",
            params={"method": "yolo"}, result={"device": "iPhone"},
        )
        data = obj.model_dump()
        assert data["stage"] == "device_detection"
        assert data["supersedes"] is None

    def test_preprocessing_event_log_shape(self):
        obj = PreprocessingEventLog(
            screenshot_id=1, base_file_path="uploads/test.png",
            stage_status={"device_detection": "completed", "cropping": "pending"},
            current_events={"device_detection": 1, "cropping": None},
            events=[],
        )
        data = obj.model_dump()
        assert data["stage_status"]["device_detection"] == "completed"

    def test_stage_preprocess_response_shape(self):
        obj = StagePreprocessResponse(
            queued_count=5, screenshot_ids=[1, 2, 3, 4, 5],
            stage="phi_detection", message="Queued",
        )
        data = obj.model_dump()
        assert data["queued_count"] == 5
        assert data["stage"] == "phi_detection"

    def test_preprocessing_details_response_shape(self):
        obj = PreprocessingDetailsResponse(
            has_preprocessing=True,
            device_detection={"device": "iPad"},
            cropping={"cropped": True},
        )
        data = obj.model_dump()
        assert data["has_preprocessing"] is True


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestManualCropSnapshots:
    """Manual crop schema snapshots."""

    def test_manual_crop_request_shape(self):
        obj = ManualCropRequest(left=10, top=20, right=500, bottom=800)
        data = obj.model_dump()
        assert data["left"] == 10
        assert data["right"] == 500

    def test_manual_crop_response_shape(self):
        obj = ManualCropResponse(
            success=True, event_id=3, output_file="cropped.png",
            width=490, height=780, message="Cropped",
        )
        data = obj.model_dump()
        assert data["width"] == 490


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestBrowserUploadSnapshots:
    """Browser upload schema snapshots."""

    def test_browser_upload_response_shape(self):
        obj = BrowserUploadResponse(
            total=3, successful=2, failed=1, results=[],
        )
        data = obj.model_dump()
        assert data["total"] == 3
        assert data["successful"] == 2

    def test_password_required_response_shape(self):
        obj = PasswordRequiredResponse(password_required=True)
        data = obj.model_dump()
        assert data["password_required"] is True


# ============================================================================
# 2. Enum Value Snapshots
# ============================================================================


@pytest.mark.skipif(not HAS_ENUMS, reason="Model enum imports unavailable")
class TestModelEnumSnapshots:
    """All enum classes should have their members verified."""

    def test_annotation_status_enum_values(self):
        expected = {"pending", "annotated", "verified", "skipped"}
        actual = {e.value for e in AnnotationStatusEnum}
        assert actual == expected

    def test_processing_status_enum_values(self):
        expected = {"pending", "processing", "completed", "failed", "skipped", "deleted"}
        actual = {e.value for e in ProcessingStatusEnum}
        assert actual == expected

    def test_processing_method_enum_values(self):
        expected = {"ocr_anchored", "line_based", "manual"}
        actual = {e.value for e in ProcessingMethodEnum}
        assert actual == expected

    def test_ocr_engine_type_enum_values(self):
        expected = {"tesseract", "paddleocr", "paddleocr_remote", "hunyuan", "hybrid"}
        actual = {e.value for e in OCREngineType}
        assert actual == expected

    def test_user_role_enum_values(self):
        expected = {"admin", "annotator"}
        actual = {e.value for e in UserRoleEnum}
        assert actual == expected

    def test_submission_status_enum_values(self):
        expected = {"submitted", "draft"}
        actual = {e.value for e in SubmissionStatusEnum}
        assert actual == expected

    def test_queue_state_status_enum_values(self):
        expected = {"pending", "skipped"}
        actual = {e.value for e in QueueStateStatusEnum}
        assert actual == expected


@pytest.mark.skipif(not HAS_SCHEMA_ENUMS, reason="Schema enum imports unavailable")
class TestSchemaEnumSnapshots:
    """Schema-level enums should have stable values."""

    def test_issue_severity_enum_values(self):
        expected = {"blocking", "non_blocking"}
        actual = {e.value for e in IssueSeverity}
        assert actual == expected

    def test_issue_type_enum_values(self):
        expected = {
            "grid_detection_failed", "ocr_extraction_failed",
            "alignment_warning", "confidence_low", "missing_data",
            "validation_error", "ProcessingError", "GridDetectionIssue",
        }
        actual = {e.value for e in IssueType}
        assert actual == expected

    def test_upload_error_code_enum_values(self):
        expected = {
            "invalid_api_key", "invalid_base64", "unsupported_format",
            "image_too_large", "checksum_mismatch", "invalid_callback_url",
            "batch_too_large", "rate_limited", "storage_error", "database_error",
        }
        actual = {e.value for e in UploadErrorCode}
        assert actual == expected


@pytest.mark.skipif(not HAS_CORE_MODELS, reason="Core model imports unavailable")
class TestCoreModelEnumSnapshots:
    """Core model enums from the processing layer."""

    def test_image_type_enum_values(self):
        expected = {"battery", "screen_time"}
        actual = {e.value for e in ImageType}
        assert actual == expected

    def test_line_extraction_mode_enum_values(self):
        expected = {"horizontal", "vertical"}
        actual = {e.value for e in LineExtractionMode}
        assert actual == expected

    def test_page_type_enum_values(self):
        expected = {"daily_total", "app_usage"}
        actual = {e.value for e in PageType}
        assert actual == expected

    def test_page_marker_word_enum_values(self):
        """All PageMarkerWord members should be stable."""
        expected = {
            "WEEK", "DAY", "MOST", "USED", "CATEGORIES", "TODAY", "SHOW",
            "ENTERTAINMENT", "EDUCATION", "INFORMATION", "READING",
            "INFO", "DEVELOPER", "RATING", "LIMIT", "AGE", "DAILY", "AVERAGE",
        }
        actual = {e.value for e in PageMarkerWord}
        assert actual == expected


# ============================================================================
# 3. WebSocket Event Payload Snapshots
# ============================================================================


@pytest.mark.skipif(not HAS_WS, reason="WebSocket imports unavailable")
class TestWebSocketEventSnapshots:
    """WebSocket event payload shapes."""

    def test_websocket_event_structure(self):
        """WebSocketEvent has type, timestamp, and data."""
        event = WebSocketEvent.create("test_event", {"key": "value"})
        data = event.model_dump()
        assert set(data.keys()) == {"type", "timestamp", "data"}
        assert data["type"] == "test_event"
        assert data["data"] == {"key": "value"}

    def test_user_joined_event_shape(self):
        event = WebSocketEvent.create("user_joined", {
            "user_id": 1, "username": "alice", "active_users": 3,
        })
        data = event.model_dump()
        assert data["type"] == "user_joined"
        assert data["data"]["username"] == "alice"
        assert data["data"]["active_users"] == 3

    def test_annotation_submitted_event_shape(self):
        event = WebSocketEvent.create("annotation_submitted", {
            "screenshot_id": 42, "user_id": 1, "username": "alice",
        })
        data = event.model_dump()
        assert data["type"] == "annotation_submitted"
        assert data["data"]["screenshot_id"] == 42

    def test_screenshot_completed_event_shape(self):
        event = WebSocketEvent.create("screenshot_completed", {
            "screenshot_id": 42, "annotation_count": 2, "has_consensus": True,
        })
        data = event.model_dump()
        assert data["type"] == "screenshot_completed"
        assert data["data"]["has_consensus"] is True

    def test_consensus_disputed_event_shape(self):
        event = WebSocketEvent.create("consensus_disputed", {
            "screenshot_id": 42, "disagreement_count": 3,
        })
        data = event.model_dump()
        assert data["type"] == "consensus_disputed"

    def test_event_timestamp_is_iso_format(self):
        event = WebSocketEvent.create("test", {})
        # Should parse as a valid ISO timestamp
        datetime.datetime.fromisoformat(event.timestamp)


# ============================================================================
# 4. Processing Pipeline Stage Names
# ============================================================================


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestProcessingPipelineSnapshots:
    """Processing pipeline stage names and ordering."""

    def test_preprocessing_summary_stage_names(self):
        """PreprocessingSummary contains exactly these stage names."""
        obj = PreprocessingSummary(
            total=0,
            device_detection=PreprocessingStageSummary(),
            cropping=PreprocessingStageSummary(),
            phi_detection=PreprocessingStageSummary(),
            phi_redaction=PreprocessingStageSummary(),
            ocr=PreprocessingStageSummary(),
        )
        data = obj.model_dump()
        expected_stages = {"device_detection", "cropping", "phi_detection", "phi_redaction", "ocr"}
        actual_stages = set(data.keys()) - {"total"}
        assert actual_stages == expected_stages

    def test_pipeline_stage_ordering(self):
        """Pipeline stages should run in a specific order."""
        expected_order = ["device_detection", "cropping", "phi_detection", "phi_redaction", "ocr"]
        # Verify by checking the model fields maintain declaration order
        obj = PreprocessingSummary(
            total=0,
            device_detection=PreprocessingStageSummary(),
            cropping=PreprocessingStageSummary(),
            phi_detection=PreprocessingStageSummary(),
            phi_redaction=PreprocessingStageSummary(),
            ocr=PreprocessingStageSummary(),
        )
        fields = [f for f in obj.model_fields if f != "total"]
        assert fields == expected_order


# ============================================================================
# 5. OCR Output Snapshots
# ============================================================================


@pytest.mark.skipif(not HAS_OCR, reason="OCR imports unavailable")
class TestTimeExtractionSnapshots:
    """Time string extraction must produce known outputs for known inputs."""

    @pytest.mark.parametrize(
        "input_text, expected",
        [
            ("4h 36m", "4h 36m"),
            ("4h36m", "4h 36m"),
            ("4h  36m", "4h 36m"),
            ("2h 30m remaining", "2h 30m"),
            ("12m 30s", "12m 30s"),
            ("45m", "45m"),
            ("3h", "3h"),
            ("15s", "15s"),
            ("no time here", ""),
            ("4h 36", "4h 36m"),  # Missing 'm' fallback
            # Additional patterns
            ("0h 5m", "0h 5m"),
            ("10h 0m", "10h 0m"),
            ("1h 1m", "1h 1m"),
            ("23h 59m", "23h 59m"),
            ("0m 0s", "0m 0s"),
            ("59m 59s", "59m 59s"),
            ("1m", "1m"),
            ("0s", "0s"),
            ("12h", "12h"),
            ("  3h 15m  ", "3h 15m"),
            ("Total: 2h 30m today", "2h 30m"),
            ("Screen Time 5h 10m", "5h 10m"),
            ("Usage: 45m (average)", "45m"),
            ("1h 0m", "1h 0m"),
            ("0h 0m", "0h 0m"),
            ("9h 9m", "9h 9m"),
            ("2h  05m", "2h 5m"),
            ("7m 3s", "7m 3s"),
            ("just text", ""),
            ("123", ""),
            ("h m s", ""),
        ],
    )
    def test_extract_time_patterns(self, input_text: str, expected: str):
        result = _extract_time_from_text(input_text)
        assert result == expected, f"Input '{input_text}' -> '{result}', expected '{expected}'"

    @pytest.mark.parametrize(
        "input_text, expected",
        [
            ("Im", "1m"),         # I -> 1
            ("Oh", "0h"),         # O -> 0
            ("Am", "4m"),         # A -> 4
            ("Sh", "5h"),         # S -> 5
            ("1O2m", "102m"),     # O between digits -> 0
            # Additional normalization patterns
            ("Bh", "8h"),         # B -> 8
            ("Gh", "6h"),         # G -> 6
            ("bh", "6h"),         # b -> 6
            ("Zh", "2h"),         # Z -> 2
            ("Th", "7h"),         # T -> 7
            ("gh", "9h"),         # g -> 9
            ("qh", "9h"),         # q -> 9
            ("lm", "1m"),         # l -> 1
            ("|m", "1m"),         # | -> 1
            ("1I2m", "112m"),     # I between digits -> 1
            ("S2m", "52m"),       # S before digit -> 5
        ],
    )
    def test_normalize_ocr_digits(self, input_text: str, expected: str):
        result = _normalize_ocr_digits(input_text)
        assert result == expected, f"Input '{input_text}' -> '{result}', expected '{expected}'"

    def test_combined_normalize_and_extract(self):
        """Normalization + extraction pipeline produces correct total."""
        # "Ih 3Om" should normalize to "1h 30m" and extract as "1h 30m"
        normalized = _normalize_ocr_digits("1h 3Om")
        result = _extract_time_from_text(normalized)
        assert result == "1h 30m"

    def test_combined_normalize_and_extract_complex(self):
        """Complex OCR misreadings normalize and extract correctly."""
        normalized = _normalize_ocr_digits("Sh I2m")
        result = _extract_time_from_text(normalized)
        assert result == "5h 12m"

    def test_extract_time_does_not_match_false_positives(self):
        """Strings that look like time but are not should not match."""
        assert _extract_time_from_text("he") == ""  # 'h' in word
        assert _extract_time_from_text("am") == ""  # 'am' is not a duration
        assert _extract_time_from_text("home") == ""

    def test_extract_preserves_zero_values(self):
        """Zero values in time strings are preserved."""
        assert _extract_time_from_text("0h 0m") == "0h 0m"
        assert _extract_time_from_text("0m") == "0m"
        assert _extract_time_from_text("0s") == "0s"


@pytest.mark.skipif(not HAS_OCR, reason="OCR imports unavailable")
class TestDailyPageDetectionSnapshot:
    """is_daily_total_page should correctly classify OCR dicts."""

    def _make_ocr_dict(self, words: list[str]) -> dict:
        return {
            "text": words,
            "level": [5] * len(words),
            "left": [0] * len(words),
            "top": [0] * len(words),
            "width": [10] * len(words),
            "height": [10] * len(words),
        }

    def test_daily_page_detected(self):
        """Words like WEEK, DAY, MOST, CATEGORIES mark a daily total page."""
        ocr_dict = self._make_ocr_dict([
            "WEEK", "DAY", "MOST", "USED", "CATEGORIES", "SHOW",
        ])
        assert is_daily_total_page(ocr_dict) is True

    def test_app_page_detected(self):
        """Words like INFO, DEVELOPER, LIMIT mark an app-specific page."""
        ocr_dict = self._make_ocr_dict([
            "INFO", "DEVELOPER", "RATING", "LIMIT", "AGE", "DAILY", "AVERAGE",
        ])
        assert is_daily_total_page(ocr_dict) is False

    def test_daily_page_with_today_keyword(self):
        ocr_dict = self._make_ocr_dict(["TODAY", "CATEGORIES", "ENTERTAINMENT", "SHOW"])
        assert is_daily_total_page(ocr_dict) is True

    def test_empty_ocr_dict_is_not_daily(self):
        ocr_dict = self._make_ocr_dict([])
        assert is_daily_total_page(ocr_dict) is False

    def test_ambiguous_text_defaults_to_not_daily(self):
        """When counts are equal, daily_count > app_count is False."""
        ocr_dict = self._make_ocr_dict(["WEEK", "INFO"])
        # 1 daily, 1 app -> daily_count NOT > app_count -> False
        assert is_daily_total_page(ocr_dict) is False


# ============================================================================
# 6. Config / Mode Detection Snapshots
# ============================================================================


@pytest.mark.skipif(not HAS_CONFIG, reason="Config imports unavailable")
class TestConfigShapeSnapshots:
    """Config dataclass shapes must remain stable."""

    def test_ocr_config_server_mode_shape(self):
        """Server mode: hybrid OCR with all engines enabled."""
        config = OCRConfig(
            engine_type="hybrid",
            use_hybrid=True,
            hybrid_enable_hunyuan=True,
            hybrid_enable_paddleocr=True,
            hybrid_enable_tesseract=True,
        )
        expected = {
            "engine_type": "hybrid",
            "use_hybrid": True,
            "hybrid_enable_hunyuan": True,
            "hybrid_enable_paddleocr": True,
            "hybrid_enable_tesseract": True,
            "psm_mode_default": "3",
            "psm_mode_data": "12",
            "hybrid_paddleocr_for_grid": False,
            "auto_select": True,
            "prefer_hunyuan": True,
        }
        for key, val in expected.items():
            assert getattr(config, key) == val, f"{key}: {getattr(config, key)} != {val}"

    def test_ocr_config_wasm_mode_shape(self):
        """WASM mode: tesseract-only, no hybrid."""
        config = OCRConfig(
            engine_type="tesseract",
            use_hybrid=False,
            hybrid_enable_hunyuan=False,
            hybrid_enable_paddleocr=False,
            hybrid_enable_tesseract=True,
        )
        assert config.engine_type == "tesseract"
        assert config.use_hybrid is False
        assert config.hybrid_enable_hunyuan is False
        assert config.hybrid_enable_paddleocr is False
        assert config.hybrid_enable_tesseract is True

    def test_image_processing_config_defaults(self):
        """ImageProcessingConfig defaults must stay stable."""
        config = ImageProcessingConfig()
        assert config.contrast == 2.0
        assert config.brightness == -220
        assert config.debug_enabled is False
        assert config.save_debug_images is True

    def test_ocr_config_default_engine_is_tesseract(self):
        """Default OCR engine type is tesseract."""
        config = OCRConfig()
        assert config.engine_type == "tesseract"

    def test_ocr_config_remote_urls_are_stable(self):
        """Remote service URLs should not silently change."""
        config = OCRConfig()
        assert "8080" in config.hunyuan_url
        assert "8081" in config.paddleocr_url


# ============================================================================
# 7. Error Response Snapshots
# ============================================================================


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestErrorResponseSnapshots:
    """Error response shapes from Pydantic validation."""

    def test_validation_error_shape(self):
        """Pydantic validation errors produce a stable structure."""
        with pytest.raises(ValidationError) as exc_info:
            AnnotationCreate(
                screenshot_id=1,
                hourly_values={"invalid_key": 10},  # not 0-23
            )

        errors = exc_info.value.errors()
        assert len(errors) >= 1

        first_error = errors[0]
        # Pydantic v2 error structure
        assert "type" in first_error
        assert "msg" in first_error
        assert "loc" in first_error

    def test_validation_error_negative_minutes(self):
        """Absurdly negative minute values produce a validation error."""
        with pytest.raises(ValidationError) as exc_info:
            AnnotationCreate(
                screenshot_id=1,
                hourly_values={"0": -100},
            )

        errors = exc_info.value.errors()
        assert any("out of bounds" in e["msg"].lower() for e in errors)

    def test_validation_error_grid_too_small(self):
        """Grid coordinates too close together produce a validation error."""
        with pytest.raises(ValidationError) as exc_info:
            AnnotationCreate(
                screenshot_id=1,
                hourly_values={"0": 0},
                grid_upper_left=Point(x=100, y=200),
                grid_lower_right=Point(x=105, y=205),  # Only 5px apart, minimum is 10
            )

        errors = exc_info.value.errors()
        assert any("too small" in e["msg"].lower() for e in errors)

    def test_processing_result_failure_shape(self):
        """Failed ProcessingResultResponse has expected shape."""
        result = ProcessingResultResponse(
            success=False,
            processing_status="failed",
            message="Grid detection failed",
            issues=[
                ProcessingIssue(
                    issue_type="grid_detection_failed",
                    severity="blocking",
                    description="Could not find 12AM anchor",
                ),
            ],
            has_blocking_issues=True,
        )
        data = result.model_dump()

        assert data["success"] is False
        assert data["processing_status"] == "failed"
        assert data["has_blocking_issues"] is True
        assert len(data["issues"]) == 1
        assert data["issues"][0]["issue_type"] == "grid_detection_failed"
        assert data["issues"][0]["severity"] == "blocking"
        assert data["extracted_hourly_data"] is None

    def test_validation_error_hour_key_out_of_range(self):
        """Hour key > 23 produces validation error."""
        with pytest.raises(ValidationError) as exc_info:
            AnnotationCreate(
                screenshot_id=1,
                hourly_values={"24": 10},
            )
        errors = exc_info.value.errors()
        assert len(errors) >= 1

    def test_validation_error_minutes_over_120(self):
        """Absurdly high minute values produce validation error."""
        with pytest.raises(ValidationError) as exc_info:
            AnnotationCreate(
                screenshot_id=1,
                hourly_values={"0": 999},
            )
        errors = exc_info.value.errors()
        assert any("out of bounds" in e["msg"].lower() for e in errors)

    def test_validation_error_grid_inverted(self):
        """Grid upper-left below lower-right produces validation error."""
        with pytest.raises(ValidationError) as exc_info:
            AnnotationCreate(
                screenshot_id=1,
                hourly_values={"0": 0},
                grid_upper_left=Point(x=500, y=200),
                grid_lower_right=Point(x=100, y=400),
            )
        errors = exc_info.value.errors()
        assert len(errors) >= 1

    def test_validation_error_negative_point(self):
        """Point with negative coordinates raises validation error."""
        with pytest.raises(ValidationError):
            Point(x=-1, y=0)

    def test_manual_crop_inverted_coords(self):
        """ManualCropRequest with right <= left raises error."""
        with pytest.raises(ValidationError):
            ManualCropRequest(left=100, top=0, right=50, bottom=200)

    def test_notes_max_length(self):
        """Notes longer than 2000 chars raise validation error."""
        with pytest.raises(ValidationError):
            AnnotationCreate(
                screenshot_id=1,
                hourly_values={"0": 0},
                notes="x" * 2001,
            )

    def test_username_too_short(self):
        """Username shorter than minimum raises validation error."""
        with pytest.raises(ValidationError):
            UserRead(id=1, username="ab", role="annotator", is_active=True, created_at=_NOW)


# ============================================================================
# 8. Grid Detection Result Shapes
# ============================================================================


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestGridDetectionResultSnapshots:
    """Grid detection results embedded in processing responses."""

    def test_full_grid_detection_result(self):
        """A complete processing result with grid detection data."""
        result = ProcessingResultResponse(
            success=True,
            processing_status="completed",
            extracted_title="Messages",
            extracted_total="1h 20m",
            extracted_hourly_data={str(i): 0 for i in range(24)},
            grid_upper_left_x=50,
            grid_upper_left_y=100,
            grid_lower_right_x=400,
            grid_lower_right_y=350,
            alignment_score=0.91,
            processing_method="ocr_anchored",
            grid_detection_confidence=0.88,
        )
        data = result.model_dump()
        assert data["grid_upper_left_x"] == 50
        assert data["grid_lower_right_y"] == 350
        assert data["processing_method"] == "ocr_anchored"

    def test_grid_detection_with_issues(self):
        """Processing result with non-blocking grid issues."""
        result = ProcessingResultResponse(
            success=True,
            processing_status="completed",
            issues=[
                ProcessingIssue(
                    issue_type="alignment_warning",
                    severity="non_blocking",
                    description="Grid slightly misaligned",
                ),
                ProcessingIssue(
                    issue_type="confidence_low",
                    severity="non_blocking",
                    description="Low confidence in 12AM anchor",
                ),
            ],
            has_blocking_issues=False,
        )
        data = result.model_dump()
        assert len(data["issues"]) == 2
        assert data["has_blocking_issues"] is False

    def test_processing_issue_create_shape(self):
        obj = ProcessingIssueCreate(
            issue_type="grid_detection_failed",
            severity="blocking",
            description="Cannot find anchors",
            annotation_id=1,
        )
        data = obj.model_dump()
        assert data["annotation_id"] == 1
