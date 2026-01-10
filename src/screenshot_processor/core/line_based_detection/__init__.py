"""
Line-Based Detection Module

Provides pluggable strategies for detecting the daily hourly chart grid
in iOS Screen Time screenshots using visual line patterns (no OCR).

This is an alternative to the OCR-anchored method which uses text markers
like "12 AM" and "60" to locate the grid.

Usage:
    from screenshot_processor.core.line_based_detection import (
        LineBasedDetector,
        GridDetectionResult,
        HorizontalLineStrategy,
        VerticalLineStrategy,
        LookupTableStrategy,
    )

    # Single strategy
    detector = LineBasedDetector(strategies=[HorizontalLineStrategy()])
    result = detector.detect(image, resolution="848x2266")

    # Multiple strategies with voting
    detector = LineBasedDetector(strategies=[
        LookupTableStrategy(),
        HorizontalLineStrategy(),
        VerticalLineStrategy(),
    ])
    results = detector.detect_all(image, resolution="848x2266")
    best = detector.detect_best(image, resolution="848x2266")
"""

from .detector import LineBasedDetector
from .protocol import GridBounds, GridDetectionResult, GridDetectionStrategy
from .strategies import (
    CombinedStrategy,
    HorizontalLineStrategy,
    LookupTableStrategy,
    VerticalLineStrategy,
)

__all__ = [
    # Protocol and types
    "GridDetectionStrategy",
    "GridDetectionResult",
    "GridBounds",
    # Main detector
    "LineBasedDetector",
    # Strategies
    "LookupTableStrategy",
    "HorizontalLineStrategy",
    "VerticalLineStrategy",
    "CombinedStrategy",
]
