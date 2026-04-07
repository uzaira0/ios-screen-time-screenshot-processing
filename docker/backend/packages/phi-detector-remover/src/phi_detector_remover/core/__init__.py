"""Core PHI detection and removal logic - framework agnostic."""

from __future__ import annotations

from phi_detector_remover.core.config import PHIDetectorConfig
from phi_detector_remover.core.detector import PHIDetector, PHIRegion
from phi_detector_remover.core.patterns import DEFAULT_PATTERNS, CustomPHIPattern
from phi_detector_remover.core.remover import PHIRemover, RedactionMethod

__all__ = [
    "PHIDetector",
    "PHIRemover",
    "PHIRegion",
    "PHIDetectorConfig",
    "RedactionMethod",
    "CustomPHIPattern",
    "DEFAULT_PATTERNS",
]
