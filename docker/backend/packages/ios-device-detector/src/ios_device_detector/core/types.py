"""Type definitions for iOS device detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DeviceCategory(StrEnum):
    """Category of iOS device."""

    IPHONE = "iphone"
    IPAD = "ipad"
    UNKNOWN = "unknown"


class DeviceFamily(StrEnum):
    """Device family/line."""

    # iPhone families
    IPHONE_SE = "iphone_se"
    IPHONE_STANDARD = "iphone_standard"
    IPHONE_PLUS = "iphone_plus"
    IPHONE_PRO = "iphone_pro"
    IPHONE_PRO_MAX = "iphone_pro_max"
    IPHONE_MINI = "iphone_mini"

    # iPad families
    IPAD_STANDARD = "ipad_standard"
    IPAD_MINI = "ipad_mini"
    IPAD_AIR = "ipad_air"
    IPAD_PRO_11 = "ipad_pro_11"
    IPAD_PRO_12_9 = "ipad_pro_12_9"

    UNKNOWN = "unknown"


class Orientation(StrEnum):
    """Screen orientation."""

    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ScreenDimensions:
    """Screen dimensions in pixels."""

    width: int
    height: int

    @property
    def aspect_ratio(self) -> float:
        """Get aspect ratio (height/width for portrait)."""
        if self.width == 0:
            return 0.0
        return self.height / self.width

    @property
    def portrait(self) -> "ScreenDimensions":
        """Return dimensions in portrait orientation (width < height)."""
        if self.width <= self.height:
            return self
        return ScreenDimensions(width=self.height, height=self.width)

    @property
    def landscape(self) -> "ScreenDimensions":
        """Return dimensions in landscape orientation (width > height)."""
        if self.width >= self.height:
            return self
        return ScreenDimensions(width=self.height, height=self.width)

    def matches(self, other: "ScreenDimensions", tolerance: int = 0) -> bool:
        """Check if dimensions match within tolerance."""
        return (
            abs(self.width - other.width) <= tolerance
            and abs(self.height - other.height) <= tolerance
        )

    def matches_either_orientation(
        self, other: "ScreenDimensions", tolerance: int = 0
    ) -> tuple[bool, Orientation]:
        """Check if dimensions match in either orientation."""
        if self.matches(other, tolerance):
            if self.width <= self.height:
                return True, Orientation.PORTRAIT
            return True, Orientation.LANDSCAPE

        # Check rotated
        rotated = ScreenDimensions(width=other.height, height=other.width)
        if self.matches(rotated, tolerance):
            if self.width <= self.height:
                return True, Orientation.PORTRAIT
            return True, Orientation.LANDSCAPE

        return False, Orientation.UNKNOWN


@dataclass
class DetectionResult:
    """Result of device detection."""

    # Detection outcome
    detected: bool
    confidence: float  # 0.0 to 1.0

    # Device information
    device_model: str = "Unknown"
    device_category: DeviceCategory = DeviceCategory.UNKNOWN
    device_family: DeviceFamily = DeviceFamily.UNKNOWN

    # Dimension information
    detected_dimensions: ScreenDimensions | None = None
    expected_dimensions: ScreenDimensions | None = None
    orientation: Orientation = Orientation.UNKNOWN
    scale_factor: int = 1

    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_iphone(self) -> bool:
        """Check if detected device is an iPhone."""
        return self.device_category == DeviceCategory.IPHONE

    @property
    def is_ipad(self) -> bool:
        """Check if detected device is an iPad."""
        return self.device_category == DeviceCategory.IPAD

    @property
    def is_portrait(self) -> bool:
        """Check if image is in portrait orientation."""
        return self.orientation == Orientation.PORTRAIT

    @property
    def is_landscape(self) -> bool:
        """Check if image is in landscape orientation."""
        return self.orientation == Orientation.LANDSCAPE

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "detected": self.detected,
            "confidence": self.confidence,
            "device_model": self.device_model,
            "device_category": self.device_category.value,
            "device_family": self.device_family.value,
            "orientation": self.orientation.value,
            "scale_factor": self.scale_factor,
            "detected_dimensions": {
                "width": self.detected_dimensions.width,
                "height": self.detected_dimensions.height,
            }
            if self.detected_dimensions
            else None,
            "expected_dimensions": {
                "width": self.expected_dimensions.width,
                "height": self.expected_dimensions.height,
            }
            if self.expected_dimensions
            else None,
            "metadata": self.metadata,
        }

    @classmethod
    def not_detected(
        cls, width: int, height: int, reason: str = ""
    ) -> "DetectionResult":
        """Create a not-detected result."""
        return cls(
            detected=False,
            confidence=0.0,
            detected_dimensions=ScreenDimensions(width=width, height=height),
            metadata={"reason": reason} if reason else {},
        )
