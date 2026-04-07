"""Hybrid OCR Engine with fallback chain.

This engine tries multiple OCR backends in priority order:
1. HunyuanOCR (vision LLM - best quality)
2. PaddleOCR (good quality with bboxes)
3. Tesseract (fast local fallback)

If the primary engine fails, it automatically falls back to the next available engine.

## Network Configuration

Remote engines (HunyuanOCR, PaddleOCR) are on a LOCAL NETWORK:
- HunyuanOCR: http://YOUR_OCR_HOST:8080 (vLLM endpoint)
- PaddleOCR:  http://YOUR_OCR_HOST:8081 (Docker container)

"Offline" = not connected to local network -> Tesseract fallback only.

## OCR Use Cases in iOS Screenshot Processing

There are 5 distinct OCR use cases in the pipeline. Choose the right method:

### Use Cases Requiring Bounding Boxes (use `extract_text_with_bboxes()`):

1. **Grid Anchor Detection** - Finding "12AM" and "60" text positions
   - Purpose: Locate bar graph boundaries for ROI extraction
   - Called by: `image_processor.py::find_left_anchor()`, `find_right_anchor()`
   - REQUIRES: Bounding boxes to determine pixel coordinates
   - Priority: PaddleOCR -> Tesseract (NO HunyuanOCR - it can't return bboxes)

### Use Cases Prioritizing Text Quality (use `extract_text()`):

2. **Title Extraction** - App name from top of screenshot
   - Purpose: Identify which app the usage data belongs to
   - Called by: `ocr.py::find_screenshot_title()`
   - REQUIRES: High accuracy for app name matching
   - Priority: HunyuanOCR -> PaddleOCR -> Tesseract

3. **Total Usage Extraction** - Time strings like "4h 36m"
   - Purpose: Extract aggregate usage for verification
   - Called by: `ocr.py::find_screenshot_total_usage()`
   - REQUIRES: Accurate time parsing
   - Priority: HunyuanOCR -> PaddleOCR -> Tesseract

4. **Daily Page Detection** - Check for "Daily Average" keywords
   - Purpose: Skip daily summary pages (not hourly data)
   - Called by: `ocr.py::is_daily_total_page()`
   - REQUIRES: Keyword matching only, moderate quality OK
   - Priority: HunyuanOCR -> PaddleOCR -> Tesseract

5. **Full Image OCR (PHI Detection)** - Extract all text from image
   - Purpose: Detect personally identifiable information
   - Called by: Pipeline Stage 3 (`apps/pipeline/`)
   - REQUIRES: Comprehensive text extraction
   - Priority: HunyuanOCR -> PaddleOCR -> Tesseract

### NOT an OCR Use Case:

- **Bar Graph Extraction** - Measuring hourly usage bars
  - Uses PIXEL COLOR ANALYSIS, not OCR
  - See: `image_processor.py::slice_image()`, `bar_processor.py`
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import numpy as np

from ...ocr_protocol import IOCREngine, OCREngineError, OCREngineNotAvailableError, OCRResult

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)


class HybridOCREngine:
    """Hybrid OCR engine with automatic fallback chain.

    Tries OCR engines in priority order, falling back on errors.
    Combines the best of each engine:
    - HunyuanOCR: Best text quality (vision LLM via vLLM)
    - PaddleOCR: Good quality with accurate bounding boxes (remote API)
    - Tesseract: Fast, always-available local fallback

    Two extraction methods with DIFFERENT priority orders:

    - `extract_text()`: Quality priority (HunyuanOCR -> PaddleOCR -> Tesseract)
      Use for: Title extraction, total usage, daily detection, PHI detection

    - `extract_text_with_bboxes()`: Bbox priority (PaddleOCR -> Tesseract ONLY)
      Use for: Grid anchor detection (finding "12AM", "60" positions)
      NOTE: HunyuanOCR is NOT used here - it cannot return bounding boxes

    Example:
        >>> engine = HybridOCREngine()
        >>> # For title extraction (quality priority)
        >>> results = engine.extract_text(title_region)
        >>> print(f"Used: {engine.last_engine_used}")  # HunyuanOCR
        >>>
        >>> # For grid detection (bbox priority)
        >>> results = engine.extract_text_with_bboxes(grid_region)
        >>> print(f"Used: {engine.last_engine_used}")  # PaddleOCR
        >>> for r in results:
        ...     print(f"{r.text} at {r.bbox}")
    """

    def __init__(
        self,
        hunyuan_url: str | None = None,
        paddleocr_url: str | None = None,
        hunyuan_timeout: int = 120,
        paddleocr_timeout: int = 60,
        enable_hunyuan: bool = True,
        enable_paddleocr: bool = True,
        enable_tesseract: bool = True,
        enable_leptess: bool = True,
    ) -> None:
        """Initialize hybrid OCR engine.

        Args:
            hunyuan_url: HunyuanOCR API URL (default from env or built-in)
            paddleocr_url: PaddleOCR API URL (default from env or built-in)
            hunyuan_timeout: Timeout for HunyuanOCR requests in seconds
            paddleocr_timeout: Timeout for PaddleOCR requests in seconds
            enable_hunyuan: Whether to try HunyuanOCR
            enable_paddleocr: Whether to try PaddleOCR
            enable_tesseract: Whether to try Tesseract as final fallback
            enable_leptess: Whether to try leptess (Rust Tesseract C API) before pytesseract
        """
        self.hunyuan_url = hunyuan_url
        self.paddleocr_url = paddleocr_url
        self.hunyuan_timeout = hunyuan_timeout
        self.paddleocr_timeout = paddleocr_timeout
        self.enable_hunyuan = enable_hunyuan
        self.enable_paddleocr = enable_paddleocr
        self.enable_tesseract = enable_tesseract
        self.enable_leptess = enable_leptess

        # Track which engine was used for the last call
        self.last_engine_used: str | None = None

        # Lazy-loaded engines
        self._hunyuan_engine: IOCREngine | None = None
        self._paddleocr_engine: IOCREngine | None = None
        self._tesseract_engine: IOCREngine | None = None
        self._leptess_engine: IOCREngine | None = None

        # Track availability
        self._hunyuan_available: bool | None = None
        self._paddleocr_available: bool | None = None
        self._tesseract_available: bool | None = None
        self._leptess_available: bool | None = None

        logger.info(
            f"HybridOCREngine initialized: leptess={enable_leptess}, "
            f"tesseract={enable_tesseract}, hunyuan={enable_hunyuan}, "
            f"paddleocr={enable_paddleocr}"
        )

    def _get_hunyuan_engine(self) -> IOCREngine | None:
        """Lazy-load HunyuanOCR engine."""
        if not self.enable_hunyuan:
            return None

        if self._hunyuan_engine is None and self._hunyuan_available is not False:
            try:
                from .hunyuan_engine import HunyuanOCREngine

                kwargs: dict[str, Any] = {"timeout": self.hunyuan_timeout}
                if self.hunyuan_url:
                    kwargs["base_url"] = self.hunyuan_url

                self._hunyuan_engine = HunyuanOCREngine(**kwargs)
                self._hunyuan_available = self._hunyuan_engine.is_available()

                if not self._hunyuan_available:
                    logger.warning("HunyuanOCR not available")
                    self._hunyuan_engine = None
                else:
                    logger.info("HunyuanOCR engine loaded and available")

            except Exception as e:
                logger.warning(f"Failed to load HunyuanOCR: {e}")
                self._hunyuan_available = False

        return self._hunyuan_engine if self._hunyuan_available else None

    def _get_paddleocr_engine(self) -> IOCREngine | None:
        """Lazy-load PaddleOCR engine (remote API version)."""
        if not self.enable_paddleocr:
            return None

        if self._paddleocr_engine is None and self._paddleocr_available is not False:
            try:
                from .paddleocr_remote_engine import PaddleOCRRemoteEngine

                kwargs: dict[str, Any] = {"timeout": self.paddleocr_timeout}
                if self.paddleocr_url:
                    kwargs["base_url"] = self.paddleocr_url

                self._paddleocr_engine = PaddleOCRRemoteEngine(**kwargs)
                self._paddleocr_available = self._paddleocr_engine.is_available()

                if not self._paddleocr_available:
                    logger.warning("PaddleOCR (remote) not available")
                    self._paddleocr_engine = None
                else:
                    logger.info("PaddleOCR (remote) engine loaded and available")

            except Exception as e:
                logger.warning(f"Failed to load PaddleOCR (remote): {e}")
                self._paddleocr_available = False

        return self._paddleocr_engine if self._paddleocr_available else None

    def _get_tesseract_engine(self) -> IOCREngine | None:
        """Lazy-load Tesseract engine."""
        if not self.enable_tesseract:
            return None

        if self._tesseract_engine is None and self._tesseract_available is not False:
            try:
                from ..tesseract_engine import TesseractOCREngine

                self._tesseract_engine = TesseractOCREngine()
                self._tesseract_available = self._tesseract_engine.is_available()

                if not self._tesseract_available:
                    logger.warning("Tesseract not available")
                    self._tesseract_engine = None
                else:
                    logger.info("Tesseract engine loaded and available")

            except Exception as e:
                logger.warning(f"Failed to load Tesseract: {e}")
                self._tesseract_available = False

        return self._tesseract_engine if self._tesseract_available else None

    def _get_leptess_engine(self) -> IOCREngine | None:
        """Lazy-load leptess engine (Rust Tesseract C API)."""
        if not self.enable_leptess:
            return None

        if self._leptess_engine is None and self._leptess_available is not False:
            try:
                from ..leptess_engine import LeptessOCREngine

                self._leptess_engine = LeptessOCREngine()
                self._leptess_available = self._leptess_engine.is_available()

                if not self._leptess_available:
                    logger.warning("leptess (Rust) not available, will use pytesseract")
                    self._leptess_engine = None
                else:
                    logger.info("leptess (Rust) engine loaded and available")

            except Exception as e:
                logger.warning(f"Failed to load leptess: {e}")
                self._leptess_available = False

        return self._leptess_engine if self._leptess_available else None

    def extract_text(
        self,
        image: NDArray[np.uint8],
        config: str | None = None,
    ) -> list[OCRResult]:
        """Extract text using the quality-priority fallback chain.

        Tries engines in order: HunyuanOCR -> PaddleOCR -> Tesseract

        USE THIS METHOD FOR:
        - Title extraction (app names)
        - Total usage extraction ("4h 36m")
        - Daily page detection ("Daily Average")
        - Full image OCR for PHI detection

        DO NOT USE FOR:
        - Grid anchor detection (use extract_text_with_bboxes instead)

        Args:
            image: Input image as numpy array (H, W, C) in RGB format
            config: Optional engine-specific configuration string

        Returns:
            List of OCRResult objects from the first successful engine

        Raises:
            OCREngineNotAvailableError: If no engines are available
            OCREngineError: If all engines fail
        """
        errors: list[tuple[str, Exception]] = []

        # Try leptess first (Rust Tesseract C API — fastest local option)
        leptess = self._get_leptess_engine()
        if leptess:
            try:
                logger.debug("Trying leptess (Rust)...")
                results = leptess.extract_text(image, config)
                self.last_engine_used = "leptess"
                logger.debug(f"leptess succeeded: {len(results)} results")
                return results
            except OCREngineError as e:
                logger.warning(f"leptess failed: {e}")
                errors.append(("leptess", e))
            except Exception as e:
                logger.warning(f"leptess unexpected error: {e}")
                errors.append(("leptess", e))

        # Try HunyuanOCR (disabled by default — remote, slow to connect)
        hunyuan = self._get_hunyuan_engine()
        if hunyuan:
            try:
                logger.debug("Trying HunyuanOCR...")
                results = hunyuan.extract_text(image, config)
                self.last_engine_used = "HunyuanOCR"
                logger.debug(f"HunyuanOCR succeeded: {len(results)} results")
                return results
            except OCREngineError as e:
                logger.warning(f"HunyuanOCR failed: {e}")
                errors.append(("HunyuanOCR", e))
            except Exception as e:
                logger.warning(f"HunyuanOCR unexpected error: {e}")
                errors.append(("HunyuanOCR", e))

        # Try PaddleOCR (disabled by default — remote, slow to connect)
        paddleocr = self._get_paddleocr_engine()
        if paddleocr:
            try:
                logger.debug("Trying PaddleOCR...")
                results = paddleocr.extract_text(image, config)
                self.last_engine_used = "PaddleOCR"
                logger.debug(f"PaddleOCR succeeded: {len(results)} results")
                return results
            except OCREngineError as e:
                logger.warning(f"PaddleOCR failed: {e}")
                errors.append(("PaddleOCR", e))
            except Exception as e:
                logger.warning(f"PaddleOCR unexpected error: {e}")
                errors.append(("PaddleOCR", e))

        # Try pytesseract as final fallback
        tesseract = self._get_tesseract_engine()
        if tesseract:
            try:
                logger.debug("Trying pytesseract...")
                results = tesseract.extract_text(image, config)
                self.last_engine_used = "Tesseract"
                logger.debug(f"pytesseract succeeded: {len(results)} results")
                return results
            except OCREngineError as e:
                logger.warning(f"pytesseract failed: {e}")
                errors.append(("Tesseract", e))
            except Exception as e:
                logger.warning(f"pytesseract unexpected error: {e}")
                errors.append(("Tesseract", e))

        # All engines failed
        self.last_engine_used = None

        if not errors:
            raise OCREngineNotAvailableError("No OCR engines available. Enable at least one engine.")

        error_summary = "; ".join(f"{name}: {err}" for name, err in errors)
        raise OCREngineError(f"All OCR engines failed: {error_summary}")

    def extract_text_with_bboxes(
        self,
        image: NDArray[np.uint8],
        config: str | None = None,
    ) -> list[OCRResult]:
        """Extract text with bounding boxes. HunyuanOCR is NOT used here.

        Priority: PaddleOCR -> Tesseract (NO HunyuanOCR - it can't return bboxes)

        USE THIS METHOD FOR:
        - Grid anchor detection (finding "12AM", "60" text positions)
        - Any use case requiring pixel coordinates of detected text

        DO NOT USE HunyuanOCR for this - it cannot return bounding boxes.
        HunyuanOCR should only be used on regions already cropped by bbox
        coordinates from PaddleOCR/Tesseract, or for full-image text extraction.

        The bounding box coordinates are used to determine the bar graph ROI
        boundaries in image_processor.py::find_left_anchor/find_right_anchor.

        Args:
            image: Input image as numpy array (H, W, C) in RGB format
            config: Optional engine-specific configuration string

        Returns:
            List of OCRResult objects with bbox attribute populated
            (bbox format: (x, y, width, height) in pixels)

        Raises:
            OCREngineNotAvailableError: If no bbox-capable engines available
        """
        errors: list[tuple[str, Exception]] = []

        # Try leptess first (Rust Tesseract C API — returns bboxes, fastest)
        leptess = self._get_leptess_engine()
        if leptess:
            try:
                results = leptess.extract_text(image, config)
                self.last_engine_used = "leptess"
                return results
            except Exception as e:
                errors.append(("leptess", e))

        # Try PaddleOCR (disabled by default — remote, slow to connect)
        paddleocr = self._get_paddleocr_engine()
        if paddleocr:
            try:
                results = paddleocr.extract_text(image, config)
                self.last_engine_used = "PaddleOCR"
                return results
            except Exception as e:
                errors.append(("PaddleOCR", e))

        # Try pytesseract as final fallback (has bboxes, always available locally)
        tesseract = self._get_tesseract_engine()
        if tesseract:
            try:
                results = tesseract.extract_text(image, config)
                self.last_engine_used = "Tesseract"
                return results
            except Exception as e:
                errors.append(("Tesseract", e))

        self.last_engine_used = None
        if not errors:
            raise OCREngineNotAvailableError("No bbox-capable OCR engines available")
        raise OCREngineError(f"All bbox-capable OCR engines failed: {errors}")

    def is_available(self) -> bool:
        """Check if at least one OCR engine is available.

        Returns:
            True if any engine is available
        """
        return any(
            [
                self._get_leptess_engine() is not None,
                self._get_tesseract_engine() is not None,
                self._get_hunyuan_engine() is not None,
                self._get_paddleocr_engine() is not None,
            ]
        )

    def get_engine_name(self) -> str:
        """Get the name of this engine.

        Returns:
            "HybridOCR"
        """
        return "HybridOCR"

    def get_available_engines(self) -> list[str]:
        """Get list of available engines.

        Returns:
            List of available engine names
        """
        available = []
        if self._get_leptess_engine():
            available.append("leptess")
        if self._get_hunyuan_engine():
            available.append("HunyuanOCR")
        if self._get_paddleocr_engine():
            available.append("PaddleOCR")
        if self._get_tesseract_engine():
            available.append("Tesseract")
        return available
