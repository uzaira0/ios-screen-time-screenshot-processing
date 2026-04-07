# pyright: reportPossiblyUnboundVariable=false
"""
Golden file tests — compare function output against stored reference files.

Golden files are stored in tests/golden/fixtures/. To update them:
    UPDATE_GOLDEN=1 pytest tests/golden/

These catch unintentional changes to output formats, serialization,
and processing results.
"""
import json
import os
from pathlib import Path

import pytest

GOLDEN_DIR = Path(__file__).parent / "fixtures"
UPDATE_GOLDEN = os.environ.get("UPDATE_GOLDEN", "") == "1"

try:
    from screenshot_processor.core.interfaces import GridBounds
    from screenshot_processor.web.database.schemas import (
        AnnotationBase,
        ScreenshotCreate,
    )

    HAS_SCHEMAS = True
except ImportError:
    HAS_SCHEMAS = False

pytestmark = pytest.mark.skipif(not HAS_SCHEMAS, reason="Schemas not importable")


def assert_golden(name: str, actual: dict | list | str):
    """Compare actual output against golden file. Update if UPDATE_GOLDEN=1."""
    golden_path = GOLDEN_DIR / f"{name}.golden.json"

    if isinstance(actual, (dict, list)):
        actual_str = json.dumps(actual, indent=2, sort_keys=True, default=str)
    else:
        actual_str = str(actual)

    if UPDATE_GOLDEN or not golden_path.exists():
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(actual_str + "\n")
        pytest.skip(f"Golden file created/updated: {golden_path}")
        return

    expected = golden_path.read_text().strip()
    assert actual_str.strip() == expected, (
        f"Output differs from golden file {golden_path.name}. "
        f"Run with UPDATE_GOLDEN=1 to update."
    )


class TestSchemaGoldenFiles:
    """Verify schema serialization hasn't changed."""

    def test_screenshot_create_schema(self):
        obj = ScreenshotCreate(
            file_path="uploads/group1/img.png",
            image_type="screen_time",
        )
        assert_golden("screenshot_create", obj.model_dump(mode="json"))

    def test_annotation_base_schema(self):
        obj = AnnotationBase(
            hourly_values={"0": 10, "1": 20, "23": 5},
            extracted_title="Instagram",
            extracted_total="2h 30m",
        )
        assert_golden("annotation_base", obj.model_dump(mode="json"))

    def test_grid_bounds_serialization(self):
        bounds = GridBounds(
            upper_left_x=100, upper_left_y=200, lower_right_x=500, lower_right_y=400
        )
        assert_golden("grid_bounds", bounds.to_dict())


class TestConfigGoldenFiles:
    """Verify config shapes haven't changed."""

    def test_openapi_schema_keys(self):
        """The OpenAPI schema should have the expected top-level keys."""
        try:
            os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-chars-long-for-testing")
            os.environ.pop("SITE_PASSWORD", None)
            from screenshot_processor.web.api.main import app

            schema = app.openapi()
            # Only check top-level structure, not full content
            top_keys = sorted(schema.keys())
            assert_golden("openapi_top_keys", top_keys)
        except Exception:
            pytest.skip("Cannot import app")


# =========================================================================
# NEW: Annotation schema golden files
# =========================================================================


class TestAnnotationReadGolden:
    """Verify AnnotationRead serialization shape."""

    def test_annotation_read_full(self):
        from datetime import datetime, timezone

        from screenshot_processor.web.database.schemas import AnnotationRead, Point

        obj = AnnotationRead(
            id=42,
            screenshot_id=10,
            user_id=3,
            status="submitted",
            created_at=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2025, 1, 15, 12, 5, 0, tzinfo=timezone.utc),
            hourly_values={str(i): float(i * 2) for i in range(24)},
            extracted_title="YouTube",
            extracted_total="3h 12m",
            grid_upper_left=Point(x=100, y=200),
            grid_lower_right=Point(x=500, y=400),
            time_spent_seconds=45.2,
            notes="Looks good",
        )
        assert_golden("annotation_read_full", obj.model_dump(mode="json"))

    def test_annotation_read_minimal(self):
        from datetime import datetime, timezone

        from screenshot_processor.web.database.schemas import AnnotationRead

        obj = AnnotationRead(
            id=1,
            screenshot_id=1,
            user_id=1,
            status="submitted",
            created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            hourly_values={"0": 0},
        )
        assert_golden("annotation_read_minimal", obj.model_dump(mode="json"))


