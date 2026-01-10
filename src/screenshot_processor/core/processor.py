from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

import cv2

from .callbacks import CancellationCheck, IssueCallback, LogCallback, ProgressCallback
from .config import ProcessorConfig
from .exceptions import ImageProcessingError
from .image_processor import process_image
from .image_utils import convert_dark_mode
from .issue_manager import IssueManager
from .models import (
    BatteryRow,
    FolderProcessingResults,
    ImageType,
    ProcessingResult,
    ScreenTimeRow,
    TitleMissingIssue,
    TotalNotFoundIssue,
    TotalOverestimationLargeIssue,
    TotalOverestimationSmallIssue,
    TotalParseErrorIssue,
    TotalUnderestimationLargeIssue,
    TotalUnderestimationSmallIssue,
)
from .ocr import find_screenshot_title, parse_time_to_minutes
from .ocr_factory import OCREngineFactory, OCREngineType
from .processing_pipeline import ProcessingPipeline

if TYPE_CHECKING:
    from .ocr_protocol import IOCREngine

logger = logging.getLogger(__name__)


class ScreenshotProcessor:
    """Screenshot processor with dependency injection for OCR engines.

    Supports swappable OCR backends via the IOCREngine protocol.
    If no OCR engine is provided, uses the best available engine (Tesseract preferred).
    """

    def __init__(
        self,
        config: ProcessorConfig,
        progress_callback: ProgressCallback | None = None,
        cancellation_check: CancellationCheck | None = None,
        issue_callback: IssueCallback | None = None,
        log_callback: LogCallback | None = None,
        ocr_engine: IOCREngine | None = None,
    ) -> None:
        """Initialize the screenshot processor.

        Args:
            config: Processor configuration
            progress_callback: Optional callback for progress updates
            cancellation_check: Optional callback to check if processing should be cancelled
            issue_callback: Optional callback for issue notifications
            log_callback: Optional callback for log messages
            ocr_engine: Optional OCR engine instance. If None, uses best available engine.
        """
        self.config = config
        self.progress_callback = progress_callback
        self.cancellation_check = cancellation_check
        self.issue_callback = issue_callback
        self.log_callback = log_callback

        # Initialize OCR engine (dependency injection)
        if ocr_engine is None:
            self.ocr_engine = self._create_ocr_engine_from_config()
            self._log("info", f"Using OCR engine: {self.ocr_engine.get_engine_name()}")
        else:
            self.ocr_engine = ocr_engine
            self._log("info", f"Using injected OCR engine: {self.ocr_engine.get_engine_name()}")

        # Initialize processing pipeline
        self.pipeline = ProcessingPipeline(config)

        self.issue_manager = IssueManager()
        if issue_callback:
            self.issue_manager.register_observer(issue_callback)

    def _create_ocr_engine_from_config(self) -> IOCREngine:
        """Create OCR engine based on config settings."""
        ocr_config = self.config.ocr

        if ocr_config.auto_select:
            # Auto-select best available engine
            return OCREngineFactory.create_best_available_engine(
                prefer_hunyuan=ocr_config.prefer_hunyuan,
                use_hybrid=ocr_config.use_hybrid,
                base_url=ocr_config.hunyuan_url,
                timeout=ocr_config.hunyuan_timeout,
                max_retries=ocr_config.hunyuan_max_retries,
                rate_limit=ocr_config.hunyuan_rate_limit,
                tesseract_cmd=ocr_config.tesseract_cmd,
                # Hybrid engine settings
                hunyuan_url=ocr_config.hunyuan_url,
                paddleocr_url=ocr_config.paddleocr_url,
                hunyuan_timeout=ocr_config.hunyuan_timeout,
                paddleocr_timeout=ocr_config.paddleocr_timeout,
                enable_hunyuan=ocr_config.hybrid_enable_hunyuan,
                enable_paddleocr=ocr_config.hybrid_enable_paddleocr,
                enable_tesseract=ocr_config.hybrid_enable_tesseract,
            )
        else:
            # Use explicitly specified engine type
            engine_kwargs = {}
            if ocr_config.engine_type == OCREngineType.HUNYUAN:
                engine_kwargs = {
                    "base_url": ocr_config.hunyuan_url,
                    "timeout": ocr_config.hunyuan_timeout,
                    "max_retries": ocr_config.hunyuan_max_retries,
                    "rate_limit": ocr_config.hunyuan_rate_limit,
                }
            elif ocr_config.engine_type == OCREngineType.TESSERACT:
                engine_kwargs = {"tesseract_cmd": ocr_config.tesseract_cmd}
            elif ocr_config.engine_type == OCREngineType.PADDLEOCR_REMOTE:
                engine_kwargs = {
                    "base_url": ocr_config.paddleocr_url,
                    "timeout": ocr_config.paddleocr_timeout,
                }
            elif ocr_config.engine_type == OCREngineType.HYBRID:
                engine_kwargs = {
                    "hunyuan_url": ocr_config.hunyuan_url,
                    "paddleocr_url": ocr_config.paddleocr_url,
                    "hunyuan_timeout": ocr_config.hunyuan_timeout,
                    "paddleocr_timeout": ocr_config.paddleocr_timeout,
                    "enable_hunyuan": ocr_config.hybrid_enable_hunyuan,
                    "enable_paddleocr": ocr_config.hybrid_enable_paddleocr,
                    "enable_tesseract": ocr_config.hybrid_enable_tesseract,
                }

            return OCREngineFactory.create_engine(
                ocr_config.engine_type,
                **engine_kwargs,
            )

    def _check_cancelled(self) -> bool:
        if self.cancellation_check and self.cancellation_check():
            return True
        return False

    def _report_progress(self, current: int, total: int, message: str = "") -> None:
        if self.progress_callback:
            self.progress_callback(current, total, message)

    def _log(self, level: str, message: str) -> None:
        if self.log_callback:
            self.log_callback(level, message)
        logger.log(getattr(logging, level.upper()), message)

    def process_folder(self, folder_path: Path | str) -> FolderProcessingResults:
        folder_path = Path(folder_path)
        results = FolderProcessingResults()

        images = self._load_images(folder_path)
        total_images = len(images)

        if total_images == 0:
            self._log("warning", f"No images found in folder: {folder_path}")
            return results

        self._log("info", f"Processing {total_images} images from {folder_path}")

        for idx, image_path in enumerate(images):
            if self._check_cancelled():
                self._log("warning", "Processing cancelled by user")
                break

            self._report_progress(idx, total_images, f"Processing {Path(image_path).name}")

            result = self.process_single_image(image_path)
            results.add_result(result)

        self._save_results_to_csv(results, folder_path)
        self._report_progress(total_images, total_images, "Processing complete")

        return results

    def _load_images(self, folder_path: Path) -> list[str]:
        images = []
        ignore_list = ["Do Not Use", "debug"]

        for root, _dirs, files in os.walk(folder_path):
            for filename in files:
                full_path = os.path.join(root, filename)
                if all(ignored not in full_path for ignored in ignore_list):
                    if filename.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif", ".jfif")):
                        images.append(full_path)

        return images

    def process_single_image_with_pipeline(self, image_path: str) -> ProcessingResult:
        """Process a single image using the multi-stage pipeline.

        This method uses the new processing pipeline that:
        - Automatically detects daily screenshots
        - Attempts OCR total detection
        - Tries fixed grid method with Y-shifts (when enabled)
        - Falls back to anchor detection
        - Validates title extraction
        - Adds comprehensive tags for tracking
        - Automatically assigns to appropriate queue

        Args:
            image_path: Path to the screenshot image

        Returns:
            ProcessingResult with metadata, tags, and queue assignment
        """
        self.issue_manager.remove_all_issues()

        try:
            # Use the pipeline for processing
            result = self.pipeline.process_single_image(image_path)

            # Convert metadata tags to issues for backward compatibility with GUI
            if result.metadata:
                from .queue_models import ProcessingTag

                # Add issues based on tags
                if ProcessingTag.TITLE_NOT_FOUND.value in result.metadata.tags:
                    self.issue_manager.add_issue(TitleMissingIssue("Title is missing or invalid."))

                if ProcessingTag.TOTAL_NOT_FOUND.value in result.metadata.tags:
                    self.issue_manager.add_issue(
                        TotalNotFoundIssue("The displayed total was unable to be extracted from the image.")
                    )

                if ProcessingTag.CLOSE_MATCH.value in result.metadata.tags:
                    diff = result.metadata.accuracy_diff_minutes or 0
                    pct = result.metadata.accuracy_diff_percent or 0
                    self.issue_manager.add_issue(
                        TotalUnderestimationSmallIssue(
                            f"The bar total differs from displayed total by {diff:.1f} minute(s) ({pct:.1f}%)."
                        )
                    )

                if ProcessingTag.POOR_MATCH.value in result.metadata.tags:
                    diff = result.metadata.accuracy_diff_minutes or 0
                    pct = result.metadata.accuracy_diff_percent or 0
                    self.issue_manager.add_issue(
                        TotalUnderestimationLargeIssue(
                            f"The bar total significantly differs from displayed total by {diff:.1f} minute(s) ({pct:.1f}%)."
                        )
                    )

                # Attach issues to result
                result.issues = self.issue_manager.get_issues()

            return result

        except Exception as e:
            self._log("error", f"Pipeline processing failed for {image_path}: {e}")
            return ProcessingResult(
                image_path=image_path,
                success=False,
                error=e,
            )

    def process_single_image(self, image_path: str) -> ProcessingResult:
        self.issue_manager.remove_all_issues()

        try:
            if self.config.skip_daily_usage and self.config.image_type == ImageType.SCREEN_TIME:
                img = cv2.imread(str(image_path))
                if img is not None:
                    img = convert_dark_mode(img)
                    title, _ = find_screenshot_title(img)

                    if title == "Daily Total":
                        self._log("info", f"Skipping Daily Total image: {image_path}")
                        return ProcessingResult(
                            image_path=image_path,
                            success=True,
                            row_data=None,
                            issues=[],
                        )

            processed_image_path, graph_image_path, row, title, total, total_image_path, _ = process_image(
                image_path,
                self.config.image_type == ImageType.BATTERY,
                self.config.snap_to_grid,
            )

            self._validate_extraction(title, total, row)

            if self.config.image_type == ImageType.BATTERY:
                row_data = BatteryRow(
                    full_path=image_path,
                    file_name=Path(image_path).name,
                    date_from_image=title or "",
                    time_from_ui="Midnight",
                    rows=row,
                )
            else:
                row_data = ScreenTimeRow(
                    full_path=image_path,
                    file_name=Path(image_path).name,
                    app_title=title or "",
                    rows=row,
                )

            issues = self.issue_manager.get_issues()

            return ProcessingResult(
                image_path=image_path,
                success=True,
                row_data=row_data,
                issues=issues,
            )

        except (ImageProcessingError, ValueError) as e:
            self._log("error", f"Failed to process {image_path}: {e}")
            return ProcessingResult(
                image_path=image_path,
                success=False,
                error=e,
            )

    def _validate_extraction(self, title: str, total: str, row: list[int]) -> None:
        invalid_title_list = ["", " ", None]

        if title in invalid_title_list and self.config.image_type == ImageType.SCREEN_TIME:
            self.issue_manager.add_issue(TitleMissingIssue("Title is missing or invalid."))

        if self.config.image_type == ImageType.SCREEN_TIME and total != "N/A":
            self._compare_totals_and_add_issues(total, row)

    def _compare_totals_and_add_issues(self, extracted_total: str, row: list[int]) -> None:
        calculated_total_minutes = row[-1] if row else 0

        extracted_total_minutes = self._parse_time_to_minutes(extracted_total, calculated_total_minutes)

        if extracted_total_minutes == 0.0 and extracted_total != "0m" and extracted_total != "0h":
            self.issue_manager.add_issue(
                TotalNotFoundIssue("The displayed total was unable to be extracted from the image.")
            )
            return

        diff = calculated_total_minutes - extracted_total_minutes
        abs_diff = abs(diff)

        if abs_diff == 0:
            return

        percent_diff = abs_diff / max(1, extracted_total_minutes) * 100

        small_total_threshold = self.config.thresholds.small_total_threshold
        small_total_diff_threshold = self.config.thresholds.small_total_diff_threshold
        large_total_percent_threshold = self.config.thresholds.large_total_percent_threshold

        if extracted_total_minutes < small_total_threshold:
            if abs_diff < small_total_diff_threshold:
                if diff < 0:
                    self.issue_manager.add_issue(
                        TotalUnderestimationSmallIssue(
                            f"The bar total underestimated the displayed total by {abs_diff} minute(s) ({percent_diff:.1f}%)."
                        )
                    )
                else:
                    self.issue_manager.add_issue(
                        TotalOverestimationSmallIssue(
                            f"The bar total overestimated the displayed total by {abs_diff} minute(s) ({percent_diff:.1f}%)."
                        )
                    )
            elif diff < 0:
                self.issue_manager.add_issue(
                    TotalUnderestimationLargeIssue(
                        f"The bar total significantly underestimated the displayed total by {abs_diff} minute(s) ({percent_diff:.1f}%)."
                    )
                )
            else:
                self.issue_manager.add_issue(
                    TotalOverestimationLargeIssue(
                        f"The bar total significantly overestimated the displayed total by {abs_diff} minute(s) ({percent_diff:.1f}%)."
                    )
                )
        elif percent_diff >= large_total_percent_threshold:
            if diff < 0:
                self.issue_manager.add_issue(
                    TotalUnderestimationLargeIssue(
                        f"The bar total significantly underestimated the displayed total by {abs_diff} minute(s) ({percent_diff:.1f}%)."
                    )
                )
            else:
                self.issue_manager.add_issue(
                    TotalOverestimationLargeIssue(
                        f"The bar total significantly overestimated the displayed total by {abs_diff} minute(s) ({percent_diff:.1f}%)."
                    )
                )

    def _apply_letter_to_number_ocr_corrections(self, time_str: str) -> str:
        substitutions = {
            "A": "4",
            "a": "4",
            "T": "1",
            "t": "1",
            "I": "1",
            "i": "1",
            "l": "1",
            "|": "1",
            "O": "0",
            "o": "0",
            "B": "8",
            "b": "8",
            "S": "5",
            "s": "5",
            "Z": "2",
            "z": "2",
            "G": "6",
            "g": "6",
        }

        corrected = list(time_str)

        for i, char in enumerate(time_str):
            if char in substitutions:
                corrected[i] = substitutions[char]

        return "".join(corrected)

    def _parse_time_to_minutes(self, total_str: str, calculated_total: float | None = None) -> float:
        """Parse time string to minutes, with OCR correction and issue reporting.

        Uses the shared parse_time_to_minutes() for core parsing, then applies
        additional OCR letter-to-number corrections when a calculated_total is
        available for comparison.
        """
        if not total_str or total_str == "N/A":
            return 0.0

        cleaned_str = re.sub(r"[^\w\s]", " ", total_str).lower()
        valid_format = bool(re.match(r"^\s*(\d+h)?(\s*\d+m)?\s*$", cleaned_str))

        total_minutes = parse_time_to_minutes(total_str) or 0.0

        if total_minutes > 0 and not valid_format:
            self.issue_manager.add_issue(
                TotalParseErrorIssue(
                    f"The extracted total '{total_str}' is not in the expected format (e.g., '2h 30m', '45m', or '6h')."
                )
            )

        if calculated_total is not None and abs(total_minutes - calculated_total) > 1:
            corrected_str = self._apply_letter_to_number_ocr_corrections(total_str)

            if corrected_str != total_str:
                corrected_minutes = parse_time_to_minutes(corrected_str) or 0.0

                if corrected_minutes > 0 and abs(corrected_minutes - calculated_total) < abs(
                    total_minutes - calculated_total
                ):
                    self.issue_manager.add_issue(
                        TotalParseErrorIssue(
                            f"Corrected OCR errors in '{total_str}' to '{corrected_str}' (closer to calculated total)"
                        )
                    )
                    return corrected_minutes

        return total_minutes

    def _save_results_to_csv(self, results: FolderProcessingResults, folder_path: Path) -> None:
        import pandas as pd

        successful_results = [r for r in results.results if r.success and r.row_data is not None]

        if not successful_results:
            self._log("warning", "No successful results to save")
            return

        if self.config.image_type == ImageType.BATTERY:
            headers = BatteryRow.headers()
        else:
            headers = ScreenTimeRow.headers()

        folder_name = folder_path.parent.name if self.config.image_type == ImageType.SCREEN_TIME else folder_path.name
        csv_filename = self.config.output.csv_filename_pattern.format(folder_name=folder_name)
        csv_path = self.config.output.output_dir / csv_filename

        csv_path.parent.mkdir(parents=True, exist_ok=True)

        if not csv_path.exists():
            df = pd.DataFrame(columns=headers)
            df.to_csv(csv_path, index=False)
            self._log("info", f"Created CSV file with headers: {csv_path}")

        old_df = pd.read_csv(csv_path).fillna("")

        new_rows = [result.row_data.to_csv_row() for result in successful_results]
        new_df = pd.DataFrame(new_rows, columns=headers).fillna("")

        combined_df = pd.concat([old_df, new_df], axis=0)

        if self.config.output.remove_duplicates:
            duplicate_columns = ["Full path"]
            duplicates = combined_df.duplicated(subset=duplicate_columns, keep="last")
            num_duplicates = duplicates.sum()
            combined_df = combined_df.drop_duplicates(subset=duplicate_columns, keep="last")

            self._log("info", f"{num_duplicates} duplicate(s) removed, kept last updated entries")

        combined_df.to_csv(csv_path, index=False)
        self._log("info", f"CSV file updated: {csv_path}")
