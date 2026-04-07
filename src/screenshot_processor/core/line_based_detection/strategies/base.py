"""
Base class for grid detection strategies with shared utilities.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from ...image_utils import simple_grayscale
from ..protocol import GridBounds, GridDetectionResult


class BaseGridStrategy(ABC):
    """Base class providing common utilities for grid detection strategies."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name identifying this strategy."""
        ...

    @abstractmethod
    def detect(
        self,
        image: np.ndarray,
        resolution: str | None = None,
        hints: dict | None = None,
    ) -> GridDetectionResult:
        """Detect the grid bounds in an image."""
        ...

    def supports_resolution(self, resolution: str) -> bool:
        """Default: support all resolutions."""
        return True

    def _make_success(
        self,
        bounds: GridBounds,
        confidence: float,
        diagnostics: dict | None = None,
    ) -> GridDetectionResult:
        """Create a successful detection result."""
        return GridDetectionResult(
            bounds=bounds,
            confidence=confidence,
            strategy_name=self.name,
            diagnostics=diagnostics or {},
        )

    def _make_failure(
        self,
        error: str,
        diagnostics: dict | None = None,
    ) -> GridDetectionResult:
        """Create a failed detection result."""
        return GridDetectionResult(
            bounds=None,
            confidence=0.0,
            strategy_name=self.name,
            error=error,
            diagnostics=diagnostics or {},
        )

    @staticmethod
    def _to_grayscale(image: np.ndarray) -> np.ndarray:
        """Convert BGR image to grayscale."""
        if len(image.shape) == 2:
            return image
        return simple_grayscale(image)

    @staticmethod
    def _cluster_positions(positions: list[int], max_gap: int = 5) -> list[int]:
        """Cluster nearby positions and return cluster centers."""
        if not positions:
            return []

        positions = sorted(positions)
        clusters = []
        current = [positions[0]]

        for pos in positions[1:]:
            if pos - current[-1] <= max_gap:
                current.append(pos)
            else:
                clusters.append(int(np.mean(current)))
                current = [pos]

        clusters.append(int(np.mean(current)))
        return clusters
