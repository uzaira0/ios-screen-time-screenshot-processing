"""Registry for PHI detectors.

Provides separate registries for text-based and vision-based detectors,
allowing runtime detector selection and configuration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from phi_detector_remover.core.protocols import TextDetector, VisionDetector


class DetectorRegistry:
    """Registry for PHI detector implementations.

    Maintains separate registries for text and vision detectors
    since they have different interfaces and use cases.

    Example:
        >>> registry = DetectorRegistry()
        >>> registry.register_text("presidio", PresidioDetector)
        >>> registry.register_vision("gemma", GemmaVisionDetector)
        >>> detector = registry.get_text("presidio", entities=["PERSON"])
    """

    _instance: DetectorRegistry | None = None
    _text_detectors: dict[str, type]
    _vision_detectors: dict[str, type]

    def __new__(cls) -> DetectorRegistry:
        """Singleton pattern for global registry."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._text_detectors = {}
            cls._instance._vision_detectors = {}
        return cls._instance

    # ========================================================================
    # Text Detector Methods
    # ========================================================================

    def register_text(self, name: str, detector_class: type) -> None:
        """Register a text-based detector class.

        Args:
            name: Unique identifier for this detector
            detector_class: Class that implements TextDetector protocol
        """
        self._text_detectors[name.lower()] = detector_class

    def get_text(self, name: str, **kwargs: Any) -> TextDetector:
        """Get an instantiated text detector by name.

        Args:
            name: Detector identifier
            **kwargs: Configuration passed to detector constructor

        Returns:
            Instantiated text detector

        Raises:
            KeyError: If detector name not found
            RuntimeError: If detector is not available
        """
        name_lower = name.lower()
        if name_lower not in self._text_detectors:
            available = ", ".join(self._text_detectors.keys())
            raise KeyError(f"Text detector '{name}' not found. Available: {available}")

        detector_class = self._text_detectors[name_lower]
        detector = detector_class(**kwargs)

        if not detector.is_available():
            raise RuntimeError(
                f"Text detector '{name}' is registered but not available. "
                "Check that required dependencies are installed."
            )

        return detector

    def list_text_detectors(self) -> list[str]:
        """List all registered text detector names."""
        return list(self._text_detectors.keys())

    def is_text_registered(self, name: str) -> bool:
        """Check if a text detector is registered."""
        return name.lower() in self._text_detectors

    # ========================================================================
    # Vision Detector Methods
    # ========================================================================

    def register_vision(self, name: str, detector_class: type) -> None:
        """Register a vision-based detector class.

        Args:
            name: Unique identifier for this detector
            detector_class: Class that implements VisionDetector protocol
        """
        self._vision_detectors[name.lower()] = detector_class

    def get_vision(self, name: str, **kwargs: Any) -> VisionDetector:
        """Get an instantiated vision detector by name.

        Args:
            name: Detector identifier
            **kwargs: Configuration passed to detector constructor

        Returns:
            Instantiated vision detector

        Raises:
            KeyError: If detector name not found
            RuntimeError: If detector is not available
        """
        name_lower = name.lower()
        if name_lower not in self._vision_detectors:
            available = ", ".join(self._vision_detectors.keys())
            raise KeyError(f"Vision detector '{name}' not found. Available: {available}")

        detector_class = self._vision_detectors[name_lower]
        detector = detector_class(**kwargs)

        if not detector.is_available():
            raise RuntimeError(
                f"Vision detector '{name}' is registered but not available. "
                "Check that required dependencies are installed."
            )

        return detector

    def list_vision_detectors(self) -> list[str]:
        """List all registered vision detector names."""
        return list(self._vision_detectors.keys())

    def is_vision_registered(self, name: str) -> bool:
        """Check if a vision detector is registered."""
        return name.lower() in self._vision_detectors

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def clear(self) -> None:
        """Clear all registered detectors (mainly for testing)."""
        self._text_detectors.clear()
        self._vision_detectors.clear()


# Global registry instance
_registry = DetectorRegistry()


# ============================================================================
# Convenience Functions
# ============================================================================


def register_text_detector(name: str, detector_class: type) -> None:
    """Register a text-based detector in the global registry."""
    _registry.register_text(name, detector_class)


def register_vision_detector(name: str, detector_class: type) -> None:
    """Register a vision-based detector in the global registry."""
    _registry.register_vision(name, detector_class)


def get_text_detector(name: str, **kwargs: Any) -> TextDetector:
    """Get a text detector from the global registry.

    Args:
        name: Detector identifier (e.g., "presidio", "regex", "llm")
        **kwargs: Configuration passed to detector constructor

    Returns:
        Instantiated text detector

    Example:
        >>> detector = get_text_detector("presidio", entities=["PERSON", "EMAIL"])
        >>> result = detector.detect(ocr_result)
    """
    return _registry.get_text(name, **kwargs)


def get_vision_detector(name: str, **kwargs: Any) -> VisionDetector:
    """Get a vision detector from the global registry.

    Args:
        name: Detector identifier (e.g., "gemma", "hunyuan")
        **kwargs: Configuration passed to detector constructor

    Returns:
        Instantiated vision detector

    Example:
        >>> detector = get_vision_detector("gemma", model="gemma-2-2b")
        >>> result = detector.detect(image_bytes)
    """
    return _registry.get_vision(name, **kwargs)


def list_text_detectors() -> list[str]:
    """List all available text detector names."""
    return _registry.list_text_detectors()


def list_vision_detectors() -> list[str]:
    """List all available vision detector names."""
    return _registry.list_vision_detectors()


def _register_builtin_detectors() -> None:
    """Register built-in detectors."""
    from phi_detector_remover.core.detectors.presidio import PresidioDetector
    from phi_detector_remover.core.detectors.regex import RegexDetector

    register_text_detector("presidio", PresidioDetector)
    register_text_detector("regex", RegexDetector)

    # Register GLiNER detector if available
    try:
        from phi_detector_remover.core.detectors.gliner import GLiNERDetector

        register_text_detector("gliner", GLiNERDetector)
    except ImportError:
        pass

    # Register LLM text detector if available
    try:
        from phi_detector_remover.core.detectors.llm import LLMTextDetector

        register_text_detector("llm", LLMTextDetector)
    except ImportError:
        pass

    # Register vision detectors if available
    try:
        from phi_detector_remover.core.detectors.vision import GemmaVisionDetector

        register_vision_detector("gemma", GemmaVisionDetector)
    except ImportError:
        pass


# Auto-register built-in detectors on import
_register_builtin_detectors()
