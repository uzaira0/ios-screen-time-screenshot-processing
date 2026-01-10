"""Rust-native OCR engine using screenshot_processor_rs (leptess via PyO3).

Calls Tesseract through leptess's C API (set_image_from_mem) instead of
pytesseract's subprocess, eliminating Python↔process serialization overhead.

Usage:
    >>> engine = RustOCREngine()
    >>> result = engine.extract(image_bytes)

Install:
    cd rust-python && maturin develop --release
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from phi_detector_remover.core.models import BoundingBox, OCRResult, OCRWord

logger = logging.getLogger(__name__)

_RUST_AVAILABLE: bool | None = None


def _check_rust() -> bool:
    global _RUST_AVAILABLE
    if _RUST_AVAILABLE is None:
        try:
            import screenshot_processor_rs

            screenshot_processor_rs.normalize_ocr_digits("test")
            _RUST_AVAILABLE = True
        except ImportError:
            _RUST_AVAILABLE = False
    return _RUST_AVAILABLE


class RustOCREngine:
    """OCR engine using Rust leptess binding (Tesseract C API, no subprocess).

    Same Tesseract engine, but called via leptess's direct C API through
    the PyO3 screenshot_processor_rs extension. Avoids pytesseract's
    subprocess spawn + PIL conversion overhead.
    """

    def __init__(self, lang: str = "eng", psm: int = 3, **kwargs):
        self.lang = lang
        self.psm = psm

    @property
    def name(self) -> str:
        return "leptess"

    def is_available(self) -> bool:
        return _check_rust()

    def extract(self, image: bytes | np.ndarray) -> OCRResult:
        """Extract text with word-level bounding boxes via Rust leptess."""
        import screenshot_processor_rs as rs

        # Convert to PNG bytes for the Rust module
        if isinstance(image, bytes):
            image_bytes = image
        else:
            _, buffer = cv2.imencode(".png", image)
            image_bytes = buffer.tobytes()

        # Call Rust OCR (leptess C API → Tesseract, no subprocess)
        raw_words = rs.ocr_extract(image_bytes, str(self.psm))

        words = []
        text_parts = []
        confidence_scores = []

        for w in raw_words:
            text = w["text"]
            if not text:
                continue

            word = OCRWord(
                text=text,
                confidence=0.9,  # leptess doesn't return per-word confidence
                bbox=BoundingBox(
                    x=w["x"],
                    y=w["y"],
                    width=w["w"],
                    height=w["h"],
                ),
            )
            words.append(word)
            text_parts.append(text)
            confidence_scores.append(0.9)

        overall_confidence = (
            sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
        )

        return OCRResult(
            text=" ".join(text_parts),
            words=words,
            confidence=overall_confidence,
            engine=self.name,
        )
