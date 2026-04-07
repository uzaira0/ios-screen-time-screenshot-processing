"""PaddleOCR Engine implementation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from ..ocr_protocol import OCREngineError, OCREngineNotAvailableError, OCRResult

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)


class PaddleOCREngine:
    """PaddleOCR engine implementation.

    Uses PaddleOCR for text extraction. PaddleOCR is a lightweight OCR engine
    that works well for English and Chinese text, and doesn't require external
    binaries like Tesseract.
    """

    def __init__(
        self,
        lang: str = "en",
        use_angle_cls: bool = True,
        use_gpu: bool = False,
        show_log: bool = False,
    ) -> None:
        """Initialize PaddleOCR engine.

        Args:
            lang: Language code (default: "en" for English)
            use_angle_cls: Whether to use angle classification (helps with rotated text)
            use_gpu: Whether to use GPU acceleration (note: may not be supported in all versions)
            show_log: Whether to show PaddleOCR logs
        """
        self.lang = lang
        self.use_angle_cls = use_angle_cls
        self.use_gpu = use_gpu
        self.show_log = show_log

        self._ocr_instance = None
        self._is_available = self._check_availability()

    def _check_availability(self) -> bool:
        """Check if PaddleOCR is available and initialize it."""
        try:
            from paddleocr import PaddleOCR

            # Initialize PaddleOCR (downloads models on first use)
            # Note: Some parameters may not be supported in all versions
            # Start with core parameters that are always supported
            init_kwargs = {
                "lang": self.lang,
                "use_angle_cls": self.use_angle_cls,
            }

            # Check which optional parameters are supported by inspecting the signature
            import inspect

            try:
                sig = inspect.signature(PaddleOCR.__init__)
                supported_params = set(sig.parameters.keys())

                # Add optional parameters if they're supported
                if "use_gpu" in supported_params and self.use_gpu is not None:
                    init_kwargs["use_gpu"] = self.use_gpu
                if "show_log" in supported_params and self.show_log is not None:
                    init_kwargs["show_log"] = self.show_log

            except Exception as e:
                # If inspection fails, just try with base parameters
                logger.debug(f"Could not inspect PaddleOCR signature: {e}")

            # Create the instance once with the supported parameters
            self._ocr_instance = PaddleOCR(**init_kwargs)

            logger.info(f"PaddleOCR initialized successfully (lang={self.lang})")
            return True

        except ImportError:
            logger.warning("PaddleOCR not available. Install with: pip install paddleocr")
            return False
        except Exception as e:
            logger.warning(f"Failed to initialize PaddleOCR: {e}")
            return False

    def extract_text(
        self,
        image: NDArray[np.uint8],
        config: str | None = None,
    ) -> list[OCRResult]:
        """Extract text from an image using PaddleOCR.

        Args:
            image: Input image as numpy array (H, W, C) in RGB format
            config: Optional configuration (unused for PaddleOCR, kept for protocol compatibility)

        Returns:
            List of OCRResult objects containing extracted text and metadata

        Raises:
            OCREngineNotAvailableError: If PaddleOCR is not available
            OCREngineError: If OCR processing fails
        """
        if not self._is_available or self._ocr_instance is None:
            raise OCREngineNotAvailableError("PaddleOCR is not available. Install with: pip install paddleocr")

        try:
            # PaddleOCR expects BGR format (OpenCV default), but we receive RGB
            # Convert RGB to BGR
            image_bgr = image[:, :, ::-1] if image.ndim == 3 else image

            # Run OCR
            # Returns: [
            #   [[[x1,y1], [x2,y2], [x3,y3], [x4,y4]], (text, confidence)],
            #   ...
            # ]
            ocr_result = self._ocr_instance.ocr(image_bgr, cls=self.use_angle_cls)

            # Convert to OCRResult objects
            results: list[OCRResult] = []

            if ocr_result is None or len(ocr_result) == 0:
                logger.debug("PaddleOCR returned no results")
                return results

            # PaddleOCR returns nested list structure
            for line in ocr_result[0] if ocr_result[0] is not None else []:
                if line is None:
                    continue

                bbox_points, (text, confidence) = line

                # Skip empty text
                if not text or not text.strip():
                    continue

                # Convert polygon bbox to rectangle (x, y, w, h)
                # bbox_points is [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                x_coords = [int(point[0]) for point in bbox_points]
                y_coords = [int(point[1]) for point in bbox_points]

                x_min = min(x_coords)
                y_min = min(y_coords)
                x_max = max(x_coords)
                y_max = max(y_coords)

                bbox = (x_min, y_min, x_max - x_min, y_max - y_min)

                # Ensure confidence is in [0, 1] range
                confidence = max(0.0, min(1.0, float(confidence)))

                results.append(OCRResult(text=text.strip(), confidence=confidence, bbox=bbox))

            logger.debug(f"Extracted {len(results)} text regions using PaddleOCR")
            return results

        except Exception as e:
            raise OCREngineError(f"PaddleOCR failed: {e}") from e

    def is_available(self) -> bool:
        """Check if PaddleOCR is available.

        Returns:
            True if PaddleOCR can be used, False otherwise
        """
        return self._is_available

    def get_engine_name(self) -> str:
        """Get the name of the OCR engine.

        Returns:
            "PaddleOCR"
        """
        return "PaddleOCR"
