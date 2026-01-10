"""
Combined grid detection strategy.

Uses multiple strategies together:
1. LookupTable for approximate x, width, height (as hints only)
2. HorizontalLines to find candidate y regions
3. VerticalLines to validate which region is the daily chart
4. Dynamic x-boundary detection using vertical grid edges
"""

from __future__ import annotations

import logging

import numpy as np

from ..protocol import GridBounds, GridDetectionResult
from .base import BaseGridStrategy
from .color_validation import ColorValidationStrategy
from .horizontal_lines import HorizontalLineStrategy
from .lookup import LookupTableStrategy
from .vertical_lines import VerticalLineStrategy

logger = logging.getLogger(__name__)

# Gray value range for detecting grid lines (dotted vertical lines)
GRID_LINE_GRAY_MIN = 190
GRID_LINE_GRAY_MAX = 220


class CombinedStrategy(BaseGridStrategy):
    """
    Combined strategy using lookup + horizontal + vertical line detection.

    This is the recommended strategy for best accuracy:
    1. Get x, width, height from lookup table
    2. Find candidate regions using horizontal line spacing
    3. Validate using vertical line count (4-5 = daily, 7+ = weekly)

    Achieves ~95% accuracy on Screen Time screenshots.
    """

    def __init__(
        self,
        lookup_strategy: LookupTableStrategy | None = None,
        horizontal_strategy: HorizontalLineStrategy | None = None,
        vertical_strategy: VerticalLineStrategy | None = None,
        color_strategy: ColorValidationStrategy | None = None,
        validate_color: bool = True,
    ):
        """
        Initialize combined strategy with sub-strategies.

        Args:
            lookup_strategy: Strategy for resolution lookup (default: new instance)
            horizontal_strategy: Strategy for horizontal line detection
            vertical_strategy: Strategy for vertical line validation
            color_strategy: Strategy for color validation (blue vs cyan bars)
            validate_color: Whether to validate bar colors (rejects pickups charts)
        """
        self._lookup = lookup_strategy or LookupTableStrategy()
        self._horizontal = horizontal_strategy or HorizontalLineStrategy()
        self._vertical = vertical_strategy or VerticalLineStrategy()
        self._color = color_strategy or ColorValidationStrategy()
        self._validate_color = validate_color

    @property
    def name(self) -> str:
        return "combined"

    def detect(
        self,
        image: np.ndarray,
        resolution: str | None = None,
        hints: dict | None = None,
    ) -> GridDetectionResult:
        """
        Detect grid using combined approach.
        """
        gray = self._to_grayscale(image)
        h, w = gray.shape

        # Infer resolution
        if resolution is None:
            resolution = f"{w}x{h}"

        # Step 1: Get x, width, height from lookup
        partial_bounds = self._lookup.get_partial_bounds(resolution)

        if partial_bounds is None:
            return self._make_failure(
                f"Resolution {resolution} not supported",
                diagnostics={"step": "lookup"},
            )

        x_start = partial_bounds["x"]
        width = partial_bounds["width"]
        expected_height = partial_bounds["height"]

        # Step 2: Find horizontal line groups
        h_result = self._horizontal.detect(
            image,
            resolution=resolution,
            hints=partial_bounds,
        )

        if not h_result.success and not h_result.diagnostics.get("lines_found"):
            return self._make_failure(
                "No horizontal grid lines found",
                diagnostics={"step": "horizontal_lines"},
            )

        # Get candidate regions from horizontal detection
        # Even if h_result failed, we might have partial data in diagnostics
        candidate_regions = []

        if h_result.success and h_result.bounds:
            # Use the detected region as primary candidate
            candidate_regions.append(
                {
                    "y_start": h_result.bounds.y,
                    "y_end": h_result.bounds.y + h_result.bounds.height,
                    "source": "horizontal_primary",
                }
            )

        # Also check if diagnostics has additional groups
        if "all_groups" in h_result.diagnostics:
            # Re-run to get all groups (the result only returns the best one)
            lines = self._horizontal._find_horizontal_lines(gray, x_start, x_start + width)
            groups = self._horizontal._find_evenly_spaced_groups(lines, expected_height)
            for g in groups:
                candidate_regions.append(
                    {
                        "y_start": g["y_start"],
                        "y_end": g["y_end"],
                        "source": "horizontal_group",
                    }
                )

        if not candidate_regions:
            return self._make_failure(
                "No candidate regions from horizontal line detection",
                diagnostics={"step": "horizontal_lines"},
            )

        # Step 3: Validate each candidate with vertical line detection + color validation
        best_result = None
        best_confidence = 0.0
        validation_results = []

        for region in candidate_regions:
            y_start = region["y_start"]
            y_end = region["y_end"]

            # Check vertical lines in this region
            bounds = GridBounds(
                x=x_start,
                y=y_start,
                width=width,
                height=y_end - y_start,
            )

            is_daily, v_confidence, v_diag = self._vertical.validate_region(image, bounds)

            # Step 4: Color validation (reject pickups charts with cyan bars)
            color_valid = True
            color_diag = {}
            if is_daily and self._validate_color:
                color_valid, _color_confidence, color_diag = self._color.validate_region(image, bounds)
                if not color_valid:
                    is_daily = False

            validation_results.append(
                {
                    "region": region,
                    "is_daily": is_daily,
                    "v_confidence": v_confidence,
                    "v_count": v_diag.get("v_count", 0),
                    "color_valid": color_valid,
                    "color_diag": color_diag,
                }
            )

            if is_daily and v_confidence > best_confidence:
                best_confidence = v_confidence
                best_result = {
                    "bounds": bounds,
                    "v_count": v_diag.get("v_count"),
                    "v_positions": v_diag.get("v_positions"),
                    "color_diag": color_diag,
                }

        if best_result is None:
            return self._make_failure(
                "No candidate region matches daily chart pattern",
                diagnostics={
                    "step": "vertical_validation",
                    "candidates_checked": len(candidate_regions),
                    "validation_results": validation_results,
                },
            )

        # Step 5: Refine x boundaries using detected vertical lines
        # The lookup table is just a hint - use actual line detection for precise bounds
        refined_bounds = self._refine_x_boundaries(gray, best_result["bounds"], best_result.get("v_positions", []))

        return self._make_success(
            bounds=refined_bounds,
            confidence=best_confidence,
            diagnostics={
                "v_line_count": best_result["v_count"],
                "v_line_positions": best_result["v_positions"],
                "candidates_checked": len(candidate_regions),
                "validation_results": validation_results,
                "original_x": best_result["bounds"].x,
                "original_width": best_result["bounds"].width,
                "refined_x": refined_bounds.x,
                "refined_width": refined_bounds.width,
            },
        )

    def _refine_x_boundaries(
        self,
        gray: np.ndarray,
        bounds: GridBounds,
        v_positions: list[int],
    ) -> GridBounds:
        """
        Refine x boundaries by detecting actual grid edges.

        The lookup table provides approximate x/width. This method finds the
        actual left and right edges of the chart grid by:
        1. Using the detected vertical line positions (if available)
        2. Scanning for vertical grid lines at the edges
        """
        _h, w = gray.shape
        y_start = bounds.y
        y_end = bounds.y + bounds.height

        # Extract the horizontal region around the chart
        # Use a wider search area than the lookup table suggests
        search_margin = 50  # pixels to search beyond lookup bounds
        search_x_start = max(0, bounds.x - search_margin)
        search_x_end = min(w, bounds.x + bounds.width + search_margin)

        # Find all vertical lines in this y-region
        left_edge, right_edge = self._find_grid_edges(gray, search_x_start, search_x_end, y_start, y_end)

        if left_edge is not None and right_edge is not None:
            # Found both edges - use them
            refined_x = left_edge
            refined_width = right_edge - left_edge
            logger.debug(
                f"Refined x boundaries: x={refined_x} width={refined_width} (was x={bounds.x} width={bounds.width})"
            )
            return GridBounds(
                x=refined_x,
                y=bounds.y,
                width=refined_width,
                height=bounds.height,
            )

        # Fallback: if we have vertical line positions from validation,
        # extrapolate the edges based on the expected 4-section layout
        if v_positions and len(v_positions) >= 3:
            # Daily chart has ~4 equal sections between 5 vertical lines
            # The spacing between lines should be width/4
            spacing = np.mean([v_positions[i + 1] - v_positions[i] for i in range(len(v_positions) - 1)])

            # Extrapolate left edge (first line position minus one spacing)
            first_line = v_positions[0]
            left_edge = int(first_line - spacing) + bounds.x

            # Extrapolate right edge (last line position plus one spacing)
            last_line = v_positions[-1]
            right_edge = int(last_line + spacing) + bounds.x

            # Clamp to image bounds
            left_edge = max(0, left_edge)
            right_edge = min(w, right_edge)

            if right_edge > left_edge:
                logger.debug(
                    f"Extrapolated x boundaries from v_positions: x={left_edge} width={right_edge - left_edge}"
                )
                return GridBounds(
                    x=left_edge,
                    y=bounds.y,
                    width=right_edge - left_edge,
                    height=bounds.height,
                )

        # No refinement possible, return original bounds
        logger.debug("Could not refine x boundaries, using lookup values")
        return bounds

    def _find_grid_edges(
        self,
        gray: np.ndarray,
        x_start: int,
        x_end: int,
        y_start: int,
        y_end: int,
    ) -> tuple[int | None, int | None]:
        """
        Find the left and right edges of the grid by detecting vertical lines.

        Returns (left_edge, right_edge) in absolute image coordinates.
        """
        region = gray[y_start:y_end, x_start:x_end]
        region_h, region_w = region.shape

        if region_h == 0 or region_w == 0:
            return None, None

        # For each column, count how many pixels are in the "gray line" range
        # A vertical grid line will have many gray pixels in its column
        min_line_coverage = 0.3  # At least 30% of column height must be gray

        vertical_line_x_positions = []
        for x in range(region_w):
            col = region[:, x]
            gray_pixels = np.sum((col >= GRID_LINE_GRAY_MIN) & (col <= GRID_LINE_GRAY_MAX))
            if gray_pixels >= region_h * min_line_coverage:
                vertical_line_x_positions.append(x)

        if not vertical_line_x_positions:
            return None, None

        # Cluster nearby positions (vertical lines are 1-3 pixels wide)
        clusters = []
        current_cluster = [vertical_line_x_positions[0]]

        for i in range(1, len(vertical_line_x_positions)):
            if vertical_line_x_positions[i] - vertical_line_x_positions[i - 1] <= 3:
                current_cluster.append(vertical_line_x_positions[i])
            else:
                clusters.append(int(np.mean(current_cluster)))
                current_cluster = [vertical_line_x_positions[i]]
        clusters.append(int(np.mean(current_cluster)))

        if len(clusters) < 2:
            return None, None

        # Pick cluster closest to expected position (x_start / x_end).
        # Using first/last would pick up gray UI elements at extreme
        # edges of the search window as false grid boundaries.
        left_edge = x_start + min(clusters, key=lambda c: abs(c - 0))
        right_edge = x_start + min(clusters, key=lambda c: abs(c - (x_end - x_start)))

        return left_edge, right_edge
