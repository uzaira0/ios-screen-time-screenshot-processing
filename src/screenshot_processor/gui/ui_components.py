from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6 import QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

from screenshot_processor.core.models import ImageType

from .magnifying_label import MagnifyingLabel

if TYPE_CHECKING:
    from screenshot_processor.core.issue_manager import IssueManager

    from .main_window import ScreenshotApp


class ScreenshotAppUI:
    def __init__(self, app: ScreenshotApp) -> None:
        self.app = app
        self.screen_scale_factor = self.calculate_scale_factor()
        self.base_font_size = int(14 * self.screen_scale_factor)
        self.init_ui()

    def calculate_scale_factor(self) -> float:
        screen_geo = QApplication.primaryScreen().geometry()
        min_dimension = min(screen_geo.width(), screen_geo.height())
        return min_dimension / 1080

    def calculate_and_set_window_size(self) -> None:
        screen_geo = QApplication.primaryScreen().geometry()
        width = int(screen_geo.width() * 0.85)
        height = int(screen_geo.height() * 0.85)

        min_width = 800
        min_height = 600

        width = max(width, min_width)
        height = max(height, min_height)

        self.app.resize(width, height)
        self.length_dimension = int(min(width, height) * 0.7)

    def init_ui(self) -> None:
        self.app.setWindowTitle("Screenshot Slideshow")
        self.app.setStyleSheet(
            f"QWidget {{ font-size: {self.base_font_size}px; }} QPushButton {{ font-weight: bold; }}"
        )

        layout = QVBoxLayout(self.app)

        self.init_selection_buttons(layout)
        self.init_instruction_label(layout)
        self.init_main_layout(layout)
        self.init_slider_and_time_label(layout)
        self.init_navigation_buttons(layout)

        self.calculate_and_set_window_size()

    def init_selection_buttons(self, layout: QVBoxLayout) -> None:
        btn_battery = QPushButton("Select Folder of Battery Images")
        btn_battery.clicked.connect(lambda: self.app.open_folder(ImageType.BATTERY))
        btn_battery.setMinimumHeight(int(40 * self.screen_scale_factor))

        btn_screen_time = QPushButton("Select Folder of Screen Time Images")
        btn_screen_time.clicked.connect(lambda: self.app.open_folder(ImageType.SCREEN_TIME))
        btn_screen_time.setMinimumHeight(int(40 * self.screen_scale_factor))

        layout.addWidget(btn_battery)
        layout.addWidget(btn_screen_time)

        self.init_progress_indicator(layout)

    def init_progress_indicator(self, layout: QVBoxLayout) -> None:
        self.progress_label = QLabel("No images loaded")
        progress_font = QFont()
        progress_font.setPointSize(int(self.base_font_size * 1.0))
        progress_font.setBold(True)
        self.progress_label.setFont(progress_font)
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_label.setStyleSheet("background-color:rgb(200,220,255); padding: 8px; border: 1px solid #0066CC;")
        self.progress_label.setMinimumHeight(int(35 * self.screen_scale_factor))
        layout.addWidget(self.progress_label)
        self.progress_label.hide()

    def init_instruction_label(self, layout: QVBoxLayout) -> None:
        self.instruction_label = QLabel(
            "Click Next/Save if the graphs match, otherwise click the upper left corner of the graph in the left image.",
        )
        instruction_font = QFont()
        instruction_font.setPointSize(int(self.base_font_size * 1.1))
        instruction_font.setBold(True)
        self.instruction_label.setFont(instruction_font)
        self.instruction_label.setStyleSheet("background-color:rgb(255,255,150); padding: 10px;")
        self.instruction_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.instruction_label.setFixedHeight(int(60 * self.screen_scale_factor))
        self.instruction_label.setWordWrap(True)
        layout.addWidget(self.instruction_label)
        self.instruction_label.hide()

    def init_main_layout(self, layout: QVBoxLayout) -> None:
        main_image_layout = QHBoxLayout()
        layout.addLayout(main_image_layout)

        self.init_original_image_layout(main_image_layout)
        self.init_cropped_image_layout(main_image_layout)
        self.init_text_fields_layout(main_image_layout)

        main_image_layout.setStretch(0, 1)
        main_image_layout.setStretch(1, 1)
        main_image_layout.setStretch(2, 1)

    def init_original_image_layout(self, layout: QHBoxLayout) -> None:
        original_image_layout = QVBoxLayout()

        self.image_label = MagnifyingLabel(self.app)
        self.image_label.setCursor(Qt.CursorShape.CrossCursor)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        original_image_layout.addWidget(self.image_label)

        layout.addLayout(original_image_layout)

        self.magnifier_label = QLabel(self.app)
        magnifier_size = int(100 * self.screen_scale_factor)
        self.magnifier_label.resize(magnifier_size, magnifier_size)
        self.magnifier_label.setFrameShape(QFrame.Shape.StyledPanel)
        self.magnifier_label.setStyleSheet("background-color: white; border: 2px solid gray;")
        self.magnifier_label.raise_()
        self.magnifier_label.setVisible(True)

    def init_cropped_image_layout(self, layout: QHBoxLayout) -> None:
        cropped_image_layout = QVBoxLayout()

        self.cropped_image_label = QLabel("No cropped image loaded.")
        self.cropped_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cropped_image_layout.addWidget(self.cropped_image_label)

        self.graph_image_label = QLabel("No graph extracted.")
        self.graph_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cropped_image_layout.addWidget(self.graph_image_label)

        cropped_image_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(cropped_image_layout)

    def init_text_fields_layout(self, layout: QHBoxLayout) -> None:
        text_fields_layout = QVBoxLayout()
        text_fields_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_fields_layout.setSpacing(10)

        instruction_font = QFont()
        instruction_font.setPointSize(int(self.base_font_size * 1.1))
        instruction_font.setBold(True)

        image_name_label = QLabel("Image Name:")
        image_name_label.setFont(instruction_font)
        text_fields_layout.addWidget(image_name_label)

        self.image_name_line_edit = QLineEdit("Image_Name_Placeholder.png")
        self.image_name_line_edit.setMinimumHeight(int(30 * self.screen_scale_factor))
        text_fields_layout.addWidget(self.image_name_line_edit)

        self.extracted_text_label = QLabel("Extracted Title/App Name:")
        self.extracted_text_label.setFont(instruction_font)
        text_fields_layout.addWidget(self.extracted_text_label)

        self.extracted_text_edit = QLineEdit("")
        self.extracted_text_edit.setMinimumHeight(int(30 * self.screen_scale_factor))
        self.extracted_text_edit.textEdited.connect(self.app.check_title)
        text_fields_layout.addWidget(self.extracted_text_edit)

        self.extracted_total_label = QLabel("Extracted Total: ")
        total_font = QFont()
        total_font.setPointSize(int(self.base_font_size * 1.2))
        total_font.setBold(True)
        self.extracted_total_label.setFont(total_font)
        self.extracted_total_label.setStyleSheet("color: #0066CC; padding: 5px;")
        text_fields_layout.addWidget(self.extracted_total_label)
        self.extracted_total_label.hide()

        self.extracted_total_image = QLabel("No total image")
        self.extracted_total_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.extracted_total_image.setMinimumHeight(int(60 * self.screen_scale_factor))
        self.extracted_total_image.setFrameShape(QFrame.Shape.Box)
        self.extracted_total_image.setStyleSheet("border: 2px solid #0066CC; padding: 5px;")
        text_fields_layout.addWidget(self.extracted_total_image)
        self.extracted_total_image.hide()

        self.init_checkboxes(text_fields_layout)

        self.skip_button = QPushButton("Skip (no saving)")
        self.skip_button.clicked.connect(self.app.skip_current_image)
        self.skip_button.setMinimumHeight(int(40 * self.screen_scale_factor))
        text_fields_layout.addWidget(self.skip_button)

        layout.addLayout(text_fields_layout)

    def init_checkboxes(self, layout: QVBoxLayout) -> None:
        self.snap_to_grid_checkbox = QCheckBox("Automatically snap to grid", self.app)
        self.snap_to_grid_checkbox.setMinimumHeight(int(30 * self.screen_scale_factor))
        layout.addWidget(self.snap_to_grid_checkbox)

        self.auto_process_images_checkbox = QCheckBox(
            "Automatically process images (minimized, until an error occurs)", self.app
        )
        self.auto_process_images_checkbox.setMinimumHeight(int(30 * self.screen_scale_factor))
        layout.addWidget(self.auto_process_images_checkbox)
        self.auto_process_images_checkbox.hide()

        self.remove_duplicates_automatically_checkbox = QCheckBox(
            "Remove duplicates in csv output, keeping last saved (based on image path)",
            self.app,
        )
        self.remove_duplicates_automatically_checkbox.setMinimumHeight(int(30 * self.screen_scale_factor))
        layout.addWidget(self.remove_duplicates_automatically_checkbox)

        self.skip_daily_usage_checkbox = QCheckBox("Skip daily usage images", self.app)
        self.skip_daily_usage_checkbox.setToolTip(
            "If checked, images with 'Daily Total' title will be automatically skipped"
        )
        self.skip_daily_usage_checkbox.setMinimumHeight(int(30 * self.screen_scale_factor))
        layout.addWidget(self.skip_daily_usage_checkbox)
        self.skip_daily_usage_checkbox.hide()

        self.init_threshold_spinners(layout)

    def init_threshold_spinners(self, layout: QVBoxLayout) -> None:
        threshold_frame = QFrame()
        threshold_frame.setFrameStyle(QFrame.Shape.Box)
        threshold_frame.setStyleSheet("QFrame { border: 1px solid #ccc; padding: 10px; margin: 5px; }")

        threshold_layout = QVBoxLayout(threshold_frame)

        threshold_title = QLabel("Discrepancy Thresholds")
        threshold_font = QFont()
        threshold_font.setPointSize(int(self.base_font_size * 1.1))
        threshold_font.setBold(True)
        threshold_title.setFont(threshold_font)
        threshold_layout.addWidget(threshold_title)

        small_threshold_layout = QHBoxLayout()
        small_threshold_label = QLabel("Small total threshold (minutes):")
        self.small_total_threshold_spinner = QSpinBox()
        self.small_total_threshold_spinner.setMinimum(10)
        self.small_total_threshold_spinner.setMaximum(120)
        self.small_total_threshold_spinner.setValue(30)
        self.small_total_threshold_spinner.setToolTip("Totals below this value use absolute difference thresholds")
        small_threshold_layout.addWidget(small_threshold_label)
        small_threshold_layout.addWidget(self.small_total_threshold_spinner)
        threshold_layout.addLayout(small_threshold_layout)

        small_diff_layout = QHBoxLayout()
        small_diff_label = QLabel("Small total difference threshold (minutes):")
        self.small_total_diff_threshold_spinner = QSpinBox()
        self.small_total_diff_threshold_spinner.setMinimum(1)
        self.small_total_diff_threshold_spinner.setMaximum(20)
        self.small_total_diff_threshold_spinner.setValue(5)
        self.small_total_diff_threshold_spinner.setToolTip(
            "Differences below this are considered small for small totals"
        )
        small_diff_layout.addWidget(small_diff_label)
        small_diff_layout.addWidget(self.small_total_diff_threshold_spinner)
        threshold_layout.addLayout(small_diff_layout)

        large_percent_layout = QHBoxLayout()
        large_percent_label = QLabel("Large total percentage threshold (%):")
        self.large_total_percent_threshold_spinner = QSpinBox()
        self.large_total_percent_threshold_spinner.setMinimum(1)
        self.large_total_percent_threshold_spinner.setMaximum(20)
        self.large_total_percent_threshold_spinner.setValue(3)
        self.large_total_percent_threshold_spinner.setToolTip(
            "Percentage differences above this are considered large for large totals"
        )
        large_percent_layout.addWidget(large_percent_label)
        large_percent_layout.addWidget(self.large_total_percent_threshold_spinner)
        threshold_layout.addLayout(large_percent_layout)

        layout.addWidget(threshold_frame)

        self.threshold_frame = threshold_frame
        threshold_frame.hide()

    def init_slider_and_time_label(self, layout: QVBoxLayout) -> None:
        self.time_mapping = {
            0: "Midnight",
            1: "3 AM",
            2: "6 AM",
            3: "9 AM",
            4: "12 PM",
            5: "3 PM",
            6: "6 PM",
            7: "9 PM",
        }

        slider_layout = QHBoxLayout()

        self.slider = QSlider(QtCore.Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(len(self.time_mapping) - 1)
        self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider.setTickInterval(1)
        self.slider.setMinimumHeight(int(40 * self.screen_scale_factor))
        slider_layout.addWidget(self.slider)

        layout.addLayout(slider_layout)
        self.slider.hide()

        label_layout = QHBoxLayout()
        label_layout.addStretch()

        instruction_font = QFont()
        instruction_font.setPointSize(int(self.base_font_size * 1.1))
        instruction_font.setBold(True)

        self.time_label = QLabel("First time displayed in screenshot: Midnight")
        self.time_label.setFont(instruction_font)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label_layout.addWidget(self.time_label)
        label_layout.addStretch()
        layout.addLayout(label_layout)
        self.time_label.hide()

        self.slider.valueChanged.connect(self.app.update_time_label)

    def init_navigation_buttons(self, layout: QVBoxLayout) -> None:
        nav_layout = QHBoxLayout()

        self.previous_button = QPushButton("Previous")
        self.previous_button.clicked.connect(self.app.show_previous_image)
        self.previous_button.setMinimumHeight(int(50 * self.screen_scale_factor))
        nav_layout.addWidget(self.previous_button)

        self.next_button = QPushButton("Next/Save")
        self.next_button.clicked.connect(self.app.show_next_image_manual_button_press)
        self.next_button.setMinimumHeight(int(50 * self.screen_scale_factor))
        nav_layout.addWidget(self.next_button)

        layout.addLayout(nav_layout)

    def adjust_ui_for_image_type(self, image_type: ImageType) -> None:
        if image_type == ImageType.BATTERY:
            self.extracted_text_label.setText("Date of first displayed time:")
            self.slider.show()
            self.time_label.hide()
            self.instruction_label.hide()
            self.extracted_total_label.hide()
            self.extracted_total_image.hide()
            self.auto_process_images_checkbox.hide()
            self.remove_duplicates_automatically_checkbox.hide()
            self.skip_daily_usage_checkbox.hide()
            self.threshold_frame.hide()
        elif image_type == ImageType.SCREEN_TIME:
            self.extracted_text_label.setText("Extracted Title/App Name:")
            self.slider.hide()
            self.time_label.hide()
            self.instruction_label.show()
            self.extracted_total_label.show()
            self.extracted_total_image.show()
            self.auto_process_images_checkbox.show()
            self.remove_duplicates_automatically_checkbox.show()
            self.skip_daily_usage_checkbox.show()
            self.threshold_frame.show()

    def update_interface(self, issue_manager: IssueManager) -> None:
        if not issue_manager.has_issues():
            self.instruction_label.setText(
                "Click Next/Save if ALL the graphs match (including the one on the left), otherwise click the upper left corner of the graph in the left image to reselect."
            )
            self.instruction_label.setStyleSheet("background-color:rgb(255,255,150)")
            return

        issue = issue_manager.get_most_important_issue()
        if issue:
            message, style = issue.get_styled_message()
            self.instruction_label.setText(message)
            self.instruction_label.setStyleSheet(style)

        if issue_manager.has_blocking_issues():
            self.bring_window_to_front()

    def bring_window_to_front(self) -> None:
        self.app.setWindowState(
            self.app.windowState() & ~QtCore.Qt.WindowState.WindowMinimized | QtCore.Qt.WindowState.WindowActive
        )
        self.app.setWindowFlags(QtCore.Qt.WindowType.WindowStaysOnTopHint)
        self.app.show()
        self.app.raise_()
        self.app.activateWindow()
