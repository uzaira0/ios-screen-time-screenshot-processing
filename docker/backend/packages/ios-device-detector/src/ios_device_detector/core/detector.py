"""Main device detector implementation."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .exceptions import ImageLoadError, InvalidDimensionsError
from .types import (
    DetectionResult,
    DeviceCategory,
    Orientation,
    ScreenDimensions,
)
from ..profiles.registry import DeviceProfile, ProfileRegistry, get_profile_registry

if TYPE_CHECKING:
    pass


class DeviceDetector:
    """Detector for iOS device models from image dimensions."""

    def __init__(
        self,
        registry: ProfileRegistry | None = None,
        tolerance: int = 5,
        min_confidence: float = 0.5,
    ) -> None:
        """
        Initialize the device detector.

        Args:
            registry: Device profile registry (uses default if None)
            tolerance: Pixel tolerance for dimension matching
            min_confidence: Minimum confidence to report a match
        """
        self.registry = registry or get_profile_registry()
        self.tolerance = tolerance
        self.min_confidence = min_confidence

    def detect_from_dimensions(
        self,
        width: int,
        height: int,
    ) -> DetectionResult:
        """
        Detect device from image dimensions.

        Args:
            width: Image width in pixels
            height: Image height in pixels

        Returns:
            DetectionResult with device information and confidence
        """
        if width <= 0 or height <= 0:
            raise InvalidDimensionsError(width, height, "Dimensions must be positive")

        input_dims = ScreenDimensions(width=width, height=height)

        # Find best matching profile
        best_match: tuple[DeviceProfile | None, float, Orientation] = (None, 0.0, Orientation.UNKNOWN)

        for profile in self.registry.get_all_profiles():
            confidence, orientation = self._calculate_match_confidence(
                input_dims, profile
            )

            if confidence > best_match[1]:
                best_match = (profile, confidence, orientation)

        profile, confidence, orientation = best_match

        if profile is None or confidence < self.min_confidence:
            return DetectionResult.not_detected(
                width, height, "No matching device profile found"
            )

        return DetectionResult(
            detected=True,
            confidence=confidence,
            device_model=profile.model_name,
            device_category=profile.category,
            device_family=profile.family,
            detected_dimensions=input_dims,
            expected_dimensions=profile.screenshot_dimensions,
            orientation=orientation,
            scale_factor=profile.scale_factor,
            metadata={
                "profile_id": profile.profile_id,
                "display_name": profile.display_name,
            },
        )

    def detect_from_file(self, filepath: str | Path) -> DetectionResult:
        """
        Detect device from image file.

        Args:
            filepath: Path to image file

        Returns:
            DetectionResult with device information

        Raises:
            ImageLoadError: If image cannot be loaded
        """
        try:
            from PIL import Image

            with Image.open(filepath) as img:
                width, height = img.size
                result = self.detect_from_dimensions(width, height)

                # Add file metadata
                result.metadata["filepath"] = str(filepath)
                if hasattr(img, "info"):
                    result.metadata["image_format"] = img.format

                return result

        except ImportError:
            raise ImageLoadError(
                str(filepath),
                Exception("Pillow is required for file detection. Install with: pip install pillow"),
            )
        except Exception as e:
            raise ImageLoadError(str(filepath), e)

    def detect_batch(
        self,
        dimensions_list: list[tuple[int, int]],
    ) -> list[DetectionResult]:
        """
        Detect devices for multiple dimension pairs.

        Args:
            dimensions_list: List of (width, height) tuples

        Returns:
            List of DetectionResult objects
        """
        return [
            self.detect_from_dimensions(width, height)
            for width, height in dimensions_list
        ]

    def get_device_category(self, width: int, height: int) -> DeviceCategory:
        """
        Quick check to determine if dimensions are iPhone or iPad.

        Args:
            width: Image width in pixels
            height: Image height in pixels

        Returns:
            DeviceCategory (IPHONE, IPAD, or UNKNOWN)
        """
        result = self.detect_from_dimensions(width, height)
        return result.device_category

    def is_valid_ios_screenshot(self, width: int, height: int) -> bool:
        """
        Check if dimensions represent a valid iOS screenshot.

        Args:
            width: Image width in pixels
            height: Image height in pixels

        Returns:
            True if dimensions match any known iOS device
        """
        result = self.detect_from_dimensions(width, height)
        return result.detected and result.confidence >= self.min_confidence

    def _calculate_match_confidence(
        self,
        input_dims: ScreenDimensions,
        profile: DeviceProfile,
    ) -> tuple[float, Orientation]:
        """
        Calculate confidence score for a profile match.

        Returns:
            Tuple of (confidence, orientation)
        """
        expected = profile.screenshot_dimensions

        # Check exact match
        if input_dims.matches(expected, 0):
            return 1.0, Orientation.PORTRAIT if input_dims.width <= input_dims.height else Orientation.LANDSCAPE

        # Check match within tolerance
        matches, orientation = input_dims.matches_either_orientation(
            expected, self.tolerance
        )

        if matches:
            # Calculate confidence based on deviation
            portrait_input = input_dims.portrait
            portrait_expected = expected.portrait

            width_diff = abs(portrait_input.width - portrait_expected.width)
            height_diff = abs(portrait_input.height - portrait_expected.height)

            max_diff = max(width_diff, height_diff)
            confidence = 1.0 - (max_diff / self.tolerance) * 0.2

            return max(0.8, confidence), orientation

        # Check for partially-cropped screenshots (width matches, height shorter)
        # This handles iPad screenshots that were manually cropped at top/bottom
        portrait_input = input_dims.portrait
        portrait_expected = expected.portrait

        width_diff = abs(portrait_input.width - portrait_expected.width)

        if width_diff <= self.tolerance:
            # Width matches - check if height is shorter (partially cropped)
            if portrait_input.height < portrait_expected.height:
                # Height is shorter but at least 50% of expected
                if portrait_input.height > portrait_expected.height * 0.5:
                    # Good match - partially cropped screenshot
                    height_ratio = portrait_input.height / portrait_expected.height
                    confidence = 0.85 * height_ratio  # Scale confidence by how much is remaining
                    orientation = (
                        Orientation.PORTRAIT
                        if input_dims.width <= input_dims.height
                        else Orientation.LANDSCAPE
                    )
                    return max(0.7, confidence), orientation

        # Check aspect ratio match only
        input_ratio = input_dims.portrait.aspect_ratio
        expected_ratio = expected.portrait.aspect_ratio

        ratio_diff = abs(input_ratio - expected_ratio)

        if ratio_diff < 0.05:
            # Aspect ratio matches but dimensions don't
            # This could be a different resolution/scale
            confidence = 0.6 - ratio_diff * 2
            orientation = (
                Orientation.PORTRAIT
                if input_dims.width <= input_dims.height
                else Orientation.LANDSCAPE
            )
            return max(0.5, confidence), orientation

        return 0.0, Orientation.UNKNOWN
