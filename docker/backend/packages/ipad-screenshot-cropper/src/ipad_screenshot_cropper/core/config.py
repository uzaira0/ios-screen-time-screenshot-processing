"""Configuration dataclasses for iPad screenshot cropping.

This module contains all configuration values for geometric cropping operations.
NO PHI-related configuration - that's handled by phi-detector-remover package.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CropDimensions:
    """Dimensions for cropping iPad screenshots."""

    x: int = 630
    y: int = 0
    width: int = 1620
    height: int = 2160


@dataclass(frozen=True)
class ROICoordinates:
    """Region of Interest coordinates."""

    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class ImageDimensions:
    """All dimension configurations for image processing."""

    crop: CropDimensions = field(default_factory=CropDimensions)


@dataclass(frozen=True)
class ColorRange:
    """HSV color range for blue detection."""

    low: tuple[int, int, int] = (100, 50, 50)
    high: tuple[int, int, int] = (130, 255, 255)


@dataclass
class ProcessingConfig:
    """Configuration for image processing."""

    min_patch_height: int = 2160
    dimension_tolerance: int = 10


@dataclass(frozen=True)
class AssetConfig:
    """Configuration for asset file paths.

    Note: These will be resolved using importlib.resources in the actual processor.
    """

    bottom_patch_image: str = "bottom_patch_image.png"
    top_patch_image: str = "top_patch_image.png"
    font_file: str = "SF-Pro-Display-Medium.otf"
    font_size: int = 40


@dataclass
class CropperConfig:
    """Main configuration for the cropper."""

    dimensions: ImageDimensions = field(default_factory=ImageDimensions)
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)
    assets: AssetConfig = field(default_factory=AssetConfig)

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.processing.min_patch_height < self.dimensions.crop.height:
            raise ValueError(
                f"min_patch_height ({self.processing.min_patch_height}) "
                f"must be >= crop height ({self.dimensions.crop.height})"
            )
