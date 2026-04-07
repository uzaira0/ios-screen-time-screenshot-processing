"""
Interfaces for grid detection and bar processing.

This module defines the contracts for:
1. Grid Detection - Finding the grid region in a screenshot
2. Bar Processing - Extracting hourly values from a grid region
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    pass


class GridDetectionMethod(StrEnum):
    """Available grid detection methods."""

    OCR_ANCHORED = "ocr_anchored"
    LINE_BASED = "line_based"
    MANUAL = "manual"


@dataclass
class GridBounds:
    """Detected grid boundaries."""

    upper_left_x: int
    upper_left_y: int
    lower_right_x: int
    lower_right_y: int

    @property
    def width(self) -> int:
        return self.lower_right_x - self.upper_left_x

    @property
    def height(self) -> int:
        return self.lower_right_y - self.upper_left_y

    @property
    def upper_left(self) -> tuple[int, int]:
        return (self.upper_left_x, self.upper_left_y)

    @property
    def lower_right(self) -> tuple[int, int]:
        return (self.lower_right_x, self.lower_right_y)

    def to_dict(self) -> dict:
        return {
            "upper_left_x": self.upper_left_x,
            "upper_left_y": self.upper_left_y,
            "lower_right_x": self.lower_right_x,
            "lower_right_y": self.lower_right_y,
        }

    @classmethod
    def from_dict(cls, data: dict) -> GridBounds:
        return cls(
            upper_left_x=data["upper_left_x"],
            upper_left_y=data["upper_left_y"],
            lower_right_x=data["lower_right_x"],
            lower_right_y=data["lower_right_y"],
        )


@dataclass
class GridDetectionResult:
    """Result of grid detection."""

    success: bool
    bounds: GridBounds | None = None
    confidence: float | None = None
    method: GridDetectionMethod = GridDetectionMethod.OCR_ANCHORED
    error: str | None = None
    diagnostics: dict = field(default_factory=dict)


@dataclass
class BarProcessingResult:
    """Result of bar value extraction."""

    success: bool
    hourly_values: dict[str, int] | dict[str, float] | None = None
    alignment_score: float | None = None
    error: str | None = None


@dataclass
class TitleTotalResult:
    """Result of title and total extraction."""

    title: str | None = None
    total: str | None = None
    title_y_position: int | None = None
    is_daily_total: bool = False


class IGridDetector(ABC):
    """Interface for grid detection strategies."""

    @property
    @abstractmethod
    def method(self) -> GridDetectionMethod:
        """Return the detection method identifier."""
        ...

    @abstractmethod
    def detect(self, image: np.ndarray, **kwargs) -> GridDetectionResult:
        """
        Detect the grid region in an image.

        Args:
            image: The screenshot image as numpy array (BGR format)
            **kwargs: Additional method-specific parameters

        Returns:
            GridDetectionResult with bounds if successful
        """
        ...


class IBarProcessor(ABC):
    """Interface for extracting bar values from a grid region."""

    @abstractmethod
    def extract(
        self,
        image: np.ndarray,
        bounds: GridBounds,
        is_battery: bool = False,
        use_fractional: bool = True,
    ) -> BarProcessingResult:
        """
        Extract hourly bar values from a grid region.

        Args:
            image: The screenshot image as numpy array (BGR format)
            bounds: The grid boundaries
            is_battery: Whether this is a battery screenshot (affects processing)
            use_fractional: If True, keep 2 decimal places; if False, round to int

        Returns:
            BarProcessingResult with hourly values if successful
        """
        ...


class ITitleExtractor(ABC):
    """Interface for extracting title and total from screenshots."""

    @abstractmethod
    def extract(
        self,
        image: np.ndarray,
        image_type: str,
        existing_title: str | None = None,
        existing_total: str | None = None,
    ) -> TitleTotalResult:
        """
        Extract title and total usage from an image.

        Args:
            image: The screenshot image as numpy array (BGR format)
            image_type: "screen_time" or "battery"
            existing_title: Existing title to preserve (skip OCR)
            existing_total: Existing total to preserve (skip OCR)

        Returns:
            TitleTotalResult with extracted values
        """
        ...
