"""Tesseract OCR Engine implementation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
from pytesseract import Output, pytesseract

from ..ocr_protocol import OCREngineError, OCREngineNotAvailableError, OCRResult

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)


class TesseractOCREngine:
    """Tesseract OCR engine implementation.

    Wraps pytesseract to conform to the IOCREngine protocol.
    """

    def __init__(self, tesseract_cmd: str | None = None) -> None:
        """Initialize Tesseract OCR engine.

        Args:
            tesseract_cmd: Optional path to tesseract executable.
                          If None, uses default from pytesseract.
        """
        if tesseract_cmd:
            pytesseract.tesseract_cmd = tesseract_cmd

        self._is_available = self._check_availability()

    def _check_availability(self) -> bool:
        """Check if Tesseract is available."""
        try:
            version = pytesseract.get_tesseract_version()
            logger.info(f"Tesseract version: {version}")
            return True
        except Exception as e:
            logger.warning(f"Tesseract not available: {e}")
            return False

    def extract_text(
        self,
        image: NDArray[np.uint8],
        config: str | None = None,
    ) -> list[OCRResult]:
        """Extract text from an image using Tesseract.

        Args:
            image: Input image as numpy array (H, W, C) in RGB format
            config: Optional Tesseract configuration string (e.g., "--psm 3")

        Returns:
            List of OCRResult objects containing extracted text and metadata

        Raises:
            OCREngineNotAvailableError: If Tesseract is not available
            OCREngineError: If OCR processing fails
        """
        if not self._is_available:
            raise OCREngineNotAvailableError("Tesseract is not available. Please install Tesseract OCR.")

        try:
            # Default config if none provided
            if config is None:
                config = "--psm 3"

            # Extract text with detailed output
            data = pytesseract.image_to_data(image, config=config, output_type=Output.DICT)

            # Convert to OCRResult objects
            results: list[OCRResult] = []

            for i in range(len(data["text"])):
                text = data["text"][i].strip()

                # Skip empty text
                if not text:
                    continue

                # Get confidence (convert from 0-100 to 0.0-1.0)
                confidence = float(data["conf"][i]) / 100.0 if data["conf"][i] != -1 else 0.0

                # Get bounding box
                bbox = (int(data["left"][i]), int(data["top"][i]), int(data["width"][i]), int(data["height"][i]))

                results.append(
                    OCRResult(
                        text=text,
                        confidence=max(0.0, min(1.0, confidence)),  # Clamp to [0, 1]
                        bbox=bbox,
                    )
                )

            logger.debug(f"Extracted {len(results)} text regions using Tesseract")
            return results

        except Exception as e:
            raise OCREngineError(f"Tesseract OCR failed: {e}") from e

    def is_available(self) -> bool:
        """Check if Tesseract is available.

        Returns:
            True if Tesseract can be used, False otherwise
        """
        return self._is_available

    def get_engine_name(self) -> str:
        """Get the name of the OCR engine.

        Returns:
            "Tesseract"
        """
        return "Tesseract"
