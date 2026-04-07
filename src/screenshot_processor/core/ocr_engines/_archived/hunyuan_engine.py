"""HunyuanOCR Engine implementation via vLLM API.

This engine calls the HunyuanOCR vision LLM running on a vLLM endpoint
for high-quality OCR extraction.

API Endpoint: http://YOUR_OCR_HOST:8080/ocr
"""

from __future__ import annotations

import base64
import io
import logging
import os
import threading
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
DEFAULT_HUNYUAN_URL = "http://YOUR_OCR_HOST:8080"
DEFAULT_TIMEOUT = 120
DEFAULT_MAX_RETRIES = 3
DEFAULT_RATE_LIMIT = 5  # requests per second

# Hallucination patterns - when the model returns these instead of actual OCR text
# These indicate the model couldn't find text but hallucinated a response
HALLUCINATION_PATTERNS = [
    # English hallucinations
    "the final translation is",
    "this image is completely black",
    "this image is completely white",
    "this image is completely blank",  # Added
    "completely blank image",  # Added
    "this image contains no text",
    "there is no text in this image",
    "no visible content",
    "no visible objects",  # Added - catches "no visible objects, text, or..."
    "no text or objects",
    "no discernible content",  # Added
    "the image shows",  # Generic description instead of OCR
    "i can see",  # LLM-style response
    "the text in the image is:",  # Self-referential loop
    # Chinese "no text" responses (these are correct but not useful)
    "图片中没有文字",  # "There is no text in the image"
    "图片中没有可识别的文字",  # "No recognizable text in the image"
    "图片中没有任何文字",  # "No text at all in the image"
]


def _is_hallucination(text: str) -> bool:
    """Check if OCR result is a hallucination rather than actual text.

    Args:
        text: The OCR result text to check

    Returns:
        True if the text appears to be a hallucination, False otherwise
    """
    if not text:
        return False

    text_lower = text.lower().strip()

    # Check for known hallucination patterns
    for pattern in HALLUCINATION_PATTERNS:
        if pattern.lower() in text_lower:
            logger.debug(f"Detected hallucination pattern: '{pattern}' in '{text[:50]}...'")
            return True

    # Check for repetitive text (loop hallucination)
    # If the same phrase repeats 3+ times, it's likely a hallucination
    words = text_lower.split()
    if len(words) > 20:
        # Check for repeating sequences
        for seq_len in range(5, 15):
            if len(words) >= seq_len * 3:
                seq = " ".join(words[:seq_len])
                count = text_lower.count(seq)
                if count >= 3:
                    logger.debug(f"Detected repetitive hallucination: '{seq}' repeated {count} times")
                    return True

    return False


class RateLimiter:
    """Thread-safe token bucket rate limiter.

    Implements a simple rate limiter that allows up to `rate` requests per second.
    Uses a sliding window approach with blocking when limit is exceeded.
    """

    def __init__(self, rate: float, burst: int | None = None):
        """Initialize rate limiter.

        Args:
            rate: Maximum requests per second
            burst: Maximum burst size (defaults to rate)
        """
        self.rate = rate
        self.burst = burst or int(rate)
        self.tokens = float(self.burst)
        self.last_update = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, timeout: float = 30.0) -> bool:
        """Acquire a token, blocking if necessary.

        Args:
            timeout: Maximum time to wait for a token (seconds)

        Returns:
            True if token acquired, False if timeout
        """
        deadline = time.monotonic() + timeout

        while True:
            with self._lock:
                now = time.monotonic()
                # Refill tokens based on time elapsed
                elapsed = now - self.last_update
                self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
                self.last_update = now

                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return True

            # Check timeout
            if time.monotonic() >= deadline:
                return False

            # Wait before retrying (sleep for time to get 1 token)
            wait_time = min(1.0 / self.rate, deadline - time.monotonic())
            if wait_time > 0:
                time.sleep(wait_time)

    def try_acquire(self) -> bool:
        """Try to acquire a token without blocking.

        Returns:
            True if token acquired, False otherwise
        """
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False


