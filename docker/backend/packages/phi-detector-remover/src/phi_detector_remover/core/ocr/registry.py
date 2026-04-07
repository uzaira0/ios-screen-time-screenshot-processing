"""Registry for OCR engines.

Provides a plugin-style registration system for OCR engines,
allowing new engines to be added without modifying core code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from phi_detector_remover.core.protocols import OCREngine


class OCREngineRegistry:
    """Registry for OCR engine implementations.

    Engines can be registered by name and instantiated with configuration.
    This enables dependency injection and runtime engine selection.

    Example:
        >>> registry = OCREngineRegistry()
        >>> registry.register("tesseract", TesseractEngine)
        >>> engine = registry.get("tesseract", lang="eng")
    """

    _instance: OCREngineRegistry | None = None
    _engines: dict[str, type]

    def __new__(cls) -> OCREngineRegistry:
        """Singleton pattern for global registry."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._engines = {}
        return cls._instance

    def register(self, name: str, engine_class: type) -> None:
        """Register an OCR engine class.

        Args:
            name: Unique identifier for this engine
            engine_class: Class that implements OCREngine protocol
        """
        self._engines[name.lower()] = engine_class

    def get(self, name: str, **kwargs: Any) -> OCREngine:
        """Get an instantiated OCR engine by name.

        Args:
            name: Engine identifier
            **kwargs: Configuration passed to engine constructor

        Returns:
            Instantiated OCR engine

        Raises:
            KeyError: If engine name not found
            RuntimeError: If engine is not available
        """
        name_lower = name.lower()
        if name_lower not in self._engines:
            available = ", ".join(self._engines.keys())
            raise KeyError(f"OCR engine '{name}' not found. Available: {available}")

        engine_class = self._engines[name_lower]
        engine = engine_class(**kwargs)

        if not engine.is_available():
            raise RuntimeError(
                f"OCR engine '{name}' is registered but not available. "
                "Check that required dependencies are installed."
            )

        return engine

    def list_available(self) -> list[str]:
        """List all registered engine names.

        Returns:
            List of engine names
        """
        return list(self._engines.keys())

    def is_registered(self, name: str) -> bool:
        """Check if an engine is registered.

        Args:
            name: Engine identifier

        Returns:
            True if engine is registered
        """
        return name.lower() in self._engines

    def clear(self) -> None:
        """Clear all registered engines (mainly for testing)."""
        self._engines.clear()


# Global registry instance
_registry = OCREngineRegistry()


def register_engine(name: str, engine_class: type) -> None:
    """Register an OCR engine class in the global registry.

    Args:
        name: Unique identifier for this engine
        engine_class: Class that implements OCREngine protocol
    """
    _registry.register(name, engine_class)


def get_engine(name: str, **kwargs: Any) -> OCREngine:
    """Get an instantiated OCR engine from the global registry.

    Args:
        name: Engine identifier (e.g., "tesseract", "hunyuan")
        **kwargs: Configuration passed to engine constructor

    Returns:
        Instantiated OCR engine

    Example:
        >>> engine = get_engine("tesseract", lang="eng", psm=6)
        >>> result = engine.extract(image_bytes)
    """
    return _registry.get(name, **kwargs)


def list_engines() -> list[str]:
    """List all available OCR engine names.

    Returns:
        List of registered engine names
    """
    return _registry.list_available()


def _register_builtin_engines() -> None:
    """Register built-in OCR engines."""
    from phi_detector_remover.core.ocr.tesseract import TesseractEngine

    register_engine("tesseract", TesseractEngine)

    # Also register as "pytesseract" (user-facing name)
    register_engine("pytesseract", TesseractEngine)

    # Register leptess OCR engine (Tesseract C API via PyO3 — faster than pytesseract)
    try:
        from phi_detector_remover.core.ocr.rust_engine import RustOCREngine

        register_engine("leptess", RustOCREngine)
    except ImportError:
        pass

    # Register placeholder engines for LVM-based OCR
    try:
        from phi_detector_remover.core.ocr.hunyuan import HunyuanOCREngine

        register_engine("hunyuan", HunyuanOCREngine)
    except ImportError:
        pass  # Optional dependency


# Auto-register built-in engines on import
_register_builtin_engines()
