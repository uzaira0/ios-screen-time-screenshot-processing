"""OCR Engine Factory for creating OCR engine instances.

This module provides a factory pattern for creating OCR engines,
enabling easy switching between different OCR backends via configuration.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ocr_protocol import IOCREngine

logger = logging.getLogger(__name__)


class OCREngineType(StrEnum):
    """Available OCR engine types."""

    TESSERACT = "tesseract"
    PADDLEOCR = "paddleocr"
    PADDLEOCR_REMOTE = "paddleocr_remote"
    HUNYUAN = "hunyuan"
    HYBRID = "hybrid"


class OCREngineFactory:
    """Factory for creating OCR engine instances.

    Example:
        >>> engine = OCREngineFactory.create_engine(OCREngineType.TESSERACT)
        >>> results = engine.extract_text(image)
    """

    @staticmethod
    def create_engine(
        engine_type: OCREngineType | str = OCREngineType.TESSERACT,
        **engine_kwargs,
    ) -> IOCREngine:
        """Create an OCR engine instance.

        Args:
            engine_type: Type of OCR engine to create (tesseract or paddleocr)
            **engine_kwargs: Additional keyword arguments passed to the engine constructor

        Returns:
            Configured OCR engine instance

        Raises:
            ValueError: If engine_type is unknown
            ImportError: If the required engine library is not installed

        Examples:
            >>> # Create Tesseract engine
            >>> engine = OCREngineFactory.create_engine("tesseract")

            >>> # Create PaddleOCR engine with GPU
            >>> engine = OCREngineFactory.create_engine("paddleocr", use_gpu=True)

            >>> # Create Tesseract with custom path
            >>> engine = OCREngineFactory.create_engine(
            ...     "tesseract",
            ...     tesseract_cmd="/usr/local/bin/tesseract"
            ... )
        """
        # Convert string to enum if needed
        if isinstance(engine_type, str):
            try:
                engine_type = OCREngineType(engine_type.lower())
            except ValueError as e:
                raise ValueError(
                    f"Unknown OCR engine type: {engine_type}. Available types: {[e.value for e in OCREngineType]}"
                ) from e

        if engine_type == OCREngineType.TESSERACT:
            from .ocr_engines import TesseractOCREngine

            logger.info(f"Creating TesseractOCREngine with kwargs: {engine_kwargs}")
            return TesseractOCREngine(**engine_kwargs)

        elif engine_type == OCREngineType.PADDLEOCR:
            from .ocr_engines import PaddleOCREngine

            logger.info(f"Creating PaddleOCREngine with kwargs: {engine_kwargs}")
            return PaddleOCREngine(**engine_kwargs)

        elif engine_type == OCREngineType.HUNYUAN:
            from .ocr_engines import HunyuanOCREngine

            logger.info(f"Creating HunyuanOCREngine with kwargs: {engine_kwargs}")
            return HunyuanOCREngine(**engine_kwargs)

        elif engine_type == OCREngineType.PADDLEOCR_REMOTE:
            from .ocr_engines import PaddleOCRRemoteEngine

            logger.info(f"Creating PaddleOCRRemoteEngine with kwargs: {engine_kwargs}")
            return PaddleOCRRemoteEngine(**engine_kwargs)

        elif engine_type == OCREngineType.HYBRID:
            from .ocr_engines import HybridOCREngine

            logger.info(f"Creating HybridOCREngine with kwargs: {engine_kwargs}")
            return HybridOCREngine(**engine_kwargs)

        else:
            raise ValueError(
                f"Unknown OCR engine type: {engine_type}. Available types: {[e.value for e in OCREngineType]}"
            )

    @staticmethod
    def get_available_engines() -> list[OCREngineType]:
        """Get list of available OCR engines on this system.

        Returns:
            List of OCREngineType values for engines that are available

        Example:
            >>> available = OCREngineFactory.get_available_engines()
            >>> print(f"Available engines: {available}")
            Available engines: [<OCREngineType.TESSERACT: 'tesseract'>]
        """
        available: list[OCREngineType] = []

        # Check Tesseract
        try:
            from .ocr_engines import TesseractOCREngine

            engine = TesseractOCREngine()
            if engine.is_available():
                available.append(OCREngineType.TESSERACT)
        except Exception as e:
            logger.debug(f"Tesseract not available: {e}")

        # Check PaddleOCR
        try:
            from .ocr_engines import PaddleOCREngine

            engine = PaddleOCREngine()
            if engine.is_available():
                available.append(OCREngineType.PADDLEOCR)
        except Exception as e:
            logger.debug(f"PaddleOCR not available: {e}")

        # Check HunyuanOCR
        try:
            from .ocr_engines import HunyuanOCREngine

            engine = HunyuanOCREngine()
            if engine.is_available():
                available.append(OCREngineType.HUNYUAN)
        except Exception as e:
            logger.debug(f"HunyuanOCR not available: {e}")

        # Check PaddleOCR Remote
        try:
            from .ocr_engines import PaddleOCRRemoteEngine

            engine = PaddleOCRRemoteEngine()
            if engine.is_available():
                available.append(OCREngineType.PADDLEOCR_REMOTE)
        except Exception as e:
            logger.debug(f"PaddleOCR Remote not available: {e}")

        # Check Hybrid (available if any engine is available)
        try:
            from .ocr_engines import HybridOCREngine

            engine = HybridOCREngine()
            if engine.is_available():
                available.append(OCREngineType.HYBRID)
        except Exception as e:
            logger.debug(f"Hybrid OCR not available: {e}")

        return available

    @staticmethod
    def create_best_available_engine(
        prefer_hunyuan: bool = True,
        use_hybrid: bool = False,
        **engine_kwargs,
    ) -> IOCREngine:
        """Create the best available OCR engine.

        Priority order (when use_hybrid=True):
        - Returns HybridOCREngine with automatic fallback: Hunyuan → PaddleOCR → Tesseract

        Priority order (when prefer_hunyuan=True, use_hybrid=False):
        1. HunyuanOCR (vision LLM, highest quality)
        2. Tesseract (fast, reliable fallback)

        Args:
            prefer_hunyuan: If True, prefer HunyuanOCR when available. Default True.
            use_hybrid: If True, return HybridOCREngine with automatic fallback. Default False.
            **engine_kwargs: Additional keyword arguments. Engine-specific kwargs are
                filtered automatically:
                - HunyuanOCR: base_url, timeout, max_retries, custom_prompt
                - HybridOCR: hunyuan_url, paddleocr_url, hunyuan_timeout, paddleocr_timeout,
                            enable_hunyuan, enable_paddleocr, enable_tesseract
                - Tesseract: tesseract_cmd

        Returns:
            Best available OCR engine instance

        Raises:
            RuntimeError: If no OCR engine is available

        Example:
            >>> engine = OCREngineFactory.create_best_available_engine()
            >>> print(f"Using: {engine.get_engine_name()}")
            Using: HunyuanOCR

            >>> # Use hybrid engine with automatic fallback
            >>> engine = OCREngineFactory.create_best_available_engine(use_hybrid=True)
            >>> print(f"Using: {engine.get_engine_name()}")
            Using: HybridOCR

            >>> # Force Tesseract even if HunyuanOCR is available
            >>> engine = OCREngineFactory.create_best_available_engine(prefer_hunyuan=False)
        """
        # Define valid kwargs per engine type
        hunyuan_kwargs = {"base_url", "timeout", "max_retries", "custom_prompt", "rate_limit"}
        tesseract_kwargs = {"tesseract_cmd"}
        hybrid_kwargs = {
            "hunyuan_url",
            "paddleocr_url",
            "hunyuan_timeout",
            "paddleocr_timeout",
            "enable_hunyuan",
            "enable_paddleocr",
            "enable_tesseract",
        }

        # Filter kwargs for each engine type
        hunyuan_filtered = {k: v for k, v in engine_kwargs.items() if k in hunyuan_kwargs}
        tesseract_filtered = {k: v for k, v in engine_kwargs.items() if k in tesseract_kwargs}
        hybrid_filtered = {k: v for k, v in engine_kwargs.items() if k in hybrid_kwargs}

        # Use hybrid engine if requested
        if use_hybrid:
            try:
                from .ocr_engines import HybridOCREngine

                engine = HybridOCREngine(**hybrid_filtered)
                if engine.is_available():
                    logger.info("Using OCR engine: hybrid (with fallback chain)")
                    return engine
            except Exception as e:
                logger.warning(f"HybridOCR not available, falling back to single engine: {e}")

        # Try HunyuanOCR first if preferred (best quality)
        if prefer_hunyuan:
            try:
                from .ocr_engines import HunyuanOCREngine

                engine = HunyuanOCREngine(**hunyuan_filtered)
                if engine.is_available():
                    logger.info("Using OCR engine: hunyuan")
                    return engine
            except Exception as e:
                logger.debug(f"HunyuanOCR not available, falling back: {e}")

        # Fallback to Tesseract
        try:
            from .ocr_engines import TesseractOCREngine

            engine = TesseractOCREngine(**tesseract_filtered)
            if engine.is_available():
                logger.info("Using OCR engine: tesseract")
                return engine
        except Exception as e:
            logger.error(f"Failed to create Tesseract engine: {e}")

        raise RuntimeError(
            "No OCR engine available. Options:\n"
            "  1. HybridOCR: Automatic fallback between available engines\n"
            "  2. HunyuanOCR: Set HUNYUAN_OCR_URL to a running endpoint\n"
            "  3. PaddleOCR: Set PADDLEOCR_URL to a running endpoint\n"
            "  4. Tesseract: Install Tesseract OCR:\n"
            "     - macOS: brew install tesseract\n"
            "     - Ubuntu: apt-get install tesseract-ocr\n"
            "     - Windows: Download from https://tesseract-ocr.github.io/"
        )