class HunyuanOCREngine:
    """HunyuanOCR engine implementation via vLLM API.

    Calls the HunyuanOCR vision LLM for high-quality text extraction.
    Supports both single and batch processing modes.
    Includes rate limiting to prevent overwhelming the API.

    Example:
        >>> engine = HunyuanOCREngine()
        >>> results = engine.extract_text(image_array)
        >>> for result in results:
        ...     print(f"{result.text} (confidence: {result.confidence})")

        >>> # Batch processing
        >>> batch_results = engine.extract_text_batch([img1, img2, img3])
    """

    # Class-level rate limiter shared across all instances
    _rate_limiter: RateLimiter | None = None
    _rate_limiter_lock = threading.Lock()

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
        custom_prompt: str | None = None,
        rate_limit: float | None = None,
    ) -> None:
        """Initialize HunyuanOCR engine.

        Args:
            base_url: API endpoint URL. Defaults to HUNYUAN_OCR_URL env var
                     or http://YOUR_OCR_HOST:8080
            timeout: Request timeout in seconds. Defaults to 120.
            max_retries: Maximum retry attempts. Defaults to 3.
            custom_prompt: Custom prompt for OCR. Defaults to standard text recognition.
            rate_limit: Max requests per second. Defaults to HUNYUAN_OCR_RATE_LIMIT or 5.
        """
        self.base_url = (base_url or os.getenv("HUNYUAN_OCR_URL") or DEFAULT_HUNYUAN_URL).rstrip("/")

        self.timeout = timeout or int(os.getenv("HUNYUAN_OCR_TIMEOUT", DEFAULT_TIMEOUT))
        self.max_retries = max_retries or int(os.getenv("HUNYUAN_OCR_MAX_RETRIES", DEFAULT_MAX_RETRIES))
        self.custom_prompt = custom_prompt

        # Initialize rate limiter (shared across instances)
        rate = rate_limit or float(os.getenv("HUNYUAN_OCR_RATE_LIMIT", DEFAULT_RATE_LIMIT))
        self._init_rate_limiter(rate)

        self._is_available: bool | None = None  # Lazy check

        # Persistent HTTP client for connection reuse (avoids TCP/TLS setup per request)
        self._client = httpx.Client(timeout=self.timeout)
        self._health_client = httpx.Client(timeout=5)

        logger.info(f"HunyuanOCR engine initialized: {self.base_url} (rate limit: {rate}/s)")

    @classmethod
    def _init_rate_limiter(cls, rate: float) -> None:
        """Initialize the class-level rate limiter if not already done."""
        with cls._rate_limiter_lock:
            if cls._rate_limiter is None:
                cls._rate_limiter = RateLimiter(rate=rate, burst=max(1, int(rate)))
                logger.debug(f"Rate limiter initialized: {rate} req/s")

    def _wait_for_rate_limit(self) -> None:
        """Wait for rate limit token before making request."""
        if self._rate_limiter is not None:
            if not self._rate_limiter.acquire(timeout=self.timeout):
                raise OCREngineError("Rate limit timeout - too many requests queued")

    def _check_availability(self) -> bool:
        """Check if the HunyuanOCR API is reachable."""
        try:
            # Try health endpoint first
            try:
                response = self._health_client.get(f"{self.base_url}/health")
                if response.status_code == 200:
                    logger.info("HunyuanOCR API health check passed")
                    return True
            except httpx.HTTPError:
                pass

            # Fallback: try a minimal OCR request
            # 1x1 white PNG
            minimal_png = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
            )
            files = [("images", ("test.png", minimal_png, "image/png"))]
            response = self._health_client.post(f"{self.base_url}/ocr", files=files)
            if response.status_code == 200:
                logger.info("HunyuanOCR API is available (OCR test passed)")
                return True

            return False

        except Exception as e:
            logger.warning(f"HunyuanOCR API not available: {e}")
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
        prompt: str | None = None,
    ) -> dict:
        """Make OCR request to the API with retry logic and rate limiting."""
        files = [("images", (filename, image_bytes, "image/png"))]
        params = {}
        if prompt:
            params["prompt"] = prompt

        last_exception: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                # Wait for rate limit before each attempt
                self._wait_for_rate_limit()

                response = self._client.post(
                    f"{self.base_url}/ocr",
                    files=files,
                    params=params if params else None,
                )
                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                if 400 <= e.response.status_code < 500:
                    raise OCREngineError(f"HunyuanOCR client error: {e}") from e
                last_exception = e
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exception = e

            if attempt < self.max_retries - 1:
                wait_time = (2**attempt) * 1
                logger.debug(f"Retry {attempt + 1}/{self.max_retries} after {wait_time}s")
                time.sleep(wait_time)

        raise OCREngineError(f"HunyuanOCR request failed after {self.max_retries} retries: {last_exception}")

    def _make_batch_request(
        self,
        images: list[tuple[bytes, str]],
        prompt: str | None = None,
    ) -> list[dict]:
        """Make batch OCR request to the API with rate limiting."""
        files = [("images", (filename, image_bytes, "image/png")) for image_bytes, filename in images]
        params = {}
        if prompt:
            params["prompt"] = prompt

        last_exception: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                # Wait for rate limit before each attempt
                self._wait_for_rate_limit()

                response = self._client.post(
                    f"{self.base_url}/ocr",
                    files=files,
                    params=params if params else None,
                )
                response.raise_for_status()
                data = response.json()

                # API returns single dict for one image, {"results": [...]} for multiple
                if isinstance(data, dict) and "results" in data:
                    return data["results"]
                elif isinstance(data, list):
                    return data
                else:
                    return [data]

            except httpx.HTTPStatusError as e:
                if 400 <= e.response.status_code < 500:
                    raise OCREngineError(f"HunyuanOCR client error: {e}") from e
                last_exception = e
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exception = e

            if attempt < self.max_retries - 1:
                wait_time = (2**attempt) * 1
                time.sleep(wait_time)

        raise OCREngineError(f"HunyuanOCR batch request failed: {last_exception}")

    def extract_text(
        self,
        image: NDArray[np.uint8],
        config: str | None = None,
    ) -> list[OCRResult]:
        """Extract text from an image using HunyuanOCR API.

        Args:
            image: Input image as numpy array (H, W, C) in RGB format
            config: Optional custom prompt (overrides default)

        Returns:
            List of OCRResult objects containing extracted text

        Raises:
            OCREngineNotAvailableError: If API is not reachable
            OCREngineError: If OCR processing fails
        """
        if self._is_available is None:
            self._is_available = self._check_availability()

        if not self._is_available:
            raise OCREngineNotAvailableError(
                f"HunyuanOCR API not available at {self.base_url}. Check network connectivity or set HUNYUAN_OCR_URL."
            )

        try:
            image_bytes = self._numpy_to_png_bytes(image)
            # IMPORTANT: Generic prompts may return "<image>" - use specific OCR instruction
            prompt = config or self.custom_prompt or "Extract all text from this image"

            data = self._make_request(image_bytes, "image.png", prompt)

            # Extract text from response
            text = data.get("text", "")

            if not text:
                logger.debug("HunyuanOCR returned no text")
                return []

            # Check for hallucinations (model returning descriptions instead of OCR)
            if _is_hallucination(text):
                logger.warning(f"HunyuanOCR returned hallucination, treating as no text: '{text[:80]}...'")
                return []

            # HunyuanOCR returns full text, not word-by-word bboxes
            # Return as single result with high confidence
            result = OCRResult(
                text=text.strip(),
                confidence=0.95,  # Vision LLMs are generally high confidence
                bbox=None,  # No bbox available from this API
            )

            logger.debug(f"HunyuanOCR extracted {len(text)} characters")
            return [result]

        except OCREngineError:
            raise
        except Exception as e:
            raise OCREngineError(f"HunyuanOCR failed: {e}") from e

    def extract_text_batch(
        self,
        images: list[NDArray[np.uint8]],
        prompt: str | None = None,
    ) -> list[list[OCRResult]]:
        """Extract text from multiple images in a single batch request.

        More efficient than calling extract_text() multiple times.

        Args:
            images: List of input images as numpy arrays
            prompt: Optional custom prompt for all images

        Returns:
            List of OCRResult lists, one per input image

        Raises:
            OCREngineNotAvailableError: If API is not reachable
            OCREngineError: If OCR processing fails
        """
        if self._is_available is None:
            self._is_available = self._check_availability()

        if not self._is_available:
            raise OCREngineNotAvailableError(f"HunyuanOCR API not available at {self.base_url}")

        try:
            # Convert all images to PNG bytes
            image_data = []
            for i, image in enumerate(images):
                image_bytes = self._numpy_to_png_bytes(image)
                image_data.append((image_bytes, f"image_{i}.png"))

            # IMPORTANT: Generic prompts may return "<image>" - use specific OCR instruction
            effective_prompt = prompt or self.custom_prompt or "Extract all text from this image"

            # Make batch request
            results_data = self._make_batch_request(image_data, effective_prompt)

            # Convert to OCRResult lists, filtering hallucinations
            all_results: list[list[OCRResult]] = []

            for data in results_data:
                text = data.get("text", "")
                if text and not _is_hallucination(text):
                    all_results.append(
                        [
                            OCRResult(
                                text=text.strip(),
                                confidence=0.95,
                                bbox=None,
                            )
                        ]
                    )
                else:
                    if text and _is_hallucination(text):
                        logger.debug(f"Filtered hallucination in batch: '{text[:50]}...'")
                    all_results.append([])

            logger.debug(f"HunyuanOCR batch processed {len(images)} images")
            return all_results

        except OCREngineError:
            raise
        except Exception as e:
            raise OCREngineError(f"HunyuanOCR batch failed: {e}") from e

    def is_available(self) -> bool:
        """Check if HunyuanOCR API is available.

        Returns:
            True if API can be reached, False otherwise
        """
        if self._is_available is None:
            self._is_available = self._check_availability()
        return self._is_available

    def get_engine_name(self) -> str:
        """Get the name of the OCR engine.

        Returns:
            "HunyuanOCR"
        """
        return "HunyuanOCR"

    def close(self) -> None:
        """Close the persistent HTTP clients."""
        self._client.close()
        self._health_client.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass  # Best-effort cleanup during garbage collection; interpreter may be shutting down

    @classmethod
    def reset_rate_limiter(cls) -> None:
        """Reset the rate limiter (useful for testing)."""
        with cls._rate_limiter_lock:
            cls._rate_limiter = None
