"""Tests for HybridOCREngine fallback logic and TesseractOCREngine.

All remote HTTP calls (HunyuanOCR, PaddleOCR) are mocked.
Focus: fallback ordering, error recovery, availability detection,
edge cases on input, and configuration.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from screenshot_processor.core.ocr_protocol import (
    IOCREngine,
    OCREngineError,
    OCREngineNotAvailableError,
    OCRResult,
)
from screenshot_processor.core.ocr_engines.hybrid_engine import HybridOCREngine  # pyright: ignore[reportMissingImports]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dummy_image(h: int = 100, w: int = 200) -> np.ndarray:
    """Create a minimal RGB image array."""
    return np.zeros((h, w, 3), dtype=np.uint8)


def _mock_engine(name: str, *, available: bool = True, results: list[OCRResult] | None = None,
                 error: Exception | None = None) -> MagicMock:
    """Create a mock OCR engine conforming to IOCREngine."""
    engine = MagicMock(spec=["extract_text", "is_available", "get_engine_name"])
    engine.is_available.return_value = available
    engine.get_engine_name.return_value = name
    if error:
        engine.extract_text.side_effect = error
    else:
        engine.extract_text.return_value = results or [OCRResult(text="hello", confidence=0.9)]
    return engine


# ---------------------------------------------------------------------------
# OCRResult tests
# ---------------------------------------------------------------------------


class TestOCRResult:
    def test_valid_result(self):
        r = OCRResult(text="abc", confidence=0.5, bbox=(0, 0, 10, 10))
        assert r.text == "abc"
        assert r.confidence == 0.5
        assert r.bbox == (0, 0, 10, 10)

    def test_confidence_boundary_zero(self):
        r = OCRResult(text="x", confidence=0.0)
        assert r.confidence == 0.0

    def test_confidence_boundary_one(self):
        r = OCRResult(text="x", confidence=1.0)
        assert r.confidence == 1.0

    def test_confidence_below_zero_raises(self):
        with pytest.raises(ValueError, match="Confidence"):
            OCRResult(text="x", confidence=-0.1)

    def test_confidence_above_one_raises(self):
        with pytest.raises(ValueError, match="Confidence"):
            OCRResult(text="x", confidence=1.1)

    def test_bbox_default_none(self):
        r = OCRResult(text="x", confidence=0.5)
        assert r.bbox is None

    def test_frozen(self):
        r = OCRResult(text="x", confidence=0.5)
        with pytest.raises(AttributeError):
            r.text = "y"


# ---------------------------------------------------------------------------
# HybridOCREngine – init & configuration
# ---------------------------------------------------------------------------


class TestHybridOCREngineConfig:
    def test_default_enables_all_engines(self):
        engine = HybridOCREngine()
        assert engine.enable_hunyuan is True
        assert engine.enable_paddleocr is True
        assert engine.enable_tesseract is True

    def test_disable_specific_engines(self):
        engine = HybridOCREngine(enable_hunyuan=False, enable_paddleocr=False)
        assert engine.enable_hunyuan is False
        assert engine.enable_paddleocr is False
        assert engine.enable_tesseract is True

    def test_custom_urls(self):
        engine = HybridOCREngine(hunyuan_url="http://h:8080", paddleocr_url="http://p:8081")
        assert engine.hunyuan_url == "http://h:8080"
        assert engine.paddleocr_url == "http://p:8081"

    def test_custom_timeouts(self):
        engine = HybridOCREngine(hunyuan_timeout=30, paddleocr_timeout=15)
        assert engine.hunyuan_timeout == 30
        assert engine.paddleocr_timeout == 15

    def test_engine_name(self):
        assert HybridOCREngine().get_engine_name() == "HybridOCR"

    def test_last_engine_used_initially_none(self):
        assert HybridOCREngine().last_engine_used is None


# ---------------------------------------------------------------------------
# HybridOCREngine – extract_text fallback chain
# ---------------------------------------------------------------------------


class TestHybridExtractTextFallback:
    def test_uses_hunyuan_first_when_available(self):
        engine = HybridOCREngine(enable_hunyuan=True, enable_paddleocr=False, enable_tesseract=False)
        mock_h = _mock_engine("HunyuanOCR")
        engine._hunyuan_engine = mock_h
        engine._hunyuan_available = True

        result = engine.extract_text(_dummy_image())
        assert engine.last_engine_used == "HunyuanOCR"
        mock_h.extract_text.assert_called_once()

    def test_falls_back_to_paddleocr_when_hunyuan_fails(self):
        engine = HybridOCREngine(enable_tesseract=False)
        engine._hunyuan_engine = _mock_engine("HunyuanOCR", error=OCREngineError("timeout"))
        engine._hunyuan_available = True
        engine._paddleocr_engine = _mock_engine("PaddleOCR")
        engine._paddleocr_available = True

        result = engine.extract_text(_dummy_image())
        assert engine.last_engine_used == "PaddleOCR"

    def test_falls_back_to_tesseract_when_others_fail(self):
        engine = HybridOCREngine()
        engine._hunyuan_engine = _mock_engine("HunyuanOCR", error=OCREngineError("fail"))
        engine._hunyuan_available = True
        engine._paddleocr_engine = _mock_engine("PaddleOCR", error=OCREngineError("fail"))
        engine._paddleocr_available = True
        engine._tesseract_engine = _mock_engine("Tesseract")
        engine._tesseract_available = True

        result = engine.extract_text(_dummy_image())
        assert engine.last_engine_used == "Tesseract"

    def test_raises_when_all_engines_fail(self):
        engine = HybridOCREngine()
        engine._hunyuan_engine = _mock_engine("H", error=OCREngineError("h"))
        engine._hunyuan_available = True
        engine._paddleocr_engine = _mock_engine("P", error=OCREngineError("p"))
        engine._paddleocr_available = True
        engine._tesseract_engine = _mock_engine("T", error=OCREngineError("t"))
        engine._tesseract_available = True

        with pytest.raises(OCREngineError, match="All OCR engines failed"):
            engine.extract_text(_dummy_image())
        assert engine.last_engine_used is None

    def test_raises_when_no_engines_enabled(self):
        engine = HybridOCREngine(enable_hunyuan=False, enable_paddleocr=False, enable_tesseract=False)
        with pytest.raises(OCREngineNotAvailableError, match="No OCR engines available"):
            engine.extract_text(_dummy_image())

    def test_skips_disabled_engines(self):
        engine = HybridOCREngine(enable_hunyuan=False, enable_paddleocr=False, enable_tesseract=True)
        engine._tesseract_engine = _mock_engine("Tesseract")
        engine._tesseract_available = True

        engine.extract_text(_dummy_image())
        assert engine.last_engine_used == "Tesseract"

    def test_handles_unexpected_exception_types(self):
        """Non-OCREngineError exceptions should still trigger fallback."""
        engine = HybridOCREngine(enable_paddleocr=False)
        engine._hunyuan_engine = _mock_engine("H", error=RuntimeError("boom"))
        engine._hunyuan_available = True
        engine._tesseract_engine = _mock_engine("Tesseract")
        engine._tesseract_available = True

        result = engine.extract_text(_dummy_image())
        assert engine.last_engine_used == "Tesseract"


# ---------------------------------------------------------------------------
# HybridOCREngine – extract_text_with_bboxes
# ---------------------------------------------------------------------------


class TestHybridExtractTextWithBboxes:
    def test_does_not_use_hunyuan(self):
        """HunyuanOCR cannot return bboxes – must never be tried."""
        engine = HybridOCREngine()
        mock_h = _mock_engine("HunyuanOCR")
        engine._hunyuan_engine = mock_h
        engine._hunyuan_available = True
        engine._paddleocr_engine = _mock_engine("PaddleOCR")
        engine._paddleocr_available = True

        engine.extract_text_with_bboxes(_dummy_image())
        mock_h.extract_text.assert_not_called()
        assert engine.last_engine_used == "PaddleOCR"

    def test_falls_back_to_tesseract(self):
        engine = HybridOCREngine(enable_paddleocr=True, enable_tesseract=True)
        engine._paddleocr_engine = _mock_engine("P", error=OCREngineError("fail"))
        engine._paddleocr_available = True
        engine._tesseract_engine = _mock_engine("Tesseract")
        engine._tesseract_available = True

        engine.extract_text_with_bboxes(_dummy_image())
        assert engine.last_engine_used == "Tesseract"

    def test_raises_when_no_bbox_engines_available(self):
        engine = HybridOCREngine(enable_hunyuan=True, enable_paddleocr=False, enable_tesseract=False)
        with pytest.raises(OCREngineNotAvailableError, match="bbox-capable"):
            engine.extract_text_with_bboxes(_dummy_image())

    def test_raises_when_all_bbox_engines_fail(self):
        engine = HybridOCREngine()
        engine._paddleocr_engine = _mock_engine("P", error=OCREngineError("p"))
        engine._paddleocr_available = True
        engine._tesseract_engine = _mock_engine("T", error=OCREngineError("t"))
        engine._tesseract_available = True

        with pytest.raises(OCREngineError, match="bbox-capable OCR engines failed"):
            engine.extract_text_with_bboxes(_dummy_image())


# ---------------------------------------------------------------------------
# HybridOCREngine – availability
# ---------------------------------------------------------------------------


class TestHybridAvailability:
    def test_available_when_tesseract_works(self):
        engine = HybridOCREngine(enable_hunyuan=False, enable_paddleocr=False)
        engine._tesseract_engine = _mock_engine("Tesseract", available=True)
        engine._tesseract_available = True
        assert engine.is_available() is True

    def test_not_available_when_all_disabled(self):
        engine = HybridOCREngine(enable_hunyuan=False, enable_paddleocr=False, enable_tesseract=False)
        assert engine.is_available() is False

    def test_get_available_engines_list(self):
        engine = HybridOCREngine(enable_hunyuan=False, enable_paddleocr=False)
        engine._tesseract_engine = _mock_engine("Tesseract")
        engine._tesseract_available = True
        available = engine.get_available_engines()
        assert "Tesseract" in available
        assert "HunyuanOCR" not in available


# ---------------------------------------------------------------------------
# HybridOCREngine – lazy loading error paths
# ---------------------------------------------------------------------------


class TestHybridLazyLoading:
    def test_hunyuan_import_failure_marks_unavailable(self):
        engine = HybridOCREngine(enable_hunyuan=True)
        with patch.dict("sys.modules", {"screenshot_processor.core.ocr_engines.hunyuan_engine": None}):
            # Force re-evaluation
            engine._hunyuan_available = None
            engine._hunyuan_engine = None
            result = engine._get_hunyuan_engine()
        # Should not crash, just return None
        assert result is None

    def test_paddleocr_import_failure_marks_unavailable(self):
        engine = HybridOCREngine(enable_paddleocr=True)
        with patch.dict("sys.modules", {"screenshot_processor.core.ocr_engines.paddleocr_remote_engine": None}):
            engine._paddleocr_available = None
            engine._paddleocr_engine = None
            result = engine._get_paddleocr_engine()
        assert result is None

    def test_disabled_engine_returns_none_immediately(self):
        engine = HybridOCREngine(enable_hunyuan=False)
        assert engine._get_hunyuan_engine() is None

    def test_cached_unavailable_not_retried(self):
        engine = HybridOCREngine(enable_hunyuan=True)
        engine._hunyuan_available = False
        assert engine._get_hunyuan_engine() is None


# ---------------------------------------------------------------------------
# TesseractOCREngine (mocked pytesseract)
# ---------------------------------------------------------------------------


class TestTesseractOCREngine:
    def test_engine_name(self):
        with patch("screenshot_processor.core.ocr_engines.tesseract_engine.pytesseract") as mock_pt:
            mock_pt.get_tesseract_version.return_value = "5.0.0"
            from screenshot_processor.core.ocr_engines.tesseract_engine import TesseractOCREngine
            eng = TesseractOCREngine()
            assert eng.get_engine_name() == "Tesseract"

    def test_not_available_when_tesseract_missing(self):
        with patch("screenshot_processor.core.ocr_engines.tesseract_engine.pytesseract") as mock_pt:
            mock_pt.get_tesseract_version.side_effect = RuntimeError("not found")
            from screenshot_processor.core.ocr_engines.tesseract_engine import TesseractOCREngine
            eng = TesseractOCREngine()
            assert eng.is_available() is False

    def test_extract_text_raises_when_unavailable(self):
        with patch("screenshot_processor.core.ocr_engines.tesseract_engine.pytesseract") as mock_pt:
            mock_pt.get_tesseract_version.side_effect = RuntimeError("not found")
            from screenshot_processor.core.ocr_engines.tesseract_engine import TesseractOCREngine
            eng = TesseractOCREngine()
            with pytest.raises(OCREngineNotAvailableError):
                eng.extract_text(_dummy_image())
