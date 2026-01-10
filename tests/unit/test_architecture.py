"""
Architecture verification tests.

Verifies that the package structure is correctly implemented:
1. Core is framework-agnostic (no PyQt6 dependencies)
2. Package structure is correct
"""

from __future__ import annotations

from pathlib import Path

import pytest


class TestCoreIsolation:
    """Verify core has no PyQt6 dependencies."""

    def test_core_no_pyqt_imports(self):
        """Verify that core module has no PyQt6 dependencies."""
        import screenshot_processor.core as core_module

        core_dir = Path(core_module.__file__).parent

        for py_file in core_dir.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # Skip files with encoding issues (unlikely to be Python source)
                continue
            assert "from PyQt6" not in content, f"Found PyQt6 import in {py_file}"
            assert "import PyQt6" not in content, f"Found PyQt6 import in {py_file}"


class TestPackageStructure:
    """Verify package structure is correct."""

    def test_core_imports(self):
        """Test that core imports work."""
        from screenshot_processor import ProcessorConfig, ScreenshotProcessor
        from screenshot_processor.core import ImageType, OutputConfig
        from screenshot_processor.core.models import BatteryRow, ScreenTimeRow

        assert ScreenshotProcessor is not None
        assert ProcessorConfig is not None
        assert ImageType is not None
        assert OutputConfig is not None
        assert BatteryRow is not None
        assert ScreenTimeRow is not None

    def test_gui_imports(self):
        """Test that GUI imports work."""
        pytest.importorskip("PyQt6")
        from screenshot_processor.gui import ScreenshotApp, main

        assert ScreenshotApp is not None
        assert main is not None


class TestProgrammaticAPI:
    """Test that the programmatic API is available."""

    def test_processor_instantiation(self):
        """Test that ScreenshotProcessor can be instantiated."""
        from unittest.mock import MagicMock

        from screenshot_processor import ProcessorConfig, ScreenshotProcessor
        from screenshot_processor.core import ImageType, OutputConfig

        config = ProcessorConfig(
            image_type=ImageType.BATTERY,
            output=OutputConfig(output_dir=Path("./output")),
        )

        mock_engine = MagicMock()
        mock_engine.get_engine_name.return_value = "mock"
        processor = ScreenshotProcessor(config=config, ocr_engine=mock_engine)
        assert processor is not None
        assert processor.config.image_type == ImageType.BATTERY
