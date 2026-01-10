"""Leptess OCR Engine — Tesseract via Rust C API (no subprocess).

Wraps screenshot_processor_rs.ocr_extract (PyO3 + leptess binding) to
conform to the IOCREngine protocol. Faster than pytesseract because it
avoids the subprocess spawn and PIL conversion overhead.
"""

from __future__ import annotations

import logging

import numpy as np

from ..ocr_protocol import OCREngineError, OCREngineNotAvailableError, OCRResult

logger = logging.getLogger(__name__)

_AVAILABLE: bool | None = None


def _check_available() -> bool:
    global _AVAILABLE
    if _AVAILABLE is None:
        try:
            import screenshot_processor_rs  # pyright: ignore[reportMissingImports]

            screenshot_processor_rs.normalize_ocr_digits("test")
            _AVAILABLE = True
            logger.info("screenshot_processor_rs (leptess) available")
        except ImportError:
            _AVAILABLE = False
            logger.info("screenshot_processor_rs not available, leptess engine disabled")
    return _AVAILABLE


class LeptessOCREngine:
    """OCR engine using Rust leptess (Tesseract C API, no subprocess).

    Conforms to the IOCREngine protocol used by HybridOCREngine.
    """

    def __init__(self, psm: int = 3) -> None:
        self.psm = psm
        self._available = _check_available()

    def is_available(self) -> bool:
        return self._available

    def get_engine_name(self) -> str:
        return "leptess"

    def extract_text(
        self,
        image: np.ndarray,
        config: str | None = None,
    ) -> list[OCRResult]:
        if not self._available:
            raise OCREngineNotAvailableError("screenshot_processor_rs (leptess) is not installed")

        try:
            import cv2
            import screenshot_processor_rs as rs  # pyright: ignore[reportMissingImports]

            # Determine PSM from config string (e.g. "--psm 7") or fall back to default
            psm = self.psm
            if config:
                parts = config.split()
                for i, p in enumerate(parts):
                    if p == "--psm" and i + 1 < len(parts):
                        try:
                            psm = int(parts[i + 1])
                        except ValueError:
                            pass

            _, buf = cv2.imencode(".png", image)
            image_bytes = buf.tobytes()

            raw_words = rs.ocr_extract(image_bytes, str(psm))

            results: list[OCRResult] = []
            for w in raw_words:
                text = (w.get("text") or "").strip()
                if not text:
                    continue
                bbox = (int(w["x"]), int(w["y"]), int(w["w"]), int(w["h"]))
                results.append(OCRResult(text=text, confidence=0.9, bbox=bbox))

            logger.debug("leptess extracted %d regions", len(results))
            return results

        except OCREngineNotAvailableError:
            raise
        except Exception as e:
            raise OCREngineError(f"leptess OCR failed: {e}") from e
