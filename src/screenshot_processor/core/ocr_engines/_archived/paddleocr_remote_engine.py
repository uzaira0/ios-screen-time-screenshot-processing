"""PaddleOCR Remote Engine via HTTP API.

This engine calls the PaddleOCR server running in Docker for OCR with bounding boxes.

API Endpoint: http://YOUR_OCR_HOST:8081/ocr
"""

from __future__ import annotations

import io
import logging
import os
import time
from typing import TYPE_CHECKING

import httpx
import numpy as np
from PIL import Image

from ...ocr_protocol import OCREngineError, OCREngineNotAvailableError, OCRResult

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_PADDLEOCR_URL = "http://YOUR_OCR_HOST:8081"
DEFAULT_TIMEOUT = 60
DEFAULT_MAX_RETRIES = 3


class PaddleOCRRemoteEngine:
    """PaddleOCR engine implementation via HTTP API.

    Calls the PaddleOCR server for OCR with bounding box support.
    Returns both text and spatial location information.

    Example:
        >>> engine = PaddleOCRRemoteEngine()
        >>> results = engine.extract_text(image_array)
        >>> for result in results:
        ...     print(f"{result.text} at {result.bbox}")
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
    ) -> None:
        """Initialize PaddleOCR remote engine.

        Args:
            base_url: API endpoint URL. Defaults to PADDLEOCR_URL env var
                     or http://YOUR_OCR_HOST:8081
            timeout: Request timeout in seconds. Defaults to 60.
            max_retries: Maximum retry attempts. Defaults to 3.
        """
        self.base_url = (base_url or os.getenv("PADDLEOCR_URL") or DEFAULT_PADDLEOCR_URL).rstrip("/")

        self.timeout = timeout or int(os.getenv("PADDLEOCR_TIMEOUT", DEFAULT_TIMEOUT))
        self.max_retries = max_retries or int(os.getenv("PADDLEOCR_MAX_RETRIES", DEFAULT_MAX_RETRIES))

        self._is_available: bool | None = None  # Lazy check

        # Persistent HTTP client for connection reuse
        self._client = httpx.Client(timeout=self.timeout)
        self._health_client = httpx.Client(timeout=10)

        logger.info(f"PaddleOCR remote engine initialized: {self.base_url}")

    def _check_availability(self) -> bool:
        """Check if the PaddleOCR API is reachable."""
        try:
            response = self._health_client.get(f"{self.base_url}/health")
            if response.status_code == 200:
                logger.info("PaddleOCR API health check passed")
                return True
            return False
        except Exception as e:
            logger.warning(f"PaddleOCR API not available: {e}")
            return False

    def _numpy_to_png_bytes(self, image: NDArray[np.uint8]) -> bytes:
        """Convert numpy array to PNG bytes."""
        pil_image = Image.fromarray(image)
        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG")
        return buffer.getvalue()

    def _make_request(
        self,
        image_bytes: bytes,
        filename: str = "image.png",
    ) -> dict:
        """Make OCR request to the API with retry logic."""
        files = [("images", (filename, image_bytes, "image/png"))]

        last_exception: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                response = self._client.post(
                    f"{self.base_url}/ocr",
                    files=files,
                )
                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                if 400 <= e.response.status_code < 500:
                    raise OCREngineError(f"PaddleOCR client error: {e}") from e
                last_exception = e
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exception = e

            if attempt < self.max_retries - 1:
                wait_time = (2**attempt) * 1
                logger.debug(f"Retry {attempt + 1}/{self.max_retries} after {wait_time}s")
                time.sleep(wait_time)

        raise OCREngineError(f"PaddleOCR request failed after {self.max_retries} retries: {last_exception}")

    def extract_text(
        self,
        image: NDArray[np.uint8],
        config: str | None = None,
    ) -> list[OCRResult]:
        """Extract text from an image using PaddleOCR API.

        Args:
            image: Input image as numpy array (H, W, C) in RGB format
            config: Optional configuration (currently unused)

        Returns:
            List of OCRResult objects containing extracted text with bboxes

        Raises:
            OCREngineNotAvailableError: If API is not reachable
            OCREngineError: If OCR processing fails
        """
        if self._is_available is None:
            self._is_available = self._check_availability()

        if not self._is_available:
            raise OCREngineNotAvailableError(
                f"PaddleOCR API not available at {self.base_url}. Check network connectivity or set PADDLEOCR_URL."
            )

        try:
            image_bytes = self._numpy_to_png_bytes(image)
            data = self._make_request(image_bytes)

            results: list[OCRResult] = []

            # PaddleOCR returns detections with bboxes
            detections = data.get("detections", [])

            for det in detections:
                text = det.get("text", "").strip()
                if not text:
                    continue

                confidence = det.get("confidence", 0.0)

                # Extract bbox if available
                bbox = None
                if "bbox" in det:
                    bb = det["bbox"]
                    # Use `or 0` to handle both missing keys AND null values
                    bbox = (
                        int(bb.get("x") or 0),
                        int(bb.get("y") or 0),
                        int(bb.get("width") or 0),
                        int(bb.get("height") or 0),
                    )

                results.append(
                    OCRResult(
                        text=text,
                        confidence=min(1.0, max(0.0, confidence)),
                        bbox=bbox,
                    )
                )

            logger.debug(f"PaddleOCR extracted {len(results)} text regions")
            return results

        except OCREngineError:
            raise
        except Exception as e:
            raise OCREngineError(f"PaddleOCR failed: {e}") from e

    def extract_full_text(self, image: NDArray[np.uint8]) -> str:
        """Extract concatenated full text from image.

        Convenience method that returns just the text as a single string.

        Args:
            image: Input image as numpy array

        Returns:
            Full extracted text as a single string
        """
        if self._is_available is None:
            self._is_available = self._check_availability()

        if not self._is_available:
            raise OCREngineNotAvailableError(f"PaddleOCR API not available at {self.base_url}")

        try:
            image_bytes = self._numpy_to_png_bytes(image)
            data = self._make_request(image_bytes)
            return data.get("text", "")
        except OCREngineError:
            raise
        except Exception as e:
            raise OCREngineError(f"PaddleOCR failed: {e}") from e

    def is_available(self) -> bool:
        """Check if PaddleOCR API is available.

        Returns:
            True if API can be reached, False otherwise
        """
        if self._is_available is None:
            self._is_available = self._check_availability()
        return self._is_available

    def close(self) -> None:
        """Close the persistent HTTP clients."""
        self._client.close()
        self._health_client.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass  # Best-effort cleanup during garbage collection; interpreter may be shutting down

    def get_engine_name(self) -> str:
        """Get the name of the OCR engine.

        Returns:
            "PaddleOCR"
        """
        return "PaddleOCR"
