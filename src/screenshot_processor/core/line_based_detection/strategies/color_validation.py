"""
Color-based validation strategy.

Validates that a detected region contains blue bars (daily usage chart)
rather than cyan bars (pickups chart) or other colors.
"""

from __future__ import annotations

import logging

import numpy as np

from ..protocol import GridBounds, GridDetectionResult
from .base import BaseGridStrategy

logger = logging.getLogger(__name__)


class ColorValidationStrategy(BaseGridStrategy):
    """
    Validate chart type by checking bar colors.

    Daily usage chart: Blue bars (hue ~100-130 in OpenCV HSV)
    Pickups chart: Cyan/teal bars (hue ~80-100)

    This strategy is used as a validator, not a primary detector.
    """

    # OpenCV uses H: 0-180, S: 0-255, V: 0-255
    BLUE_HUE_MIN = 100
    BLUE_HUE_MAX = 130
    CYAN_HUE_MIN = 80
    CYAN_HUE_MAX = 100

    def __init__(
        self,
        min_saturation: int = 50,
        min_value: int = 50,
        min_blue_ratio: float = 0.5,
    ):
        """
        Initialize color validation strategy.

        Args:
            min_saturation: Minimum saturation to consider a pixel colored
            min_value: Minimum value to consider a pixel colored
            min_blue_ratio: Minimum ratio of blue/(blue+cyan) pixels to pass
        """
        self._min_saturation = min_saturation
        self._min_value = min_value
        self._min_blue_ratio = min_blue_ratio

    @property
    def name(self) -> str:
        return "color_validation"

    def detect(
        self,
        image: np.ndarray,
        resolution: str | None = None,
        hints: dict | None = None,
    ) -> GridDetectionResult:
        """
        This strategy requires a pre-detected region in hints.
        """
        if not hints or "bounds" not in hints:
            return self._make_failure("ColorValidationStrategy requires 'bounds' in hints")

        bounds = hints["bounds"]
        if isinstance(bounds, dict):
            bounds = GridBounds(**bounds)

        is_daily, confidence, diagnostics = self.validate_region(image, bounds)

        if is_daily:
            return self._make_success(
                bounds=bounds,
                confidence=confidence,
                diagnostics=diagnostics,
            )
        else:
            return self._make_failure(
                "Region does not contain blue bars (likely pickups chart)",
                diagnostics=diagnostics,
            )

    def validate_region(
        self,
        image: np.ndarray,
        bounds: GridBounds,
    ) -> tuple[bool, float, dict]:
        """
        Validate that a region contains blue bars (daily chart).

        Returns:
            (is_daily_chart, confidence, diagnostics)
        """
        import cv2

        # Extract region
        x, y, w, h = bounds.x, bounds.y, bounds.width, bounds.height
        region = image[y : y + h, x : x + w]

        if region.size == 0:
            return False, 0.0, {"error": "empty region"}

        # Convert to HSV
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

        # Find colored pixels (saturation and value above threshold)
        colored_mask = (hsv[:, :, 1] > self._min_saturation) & (hsv[:, :, 2] > self._min_value)

        if not np.any(colored_mask):
            # No colored bars - might be empty chart, allow it
            return True, 0.7, {"note": "no colored bars detected", "blue_count": 0, "cyan_count": 0}

        hues = hsv[:, :, 0][colored_mask]

        # Count blue vs cyan pixels
        blue_count = np.sum((hues >= self.BLUE_HUE_MIN) & (hues <= self.BLUE_HUE_MAX))
        cyan_count = np.sum((hues >= self.CYAN_HUE_MIN) & (hues < self.BLUE_HUE_MIN))

        total_relevant = blue_count + cyan_count

        diagnostics = {
            "blue_count": int(blue_count),
            "cyan_count": int(cyan_count),
            "blue_ratio": float(blue_count / total_relevant) if total_relevant > 0 else 0.0,
            "mean_hue": float(np.mean(hues)),
        }

        if total_relevant == 0:
            # No blue or cyan - might be gray bars (weekly) or other
            # Check if there are any bars at all
            return True, 0.6, {**diagnostics, "note": "no blue/cyan bars"}

        blue_ratio = blue_count / total_relevant

        # Daily chart should have predominantly blue bars
        is_daily = blue_ratio >= self._min_blue_ratio

        # Confidence based on how strongly blue vs cyan
        if is_daily:
            confidence = 0.7 + (blue_ratio - self._min_blue_ratio) * 0.6
            confidence = min(0.99, confidence)
        else:
            confidence = 0.0

        return is_daily, confidence, diagnostics
