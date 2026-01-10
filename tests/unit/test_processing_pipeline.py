"""Unit tests for the processing pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from screenshot_processor.core.config import (
    OutputConfig,
    ProcessorConfig,
    ThresholdConfig,
)
from screenshot_processor.core.models import (
    BatteryRow,
    ImageType,
    ProcessingResult,
    ScreenTimeRow,
)
from screenshot_processor.core.processing_pipeline import ProcessingPipeline
from screenshot_processor.core.queue_models import (
    ProcessingMetadata,
    ProcessingMethod,
    ProcessingTag,
    ScreenshotQueue,
)


class TestProcessorConfig:
    """Tests for ProcessorConfig dataclass."""

    def test_default_config_creation(self):
        """Test creating config with defaults."""
        output = OutputConfig(output_dir=Path("./output"))
        config = ProcessorConfig(
            image_type=ImageType.SCREEN_TIME,
            output=output,
        )

        assert config.image_type == ImageType.SCREEN_TIME
        assert config.snap_to_grid is False
        assert config.skip_daily_usage is False
        assert config.auto_process is False

    def test_config_with_custom_thresholds(self):
        """Test creating config with custom thresholds."""
        output = OutputConfig(output_dir=Path("./output"))
        thresholds = ThresholdConfig(
            small_total_threshold=50,
            small_total_diff_threshold=10,
            large_total_percent_threshold=5,
        )
        config = ProcessorConfig(
            image_type=ImageType.SCREEN_TIME,
            output=output,
            thresholds=thresholds,
        )

        assert config.thresholds.small_total_threshold == 50
        assert config.thresholds.small_total_diff_threshold == 10

    def test_config_with_battery_type(self):
        """Test creating config for battery screenshots."""
        output = OutputConfig(output_dir=Path("./output"))
        config = ProcessorConfig(
            image_type=ImageType.BATTERY,
            output=output,
        )

        assert config.image_type == ImageType.BATTERY


class TestThresholdConfig:
    """Tests for ThresholdConfig dataclass."""

    def test_default_thresholds(self):
        """Test default threshold values."""
        thresholds = ThresholdConfig()

        assert thresholds.small_total_threshold == 30
        assert thresholds.small_total_diff_threshold == 5
        assert thresholds.large_total_percent_threshold == 3

    def test_custom_thresholds(self):
        """Test custom threshold values."""
        thresholds = ThresholdConfig(
            small_total_threshold=60,
            small_total_diff_threshold=10,
            large_total_percent_threshold=5,
        )

        assert thresholds.small_total_threshold == 60
        assert thresholds.small_total_diff_threshold == 10
        assert thresholds.large_total_percent_threshold == 5


class TestOutputConfig:
    """Tests for OutputConfig dataclass."""

    def test_output_config_with_path(self):
        """Test output config with Path object."""
        config = OutputConfig(output_dir=Path("./output"))

        assert isinstance(config.output_dir, Path)

    def test_output_config_with_string(self):
        """Test output config with string path (auto-converted)."""
        config = OutputConfig(output_dir="./output")

        assert isinstance(config.output_dir, Path)

    def test_default_csv_pattern(self):
        """Test default CSV filename pattern."""
        config = OutputConfig(output_dir=Path("./output"))

        assert config.csv_filename_pattern == "{folder_name} Arcascope Output.csv"


class TestProcessingMetadata:
    """Tests for ProcessingMetadata dataclass."""

    def test_metadata_with_tags(self):
        """Test creating metadata with tags."""
        metadata = ProcessingMetadata(
            method=ProcessingMethod.ANCHOR_DETECTION,
            tags=frozenset([ProcessingTag.TOTAL_DETECTED.value, ProcessingTag.EXACT_MATCH.value]),
        )

        assert ProcessingTag.TOTAL_DETECTED.value in metadata.tags
        assert ProcessingTag.EXACT_MATCH.value in metadata.tags

    def test_metadata_queue_auto_assignment_daily(self):
        """Test queue is auto-assigned for daily screenshots."""
        metadata = ProcessingMetadata(
            tags=frozenset([ProcessingTag.DAILY_SCREENSHOT.value]),
        )

        assert metadata.queue == ScreenshotQueue.DAILY

    def test_metadata_queue_auto_assignment_needs_review(self):
        """Test queue is auto-assigned for close match."""
        metadata = ProcessingMetadata(
            tags=frozenset([ProcessingTag.CLOSE_MATCH.value]),
        )

        assert metadata.queue == ScreenshotQueue.NEEDS_REVIEW_CLOSE

    def test_metadata_queue_auto_assignment_poor_match(self):
        """Test queue is auto-assigned for poor match."""
        metadata = ProcessingMetadata(
            tags=frozenset([ProcessingTag.POOR_MATCH.value]),
        )

        assert metadata.queue == ScreenshotQueue.NEEDS_REVIEW_POOR

    def test_metadata_queue_auto_assignment_failed_no_total(self):
        """Test queue is auto-assigned for no total detected."""
        metadata = ProcessingMetadata(
            tags=frozenset([ProcessingTag.TOTAL_NOT_FOUND.value]),
        )

        assert metadata.queue == ScreenshotQueue.FAILED_NO_TOTAL

    def test_metadata_queue_auto_assignment_extraction_failed(self):
        """Test queue is auto-assigned for extraction failure."""
        metadata = ProcessingMetadata(
            tags=frozenset([ProcessingTag.EXTRACTION_FAILED.value]),
        )

        assert metadata.queue == ScreenshotQueue.FAILED_EXTRACTION

    def test_metadata_mutually_exclusive_tags_raises(self):
        """Test that mutually exclusive tags raise error."""
        with pytest.raises(ValueError, match="mutually exclusive"):
            ProcessingMetadata(
                tags=frozenset([ProcessingTag.EXACT_MATCH.value, ProcessingTag.POOR_MATCH.value]),
            )

    def test_metadata_to_dict(self):
        """Test conversion to dictionary."""
        metadata = ProcessingMetadata(
            method=ProcessingMethod.ANCHOR_DETECTION,
            tags=frozenset([ProcessingTag.TOTAL_DETECTED.value]),
            ocr_total_minutes=45.0,
            extracted_total_minutes=44.0,
        )

        d = metadata.to_dict()

        assert d["method"] == "anchor_detection"
        assert ProcessingTag.TOTAL_DETECTED.value in d["tags"]
        assert d["ocr_total_minutes"] == 45.0
        assert d["extracted_total_minutes"] == 44.0

    def test_metadata_from_dict(self):
        """Test creation from dictionary."""
        d = {
            "method": "anchor_detection",
            "tags": [ProcessingTag.TOTAL_DETECTED.value],
            "queue": "needs_review_close_match",
            "ocr_total_minutes": 45.0,
        }

        metadata = ProcessingMetadata.from_dict(d)

        assert metadata.method == ProcessingMethod.ANCHOR_DETECTION
        assert ProcessingTag.TOTAL_DETECTED.value in metadata.tags
        assert metadata.ocr_total_minutes == 45.0

    def test_metadata_with_additional_tags(self):
        """Test adding tags creates new instance."""
        original = ProcessingMetadata(tags=frozenset([ProcessingTag.TOTAL_DETECTED.value]))

        updated = original.with_additional_tags(ProcessingTag.USER_VALIDATED)

        assert ProcessingTag.USER_VALIDATED.value in updated.tags
        assert ProcessingTag.TOTAL_DETECTED.value in updated.tags
        # Original unchanged
        assert ProcessingTag.USER_VALIDATED.value not in original.tags

    def test_metadata_with_validation(self):
        """Test adding validation timestamp."""
        original = ProcessingMetadata(tags=frozenset([ProcessingTag.TOTAL_DETECTED.value]))

        validated = original.with_validation()

        assert ProcessingTag.USER_VALIDATED.value in validated.tags
        assert validated.validated_at is not None

    def test_metadata_default_queue_is_unprocessed(self):
        """Test default queue is unprocessed."""
        metadata = ProcessingMetadata()

        assert metadata.queue == ScreenshotQueue.UNPROCESSED


class TestProcessingPipeline:
    """Tests for ProcessingPipeline class."""

    @pytest.fixture
    def pipeline_config(self) -> ProcessorConfig:
        """Create a test pipeline configuration."""
        output = OutputConfig(output_dir=Path("./output"))
        return ProcessorConfig(
            image_type=ImageType.SCREEN_TIME,
            output=output,
            thresholds=ThresholdConfig(
                small_total_diff_threshold=2,
                large_total_percent_threshold=10,
            ),
        )

    @pytest.fixture
    def pipeline(self, pipeline_config) -> ProcessingPipeline:
        """Create a test pipeline."""
        return ProcessingPipeline(pipeline_config)

    def test_pipeline_creation(self, pipeline_config):
        """Test pipeline can be created."""
        pipeline = ProcessingPipeline(pipeline_config)

        assert pipeline.config == pipeline_config

    def test_parse_time_to_minutes_hours_and_minutes(self, pipeline):
        """Test parsing 'Xh Ym' format."""
        assert pipeline._parse_time_to_minutes("4h 36m") == 276.0
        assert pipeline._parse_time_to_minutes("1h 30m") == 90.0

    def test_parse_time_to_minutes_minutes_only(self, pipeline):
        """Test parsing 'Xm' format."""
        assert pipeline._parse_time_to_minutes("45m") == 45.0
        assert pipeline._parse_time_to_minutes("5m") == 5.0

    def test_parse_time_to_minutes_hours_only(self, pipeline):
        """Test parsing 'Xh' format."""
        assert pipeline._parse_time_to_minutes("2h") == 120.0
        assert pipeline._parse_time_to_minutes("1h") == 60.0

    def test_parse_time_to_minutes_with_seconds(self, pipeline):
        """Test parsing time with seconds."""
        assert pipeline._parse_time_to_minutes("30s") == 0.5

    def test_parse_time_to_minutes_empty_returns_none(self, pipeline):
        """Test parsing empty string returns None."""
        assert pipeline._parse_time_to_minutes("") is None
        assert pipeline._parse_time_to_minutes("N/A") is None

    def test_parse_time_to_minutes_invalid_returns_none(self, pipeline):
        """Test parsing invalid string returns None."""
        assert pipeline._parse_time_to_minutes("invalid") is None
        assert pipeline._parse_time_to_minutes("no time here") is None

    @patch("screenshot_processor.core.processing_pipeline.cv2.imread")
    @patch("screenshot_processor.core.processing_pipeline.find_title_and_total")
    def test_process_daily_screenshot_detection(
        self,
        mock_find_all,
        mock_imread,
        pipeline,
    ):
        """Test that daily screenshots are detected and marked."""
        # Setup mocks
        mock_imread.return_value = np.ones((500, 400, 3), dtype=np.uint8) * 255
        mock_find_all.return_value = ("Daily Total", None, "", None)

        result = pipeline.process_single_image("/path/to/image.png")

        assert result.success is True
        assert result.metadata is not None
        assert ProcessingTag.DAILY_SCREENSHOT.value in result.metadata.tags

    @patch("screenshot_processor.core.processing_pipeline.cv2.imread")
    @patch("screenshot_processor.core.processing_pipeline.find_title_and_total")
    def test_process_no_total_detected(
        self,
        mock_find_all,
        mock_imread,
        pipeline,
    ):
        """Test handling when no total is detected."""
        mock_imread.return_value = np.ones((500, 400, 3), dtype=np.uint8) * 255
        mock_find_all.return_value = ("App Name", 100, "", None)  # No total detected

        result = pipeline.process_single_image("/path/to/image.png")

        assert result.success is False
        assert result.metadata is not None
        assert ProcessingTag.TOTAL_NOT_FOUND.value in result.metadata.tags
        assert ProcessingTag.NEEDS_MANUAL.value in result.metadata.tags

    @patch("screenshot_processor.core.processing_pipeline.cv2.imread")
    def test_process_image_load_failure(self, mock_imread, pipeline):
        """Test handling when image cannot be loaded."""
        mock_imread.return_value = None

        result = pipeline.process_single_image("/path/to/nonexistent.png")

        assert result.success is False
        assert result.metadata is not None
        assert ProcessingTag.EXTRACTION_FAILED.value in result.metadata.tags

    @patch("screenshot_processor.core.processing_pipeline.cv2.imread")
    @patch("screenshot_processor.core.processing_pipeline.find_title_and_total")
    @patch("screenshot_processor.core.processing_pipeline.process_image")
    def test_process_exact_match(
        self,
        mock_process_image,
        mock_find_all,
        mock_imread,
        pipeline,
    ):
        """Test handling exact match (OCR total == extracted total)."""
        mock_imread.return_value = np.ones((500, 400, 3), dtype=np.uint8) * 255
        mock_find_all.return_value = ("App Name", 100, "1h 0m", None)  # 60 minutes
        # process_image returns: (path, graph_path, row, title, total, total_img, coords)
        # Row with 24 values summing to 60
        row_data = [2.5] * 24 + [60.0]  # 24 * 2.5 = 60
        mock_process_image.return_value = (
            "/path/to/image.png",
            "/path/to/graph.png",
            row_data,
            "App Name",
            "1h 0m",
            None,
            {"upper_left_x": 50, "upper_left_y": 100, "lower_right_x": 450, "lower_right_y": 300},
        )

        result = pipeline.process_single_image("/path/to/image.png")

        assert result.success is True
        assert result.metadata is not None
        assert ProcessingTag.EXACT_MATCH.value in result.metadata.tags
        assert ProcessingTag.AUTO_PROCESSED.value in result.metadata.tags

    @patch("screenshot_processor.core.processing_pipeline.cv2.imread")
    @patch("screenshot_processor.core.processing_pipeline.find_title_and_total")
    @patch("screenshot_processor.core.processing_pipeline.process_image")
    def test_process_close_match(
        self,
        mock_process_image,
        mock_find_all,
        mock_imread,
        pipeline,
    ):
        """Test handling close match (small difference)."""
        mock_imread.return_value = np.ones((500, 400, 3), dtype=np.uint8) * 255
        mock_find_all.return_value = ("App Name", 100, "1h 0m", None)  # 60 minutes
        # Row with 24 values summing to 59 (1 minute difference = close match)
        row_data = [59.0 / 24] * 24 + [59.0]
        mock_process_image.return_value = (
            "/path/to/image.png",
            "/path/to/graph.png",
            row_data,
            "App Name",
            "1h 0m",
            None,
            None,
        )

        result = pipeline.process_single_image("/path/to/image.png")

        assert result.success is True
        assert result.metadata is not None
        # Note: 1 minute diff with 2 minute threshold = close match
        assert ProcessingTag.CLOSE_MATCH.value in result.metadata.tags
        assert ProcessingTag.NEEDS_VALIDATION.value in result.metadata.tags

    @patch("screenshot_processor.core.processing_pipeline.cv2.imread")
    @patch("screenshot_processor.core.processing_pipeline.find_title_and_total")
    @patch("screenshot_processor.core.processing_pipeline.process_image")
    def test_process_poor_match(
        self,
        mock_process_image,
        mock_find_all,
        mock_imread,
        pipeline,
    ):
        """Test handling poor match (large difference)."""
        mock_imread.return_value = np.ones((500, 400, 3), dtype=np.uint8) * 255
        mock_find_all.return_value = ("App Name", 100, "1h 0m", None)  # 60 minutes
        # Row with 24 values summing to 48 (12 minutes difference = 20% = poor match)
        row_data = [48.0 / 24] * 24 + [48.0]
        mock_process_image.return_value = (
            "/path/to/image.png",
            "/path/to/graph.png",
            row_data,
            "App Name",
            "1h 0m",
            None,
            None,
        )

        result = pipeline.process_single_image("/path/to/image.png")

        assert result.success is True
        assert result.metadata is not None
        assert ProcessingTag.POOR_MATCH.value in result.metadata.tags
        assert ProcessingTag.NEEDS_MANUAL.value in result.metadata.tags

    @patch("screenshot_processor.core.processing_pipeline.cv2.imread")
    @patch("screenshot_processor.core.processing_pipeline.find_title_and_total")
    @patch("screenshot_processor.core.processing_pipeline.process_image")
    def test_process_extraction_failure(
        self,
        mock_process_image,
        mock_find_all,
        mock_imread,
        pipeline,
    ):
        """Test handling extraction failure."""
        mock_imread.return_value = np.ones((500, 400, 3), dtype=np.uint8) * 255
        mock_find_all.return_value = ("App Name", 100, "1h 0m", None)
        mock_process_image.side_effect = ValueError("Could not find graph anchors")

        result = pipeline.process_single_image("/path/to/image.png")

        assert result.success is False
        assert result.metadata is not None
        assert ProcessingTag.EXTRACTION_FAILED.value in result.metadata.tags
        assert ProcessingTag.NEEDS_MANUAL.value in result.metadata.tags

    @patch("screenshot_processor.core.processing_pipeline.cv2.imread")
    @patch("screenshot_processor.core.processing_pipeline.find_title_and_total")
    @patch("screenshot_processor.core.processing_pipeline.process_image")
    def test_process_title_not_found(
        self,
        mock_process_image,
        mock_find_all,
        mock_imread,
        pipeline,
    ):
        """Test handling when title is not found."""
        mock_imread.return_value = np.ones((500, 400, 3), dtype=np.uint8) * 255
        mock_find_all.return_value = ("", None, "1h 0m", None)  # No title, has total
        row_data = [2.5] * 24 + [60.0]
        mock_process_image.return_value = (
            "/path/to/image.png",
            "/path/to/graph.png",
            row_data,
            "",  # Also no title from process_image
            "1h 0m",
            None,
            None,
        )

        result = pipeline.process_single_image("/path/to/image.png")

        assert result.success is True
        assert result.metadata is not None
        assert ProcessingTag.TITLE_NOT_FOUND.value in result.metadata.tags


class TestProcessingResult:
    """Tests for ProcessingResult class."""

    def test_successful_result(self):
        """Test creating successful result."""
        result = ProcessingResult(
            image_path="/path/to/image.png",
            success=True,
            row_data=None,
        )

        assert result.success is True
        assert result.image_path == "/path/to/image.png"
        assert result.error is None

    def test_failed_result_with_error(self):
        """Test creating failed result with error."""
        error = ValueError("Processing failed")
        result = ProcessingResult(
            image_path="/path/to/image.png",
            success=False,
            error=error,
        )

        assert result.success is False
        assert result.error == error

    def test_result_with_metadata(self):
        """Test creating result with metadata."""
        metadata = ProcessingMetadata(
            method=ProcessingMethod.ANCHOR_DETECTION,
            tags=frozenset([ProcessingTag.EXACT_MATCH.value]),
        )
        result = ProcessingResult(
            image_path="/path/to/image.png",
            success=True,
            metadata=metadata,
        )

        assert result.metadata == metadata

    def test_result_with_row_data(self):
        """Test creating result with row data."""
        row_data = ScreenTimeRow(
            full_path="/path/to/image.png",
            file_name="image.png",
            app_title="Test App",
            rows=[30.0] * 24 + [720.0],
        )
        result = ProcessingResult(
            image_path="/path/to/image.png",
            success=True,
            row_data=row_data,
        )

        assert result.row_data == row_data
        assert result.row_data.app_title == "Test App"


class TestRowDataModels:
    """Tests for row data models (ScreenTimeRow, BatteryRow)."""

    def test_screen_time_row_creation(self):
        """Test creating ScreenTimeRow."""
        row = ScreenTimeRow(
            full_path="/path/to/image.png",
            file_name="image.png",
            app_title="Instagram",
            rows=[30.0] * 24 + [720.0],
        )

        assert row.app_title == "Instagram"
        assert len(row.rows) == 25

    def test_battery_row_creation(self):
        """Test creating BatteryRow."""
        row = BatteryRow(
            full_path="/path/to/image.png",
            file_name="image.png",
            date_from_image="Jan 15",
            time_from_ui="Midnight",
            rows=[50.0] * 24 + [1200.0],
        )

        assert row.date_from_image == "Jan 15"
        assert row.time_from_ui == "Midnight"
        assert len(row.rows) == 25

    def test_screen_time_row_headers(self):
        """Test ScreenTimeRow headers."""
        headers = ScreenTimeRow.headers()

        assert "Full path" in headers
        assert "Filename" in headers
        assert "App Title" in headers
        assert "0" in headers  # First hour
        assert "23" in headers  # Last hour
        assert "Total" in headers

    def test_battery_row_headers(self):
        """Test BatteryRow headers."""
        headers = BatteryRow.headers()

        assert "Full path" in headers
        assert "File name" in headers
        assert "Date from image" in headers
        assert "Time from image" in headers
        assert "0" in headers
        assert "23" in headers
        assert "Total" in headers

    def test_screen_time_row_to_csv_row(self):
        """Test converting ScreenTimeRow to CSV row."""
        row = ScreenTimeRow(
            full_path="/path/to/subject1/image.png",
            file_name="image.png",
            app_title="Instagram",
            rows=[30.0] * 24 + [720.0],
        )

        csv_row = row.to_csv_row()

        assert csv_row[0] == "/path/to/subject1/image.png"  # Full path
        assert csv_row[1] == "image.png"  # File name
        assert "Instagram" in csv_row  # App title
        assert 30.0 in csv_row  # Hour value
        assert 720.0 in csv_row  # Total

    def test_date_extraction_from_filename(self):
        """Test date extraction from filename."""
        row = ScreenTimeRow(
            full_path="/path/to/01-15-2024_image.png",
            file_name="01-15-2024_image.png",
            app_title="Test",
            rows=[0.0] * 25,
        )

        date = row.date_extracted_from_file_name()

        assert date == "01-15-2024"


class TestProcessingTagEnum:
    """Tests for ProcessingTag enum."""

    def test_tag_values_are_strings(self):
        """Test that all tag values are strings."""
        for tag in ProcessingTag:
            assert isinstance(tag.value, str)

    def test_tag_uniqueness(self):
        """Test that all tag values are unique."""
        values = [tag.value for tag in ProcessingTag]
        assert len(values) == len(set(values))


class TestScreenshotQueueEnum:
    """Tests for ScreenshotQueue enum."""

    def test_queue_values_are_strings(self):
        """Test that all queue values are strings."""
        for queue in ScreenshotQueue:
            assert isinstance(queue.value, str)

    def test_queue_uniqueness(self):
        """Test that all queue values are unique."""
        values = [queue.value for queue in ScreenshotQueue]
        assert len(values) == len(set(values))


class TestProcessingMethodEnum:
    """Tests for ProcessingMethod enum."""

    def test_method_values(self):
        """Test processing method values."""
        assert ProcessingMethod.FIXED_GRID.value == "fixed_grid"
        assert ProcessingMethod.ANCHOR_DETECTION.value == "anchor_detection"
        assert ProcessingMethod.MANUAL.value == "manual"
