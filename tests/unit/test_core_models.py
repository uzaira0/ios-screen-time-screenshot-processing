"""Unit tests for core data models (models.py)."""

from __future__ import annotations

from pathlib import Path

from screenshot_processor.core.models import (
    BatteryRow,
    BlockingIssue,
    FolderProcessingResults,
    GraphDetectionIssue,
    ImageType,
    LineExtractionMode,
    NonBlockingIssue,
    PageMarkerWord,
    PageType,
    ProcessingResult,
    ScreenTimeRow,
    TitleMissingIssue,
    TotalNotFoundIssue,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class TestEnums:
    def test_image_type_values(self):
        assert ImageType.BATTERY == "battery"
        assert ImageType.SCREEN_TIME == "screen_time"

    def test_line_extraction_mode_values(self):
        assert LineExtractionMode.HORIZONTAL == "horizontal"
        assert LineExtractionMode.VERTICAL == "vertical"

    def test_page_type_values(self):
        assert PageType.DAILY_TOTAL == "daily_total"
        assert PageType.APP_USAGE == "app_usage"

    def test_page_marker_word_contains_expected(self):
        expected = {"WEEK", "DAY", "MOST", "USED", "CATEGORIES", "TODAY", "DAILY"}
        actual = {m.value for m in PageMarkerWord}
        assert expected.issubset(actual)


# ---------------------------------------------------------------------------
# ScreenTimeRow
# ---------------------------------------------------------------------------
class TestScreenTimeRow:
    def test_creation(self):
        row = ScreenTimeRow(
            full_path="/data/subj/session/img.png",
            file_name="img.png",
            app_title="Safari",
            rows=[1.0] * 24 + [24.0],
        )
        assert row.app_title == "Safari"
        assert len(row.rows) == 25

    def test_headers_has_24_hours_plus_total(self):
        headers = ScreenTimeRow.headers()
        assert "0" in headers
        assert "23" in headers
        assert "Total" in headers
        assert "App Title" in headers

    def test_subject_id_from_path(self):
        row = ScreenTimeRow(
            full_path="/root/subjects/P001/session1/img.png",
            file_name="img.png",
            app_title="App",
            rows=[0.0] * 25,
        )
        assert row.subject_id_extracted_from_file_path() == "P001"

    def test_subject_id_short_path(self):
        row = ScreenTimeRow(
            full_path="img.png",
            file_name="img.png",
            app_title="App",
            rows=[0.0] * 25,
        )
        assert row.subject_id_extracted_from_file_path() == ""

    def test_date_extracted_from_file_name(self):
        row = ScreenTimeRow(
            full_path="/data/01-15-2024_shot.png",
            file_name="01-15-2024_shot.png",
            app_title="App",
            rows=[0.0] * 25,
        )
        assert row.date_extracted_from_file_name() == "01-15-2024"

    def test_date_not_found_returns_empty(self):
        row = ScreenTimeRow(
            full_path="/data/image.png",
            file_name="image.png",
            app_title="App",
            rows=[0.0] * 25,
        )
        assert row.date_extracted_from_file_name() == ""

    def test_to_csv_row_length(self):
        rows_data = [2.0] * 24 + [48.0]
        row = ScreenTimeRow(
            full_path="/a/b/c/img.png",
            file_name="img.png",
            app_title="Chrome",
            rows=rows_data,
        )
        csv = row.to_csv_row()
        # full_path + file_name + subject_id + date + app_title + 25 values
        assert len(csv) == 5 + 25

    def test_get_specific_row_fields(self):
        row = ScreenTimeRow("/a", "a", "TikTok", [0.0] * 25)
        assert row.get_specific_row_fields() == ["TikTok"]


# ---------------------------------------------------------------------------
# BatteryRow
# ---------------------------------------------------------------------------
class TestBatteryRow:
    def test_creation(self):
        row = BatteryRow(
            full_path="/data/P001/img.png",
            file_name="img.png",
            date_from_image="Jan 15",
            time_from_ui="Midnight",
            rows=[50.0] * 24 + [1200.0],
        )
        assert row.date_from_image == "Jan 15"
        assert row.time_from_ui == "Midnight"

    def test_headers_has_date_and_time(self):
        headers = BatteryRow.headers()
        assert "Date from image" in headers
        assert "Time from image" in headers

    def test_subject_id_from_path(self):
        row = BatteryRow("/a/SUBJ01/img.png", "img.png", "Jan 1", "Noon", [0.0] * 25)
        assert row.subject_id_extracted_from_file_path() == "SUBJ01"

    def test_get_specific_row_fields(self):
        row = BatteryRow("/a", "a", "Feb 10", "3pm", [0.0] * 25)
        assert row.get_specific_row_fields() == ["Feb 10", "3pm"]


# ---------------------------------------------------------------------------
# ProcessingResult
# ---------------------------------------------------------------------------
class TestProcessingResult:
    def test_success_result(self):
        r = ProcessingResult(image_path="/img.png", success=True)
        assert r.success is True
        assert r.error is None
        assert r.issues == []

    def test_failure_result(self):
        err = ValueError("bad")
        r = ProcessingResult(image_path="/img.png", success=False, error=err)
        assert r.success is False
        assert r.error is err

    def test_with_issues(self):
        issue = GraphDetectionIssue("problem")
        r = ProcessingResult(image_path="/img.png", success=False, issues=[issue])
        assert len(r.issues) == 1

    def test_default_issues_empty_list(self):
        r = ProcessingResult(image_path="/img.png", success=True)
        assert r.issues == []


# ---------------------------------------------------------------------------
# FolderProcessingResults
# ---------------------------------------------------------------------------
class TestFolderProcessingResults:
    def test_initially_empty(self):
        fpr = FolderProcessingResults()
        assert fpr.total_count == 0
        assert fpr.successful_count == 0
        assert fpr.failed_count == 0
        assert fpr.skipped_count == 0

    def test_add_successful_result(self):
        fpr = FolderProcessingResults()
        fpr.add_result(ProcessingResult("/a.png", success=True))
        assert fpr.successful_count == 1
        assert fpr.failed_count == 0
        assert fpr.total_count == 1

    def test_add_failed_result(self):
        fpr = FolderProcessingResults()
        fpr.add_result(ProcessingResult("/a.png", success=False))
        assert fpr.failed_count == 1
        assert fpr.successful_count == 0
        assert fpr.total_count == 1

    def test_add_skipped(self):
        fpr = FolderProcessingResults()
        fpr.add_skipped("/a.png")
        assert fpr.skipped_count == 1
        assert fpr.total_count == 1

    def test_total_count_combined(self):
        fpr = FolderProcessingResults()
        fpr.add_result(ProcessingResult("/a.png", success=True))
        fpr.add_result(ProcessingResult("/b.png", success=False))
        fpr.add_skipped("/c.png")
        assert fpr.total_count == 3

    def test_has_issues(self):
        fpr = FolderProcessingResults()
        issue = GraphDetectionIssue("p")
        fpr.add_result(ProcessingResult("/a.png", success=False, issues=[issue]))
        assert fpr.has_issues is True

    def test_no_issues(self):
        fpr = FolderProcessingResults()
        fpr.add_result(ProcessingResult("/a.png", success=True))
        assert fpr.has_issues is False

    def test_get_all_issues(self):
        fpr = FolderProcessingResults()
        i1 = GraphDetectionIssue("p1")
        i2 = TitleMissingIssue("p2")
        fpr.add_result(ProcessingResult("/a.png", success=False, issues=[i1]))
        fpr.add_result(ProcessingResult("/b.png", success=False, issues=[i2]))
        all_issues = fpr.get_all_issues()
        assert len(all_issues) == 2
        paths = [path for path, _ in all_issues]
        assert "/a.png" in paths
        assert "/b.png" in paths


# ---------------------------------------------------------------------------
# Issue hierarchy
# ---------------------------------------------------------------------------
class TestIssueHierarchy:
    def test_blocking_issue_is_abstract(self):
        # BlockingIssue itself lacks get_message, so direct instantiation would fail
        # at usage time. GraphDetectionIssue is the concrete subclass.
        issue = GraphDetectionIssue("test")
        assert isinstance(issue, BlockingIssue)

    def test_non_blocking_style(self):
        issue = TitleMissingIssue("missing")
        assert "background-color" in issue.get_style()

    def test_blocking_style_is_red(self):
        issue = GraphDetectionIssue("fail")
        assert "255,0,0" in issue.get_style()

    def test_non_blocking_base_style_is_light_red(self):
        issue = TotalNotFoundIssue("no total")
        style = issue.get_style()
        assert "255,179,179" in style


# ---------------------------------------------------------------------------
# Custom exceptions (exceptions.py)
# ---------------------------------------------------------------------------
class TestExceptions:
    def test_screenshot_processor_error_is_exception(self):
        from screenshot_processor.core.exceptions import ScreenshotProcessorError
        assert issubclass(ScreenshotProcessorError, Exception)

    def test_image_processing_error_wraps_cause(self):
        from screenshot_processor.core.exceptions import ImageProcessingError
        cause = ValueError("bad pixel")
        err = ImageProcessingError("processing failed", errors=cause)
        assert str(err) == "processing failed"
        assert err.errors is cause

    def test_ocr_error_hierarchy(self):
        from screenshot_processor.core.exceptions import OCRError, ScreenshotProcessorError
        assert issubclass(OCRError, ScreenshotProcessorError)

    def test_grid_detection_error_hierarchy(self):
        from screenshot_processor.core.exceptions import GridDetectionError, ScreenshotProcessorError
        assert issubclass(GridDetectionError, ScreenshotProcessorError)

    def test_configuration_error_hierarchy(self):
        from screenshot_processor.core.exceptions import ConfigurationError, ScreenshotProcessorError
        assert issubclass(ConfigurationError, ScreenshotProcessorError)

    def test_validation_error_hierarchy(self):
        from screenshot_processor.core.exceptions import ValidationError, ScreenshotProcessorError
        assert issubclass(ValidationError, ScreenshotProcessorError)