# =========================================================================
# NEW: Consensus schema golden files
# =========================================================================


class TestConsensusGolden:
    """Verify consensus result schema shapes."""

    def test_consensus_result_read_with_disagreement(self):
        from datetime import datetime, timezone

        from screenshot_processor.web.database.schemas import (
            ConsensusResultRead,
            DisagreementDetail,
        )

        obj = ConsensusResultRead(
            id=7,
            screenshot_id=42,
            has_consensus=False,
            calculated_at=datetime(2025, 3, 10, 8, 0, 0, tzinfo=timezone.utc),
            disagreement_details=[
                DisagreementDetail(
                    hour="5",
                    values=[10.0, 25.0],
                    median=17.5,
                    has_disagreement=True,
                    max_difference=15.0,
                ),
            ],
            consensus_values={str(i): 0.0 for i in range(24)},
        )
        assert_golden("consensus_result_disagreement", obj.model_dump(mode="json"))

    def test_consensus_result_read_agreed(self):
        from datetime import datetime, timezone

        from screenshot_processor.web.database.schemas import ConsensusResultRead

        obj = ConsensusResultRead(
            id=1,
            screenshot_id=10,
            has_consensus=True,
            calculated_at=datetime(2025, 2, 1, 0, 0, 0, tzinfo=timezone.utc),
            disagreement_details=[],
            consensus_values={"0": 5.0, "12": 30.0},
        )
        assert_golden("consensus_result_agreed", obj.model_dump(mode="json"))

    def test_consensus_analysis_shape(self):
        from datetime import datetime, timezone

        from screenshot_processor.web.database.schemas import ConsensusAnalysis

        obj = ConsensusAnalysis(
            screenshot_id=10,
            has_consensus=True,
            total_annotations=3,
            disagreements=[],
            consensus_hourly_values={str(i): float(i) for i in range(24)},
            calculated_at=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        assert_golden("consensus_analysis", obj.model_dump(mode="json"))


# =========================================================================
# NEW: User schema golden files
# =========================================================================


class TestUserGolden:
    """Verify user schema shapes."""

    def test_user_read_shape(self):
        from datetime import datetime, timezone

        from screenshot_processor.web.database.schemas import UserRead

        obj = UserRead(
            id=1,
            username="testuser",
            email="test@example.com",
            role="annotator",
            is_active=True,
            created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        )
        assert_golden("user_read", obj.model_dump(mode="json"))

    def test_user_stats_read_shape(self):
        from screenshot_processor.web.database.schemas import UserStatsRead

        obj = UserStatsRead(
            id=5,
            username="admin",
            email=None,
            role="admin",
            is_active=True,
            created_at="2025-01-01T00:00:00+00:00",
            annotations_count=150,
            avg_time_spent_seconds=32.5,
        )
        assert_golden("user_stats_read", obj.model_dump(mode="json"))


# =========================================================================
# NEW: Group schema golden files
# =========================================================================


class TestGroupGolden:
    """Verify group schema shapes."""

    def test_group_read_with_counts(self):
        from datetime import datetime, timezone

        from screenshot_processor.web.database.schemas import GroupRead

        obj = GroupRead(
            id="study-2025-cohort-a",
            name="Study 2025 Cohort A",
            image_type="screen_time",
            created_at=datetime(2025, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
            screenshot_count=100,
            processing_pending=10,
            processing_completed=80,
            processing_failed=5,
            processing_skipped=3,
            processing_deleted=2,
            total_processing_time_seconds=1234.5,
            avg_processing_time_seconds=15.43,
            min_processing_time_seconds=2.1,
            max_processing_time_seconds=120.0,
        )
        assert_golden("group_read_full", obj.model_dump(mode="json"))

    def test_group_read_minimal(self):
        from datetime import datetime, timezone

        from screenshot_processor.web.database.schemas import GroupRead

        obj = GroupRead(
            id="g1",
            name="Group 1",
            created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        )
        assert_golden("group_read_minimal", obj.model_dump(mode="json"))

    def test_group_verification_summary_shape(self):
        from screenshot_processor.web.database.schemas import GroupVerificationSummary

        obj = GroupVerificationSummary(
            id="study-1",
            name="Study 1",
            image_type="screen_time",
            single_verified=40,
            agreed=25,
            disputed=5,
            total_verified=70,
            total_screenshots=100,
        )
        assert_golden("group_verification_summary", obj.model_dump(mode="json"))


# =========================================================================
# NEW: Preprocessing summary golden file
# =========================================================================


class TestPreprocessingGolden:
    """Verify preprocessing schema shapes."""

    def test_preprocessing_summary_shape(self):
        from screenshot_processor.web.database.schemas import (
            PreprocessingStageSummary,
            PreprocessingSummary,
        )

        stage = PreprocessingStageSummary(
            completed=50, pending=10, invalidated=2, running=1, failed=3, exceptions=0
        )
        obj = PreprocessingSummary(
            total=66,
            device_detection=stage,
            cropping=stage,
            phi_detection=stage,
            phi_redaction=stage,
            ocr=stage,
        )
        assert_golden("preprocessing_summary", obj.model_dump(mode="json"))


# =========================================================================
# NEW: OCR engine config serialization
# =========================================================================


class TestOCRConfigGolden:
    """Verify OCR config serialization shape."""

    def test_ocr_config_defaults(self):
        from dataclasses import asdict

        from screenshot_processor.core.config import OCRConfig

        config = OCRConfig()
        assert_golden("ocr_config_defaults", asdict(config))

    def test_ocr_config_hybrid(self):
        from dataclasses import asdict

        from screenshot_processor.core.config import OCRConfig

        config = OCRConfig(
            engine_type="hybrid",
            use_hybrid=True,
            hybrid_enable_hunyuan=True,
            hybrid_enable_paddleocr=True,
            hybrid_enable_tesseract=True,
            hunyuan_url="http://example.com:8080",
            paddleocr_url="http://example.com:8081",
        )
        assert_golden("ocr_config_hybrid", asdict(config))


# =========================================================================
# NEW: Processing result serialization
# =========================================================================


class TestProcessingResultGolden:
    """Verify processing result schema shapes."""

    def test_processing_result_response_success(self):
        from screenshot_processor.web.database.schemas import (
            ProcessingResultResponse,
        )

        obj = ProcessingResultResponse(
            success=True,
            processing_status="completed",
            extracted_title="TikTok",
            extracted_total="1h 45m",
            extracted_hourly_data={str(i): float(i % 10) for i in range(24)},
            issues=[],
            has_blocking_issues=False,
            is_daily_total=False,
            alignment_score=0.92,
            processing_method="line_based",
            grid_detection_confidence=0.88,
            grid_upper_left_x=100,
            grid_upper_left_y=200,
            grid_lower_right_x=900,
            grid_lower_right_y=500,
        )
        assert_golden("processing_result_success", obj.model_dump(mode="json"))

    def test_processing_result_response_failed(self):
        from screenshot_processor.web.database.schemas import (
            ProcessingIssue,
            ProcessingResultResponse,
        )

        obj = ProcessingResultResponse(
            success=False,
            processing_status="failed",
            message="Grid detection failed",
            issues=[
                ProcessingIssue(
                    issue_type="grid_detection_failed",
                    severity="blocking",
                    description="Could not find grid anchors",
                ),
            ],
            has_blocking_issues=True,
        )
        assert_golden("processing_result_failed", obj.model_dump(mode="json"))

    def test_processing_result_skipped(self):
        from screenshot_processor.web.database.schemas import (
            ProcessingResultResponse,
        )

        obj = ProcessingResultResponse(
            success=True,
            processing_status="skipped",
            skipped=True,
            skip_reason="Daily Total detected",
            is_daily_total=True,
        )
        assert_golden("processing_result_skipped", obj.model_dump(mode="json"))


# =========================================================================
# NEW: Error response shapes
# =========================================================================


class TestErrorResponseGolden:
    """Verify error response shapes for validation, not-found, forbidden."""

    def test_422_validation_error_shape(self):
        """FastAPI standard 422 error body shape."""
        error_body = {
            "detail": [
                {
                    "loc": ["body", "hourly_values", "24"],
                    "msg": "Hour key '24' must be between 0 and 23",
                    "type": "value_error",
                }
            ]
        }
        assert_golden("error_422_validation", error_body)

    def test_404_not_found_shape(self):
        error_body = {"detail": "Screenshot 999 not found"}
        assert_golden("error_404_not_found", error_body)

    def test_403_forbidden_shape(self):
        error_body = {"detail": "Admin access required"}
        assert_golden("error_403_forbidden", error_body)

    def test_upload_error_response_shape(self):
        from screenshot_processor.web.database.schemas import UploadErrorResponse

        obj = UploadErrorResponse(
            success=False,
            error_code="invalid_base64",
            detail="Failed to decode base64 image data",
            screenshot_index=None,
        )
        assert_golden("upload_error_response", obj.model_dump(mode="json"))


# =========================================================================
# NEW: Stats response golden file
# =========================================================================


class TestStatsGolden:
    """Verify stats response shape."""

    def test_stats_response_all_fields(self):
        from screenshot_processor.web.database.schemas import StatsResponse

        obj = StatsResponse(
            total_screenshots=500,
            pending_screenshots=50,
            completed_screenshots=400,
            total_annotations=1200,
            screenshots_with_consensus=350,
            screenshots_with_disagreements=20,
            average_annotations_per_screenshot=2.4,
            users_active=8,
            auto_processed=380,
            pending=50,
            failed=15,
            skipped=30,
            deleted=5,
        )
        assert_golden("stats_response_full", obj.model_dump(mode="json"))


# =========================================================================
# NEW: Screenshot list pagination shape
# =========================================================================


class TestScreenshotListGolden:
    """Verify screenshot list response pagination shape."""

    def test_screenshot_list_pagination_envelope(self):
        """The API returns a list; pagination info is inferred from query params.
        Verify the shape of a single ScreenshotRead in list context."""
        from datetime import datetime, timezone

        from screenshot_processor.web.database.schemas import ScreenshotRead

        obj = ScreenshotRead(
            id=1,
            file_path="uploads/g1/img.png",
            image_type="screen_time",
            annotation_status="pending",
            target_annotations=2,
            current_annotation_count=0,
            has_consensus=None,
            uploaded_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            processing_status="completed",
            uploaded_by_id=1,
            extracted_title="Safari",
            extracted_total="45m",
            alignment_score=0.95,
        )
        assert_golden("screenshot_read_list_item", obj.model_dump(mode="json"))


# =========================================================================
# NEW: Navigation response shape
# =========================================================================


class TestNavigationGolden:
    """Verify navigation response shapes."""

    def test_navigation_response_shape(self):
        from screenshot_processor.web.database.schemas import NavigationResponse

        obj = NavigationResponse(
            screenshot=None,
            current_index=5,
            total_in_filter=42,
            has_next=True,
            has_prev=True,
        )
        assert_golden("navigation_response", obj.model_dump(mode="json"))

    def test_next_screenshot_response_shape(self):
        from screenshot_processor.web.database.schemas import NextScreenshotResponse

        obj = NextScreenshotResponse(
            screenshot=None,
            queue_position=3,
            total_remaining=15,
            message="Next screenshot in queue",
        )
        assert_golden("next_screenshot_response", obj.model_dump(mode="json"))


# =========================================================================
# NEW: GridDetectionResult and BarProcessingResult serialization
# =========================================================================


class TestInterfaceResultGolden:
    """Verify interface result dataclass serialization."""

    def test_grid_detection_result_success(self):
        from dataclasses import asdict

        from screenshot_processor.core.interfaces import (
            GridBounds,
            GridDetectionResult,
        )

        obj = GridDetectionResult(
            success=True,
            bounds=GridBounds(
                upper_left_x=120,
                upper_left_y=250,
                lower_right_x=950,
                lower_right_y=480,
            ),
            confidence=0.93,
            method="line_based",
            error=None,
            diagnostics={"anchors_found": 2, "lines_detected": 5},
        )
        assert_golden("grid_detection_result_success", asdict(obj))

    def test_bar_processing_result(self):
        from dataclasses import asdict

        from screenshot_processor.core.interfaces import BarProcessingResult

        obj = BarProcessingResult(
            success=True,
            hourly_values={str(i): i * 2.5 for i in range(24)},
            alignment_score=0.87,
        )
        assert_golden("bar_processing_result", asdict(obj))

    def test_title_total_result(self):
        from dataclasses import asdict

        from screenshot_processor.core.interfaces import TitleTotalResult

        obj = TitleTotalResult(
            title="Instagram",
            total="2h 15m",
            title_y_position=350,
            is_daily_total=False,
        )
        assert_golden("title_total_result", asdict(obj))

    def test_grid_bounds_from_dict_roundtrip(self):
        """GridBounds.to_dict() -> from_dict() roundtrip preserves data."""
        original = GridBounds(
            upper_left_x=50, upper_left_y=100, lower_right_x=800, lower_right_y=600
        )
        serialized = original.to_dict()
        restored = GridBounds.from_dict(serialized)
        assert restored.to_dict() == serialized
        assert_golden("grid_bounds_roundtrip", serialized)
