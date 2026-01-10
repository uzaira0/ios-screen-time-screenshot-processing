"""
Vertical dotted line based grid detection strategy.

Detects the daily chart by finding exactly 4-5 evenly-spaced vertical dotted lines
(at 12AM, 6AM, 12PM, 6PM, and optionally edges).

This is the key differentiator between daily charts (4 internal lines) and
weekly charts (7 lines for each day of the week).
"""

from __future__ import annotations

import logging

import numpy as np

from ..protocol import GridBounds, GridDetectionResult
from .base import BaseGridStrategy

logger = logging.getLogger(__name__)


class VerticalLineStrategy(BaseGridStrategy):
    """
    Detect daily chart by counting vertical dotted lines.

    The daily hourly chart has 4-5 evenly-spaced vertical dotted lines:
    - 4 internal lines at 6AM, 12PM, 6PM positions (+ edges = 5 total)
    - Spacing is approximately width/4

    Weekly charts have 7+ vertical sections (one per day).

    This strategy is best used in combination with HorizontalLineStrategy:
    1. HorizontalLineStrategy finds candidate chart regions
    2. VerticalLineStrategy validates which one is the daily chart
    """

    def __init__(
        self,
        gray_min: int = 190,
        gray_max: int = 215,
        min_height_pct: float = 0.4,
        expected_lines: tuple[int, ...] = (3, 4, 5),  # 3 if edges cropped, 4-5 if full
        spacing_tolerance: float = 0.25,
    ):
        """
        Initialize the vertical line detection strategy.

        Args:
            gray_min: Minimum gray value for dotted line pixels
            gray_max: Maximum gray value for dotted line pixels
            min_height_pct: Minimum percentage of column height that must be gray
            expected_lines: Expected number of vertical lines (4 or 5)
            spacing_tolerance: Tolerance for spacing deviation (as fraction of expected)
        """
        self._gray_min = gray_min
        self._gray_max = gray_max
        self._min_height_pct = min_height_pct
        self._expected_lines = expected_lines
        self._spacing_tolerance = spacing_tolerance

    @property
    def name(self) -> str:
        return "vertical_lines"

    def detect(
        self,
        image: np.ndarray,
        resolution: str | None = None,
        hints: dict | None = None,
    ) -> GridDetectionResult:
        """
        Detect grid by finding vertical dotted line pattern.

        Requires hints with x, width, and candidate y regions from
        horizontal line detection.
        """
        if not hints:
            return self._make_failure("VerticalLineStrategy requires hints (x, width, and candidate regions)")

        gray = self._to_grayscale(image)
        h, w = gray.shape

        x_start = hints.get("x", 0)
        width = hints.get("width", w - x_start)

        # If we have candidate regions from horizontal line detection, check each
        candidate_regions = hints.get("candidate_regions", [])

        if not candidate_regions:
            # Fall back to checking the whole image in chunks
            expected_height = hints.get("height", 180)
            candidate_regions = self._generate_candidate_regions(h, expected_height)

        # Check each candidate region for the daily chart pattern
        best_match = None
        best_confidence = 0.0

        for region in candidate_regions:
            y_start = region.get("y_start", region.get("y", 0))
            y_end = region.get("y_end", y_start + region.get("height", 180))

            result = self._check_region(gray, x_start, width, y_start, y_end)

            if result["is_daily"] and result["confidence"] > best_confidence:
                best_confidence = result["confidence"]
                best_match = {
                    "y_start": y_start,
                    "y_end": y_end,
                    **result,
                }

        if best_match is None:
            return self._make_failure(
                "No region matches daily chart vertical line pattern",
                diagnostics={"regions_checked": len(candidate_regions)},
            )

        bounds = GridBounds(
            x=x_start,
            y=best_match["y_start"],
            width=width,
            height=best_match["y_end"] - best_match["y_start"],
        )

        return self._make_success(
            bounds=bounds,
            confidence=best_match["confidence"],
            diagnostics={
                "v_line_count": best_match["v_count"],
                "v_line_positions": best_match["v_positions"],
                "mean_spacing": best_match.get("mean_spacing"),
                "regions_checked": len(candidate_regions),
            },
        )

    def _check_region(
        self,
        gray: np.ndarray,
        x_start: int,
        width: int,
        y_start: int,
        y_end: int,
    ) -> dict:
        """Check if a region matches the daily chart vertical line pattern."""
        region = gray[y_start:y_end, x_start : x_start + width]
        region_h, region_w = region.shape

        if region_h == 0 or region_w == 0:
            return {"is_daily": False, "confidence": 0.0, "v_count": 0, "v_positions": []}

        # Count vertical dotted lines
        v_count, v_positions = self._count_vertical_lines(region)

        # Check if count matches expected
        if v_count not in self._expected_lines:
            return {
                "is_daily": False,
                "confidence": 0.0,
                "v_count": v_count,
                "v_positions": v_positions,
            }

        # Check spacing - should be approximately width/4
        if len(v_positions) < 2:
            return {
                "is_daily": False,
                "confidence": 0.0,
                "v_count": v_count,
                "v_positions": v_positions,
            }

        spacings = [v_positions[i + 1] - v_positions[i] for i in range(len(v_positions) - 1)]
        mean_spacing = np.mean(spacings)
        expected_spacing = width / 4

        # Check spacing is close to expected
        spacing_error = abs(mean_spacing - expected_spacing) / expected_spacing
        if spacing_error > self._spacing_tolerance:
            return {
                "is_daily": False,
                "confidence": 0.0,
                "v_count": v_count,
                "v_positions": v_positions,
                "mean_spacing": mean_spacing,
                "expected_spacing": expected_spacing,
            }

        # Check spacing consistency
        max_deviation = max(abs(s - mean_spacing) for s in spacings)
        if max_deviation > mean_spacing * 0.15:
            return {
                "is_daily": False,
                "confidence": 0.0,
                "v_count": v_count,
                "v_positions": v_positions,
                "mean_spacing": mean_spacing,
            }

        # Calculate confidence
        # Higher confidence for:
        # - Closer to expected spacing
        # - More consistent spacing
        # - Exactly 4 or 5 lines
        confidence = 0.8
        confidence += (1 - spacing_error) * 0.1
        confidence += (1 - max_deviation / mean_spacing) * 0.1
        confidence = min(0.99, confidence)

        return {
            "is_daily": True,
            "confidence": confidence,
            "v_count": v_count,
            "v_positions": v_positions,
            "mean_spacing": mean_spacing,
        }

    def _count_vertical_lines(self, region: np.ndarray) -> tuple[int, list[int]]:
        """Count vertical dotted lines in a region."""
        h, w = region.shape
        vertical_positions = []

        for x in range(w):
            col = region[:, x]
            gray_pixels = np.sum((col >= self._gray_min) & (col <= self._gray_max))
            if gray_pixels > h * self._min_height_pct:
                vertical_positions.append(x)

        if not vertical_positions:
            return 0, []

        # Cluster nearby positions
        clusters = self._cluster_positions(vertical_positions, max_gap=5)

        return len(clusters), clusters

    def _generate_candidate_regions(
        self,
        image_height: int,
        expected_height: int,
    ) -> list[dict]:
        """Generate candidate regions to check when no hints provided."""
        regions = []
        step = expected_height // 2

        for y in range(0, image_height - expected_height, step):
            regions.append(
                {
                    "y_start": y,
                    "y_end": y + expected_height,
                }
            )

        return regions

    def validate_region(
        self,
        image: np.ndarray,
        bounds: GridBounds,
    ) -> tuple[bool, float, dict]:
        """
        Validate that a region is a daily chart based on vertical lines.

        Useful for validating results from other strategies.

        Returns:
            (is_valid, confidence, diagnostics)
        """
        gray = self._to_grayscale(image)

        result = self._check_region(
            gray,
            bounds.x,
            bounds.width,
            bounds.y,
            bounds.y + bounds.height,
        )

        return result["is_daily"], result["confidence"], result
