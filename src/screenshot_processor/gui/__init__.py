from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from .magnifying_label import MagnifyingLabel
from .main_window import ScreenshotApp
from .ui_components import ScreenshotAppUI

__all__ = ["MagnifyingLabel", "ScreenshotApp", "ScreenshotAppUI", "main"]


def main() -> None:
    sys.argv += ["-platform", "windows:darkmode=1"]
    app = QApplication(sys.argv)
    window = ScreenshotApp()
    window.show()
    sys.exit(app.exec())
