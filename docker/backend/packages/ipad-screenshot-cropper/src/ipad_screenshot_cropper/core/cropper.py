"""Main cropping logic for iPad screenshots.

This module contains the core cropping functionality, focusing solely on geometric
operations. NO PHI detection or removal - that's handled by phi-detector-remover package.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import cv2
import numpy as np

from .callbacks import CancellationCheck, LogCallback, ProgressCallback
from .config import CropperConfig
from .device_profiles import (
    DEFAULT_DIMENSION_RULES,
    DeviceProfile,
    detect_device_from_dimensions,
    detect_device_from_width,
    is_already_cropped,
    is_landscape_orientation,
    is_valid_aspect_ratio,
)
from .exceptions import CancellationError, DeviceDetectionError, ImageProcessingError
from .patch import ImagePatcher


@dataclass
class CropResult:
    """Result of cropping operation.

    Attributes:
        cropped_image: The cropped image as numpy array
        device: Detected device profile
        was_patched: Whether the image was patched to meet minimum height
        original_dimensions: Original image dimensions (width, height)
        cropped_dimensions: Final cropped dimensions (width, height)
    """

    cropped_image: np.ndarray
    device: DeviceProfile
    was_patched: bool
    original_dimensions: tuple[int, int]
    cropped_dimensions: tuple[int, int]


@dataclass
class ProcessingCheck:
    """Result of checking if image should be processed.

    Attributes:
        should_process: Whether the image should be processed
        reason: Human-readable reason for the decision
        device: Detected device profile (if applicable)
    """

    should_process: bool
    reason: str
    device: DeviceProfile | None = None


class ScreenshotCropper:
    """Main screenshot cropper class - framework agnostic.

    This class handles device detection and geometric cropping of iPad screenshots.
    It uses callbacks for progress reporting and logging, making it usable from any interface.
    """

    def __init__(
        self,
        config: CropperConfig | None = None,
        progress_callback: ProgressCallback | None = None,
        cancellation_check: CancellationCheck | None = None,
        log_callback: LogCallback | None = None,
    ):
        """Initialize the screenshot cropper.

        Args:
            config: Configuration for cropping (uses defaults if not provided)
            progress_callback: Optional callback for progress updates
            cancellation_check: Optional callback to check for cancellation
            log_callback: Optional callback for log messages
        """
        self.config = config or CropperConfig()
        self.progress_callback = progress_callback
        self.cancellation_check = cancellation_check
        self.log_callback = log_callback
        self.patcher = ImagePatcher(self.config.assets)

    def _check_cancelled(self) -> None:
        """Check if operation should be cancelled."""
        if self.cancellation_check and self.cancellation_check():
            raise CancellationError("Operation cancelled by user")

    def _log(self, level: str, message: str) -> None:
        """Log a message if callback is set."""
        if self.log_callback:
            self.log_callback(level, message)  # type: ignore

    def should_process_image(
        self, image_source: str | Path | bytes | np.ndarray
    ) -> ProcessingCheck:
        """Determine if an image should be processed based on dimensions.

        This method quickly checks image dimensions to filter out:
        - Already-cropped images (990x2160 - OUTPUT of this tool)
        - Landscape orientation iPad screenshots (2160x1620)
        - iPhone screenshots (wrong dimensions/aspect ratio)
        - Invalid or corrupted images
        - Images that are too small or incompatible

        Only uncropped iPad screenshots (1620x2160) should be processed.

        Args:
            image_source: Path to image file, image bytes, or numpy array

        Returns:
            ProcessingCheck with should_process flag and reason
        """
        try:
            # Load image based on source type
            if isinstance(image_source, np.ndarray):
                img = image_source
            elif isinstance(image_source, bytes):
                nparr = np.frombuffer(image_source, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            else:
                img = cv2.imread(str(image_source))

            if img is None:
                return ProcessingCheck(should_process=False, reason="Invalid/corrupted image")

            height, width = img.shape[:2]
            rules = DEFAULT_DIMENSION_RULES

            # Check if already cropped
            if is_already_cropped(width, height, rules.dimension_tolerance):
                return ProcessingCheck(
                    should_process=False, reason=f"Already cropped ({width}x{height})"
                )

            # Detect device by exact dimensions
            device = detect_device_from_dimensions(width, height, rules.dimension_tolerance)

            # Check if valid iPad screenshot (exact match)
            if device.model.value != "Unknown":
                return ProcessingCheck(
                    should_process=True,
                    reason=f"Valid iPad screenshot ({width}x{height})",
                    device=device,
                )

            # Check for partially-cropped images (width matches, height shorter)
            partial_device = detect_device_from_width(width, height, rules.dimension_tolerance)
            if partial_device is not None:
                return ProcessingCheck(
                    should_process=True,
                    reason=f"Partially-cropped iPad screenshot ({width}x{height})",
                    device=partial_device,
                )

            # Check if landscape orientation
            if is_landscape_orientation(width, height, rules.dimension_tolerance):
                return ProcessingCheck(
                    should_process=False, reason=f"Landscape orientation ({width}x{height})"
                )

            # Check minimum dimensions
            if width < rules.min_width or height < rules.min_height:
                return ProcessingCheck(should_process=False, reason=f"Too small ({width}x{height})")

            # Check aspect ratio
            if not is_valid_aspect_ratio(width, height):
                aspect_ratio = height / width if width > 0 else 0
                return ProcessingCheck(
                    should_process=False,
                    reason=f"Wrong aspect ratio ({width}x{height}, ratio={aspect_ratio:.2f})",
                )

            return ProcessingCheck(
                should_process=False, reason=f"Incompatible dimensions ({width}x{height})"
            )

        except Exception as e:
            return ProcessingCheck(should_process=False, reason=f"Error reading image: {e}")
        finally:
            if not isinstance(image_source, np.ndarray):
                del img

    def detect_device(self, image_source: str | Path | bytes | np.ndarray) -> DeviceProfile:
        """Detect device type from image dimensions.

        Args:
            image_source: Path to image file, image bytes, or numpy array

        Returns:
            DeviceProfile for the detected device

        Raises:
            DeviceDetectionError: If device cannot be detected
        """
        try:
            # Load image based on source type
            if isinstance(image_source, np.ndarray):
                img = image_source
            elif isinstance(image_source, bytes):
                nparr = np.frombuffer(image_source, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            else:
                img = cv2.imread(str(image_source))

            if img is None:
                raise DeviceDetectionError("Invalid/corrupted image")

            height, width = img.shape[:2]
            device = detect_device_from_dimensions(
                width, height, DEFAULT_DIMENSION_RULES.dimension_tolerance
            )

            return device

        except DeviceDetectionError:
            raise
        except Exception as e:
            raise DeviceDetectionError(f"Error detecting device: {e}") from e
        finally:
            if not isinstance(image_source, np.ndarray):
                del img

    def crop_screenshot(
        self,
        image_source: str | Path | bytes | np.ndarray,
        device: DeviceProfile | None = None,
    ) -> CropResult:
        """Crop an iPad screenshot to the specified dimensions.

        This performs geometric cropping only. For PHI removal, use the
        phi-detector-remover package separately.

        Args:
            image_source: Path to image file, image bytes, or numpy array
            device: Device profile (auto-detected if not provided)

        Returns:
            CropResult with cropped image and metadata

        Raises:
            ImageProcessingError: If image cannot be processed
            CancellationError: If operation is cancelled
        """
        try:
            self._check_cancelled()

            # Load image based on source type
            if isinstance(image_source, np.ndarray):
                current_image = image_source.copy()
            elif isinstance(image_source, bytes):
                nparr = np.frombuffer(image_source, np.uint8)
                current_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            else:
                current_image = cv2.imread(str(image_source))

            if current_image is None:
                raise ImageProcessingError("Failed to load image")

            original_height, original_width = current_image.shape[:2]
            original_dimensions = (original_width, original_height)

            # Auto-detect device if not provided
            if device is None:
                device = detect_device_from_dimensions(
                    original_width, original_height, DEFAULT_DIMENSION_RULES.dimension_tolerance
                )

            self._log("info", f"Detected device: {device.model.value}")

            # Patch image if needed (only for images shorter than expected)
            was_patched = False
            expected_height = device.uncropped_dimensions.height
            if original_height < expected_height:
                self._log("info", f"Patching image from {original_height} to {expected_height}")
                current_image = self.patcher.patch_image(
                    current_image, expected_height, location="bottom"
                )
                was_patched = True

            # Perform crop using device profile dimensions
            crop_x = device.crop_x
            crop_y = device.crop_y
            crop_width = device.crop_width
            crop_height = device.crop_height
            cropped_image = current_image[crop_y : crop_y + crop_height, crop_x : crop_x + crop_width]

            cropped_height, cropped_width = cropped_image.shape[:2]
            cropped_dimensions = (cropped_width, cropped_height)

            self._log("info", f"Cropped to {cropped_width}x{cropped_height}")

            return CropResult(
                cropped_image=cropped_image,
                device=device,
                was_patched=was_patched,
                original_dimensions=original_dimensions,
                cropped_dimensions=cropped_dimensions,
            )

        except CancellationError:
            raise
        except Exception as e:
            raise ImageProcessingError(f"Error cropping screenshot: {e}") from e

    def save_cropped_image(
        self,
        crop_result: CropResult,
        output_path: str | Path,
    ) -> Path:
        """Save a cropped image to disk.

        Args:
            crop_result: Result from crop_screenshot
            output_path: Path to save the image

        Returns:
            Path where image was saved

        Raises:
            ImageProcessingError: If image cannot be saved
        """
        try:
            output_file = Path(output_path)
            cv2.imwrite(str(output_file), crop_result.cropped_image)
            self._log("info", f"Saved to {output_file}")
            return output_file

        except Exception as e:
            raise ImageProcessingError(f"Error saving image: {e}") from e

    def crop_and_save(
        self,
        input_path: str | Path,
        output_path: str | Path,
        device: DeviceProfile | None = None,
    ) -> CropResult:
        """Crop a screenshot and save it in one operation.

        Args:
            input_path: Path to input image
            output_path: Path to save cropped image
            device: Device profile (auto-detected if not provided)

        Returns:
            CropResult with cropped image and metadata

        Raises:
            ImageProcessingError: If processing fails
            CancellationError: If operation is cancelled
        """
        crop_result = self.crop_screenshot(input_path, device)
        self.save_cropped_image(crop_result, output_path)
        return crop_result
