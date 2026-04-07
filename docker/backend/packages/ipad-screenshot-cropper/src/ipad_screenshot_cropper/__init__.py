"""iPad Screenshot Cropper - Geometric cropping and device detection for iPad screenshots.

This package provides focused functionality for:
- Device detection based on image dimensions
- Geometric cropping of iPad screenshots
- Image patching for screenshots below minimum height

For PHI (Protected Health Information) detection and removal, use the separate
phi-detector-remover package.

Basic usage:
    >>> from ipad_screenshot_cropper import crop_screenshot, detect_device
    >>>
    >>> # Detect device from image
    >>> device = detect_device("screenshot.png")
    >>> print(f"Device: {device.model.value}")
    >>>
    >>> # Crop screenshot
    >>> result = crop_screenshot("screenshot.png")
    >>>
    >>> # Save cropped image
    >>> import cv2
    >>> cv2.imwrite("cropped.png", result.cropped_image)

Advanced usage with configuration:
    >>> from ipad_screenshot_cropper import ScreenshotCropper, CropperConfig
    >>>
    >>> config = CropperConfig()
    >>> cropper = ScreenshotCropper(config=config)
    >>>
    >>> # Check if image should be processed
    >>> check = cropper.should_process_image("screenshot.png")
    >>> if check.should_process:
    ...     result = cropper.crop_screenshot("screenshot.png")
"""

from .core import (
    CropperConfig,
    CropResult,
    DeviceModel,
    DeviceProfile,
    ProcessingCheck,
    ScreenshotCropper,
    detect_device_from_dimensions,
    is_already_cropped,
)

__version__ = "1.0.0"

__all__ = [
    # Main functions
    "crop_screenshot",
    "detect_device",
    "should_process_image",
    # Classes
    "ScreenshotCropper",
    "CropResult",
    "ProcessingCheck",
    "DeviceProfile",
    "DeviceModel",
    "CropperConfig",
    # Utility functions
    "detect_device_from_dimensions",
    "is_already_cropped",
]


def crop_screenshot(
    image_source: str | bytes,
    device: DeviceProfile | None = None,
) -> CropResult:
    """Crop an iPad screenshot (convenience function).

    Args:
        image_source: Path to image file or image bytes
        device: Device profile (auto-detected if not provided)

    Returns:
        CropResult with cropped image and metadata

    Example:
        >>> result = crop_screenshot("screenshot.png")
        >>> print(f"Cropped to {result.cropped_dimensions}")
    """
    cropper = ScreenshotCropper()
    return cropper.crop_screenshot(image_source, device)


def detect_device(image_source: str | bytes) -> DeviceProfile:
    """Detect device type from image (convenience function).

    Args:
        image_source: Path to image file or image bytes

    Returns:
        DeviceProfile for the detected device

    Example:
        >>> device = detect_device("screenshot.png")
        >>> print(f"Device: {device.model.value}")
    """
    cropper = ScreenshotCropper()
    return cropper.detect_device(image_source)


def should_process_image(image_source: str | bytes) -> ProcessingCheck:
    """Check if an image should be processed (convenience function).

    Args:
        image_source: Path to image file or image bytes

    Returns:
        ProcessingCheck with should_process flag and reason

    Example:
        >>> check = should_process_image("screenshot.png")
        >>> if check.should_process:
        ...     print(f"Should process: {check.reason}")
        ... else:
        ...     print(f"Skip: {check.reason}")
    """
    cropper = ScreenshotCropper()
    return cropper.should_process_image(image_source)
