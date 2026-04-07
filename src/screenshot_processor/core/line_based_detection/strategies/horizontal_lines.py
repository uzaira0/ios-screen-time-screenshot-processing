"""
Horizontal line based grid detection strategy.

Detects the daily chart by finding groups of evenly-spaced horizontal grid lines
(gray lines at ~200 value that span the chart width).
"""

from __future__ import annotations

import logging

import numpy as np

from ..protocol import GridBounds, GridDetectionResult
from .base import BaseGridStrategy

logger = logging.getLogger(__name__)


class HorizontalLineStrategy(BaseGridStrategy):
    """
    Detect grid by finding evenly-spaced horizontal grid lines.

    The daily hourly chart has 4-5 horizontal lines with consistent spacing
    (~45px for most resolutions, ~67px for larger ones).

    This strategy:
    1. Scans for rows with many gray pixels (~200 value)
    2. Clusters nearby rows into line positions
    3. Finds groups of 4-5 lines with even spacing
    4. Returns the region bounded by these lines
    """

    def __init__(
        self,
        gray_min: int = 195,
        gray_max: int = 210,
        min_width_pct: float = 0.35,  # Lowered from 0.5 - bars can cover grid lines
        min_lines: int = 4,
        max_lines: int = 8,
        max_spacing_deviation: int = 10,
    ):
        """
        Initialize the horizontal line detection strategy.

        Args:
            gray_min: Minimum gray value for grid lines
            gray_max: Maximum gray value for grid lines
            min_width_pct: Minimum percentage of width that must be gray
            min_lines: Minimum number of evenly-spaced lines to detect
            max_lines: Maximum number of lines to consider in a group
            max_spacing_deviation: Maximum deviation from mean spacing (pixels)
        """
        self._gray_min = gray_min
        self._gray_max = gray_max
        self._min_width_pct = min_width_pct
        self._min_lines = min_lines
        self._max_lines = max_lines
        self._max_spacing_deviation = max_spacing_deviation

    @property
    def name(self) -> str:
        return "horizontal_lines"

    def detect(
        self,
        image: np.ndarray,
        resolution: str | None = None,
        hints: dict | None = None,
    ) -> GridDetectionResult:
        """
        Detect grid by finding horizontal line patterns.

        Uses hints for x and width if available (from lookup table).
        """
        gray = self._to_grayscale(image)
        _h, w = gray.shape

        # Get x range from hints or use full width
        x_start = hints.get("x", 0) if hints else 0
        width = hints.get("width", w - x_start) if hints else w - x_start
        x_end = min(x_start + width, w)

        # Expected height from hints
        expected_height = hints.get("height") if hints else None

        # Find horizontal lines
        lines = self._find_horizontal_lines(gray, x_start, x_end)

        if len(lines) < self._min_lines:
            return self._make_failure(
                f"Only found {len(lines)} horizontal lines (need {self._min_lines}+)",
                diagnostics={"lines_found": lines},
            )

        # Find evenly-spaced groups
        groups = self._find_evenly_spaced_groups(lines, expected_height)

        if not groups:
            return self._make_failure(
                "No evenly-spaced line groups found",
                diagnostics={"lines_found": lines},
            )

        # Return the best group (most lines, best spacing consistency)
        best = groups[0]

        bounds = GridBounds(
            x=x_start,
            y=best["y_start"],
            width=width,
            height=best["y_end"] - best["y_start"],
        )

        # Confidence based on number of lines and spacing consistency
        confidence = min(0.95, 0.7 + (best["num_lines"] - 4) * 0.05)

        return self._make_success(
            bounds=bounds,
            confidence=confidence,
            diagnostics={
                "num_lines": best["num_lines"],
                "mean_spacing": best["mean_spacing"],
                "line_positions": best["lines"],
                "all_groups": len(groups),
            },
        )

    def _find_horizontal_lines(
        self,
        gray: np.ndarray,
        x_start: int,
        x_end: int,
    ) -> list[int]:
        """Find y positions of horizontal grid lines."""
        h, _w = gray.shape
        region = gray[:, x_start:x_end]
        region_w = region.shape[1]

        line_y_positions = []

        for y in range(h):
            row = region[y, :]
            gray_pixels = np.sum((row >= self._gray_min) & (row <= self._gray_max))
            if gray_pixels > region_w * self._min_width_pct:
                line_y_positions.append(y)

        # Cluster nearby positions
        return self._cluster_positions(line_y_positions, max_gap=3)

    def _find_evenly_spaced_groups(
        self,
        lines: list[int],
        expected_height: int | None = None,
    ) -> list[dict]:
        """Find groups of evenly-spaced horizontal lines."""
        groups = []

        for start_idx in range(len(lines) - self._min_lines + 1):
            for end_idx in range(start_idx + self._min_lines, min(start_idx + self._max_lines + 1, len(lines) + 1)):
                group = lines[start_idx:end_idx]
                spacings = [group[i + 1] - group[i] for i in range(len(group) - 1)]
                mean_spacing = np.mean(spacings)
                max_dev = max(abs(s - mean_spacing) for s in spacings)

                # Check spacing consistency
                if max_dev > self._max_spacing_deviation:
                    continue

                # Check spacing is reasonable (not too small or large)
                if mean_spacing < 20 or mean_spacing > 150:
                    continue

                # If we have expected height, use it as a soft preference, not hard filter
                # Some resolutions have significant height variation
                group_height = group[-1] - group[0]
                height_score = 1.0
                if expected_height:
                    height_error = abs(group_height - expected_height)
                    # Penalize but don't reject if height differs
                    height_score = max(0.5, 1.0 - (height_error / expected_height))

                groups.append(
                    {
                        "y_start": group[0],
                        "y_end": group[-1],
                        "num_lines": len(group),
                        "mean_spacing": mean_spacing,
                        "max_deviation": max_dev,
                        "height_score": height_score,
                        "lines": group,
                    }
                )

        # Sort by: number of lines (desc), height_score (desc), spacing deviation (asc)
        groups.sort(key=lambda g: (-g["num_lines"], -g["height_score"], g["max_deviation"]))

        # Remove overlapping groups, keeping best ones
        non_overlapping = []
        for g in groups:
            overlaps = False
            for existing in non_overlapping:
                overlap_start = max(g["y_start"], existing["y_start"])
                overlap_end = min(g["y_end"], existing["y_end"])
                if overlap_end > overlap_start:
                    overlaps = True
                    break
            if not overlaps:
                non_overlapping.append(g)

        return non_overlapping
