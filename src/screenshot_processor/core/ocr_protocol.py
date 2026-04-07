"""OCR Engine Protocol for cross-platform OCR abstraction.

This module defines the protocol (interface) that all OCR engines must implement,
enabling dependency injection and swappable OCR backends across Python, TypeScript, and WASM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class OCRResult:
    """Cross-platform OCR result dataclass.

    Attributes:
        text: Extracted text content
        confidence: Confidence score (0.0-1.0)
        bbox: Bounding box as (x, y, width, height) or None if not available
    """

    text: str
    confidence: float
    bbox: tuple[int, int, int, int] | None = None

    def __post_init__(self) -> None:
        """Validate OCR result fields."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {self.confidence}")


@runtime_checkable
class IOCREngine(Protocol):
    """Protocol defining the interface for OCR engines.

    All OCR implementations (Tesseract, PaddleOCR, tesseract-wasm, etc.)
    must implement this interface to be compatible with the processing pipeline.
    """

    def extract_text(
        self,
        image: NDArray[np.uint8],
        config: str | None = None,
    ) -> list[OCRResult]:
        """Extract text from an image.

        Args:
            image: Input image as numpy array (H, W, C) in RGB format
            config: Optional engine-specific configuration string

        Returns:
            List of OCRResult objects containing extracted text and metadata

        Raises:
            OCREngineError: If OCR processing fails
        """
        ...

    def is_available(self) -> bool:
        """Check if the OCR engine is available and properly configured.

        Returns:
            True if engine can be used, False otherwise
        """
        ...

    def get_engine_name(self) -> str:
        """Get the name of the OCR engine.

        Returns:
            Human-readable engine name (e.g., "Tesseract", "PaddleOCR")
        """
        ...


class OCREngineError(Exception):
    """Base exception for OCR engine errors."""


class OCREngineNotAvailableError(OCREngineError):
    """Raised when an OCR engine is not available or not properly configured."""
