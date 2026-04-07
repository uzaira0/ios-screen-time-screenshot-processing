"""PHI detectors for text and vision-based detection.

This module provides:
- DetectorRegistry: Registry for discovering and instantiating detectors
- Text Detectors: Presidio, Regex, LLM-based (require OCR first)
- Vision Detectors: LVM-based (analyze images directly)

Usage:
    >>> from phi_detector_remover.core.detectors import (
    ...     get_text_detector,
    ...     get_vision_detector,
    ...     list_text_detectors,
    ...     list_vision_detectors,
    ... )
    >>> detector = get_text_detector("presidio", entities=["PERSON", "EMAIL"])
    >>> result = detector.detect(ocr_result)
"""

from phi_detector_remover.core.detectors.presidio import PresidioDetector
from phi_detector_remover.core.detectors.regex import RegexDetector
from phi_detector_remover.core.detectors.registry import (
    DetectorRegistry,
    get_text_detector,
    get_vision_detector,
    list_text_detectors,
    list_vision_detectors,
    register_text_detector,
    register_vision_detector,
)

__all__ = [
    "DetectorRegistry",
    "PresidioDetector",
    "RegexDetector",
    "get_text_detector",
    "get_vision_detector",
    "list_text_detectors",
    "list_vision_detectors",
    "register_text_detector",
    "register_vision_detector",
]
