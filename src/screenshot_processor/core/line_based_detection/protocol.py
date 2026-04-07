"""
Protocol definitions for grid detection strategies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np


@dataclass(frozen=True)
class GridBounds:
    """Immutable grid boundary coordinates."""

    x: int
    y: int
    width: int
    height: int

    def to_tuple(self) -> tuple[int, int, int, int]:
        """Return as (x, y, width, height) tuple."""
        return (self.x, self.y, self.width, self.height)

    def to_corners(self) -> tuple[tuple[int, int], tuple[int, int]]:
        """Return as ((upper_left_x, upper_left_y), (lower_right_x, lower_right_y))."""
        return ((self.x, self.y), (self.x + self.width, self.y + self.height))

    @classmethod
    def from_corners(cls, upper_left: tuple[int, int], lower_right: tuple[int, int]) -> GridBounds:
        """Create from corner coordinates."""
        return cls(
            x=upper_left[0],
            y=upper_left[1],
            width=lower_right[0] - upper_left[0],
            height=lower_right[1] - upper_left[1],
        )


@dataclass
class GridDetectionResult:
    """Result from a grid detection strategy."""

    # The detected grid bounds (None if detection failed)
    bounds: GridBounds | None

    # Confidence score from 0.0 to 1.0
    confidence: float

    # Name of the strategy that produced this result
    strategy_name: str

    # Whether detection succeeded
    success: bool = field(init=False)

    # Optional diagnostic information
    diagnostics: dict = field(default_factory=dict)

    # Optional error message if detection failed
    error: str | None = None

    def __post_init__(self):
        self.success = self.bounds is not None and self.confidence > 0

    def __repr__(self) -> str:
        if self.success:
            return (
                f"GridDetectionResult("
                f"strategy={self.strategy_name!r}, "
                f"bounds={self.bounds}, "
                f"confidence={self.confidence:.2f})"
            )
        return f"GridDetectionResult(strategy={self.strategy_name!r}, success=False, error={self.error!r})"


@runtime_checkable
class GridDetectionStrategy(Protocol):
    """
    Protocol for grid detection strategies.

    Each strategy implements a different method for detecting the
    daily hourly chart grid in iOS Screen Time screenshots.
    """

    @property
    def name(self) -> str:
        """Unique name identifying this strategy."""
        ...

    def detect(
        self,
        image: np.ndarray,
        resolution: str | None = None,
        hints: dict | None = None,
    ) -> GridDetectionResult:
        """
        Detect the grid bounds in an image.

        Args:
            image: BGR image as numpy array
            resolution: Optional resolution string (e.g., "848x2266")
            hints: Optional hints from other strategies or prior knowledge
                   (e.g., {"x": 70, "width": 640} from lookup table)

        Returns:
            GridDetectionResult with bounds and confidence
        """
        ...

    def supports_resolution(self, resolution: str) -> bool:
        """Check if this strategy supports the given resolution."""
        ...
