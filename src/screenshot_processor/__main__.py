from __future__ import annotations


def main():
    print("=" * 70)
    print("Screenshot Processor Package Information")
    print("=" * 70)
    print()
    print("Available imports:")
    print("    from screenshot_processor import ScreenshotProcessor, ProcessorConfig")
    print("    from screenshot_processor.core import ImageType, OutputConfig")
    print()
    print("Example usage (programmatic):")
    print("    from pathlib import Path")
    print("    from screenshot_processor import ScreenshotProcessor, ProcessorConfig, ImageType, OutputConfig")
    print()
    print("    config = ProcessorConfig(")
    print("        image_type=ImageType.BATTERY,")
    print("        output=OutputConfig(output_dir=Path('./output'))")
    print("    )")
    print()
    print("    processor = ScreenshotProcessor(config=config)")
    print("    results = processor.process_folder(Path('./screenshots'))")
    print("    print(f'Processed {results.successful_count} images')")
    print()
    print("Entry points:")
    print("    screenshot-gui              # Launch GUI application")
    print()
    print("Get help:")
    print("    >>> from screenshot_processor import ScreenshotProcessor")
    print("    >>> help(ScreenshotProcessor)")
    print()


if __name__ == "__main__":
    main()
