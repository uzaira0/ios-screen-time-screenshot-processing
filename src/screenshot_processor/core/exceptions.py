from __future__ import annotations


class ScreenshotProcessorError(Exception):
    pass


class ImageProcessingError(ScreenshotProcessorError):
    def __init__(self, message: str, errors: Exception | None = None) -> None:
        super().__init__(message)
        self.errors = errors


class OCRError(ScreenshotProcessorError):
    pass


class GridDetectionError(ScreenshotProcessorError):
    pass


class ConfigurationError(ScreenshotProcessorError):
    pass


class ValidationError(ScreenshotProcessorError):
    pass
