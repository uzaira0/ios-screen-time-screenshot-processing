"""Device profiles for iPad models with dimension tolerances.

This module contains device detection logic and dimension profiles for various iPad models.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple


class DeviceModel(str, Enum):
    """Supported iPad models."""

    # Models identified by ios-device-detector
    IPAD_9TH_GEN = "iPad 9th Gen"  # 1620x2160
    IPAD_10TH_GEN = "iPad 10th Gen"  # 1640x2360
    IPAD_MINI_5TH_GEN = "iPad mini 5th Gen"  # 1536x2048
    IPAD_MINI_6TH_GEN = "iPad mini 6th Gen"  # 1488x2266
    IPAD_AIR_3RD_GEN = "iPad Air 3rd Gen"  # 1488x2266
    IPAD_PRO_11 = 'iPad Pro 11"'  # 1668x2388 or 1668x2224
    IPAD_PRO_11_ALT = 'iPad Pro 11" (alt)'  # 1668x2224
    IPAD_PRO_12_9 = 'iPad Pro 12.9"'  # 2048x2732
    # Legacy names (kept for backward compatibility)
    IPAD_AIR = "iPad Air"
    IPAD_MINI = "iPad Mini"
    IPAD_STANDARD = "iPad"
    UNKNOWN = "Unknown"


class DeviceDimensions(NamedTuple):
    """Expected dimensions for a device in portrait orientation."""

    width: int
    height: int


@dataclass(frozen=True)
class DeviceProfile:
    """Profile for a specific iPad model.

    Attributes:
        model: Device model identifier
        uncropped_dimensions: Expected dimensions before cropping
        cropped_dimensions: Expected dimensions after cropping
        crop_x: X-coordinate to start cropping
        crop_y: Y-coordinate to start cropping (usually 0)
        crop_width: Width of the cropped region
        crop_height: Height of the cropped region
    """

    model: DeviceModel
    uncropped_dimensions: DeviceDimensions
    cropped_dimensions: DeviceDimensions
    crop_x: int
    crop_y: int
    crop_width: int
    crop_height: int


# =============================================================================
# Device Profiles - Based on manual crop reference images
# All use crop_x=640 (standardized left panel removal)
# =============================================================================

# iPad 9th Gen - 1620x2160 -> 980x2160
IPAD_9TH_GEN_PROFILE = DeviceProfile(
    model=DeviceModel.IPAD_9TH_GEN,
    uncropped_dimensions=DeviceDimensions(width=1620, height=2160),
    cropped_dimensions=DeviceDimensions(width=980, height=2160),
    crop_x=640,
    crop_y=0,
    crop_width=980,
    crop_height=2160,
)

# iPad 10th Gen - 1640x2360 -> 1000x2360
IPAD_10TH_GEN_PROFILE = DeviceProfile(
    model=DeviceModel.IPAD_10TH_GEN,
    uncropped_dimensions=DeviceDimensions(width=1640, height=2360),
    cropped_dimensions=DeviceDimensions(width=1000, height=2360),
    crop_x=640,
    crop_y=0,
    crop_width=1000,
    crop_height=2360,
)

# iPad mini 5th Gen - 1536x2048 -> 896x2048
IPAD_MINI_5TH_GEN_PROFILE = DeviceProfile(
    model=DeviceModel.IPAD_MINI_5TH_GEN,
    uncropped_dimensions=DeviceDimensions(width=1536, height=2048),
    cropped_dimensions=DeviceDimensions(width=896, height=2048),
    crop_x=640,
    crop_y=0,
    crop_width=896,
    crop_height=2048,
)

# iPad mini 6th Gen / iPad Air 3rd Gen - 1488x2266 -> 848x2266
IPAD_MINI_6TH_GEN_PROFILE = DeviceProfile(
    model=DeviceModel.IPAD_MINI_6TH_GEN,
    uncropped_dimensions=DeviceDimensions(width=1488, height=2266),
    cropped_dimensions=DeviceDimensions(width=848, height=2266),
    crop_x=640,
    crop_y=0,
    crop_width=848,
    crop_height=2266,
)

# iPad Pro 11" - 1668x2388 -> 1028x2388
IPAD_PRO_11_PROFILE = DeviceProfile(
    model=DeviceModel.IPAD_PRO_11,
    uncropped_dimensions=DeviceDimensions(width=1668, height=2388),
    cropped_dimensions=DeviceDimensions(width=1028, height=2388),
    crop_x=640,
    crop_y=0,
    crop_width=1028,
    crop_height=2388,
)

# iPad Pro 11" (alternate resolution) - 1668x2224 -> 1028x2224
IPAD_PRO_11_ALT_PROFILE = DeviceProfile(
    model=DeviceModel.IPAD_PRO_11_ALT,
    uncropped_dimensions=DeviceDimensions(width=1668, height=2224),
    cropped_dimensions=DeviceDimensions(width=1028, height=2224),
    crop_x=640,
    crop_y=0,
    crop_width=1028,
    crop_height=2224,
)

# iPad Pro 12.9" - 2048x2732 -> 1258x2732
# Note: iPad Pro 12.9" has a wider sidebar (~790px vs 640px on other models)
# due to higher resolution and larger sidebar UI elements
IPAD_PRO_12_9_PROFILE = DeviceProfile(
    model=DeviceModel.IPAD_PRO_12_9,
    uncropped_dimensions=DeviceDimensions(width=2048, height=2732),
    cropped_dimensions=DeviceDimensions(width=1258, height=2732),
    crop_x=790,
    crop_y=0,
    crop_width=1258,
    crop_height=2732,
)

# All supported device profiles
SUPPORTED_PROFILES: list[DeviceProfile] = [
    IPAD_9TH_GEN_PROFILE,
    IPAD_10TH_GEN_PROFILE,
    IPAD_MINI_5TH_GEN_PROFILE,
    IPAD_MINI_6TH_GEN_PROFILE,
    IPAD_PRO_11_PROFILE,
    IPAD_PRO_11_ALT_PROFILE,
    IPAD_PRO_12_9_PROFILE,
]


@dataclass(frozen=True)
class DimensionRules:
    """Rules for image dimension filtering and device detection.

    This configuration defines the expected dimensions for iPad screenshots
    and the rules for filtering out incompatible images (iPhone screenshots,
    already-cropped images, etc.).

    Attributes:
        dimension_tolerance: Allowed pixel variance for dimension matching (±pixels)
        min_width: Minimum width for any valid image
        min_height: Minimum height for any valid image
        ipad_target_aspect_ratio: Expected aspect ratio for iPad (height/width)
        aspect_ratio_tolerance: Allowed variance for aspect ratio matching
    """

    dimension_tolerance: int = 10
    min_width: int = 848  # Smallest cropped width (iPad mini 6th gen)
    min_height: int = 2000
    ipad_target_aspect_ratio: float = 1.45  # Average across all iPad models
    aspect_ratio_tolerance: float = 0.2  # Wider tolerance for different models


DEFAULT_DIMENSION_RULES = DimensionRules()


def detect_device_from_dimensions(width: int, height: int, tolerance: int = 10) -> DeviceProfile:
    """Detect device profile from image dimensions.

    Args:
        width: Image width in pixels
        height: Image height in pixels
        tolerance: Allowed pixel variance for dimension matching

    Returns:
        DeviceProfile matching the dimensions, or a profile with UNKNOWN model

    Note:
        Currently all supported iPad models use the same screenshot dimensions,
        so this returns the standard iPad Pro 12.9" profile for all valid matches.
        Future versions may differentiate based on additional metadata.
    """
    for profile in SUPPORTED_PROFILES:
        uncropped = profile.uncropped_dimensions
        if (
            abs(width - uncropped.width) <= tolerance
            and abs(height - uncropped.height) <= tolerance
        ):
            return profile

    # Return unknown profile with detected dimensions
    return DeviceProfile(
        model=DeviceModel.UNKNOWN,
        uncropped_dimensions=DeviceDimensions(width=width, height=height),
        cropped_dimensions=DeviceDimensions(width=width, height=height),
        crop_x=0,
        crop_y=0,
        crop_width=width,
        crop_height=height,
    )


def is_already_cropped(width: int, height: int, tolerance: int = 10) -> bool:
    """Check if image dimensions match already-cropped output.

    Args:
        width: Image width in pixels
        height: Image height in pixels
        tolerance: Allowed pixel variance for dimension matching

    Returns:
        True if dimensions match any cropped output format
    """
    for profile in SUPPORTED_PROFILES:
        cropped = profile.cropped_dimensions
        if (
            abs(width - cropped.width) <= tolerance
            and abs(height - cropped.height) <= tolerance
        ):
            return True
    return False


def is_landscape_orientation(width: int, height: int, tolerance: int = 10) -> bool:
    """Check if image is in landscape orientation.

    Args:
        width: Image width in pixels
        height: Image height in pixels
        tolerance: Allowed pixel variance for dimension matching

    Returns:
        True if image appears to be rotated to landscape (any known profile)
    """
    for profile in SUPPORTED_PROFILES:
        uncropped = profile.uncropped_dimensions
        # Check if dimensions are swapped (landscape)
        if (
            abs(width - uncropped.height) <= tolerance
            and abs(height - uncropped.width) <= tolerance
        ):
            return True
    return False


def is_valid_aspect_ratio(width: int, height: int) -> bool:
    """Check if image has valid iPad aspect ratio.

    Args:
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        True if aspect ratio is within tolerance for iPad screenshots
    """
    if width == 0:
        return False

    rules = DEFAULT_DIMENSION_RULES
    aspect_ratio = height / width
    return abs(aspect_ratio - rules.ipad_target_aspect_ratio) <= rules.aspect_ratio_tolerance


def detect_device_from_width(width: int, height: int, tolerance: int = 10) -> DeviceProfile | None:
    """Detect device profile from width only, for partially-cropped images.

    This handles images that have been manually cropped (e.g., bottom removed)
    but still have the correct width and need the left sidebar removed.

    The returned profile preserves the original expected dimensions so that
    the ImagePatcher can pad the image back to the standard height before
    cropping. This ensures output dimensions match standard cropped sizes.

    Args:
        width: Image width in pixels
        height: Image height in pixels
        tolerance: Allowed pixel variance for width matching

    Returns:
        DeviceProfile if width matches a known profile and height is shorter
        than expected (partially cropped), None otherwise.
    """
    for profile in SUPPORTED_PROFILES:
        uncropped = profile.uncropped_dimensions
        # Width must match within tolerance
        if abs(width - uncropped.width) <= tolerance:
            # Height must be shorter than expected (partially cropped)
            # but not too short (at least 50% of expected height)
            if height < uncropped.height and height > uncropped.height * 0.5:
                # Return the original profile - preserves expected dimensions
                # so ImagePatcher can pad back to standard height before cropping
                return profile
    return None
