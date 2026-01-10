"""
Lookup table based grid detection strategy.

Uses pre-computed grid coordinates for known resolutions.
Fast but only provides x, width, height - y position varies with scroll.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from ..protocol import GridBounds, GridDetectionResult
from .base import BaseGridStrategy

logger = logging.getLogger(__name__)

# Default lookup table based on iOS Screen Time screenshots
# Keys are "widthxheight" resolution strings
# Values are grid bounds (x, y, width, height)
# Note: y is approximate - varies based on scroll position
DEFAULT_LOOKUP_TABLE: dict[str, dict[str, int]] = {
    "640x1136": {"x": 30, "y": 270, "width": 510, "height": 180},
    "750x1334": {"x": 60, "y": 670, "width": 560, "height": 180},
    "750x1624": {"x": 60, "y": 450, "width": 560, "height": 180},
    "828x1792": {"x": 70, "y": 450, "width": 620, "height": 180},
    "848x2266": {"x": 70, "y": 390, "width": 640, "height": 180},
    "858x2160": {"x": 70, "y": 390, "width": 640, "height": 180},
    "896x2048": {"x": 70, "y": 500, "width": 670, "height": 180},
    "906x2160": {"x": 70, "y": 390, "width": 690, "height": 180},
    "960x2079": {"x": 80, "y": 620, "width": 720, "height": 270},
    "980x2160": {"x": 80, "y": 390, "width": 730, "height": 180},
    "990x2160": {"x": 80, "y": 390, "width": 740, "height": 180},
    "1000x2360": {"x": 80, "y": 420, "width": 790, "height": 180},
    "1028x2224": {"x": 80, "y": 400, "width": 820, "height": 180},
    "1028x2388": {"x": 80, "y": 400, "width": 820, "height": 180},
    "1170x2532": {"x": 90, "y": 640, "width": 880, "height": 270},
    # iPad Pro 12.9" cropped (2048-790=1258 width)
    "1258x2732": {"x": 80, "y": 450, "width": 1020, "height": 180},
}


class LookupTableStrategy(BaseGridStrategy):
    """
    Grid detection using a lookup table of known resolutions.

    Provides x, width, and height from the lookup table.
    The y coordinate is approximate and should be refined by other strategies.

    Attributes:
        provide_y: If True, include the approximate y from lookup.
                   If False, only provide x, width, height (y must come from hints or other strategies).
    """

    def __init__(
        self,
        lookup_table: dict[str, dict[str, int]] | None = None,
        lookup_file: Path | str | None = None,
        provide_y: bool = False,
    ):
        """
        Initialize the lookup table strategy.

        Args:
            lookup_table: Dictionary mapping resolution strings to grid bounds
            lookup_file: Path to JSON file with lookup table
            provide_y: Whether to include y coordinate from lookup (default False)
        """
        self._lookup_table = lookup_table or {}
        self._provide_y = provide_y

        # Load from file if provided
        if lookup_file:
            self._load_from_file(lookup_file)

        # Fall back to defaults if empty
        if not self._lookup_table:
            self._lookup_table = DEFAULT_LOOKUP_TABLE.copy()

    def _load_from_file(self, path: Path | str) -> None:
        """Load lookup table from JSON file."""
        try:
            with open(path) as f:
                self._lookup_table = json.load(f)
            logger.debug(f"Loaded lookup table from {path} with {len(self._lookup_table)} entries")
        except Exception as e:
            logger.warning(f"Failed to load lookup table from {path}: {e}")

    @property
    def name(self) -> str:
        return "lookup_table"

    @property
    def lookup_table(self) -> dict[str, dict[str, int]]:
        """Get the current lookup table."""
        return self._lookup_table

    def supports_resolution(self, resolution: str) -> bool:
        """Check if resolution is in the lookup table."""
        return resolution in self._lookup_table

    def detect(
        self,
        image: np.ndarray,
        resolution: str | None = None,
        hints: dict | None = None,
    ) -> GridDetectionResult:
        """
        Look up grid bounds for the given resolution.

        If resolution is not provided, it's inferred from image dimensions.
        """
        # Infer resolution from image if not provided
        if resolution is None:
            h, w = image.shape[:2]
            resolution = f"{w}x{h}"

        # Look up in table
        if resolution not in self._lookup_table:
            return self._make_failure(
                f"Resolution {resolution} not in lookup table",
                diagnostics={"available_resolutions": list(self._lookup_table.keys())},
            )

        entry = self._lookup_table[resolution]

        # Get y from hints if available, otherwise from lookup (if provide_y is True)
        y = None
        if hints and "y" in hints:
            y = hints["y"]
        elif self._provide_y:
            y = entry.get("y")

        # If we don't have y, we can still provide partial bounds
        if y is None:
            # Return partial result - useful for other strategies
            return GridDetectionResult(
                bounds=None,  # Can't create full bounds without y
                confidence=0.8,  # High confidence in x, width, height
                strategy_name=self.name,
                diagnostics={
                    "x": entry["x"],
                    "width": entry["width"],
                    "height": entry["height"],
                    "note": "y position requires detection (varies with scroll)",
                },
            )

        bounds = GridBounds(
            x=entry["x"],
            y=y,
            width=entry["width"],
            height=entry["height"],
        )

        return self._make_success(
            bounds=bounds,
            confidence=0.9 if self._provide_y else 0.95,
            diagnostics={
                "source": "lookup_table",
                "y_source": "hints" if hints and "y" in hints else "lookup",
            },
        )

    def get_partial_bounds(self, resolution: str) -> dict[str, int] | None:
        """
        Get partial bounds (x, width, height) for a resolution.

        Useful for providing hints to other strategies.
        """
        if resolution not in self._lookup_table:
            return None

        entry = self._lookup_table[resolution]
        return {
            "x": entry["x"],
            "width": entry["width"],
            "height": entry["height"],
        }
