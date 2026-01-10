"""OCR engines for text extraction from images.

This module provides:
- OCREngineRegistry: Registry for discovering and instantiating OCR engines
- TesseractEngine: Traditional Tesseract OCR implementation
- Placeholder interfaces for LVM-based OCR (Hunyuan, etc.)

Usage:
    >>> from phi_detector_remover.core.ocr import get_engine, list_engines
    >>> engine = get_engine("tesseract", lang="eng")
    >>> result = engine.extract(image_bytes)
"""

from phi_detector_remover.core.ocr.registry import (
    OCREngineRegistry,
    get_engine,
    list_engines,
    register_engine,
)
from phi_detector_remover.core.ocr.tesseract import TesseractEngine

__all__ = [
    "OCREngineRegistry",
    "TesseractEngine",
    "get_engine",
    "list_engines",
    "register_engine",
]
