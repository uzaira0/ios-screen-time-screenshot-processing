from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any


class ImageType(StrEnum):
    """Image type enum with lowercase underscore values for cross-platform compatibility"""

    BATTERY = "battery"
    SCREEN_TIME = "screen_time"


class LineExtractionMode(StrEnum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class PageType(StrEnum):
    DAILY_TOTAL = "daily_total"
    APP_USAGE = "app_usage"


class PageMarkerWord(StrEnum):
    WEEK = "WEEK"
    DAY = "DAY"
    MOST = "MOST"
    USED = "USED"
    CATEGORIES = "CATEGORIES"
    TODAY = "TODAY"
    SHOW = "SHOW"
    ENTERTAINMENT = "ENTERTAINMENT"
    EDUCATION = "EDUCATION"
    INFORMATION = "INFORMATION"
    READING = "READING"
    INFO = "INFO"
    DEVELOPER = "DEVELOPER"
    RATING = "RATING"
    LIMIT = "LIMIT"
    AGE = "AGE"
    DAILY = "DAILY"
    AVERAGE = "AVERAGE"


class Issue(ABC):
    def __init__(self, description: str) -> None:
        self.description = description

    def get_styled_message(self) -> tuple[str, str]:
        message = self.get_message()
        return (message, self.get_style())

    @abstractmethod
    def get_message(self) -> str: ...

    @abstractmethod
    def get_style(self) -> str: ...


class BlockingIssue(Issue):
    def get_style(self) -> str:
        return "background-color:rgb(255,0,0)"


class NonBlockingIssue(Issue):
    def get_style(self) -> str:
        return "background-color:rgb(255,179,179)"


class GraphDetectionIssue(BlockingIssue):
    def get_message(self) -> str:
        return "A graph detection issue occurred. To start reselecting, first click the upper left corner of the graph in the left image."


class TitleMissingIssue(NonBlockingIssue):
    def get_message(self) -> str:
        return (
            "A title issue occurred. Please enter the title correctly and click Next/Save when finished.\n"
            "If the title is for the daily view, please either skip or enter 'Daily Total'."
        )

    def get_style(self) -> str:
        return "background-color:rgb(255,165,0)"


class TotalIssue(Issue):
    def _get_continuation_message(self) -> str:
        return "Please reselect the graph to better approximate the total."

    def get_message(self) -> str:
        continuation_message = self._get_continuation_message()
        return f"A total time discrepancy issue occurred: {self.description}\n{continuation_message}"


class TotalNotFoundIssue(TotalIssue, NonBlockingIssue):
    def _get_continuation_message(self) -> str:
        return "You can proceed or reselect the graph for better accuracy."


class TotalParseErrorIssue(TotalIssue, NonBlockingIssue):
    def _get_continuation_message(self) -> str:
        return "You can proceed or reselect the graph for better accuracy."


class TotalUnderestimationSmallIssue(TotalIssue, NonBlockingIssue):
    def _get_continuation_message(self) -> str:
        return "You can proceed or reselect the graph for better accuracy."


class TotalUnderestimationLargeIssue(TotalIssue, BlockingIssue):
    def _get_continuation_message(self) -> str:
        return "WARNING: Significant underestimation detected. You may proceed after acknowledging this warning, but reselecting the graph is strongly recommended."


class TotalOverestimationSmallIssue(TotalIssue, NonBlockingIssue):
    def _get_continuation_message(self) -> str:
        return "You can proceed or reselect the graph for better accuracy."


class TotalOverestimationLargeIssue(TotalIssue, BlockingIssue):
    def _get_continuation_message(self) -> str:
        return "WARNING: Significant overestimation detected. You may proceed after acknowledging this warning, but reselecting the graph is strongly recommended."


class BaseRow(ABC):
    @classmethod
    @abstractmethod
    def headers(cls) -> list[str]: ...

    def __init__(self, full_path: Path | str, file_name: Path | str, rows: Sequence[float]) -> None:
        self.full_path = full_path
        self.file_name = file_name
        self.rows = rows

    def date_extracted_from_file_name(self) -> str:
        date_match = re.search(r"\d{1,2}[\.|-]\d{1,2}[\.|-]\d{2,4}", str(self.full_path))
        if date_match:
            return date_match.group(0)
        return ""

    @abstractmethod
    def subject_id_extracted_from_file_path(self) -> str: ...

    def get_common_row_fields(self) -> list[Any]:
        return [
            self.full_path,
            self.file_name,
            self.subject_id_extracted_from_file_path(),
            self.date_extracted_from_file_name(),
        ]

    @abstractmethod
    def get_specific_row_fields(self) -> list[Any]: ...

    def to_csv_row(self) -> list[Any]:
        return self.get_common_row_fields() + self.get_specific_row_fields() + list(self.rows)


class BatteryRow(BaseRow):
    @classmethod
    def headers(cls) -> list[str]:
        return (
            [
                "Full path",
                "File name",
                "ID",
                "Date from file name",
                "Date from image",
                "Time from image",
            ]
            + [str(i) for i in range(24)]
            + ["Total"]
        )

    def __init__(
        self,
        full_path: Path | str,
        file_name: Path | str,
        date_from_image: str,
        time_from_ui: str,
        rows: Sequence[float],
    ) -> None:
        super().__init__(full_path, file_name, rows)
        self.date_from_image = date_from_image
        self.time_from_ui = time_from_ui

    def subject_id_extracted_from_file_path(self) -> str:
        return Path(self.full_path).parent.name

    def get_specific_row_fields(self) -> list[Any]:
        return [
            self.date_from_image,
            self.time_from_ui,
        ]


class ScreenTimeRow(BaseRow):
    @classmethod
    def headers(cls) -> list[str]:
        return ["Full path", "Filename", "ID", "Date", "App Title"] + [str(i) for i in range(24)] + ["Total"]

    def __init__(
        self,
        full_path: Path | str,
        file_name: Path | str,
        app_title: str,
        rows: Sequence[float],
    ) -> None:
        super().__init__(full_path, file_name, rows)
        self.app_title = app_title

    def subject_id_extracted_from_file_path(self) -> str:
        path_parts = Path(self.full_path).parts
        if len(path_parts) > 3:
            return path_parts[-3]
        else:
            return ""

    def get_specific_row_fields(self) -> list[Any]:
        return [
            self.app_title,
        ]


class ProcessingResult:
    def __init__(
        self,
        image_path: str,
        success: bool,
        row_data: BaseRow | None = None,
        issues: list[Issue] | None = None,
        error: Exception | None = None,
        metadata: Any | None = None,  # ProcessingMetadata, using Any to avoid circular import
    ) -> None:
        self.image_path = image_path
        self.success = success
        self.row_data = row_data
        self.issues = issues or []
        self.error = error
        self.metadata = metadata


class FolderProcessingResults:
    def __init__(self) -> None:
        self.results: list[ProcessingResult] = []
        self.successful_count = 0
        self.failed_count = 0
        self.skipped_count = 0

    def add_result(self, result: ProcessingResult) -> None:
        self.results.append(result)
        if result.success:
            self.successful_count += 1
        else:
            self.failed_count += 1

    def add_skipped(self, image_path: str) -> None:
        self.skipped_count += 1

    @property
    def total_count(self) -> int:
        return self.successful_count + self.failed_count + self.skipped_count

    @property
    def has_issues(self) -> bool:
        return any(result.issues for result in self.results)

    def get_all_issues(self) -> list[tuple[str, Issue]]:
        all_issues: list[tuple[str, Issue]] = []
        for result in self.results:
            for issue in result.issues:
                all_issues.append((result.image_path, issue))
        return all_issues
