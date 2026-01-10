from __future__ import annotations

import logging
import os
import sys
import traceback
from pathlib import Path

import cv2
from PyQt6 import QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMouseEvent, QPixmap
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget

from screenshot_processor.core.config import OutputConfig, ProcessorConfig, ThresholdConfig
from screenshot_processor.core.exceptions import ImageProcessingError
from screenshot_processor.core.image_processor import (
    compare_blue_in_images,
    hconcat_resize,
    mse_between_loaded_images,
    process_image,
    process_image_with_grid,
)
from screenshot_processor.core.issue_manager import IssueManager
from screenshot_processor.core.models import (
    BatteryRow,
    GraphDetectionIssue,
    ImageType,
    NonBlockingIssue,
    ScreenTimeRow,
    TitleMissingIssue,
)

from .ui_components import ScreenshotAppUI

logger = logging.getLogger(__name__)


class ScreenshotApp(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[str] = []
        self.current_image_index = 0
        self.current_row: BatteryRow | ScreenTimeRow | None = None
        self.click_count = 0
        self.coordinates: list[tuple[int, int]] = []
        self.folder_name = ""
        self.image_mode = ImageType.BATTERY
        self.invalid_title_list = ["", " ", None]

        self.ui = ScreenshotAppUI(self)

        self.issue_manager = IssueManager()
        self.issue_manager.register_observer(self.update_interface)

    @property
    def magnifier_label(self):
        return self.ui.magnifier_label

    @property
    def image_label(self):
        return self.ui.image_label

    @property
    def screen_geometry(self) -> QtCore.QRect:
        from PyQt6.QtWidgets import QApplication

        screen_geo = None
        if QApplication.primaryScreen() is not None:
            screen = QApplication.primaryScreen()
            if screen is not None:
                screen_geo = screen.geometry()

        if screen_geo is None:
            screen_geo = QtCore.QRect(0, 0, 800, 600)

        return screen_geo

    def capture_click(self, event: QMouseEvent) -> None:
        x = event.pos().x()
        y = event.pos().y()
        self.coordinates.append((x, y))
        self.click_count += 1

        if self.click_count == 1:
            self.ui.instruction_label.setText(
                "Now click the bottom right corner of the graph in the left image to finish the selection."
            )
            self.ui.instruction_label.setStyleSheet("background-color:rgb(0,255,0)")
        elif self.click_count == 2:
            self.process_coordinates(self.coordinates[0], self.coordinates[1])
            self.coordinates = []
            self.click_count = 0

            self.update_interface()

    def update_time_label(self, value: int) -> None:
        selected_time = self.ui.time_mapping.get(value, "Midnight")
        self.ui.time_label.setText(f"First time displayed in screenshot: {selected_time}")

    def open_folder(self, selection_type: ImageType) -> None:
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder")
        self.folder_name = folder_path
        self.image_mode = selection_type
        self.ui.adjust_ui_for_image_type(selection_type)
        if folder_path:
            self.load_images(folder_path)
            if self.images:
                self.ui.progress_label.show()
                self.show_image(0)
            else:
                self.ui.progress_label.hide()
                QMessageBox.information(self, "No Images Found", "No images found in the folder.")

    def load_images(self, folder_path: Path | str) -> None:
        self.images = []
        ignore_list = ["Do Not Use", "debug"]
        for root, _dirs, files in os.walk(folder_path):
            for filename in files:
                if all(ignored not in os.path.join(root, filename) for ignored in ignore_list):
                    if filename.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif", ".jfif")):
                        self.images.append(os.path.join(root, filename))
        if not self.images:
            self.ui.image_label.setText("No image loaded.")
            self.ui.cropped_image_label.setText("No cropped image loaded.")
            self.ui.image_name_line_edit.setText("Image name will appear here.")

    def skip_current_image(self) -> None:
        if self.current_image_index + 1 < len(self.images):
            self.show_image(self.current_image_index + 1)

    def show_previous_image(self) -> None:
        if self.current_image_index > 0:
            self.show_image(self.current_image_index - 1)

    def save_current_row(self) -> None:
        import pandas as pd

        if not self.current_row:
            return

        csv_path = (
            Path(sys.argv[0]).parent
            / "output"
            / f"{Path(self.images[self.current_image_index]).parents[1].name} Arcascope Output.csv"
        )

        if self.image_mode == ImageType.BATTERY:
            if not isinstance(self.current_row, BatteryRow):
                msg = f"Expected BatteryRow object for Battery mode, got {type(self.current_row)}"
                raise ValueError(msg)

            headers = BatteryRow.headers()
            self.current_row.date_from_image = self.ui.extracted_text_edit.text()
            self.current_row.time_from_ui = self.ui.time_mapping[self.ui.slider.value()]

        elif self.image_mode == ImageType.SCREEN_TIME:
            if not isinstance(self.current_row, ScreenTimeRow):
                msg = f"Expected ScreenTimeRow object for Screen Time mode, got {type(self.current_row)}"
                raise ValueError(msg)

            headers = ScreenTimeRow.headers()
            self.current_row.app_title = self.ui.extracted_text_edit.text()

        else:
            msg = f"Invalid image mode: {self.image_mode}"
            raise ValueError(msg)

        if not csv_path.exists():
            df = pd.DataFrame(columns=headers)
            df.to_csv(csv_path, index=False)
            logger.info("CSV file created with headers.")
        else:
            new_row_to_check = pd.DataFrame([self.current_row.to_csv_row()], columns=headers).fillna("")
            old_df = pd.read_csv(csv_path).fillna("")

            new_row_to_check = new_row_to_check[old_df.columns]

            combined_df = pd.concat([old_df, new_row_to_check], axis=0)

            if self.ui.remove_duplicates_automatically_checkbox.isChecked():
                duplicate_columns = ["Full path"]

                duplicates = combined_df.duplicated(subset=duplicate_columns, keep="last")
                num_duplicates = duplicates.sum()

                combined_df = combined_df.drop_duplicates(subset=duplicate_columns, keep="last")

                logger.info(
                    f"{num_duplicates} duplicate(s) based on full image path removed, kept the last updated entries."
                )

            csv_path.parent.mkdir(parents=True, exist_ok=True)

            combined_df.to_csv(csv_path, index=False)

            logger.info(f"CSV file {csv_path} updated")

    def check_title(self) -> None:
        title = self.ui.extracted_text_edit.text()
        if title in self.invalid_title_list:
            self.issue_manager.add_issue(TitleMissingIssue("Title is missing or invalid. Please enter a valid title."))
        else:
            self.issue_manager.remove_issues_of_class(TitleMissingIssue)

    def _build_threshold_config(self) -> ThresholdConfig:
        return ThresholdConfig(
            small_total_threshold=self.ui.small_total_threshold_spinner.value(),
            small_total_diff_threshold=self.ui.small_total_diff_threshold_spinner.value(),
            large_total_percent_threshold=self.ui.large_total_percent_threshold_spinner.value(),
        )

    def compare_totals_and_add_issues(self, extracted_total: str, row: list[int]) -> None:
        from screenshot_processor.core.processor import ScreenshotProcessor

        temp_config = ProcessorConfig(
            image_type=self.image_mode.value,
            output=OutputConfig(output_dir=Path(".")),
            thresholds=self._build_threshold_config(),
        )

        temp_processor = ScreenshotProcessor(config=temp_config)
        temp_processor.issue_manager = self.issue_manager

        temp_processor._compare_totals_and_add_issues(extracted_total, row)

    def update_(
        self,
        title: str,
        total: str,
        row: list[int],
        processed_image_path: Path | str,
        graph_image_path: Path | str,
        total_image_path: Path | str | None = None,
    ) -> None:
        self.issue_manager.remove_all_issues()

        self.ui.extracted_text_edit.setText(title)
        self.ui.extracted_total_label.setText(f"Extracted Total: {total}")

        if total_image_path and Path(total_image_path).exists():
            total_pixmap = QPixmap(total_image_path)
            scaled_pixmap = total_pixmap.scaled(
                300,
                100,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.ui.extracted_total_image.setPixmap(scaled_pixmap)
        else:
            self.ui.extracted_total_image.setText("No total image available")

        if self.image_mode == ImageType.SCREEN_TIME and total != "N/A":
            self.compare_totals_and_add_issues(total, row)

        if not processed_image_path:
            self.ui.cropped_image_label.setText("No cropped image could be loaded from the selection.")
            self.issue_manager.add_issue(GraphDetectionIssue("Failed to extract a valid graph from the image."))
        else:
            processed_pixmap = QPixmap(processed_image_path)

            self.ui.cropped_image_label.setPixmap(
                processed_pixmap.scaled(
                    self.ui.length_dimension,
                    self.ui.length_dimension,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        if not graph_image_path:
            self.ui.graph_image_label.setText("No graph could be extracted from the selection.")
            self.issue_manager.add_issue(GraphDetectionIssue("Failed to extract a valid graph from the image."))
        else:
            processed_graph_pixmap = QPixmap(graph_image_path)

            self.ui.graph_image_label.setPixmap(
                processed_graph_pixmap.scaled(
                    self.ui.length_dimension,
                    self.ui.length_dimension,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        if processed_image_path and graph_image_path:
            processed_image = cv2.imread(str(processed_image_path))
            graph_image = cv2.imread(str(graph_image_path))

            compare_blue_in_images(image1=processed_image, image2=graph_image)

            if mse_between_loaded_images(processed_image, graph_image) > 100:
                check_folder = "./debug/check/"

                Path(check_folder).mkdir(parents=True, exist_ok=True)
                try:
                    combined_image = cv2.vconcat([processed_image, graph_image])
                    original_screenshot_image = cv2.imread(self.images[self.current_image_index])
                    combined_image = hconcat_resize([original_screenshot_image, combined_image])

                    cv2.imwrite(
                        f"{check_folder}/{Path(processed_image_path).name}_combined.jpg",
                        combined_image,
                    )
                except Exception:
                    logger.error(f"Error processing image: {traceback.format_exc()}")

        self.check_title()

        if self.image_mode == ImageType.BATTERY:
            self.current_row = BatteryRow(
                full_path=self.images[self.current_image_index],
                file_name=self.ui.image_name_line_edit.text(),
                date_from_image=self.ui.extracted_text_edit.text(),
                time_from_ui=self.ui.time_mapping[self.ui.slider.value()],
                rows=row,
            )
        elif self.image_mode == ImageType.SCREEN_TIME:
            self.current_row = ScreenTimeRow(
                full_path=self.images[self.current_image_index],
                file_name=self.ui.image_name_line_edit.text(),
                app_title=self.ui.extracted_text_edit.text(),
                rows=row,
            )

    def update_interface(self) -> None:
        if not self.issue_manager.has_issues():
            self.ui.instruction_label.setText(
                "Click Next/Save if ALL the graphs match (including the one on the left), otherwise click the upper left corner of the graph in the left image to reselect."
            )
            self.ui.instruction_label.setStyleSheet("background-color:rgb(255,255,150)")
            return

        if self.issue_manager.has_issues():
            issue = self.issue_manager.get_most_important_issue()
            if issue:
                message, style = issue.get_styled_message()
                self.ui.instruction_label.setText(message)
                self.ui.instruction_label.setStyleSheet(style)
                self.bring_window_to_front()

    def bring_window_to_front(self) -> None:
        self.setWindowState(
            self.windowState() & ~QtCore.Qt.WindowState.WindowMinimized | QtCore.Qt.WindowState.WindowActive
        )

        self.setWindowFlags(QtCore.Qt.WindowType.WindowStaysOnTopHint)

        self.show()

        self.raise_()
        self.activateWindow()

    def show_next_image_manual_button_press(self) -> None:
        if self.issue_manager.has_blocking_issues():
            response = QMessageBox.warning(
                self,
                "Warning: Blocking Issues",
                "There are blocking issues that need to be resolved. Are you sure you want to continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response == QMessageBox.StandardButton.No:
                return
            else:
                self.issue_manager.remove_all_issues()

        self.issue_manager.remove_issues_of_class(NonBlockingIssue)
        self.show_next_image()

    def show_next_image(self) -> None:
        if self.current_row and not self.issue_manager.has_issues():
            self.save_current_row()
            if self.current_image_index + 1 < len(self.images):
                self.show_image(self.current_image_index + 1)

    def show_image(self, index: int) -> None:
        from screenshot_processor.core.image_utils import convert_dark_mode
        from screenshot_processor.core.ocr import find_screenshot_title

        self.issue_manager.remove_all_issues()

        if 0 <= index < len(self.images):
            image_path = self.images[index]
            pixmap = QPixmap(image_path)
            self.ui.image_label.setPixmap(
                pixmap.scaled(
                    self.ui.length_dimension,
                    self.ui.length_dimension,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self.ui.image_name_line_edit.setText(Path(image_path).name)
            self.current_image_index = index

            self.ui.progress_label.setText(f"Image {index + 1} of {len(self.images)}")
            self.ui.progress_label.show()

            if self.image_mode == ImageType.SCREEN_TIME and self.ui.skip_daily_usage_checkbox.isChecked():
                try:
                    img = cv2.imread(str(image_path))
                    if img is not None:
                        img = convert_dark_mode(img)
                        title = find_screenshot_title(img)

                        if title == "Daily Total":
                            logger.info(f"Skipping Daily Total image: {image_path}")
                            self.skip_current_image()
                            return
                except Exception as e:
                    logger.warning(f"Error checking title for skipping: {e}")

            try:
                (
                    processed_image_path,
                    graph_image_path,
                    row,
                    title,
                    total,
                    total_image_path,
                    _,  # grid_coords - not needed for GUI
                ) = process_image(
                    image_path,
                    self.image_mode == ImageType.BATTERY,
                    self.ui.snap_to_grid_checkbox.isChecked(),
                )

                self.update_(
                    title or "",
                    total,
                    row,
                    processed_image_path,
                    graph_image_path,
                    total_image_path,
                )

                if self.ui.auto_process_images_checkbox.isChecked() and not self.issue_manager.has_issues():
                    self.showMinimized()
                    self.show_next_image()

            except ImageProcessingError as e:
                logger.error(f"Image processing error: {e}")
                self.issue_manager.add_issue(GraphDetectionIssue(f"Failed to process the image: {e}"))
                self.ui.cropped_image_label.setText("No cropped image loaded.")
            except (OSError, cv2.error) as e:
                logger.error(f"File or OpenCV error: {e}")
                self.issue_manager.add_issue(GraphDetectionIssue(f"Failed to load or process image file: {e}"))
                self.ui.cropped_image_label.setText("No cropped image loaded.")
                self.ui.graph_image_label.setText("No graph extracted")
                self.ui.image_name_line_edit.setText("No image available.")
        else:
            self.ui.image_label.setText("No image loaded.")
            self.ui.cropped_image_label.setText("No cropped image loaded.")
            self.ui.graph_image_label.setText("No graph extracted")
            self.ui.image_name_line_edit.setText("No image available.")
            self.ui.progress_label.setText("No images loaded")
            self.ui.progress_label.hide()

    def process_coordinates(self, upper_left: tuple[int, int], lower_right: tuple[int, int]) -> None:
        image_path = self.images[self.current_image_index]
        original_pixmap = QPixmap(image_path)

        original_width = original_pixmap.width()
        original_height = original_pixmap.height()

        scalar = self.ui.length_dimension / original_height

        display_width = original_width * scalar
        display_height = original_height * scalar

        scale_x = original_width / display_width
        scale_y = original_height / display_height

        true_upper_left = (
            int(upper_left[0] * scale_x),
            int(upper_left[1] * scale_y),
        )
        true_lower_right = (
            int(lower_right[0] * scale_x),
            int(lower_right[1] * scale_y),
        )

        logger.debug(f"Scaled coordinates - Upper Left: {true_upper_left}, Lower Right: {true_lower_right}")
        logger.debug(
            f"Image dimensions - Original: {original_width}x{original_height}, Display: {display_width}x{display_height}"
        )

        logger.debug("Processing image from clicks...")
        processed_image_path, graph_image_path, row, title, total, total_image_path = process_image_with_grid(
            image_path,
            true_upper_left,
            true_lower_right,
            self.image_mode == ImageType.BATTERY,
            self.ui.snap_to_grid_checkbox.isChecked(),
        )

        self.update_(title, total, row, processed_image_path, graph_image_path, total_image_path)
