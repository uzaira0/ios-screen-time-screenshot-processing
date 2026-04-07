from __future__ import annotations

from .callbacks import CancellationCheck, IssueCallback, LogCallback, ProgressCallback
from .config import (
    ImageProcessingConfig,
    OCRConfig,
    OutputConfig,
    ProcessorConfig,
    ThresholdConfig,
)
from .exceptions import (
    ConfigurationError,
    GridDetectionError,
    ImageProcessingError,
    OCRError,
    ScreenshotProcessorError,
    ValidationError,
)
from .models import (
    BaseRow,
    BatteryRow,
    BlockingIssue,
    FolderProcessingResults,
    GraphDetectionIssue,
    ImageType,
    Issue,
    LineExtractionMode,
    NonBlockingIssue,
    PageMarkerWord,
    PageType,
    ProcessingResult,
    ScreenTimeRow,
    TitleMissingIssue,
    TotalIssue,
    TotalNotFoundIssue,
    TotalOverestimationLargeIssue,
    TotalOverestimationSmallIssue,
    TotalParseErrorIssue,
    TotalUnderestimationLargeIssue,
    TotalUnderestimationSmallIssue,
)
from .ocr_protocol import IOCREngine, OCREngineError, OCREngineNotAvailableError, OCRResult

# Heavy imports deferred via __getattr__ to avoid pulling in
# matplotlib (515ms), pandas (531ms), httpx (172ms) at import time.
# These are only loaded when actually accessed.
_LAZY_IMPORTS = {
    "PaddleOCREngine": ".ocr_engines",
    "TesseractOCREngine": ".ocr_engines",
    "OCREngineFactory": ".ocr_factory",
    "OCREngineType": ".ocr_factory",
    "ProcessingPipeline": ".processing_pipeline",
    "ScreenshotProcessor": ".processor",
    "QueueManager": ".queue_manager",
    "QueueStatistics": ".queue_manager",
    "ProcessingMetadata": ".queue_models",
    "ProcessingMethod": ".queue_models",
    "ProcessingTag": ".queue_models",
    "ScreenshotQueue": ".queue_models",
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        import importlib

        module = importlib.import_module(_LAZY_IMPORTS[name], __name__)
        value = getattr(module, name)
        # Cache on the module so __getattr__ isn't called again
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Processor
    "ScreenshotProcessor",
    "ProcessingPipeline",
    # Config
    "ProcessorConfig",
    "ImageProcessingConfig",
    "OCRConfig",
    "OutputConfig",
    "ThresholdConfig",
    # Callbacks
    "ProgressCallback",
    "IssueCallback",
    "CancellationCheck",
    "LogCallback",
    # Exceptions
    "ScreenshotProcessorError",
    "ImageProcessingError",
    "OCRError",
    "GridDetectionError",
    "ConfigurationError",
    "ValidationError",
    # OCR
    "IOCREngine",
    "OCRResult",
    "OCREngineError",
    "OCREngineNotAvailableError",
    "OCREngineFactory",
    "OCREngineType",
    "TesseractOCREngine",
    "PaddleOCREngine",
    # Queue System
    "ProcessingMetadata",
    "ProcessingMethod",
    "ProcessingTag",
    "ScreenshotQueue",
    "QueueManager",
    "QueueStatistics",
    # Enums
    "ImageType",
    "LineExtractionMode",
    "PageType",
    "PageMarkerWord",
    # Models
    "BaseRow",
    "BatteryRow",
    "ScreenTimeRow",
    "Issue",
    "BlockingIssue",
    "NonBlockingIssue",
    "GraphDetectionIssue",
    "TitleMissingIssue",
    "TotalIssue",
    "TotalNotFoundIssue",
    "TotalParseErrorIssue",
    "TotalUnderestimationSmallIssue",
    "TotalUnderestimationLargeIssue",
    "TotalOverestimationSmallIssue",
    "TotalOverestimationLargeIssue",
    "ProcessingResult",
    "FolderProcessingResults",
]
