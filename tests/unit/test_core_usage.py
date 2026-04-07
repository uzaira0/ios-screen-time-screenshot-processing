"""
Test core programmatic usage (no GUI dependencies).
"""

from __future__ import annotations

from pathlib import Path


class TestCoreUsage:
    """Test core module can be used programmatically."""

    def test_processor_config_creation(self):
        """Test that ProcessorConfig can be created."""
        from screenshot_processor.core import (
            ImageType,
            OutputConfig,
            ProcessorConfig,
        )

        config = ProcessorConfig(
            image_type=ImageType.BATTERY,
            output=OutputConfig(output_dir=Path("./output")),
        )

        assert config.image_type == ImageType.BATTERY
        assert config.output.output_dir == Path("./output")

    def test_processor_instantiation(self):
        """Test that ScreenshotProcessor can be instantiated."""
        from unittest.mock import MagicMock

        from screenshot_processor.core import (
            ImageType,
            OutputConfig,
            ProcessorConfig,
            ScreenshotProcessor,
        )

        config = ProcessorConfig(
            image_type=ImageType.BATTERY,
            output=OutputConfig(output_dir=Path("./output")),
        )

        mock_engine = MagicMock()
        mock_engine.get_engine_name.return_value = "mock"
        processor = ScreenshotProcessor(config=config, ocr_engine=mock_engine)
        assert processor is not None

    def test_image_type_enum(self):
        """Test ImageType enum values."""
        from screenshot_processor.core import ImageType

        assert ImageType.BATTERY.value == "battery"
        assert ImageType.SCREEN_TIME.value == "screen_time"
