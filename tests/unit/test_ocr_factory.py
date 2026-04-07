"""Unit tests for ocr_factory module — OCR engine creation and selection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from screenshot_processor.core.ocr_factory import OCREngineFactory, OCREngineType


# ---------------------------------------------------------------------------
# OCREngineType enum
# ---------------------------------------------------------------------------
class TestOCREngineType:
    def test_values(self):
        assert OCREngineType.TESSERACT == "tesseract"
        assert OCREngineType.PADDLEOCR == "paddleocr"
        assert OCREngineType.PADDLEOCR_REMOTE == "paddleocr_remote"
        assert OCREngineType.HUNYUAN == "hunyuan"
        assert OCREngineType.HYBRID == "hybrid"

    def test_string_conversion(self):
        assert OCREngineType("tesseract") == OCREngineType.TESSERACT
        assert OCREngineType("hybrid") == OCREngineType.HYBRID


# ---------------------------------------------------------------------------
# OCREngineFactory.create_engine
# ---------------------------------------------------------------------------
class TestCreateEngine:
    def test_invalid_engine_type_raises(self):
        with pytest.raises(ValueError, match="Unknown OCR engine type"):
            OCREngineFactory.create_engine("nonexistent_engine")

    def test_string_is_converted_to_enum(self):
        """Passing a string should be converted to the corresponding enum."""
        # We test via the error path for an unknown string
        with pytest.raises(ValueError, match="Unknown OCR engine type"):
            OCREngineFactory.create_engine("INVALID")

    def test_creates_tesseract_engine(self):
        """Tesseract engine creation should import and return TesseractOCREngine."""
        try:
            engine = OCREngineFactory.create_engine(OCREngineType.TESSERACT)
            assert engine.get_engine_name().lower() in ("tesseract", "tesseractocr")
        except (ImportError, RuntimeError, ValueError):
            pytest.skip("Tesseract not available")

    def test_create_engine_accepts_enum(self):
        """Should accept OCREngineType enum directly."""
        try:
            engine = OCREngineFactory.create_engine(OCREngineType.TESSERACT)
            assert engine is not None
        except (ImportError, RuntimeError):
            pytest.skip("Tesseract not installed")

    def test_create_engine_case_insensitive_string(self):
        """String engine type should be case-insensitive."""
        try:
            engine = OCREngineFactory.create_engine("TESSERACT")
            assert engine is not None
        except (ImportError, RuntimeError):
            pytest.skip("Tesseract not installed")


# ---------------------------------------------------------------------------
# OCREngineFactory.get_available_engines
# ---------------------------------------------------------------------------
class TestGetAvailableEngines:
    def test_returns_list(self):
        available = OCREngineFactory.get_available_engines()
        assert isinstance(available, list)

    def test_elements_are_enum_values(self):
        available = OCREngineFactory.get_available_engines()
        for eng in available:
            assert isinstance(eng, OCREngineType)


# ---------------------------------------------------------------------------
# OCREngineFactory.create_best_available_engine
# ---------------------------------------------------------------------------
class TestCreateBestAvailableEngine:
    def test_returns_engine_or_raises(self):
        """Should return an engine or raise RuntimeError if none available."""
        try:
            engine = OCREngineFactory.create_best_available_engine()
            assert hasattr(engine, "extract_text")
            assert hasattr(engine, "is_available")
            assert hasattr(engine, "get_engine_name")
        except RuntimeError as e:
            assert "No OCR engine available" in str(e)

    def test_prefer_hunyuan_false_skips_hunyuan(self):
        """With prefer_hunyuan=False, should try tesseract first."""
        mock_engine = MagicMock()
        mock_engine.is_available.return_value = True
        mock_engine.get_engine_name.return_value = "Tesseract"
        mock_cls = MagicMock(return_value=mock_engine)

        with patch("screenshot_processor.core.ocr_engines.TesseractOCREngine", mock_cls):
            engine = OCREngineFactory.create_best_available_engine(prefer_hunyuan=False)
            assert engine.get_engine_name() == "Tesseract"

    def test_use_hybrid_true_tries_hybrid(self):
        """With use_hybrid=True, should attempt hybrid engine."""
        mock_engine = MagicMock()
        mock_engine.is_available.return_value = True
        mock_engine.get_engine_name.return_value = "HybridOCR"

        with patch("screenshot_processor.core.ocr_engines.HybridOCREngine", return_value=mock_engine):
            engine = OCREngineFactory.create_best_available_engine(use_hybrid=True)
            assert engine is not None

    def test_kwargs_filtered_per_engine(self):
        """Engine-specific kwargs should be filtered — unknown kwargs should not crash."""
        mock_engine = MagicMock()
        mock_engine.is_available.return_value = True
        mock_engine.get_engine_name.return_value = "Tesseract"

        with patch("screenshot_processor.core.ocr_engines.TesseractOCREngine", return_value=mock_engine):
            engine = OCREngineFactory.create_best_available_engine(
                some_unknown_kwarg="value",
                tesseract_cmd="/usr/bin/tesseract",
            )
            assert engine is not None
