"""PHI removal/redaction from images."""

from __future__ import annotations

import io
from enum import Enum
from typing import Literal

import cv2
import numpy as np
from PIL import Image

from phi_detector_remover.core.config import RedactionConfig
from phi_detector_remover.core.detector import PHIRegion


class RedactionMethod(str, Enum):
    """Available redaction methods."""

    REDBOX = "redbox"
    BLACKBOX = "blackbox"
    PIXELATE = "pixelate"


class PHIRemover:
    """PHI remover for images.

    This class handles image redaction using various methods (redbox, blackbox, pixelate)
    for detected PHI regions.
    """

    def __init__(
        self,
        method: RedactionMethod | str = RedactionMethod.REDBOX,
        config: RedactionConfig | None = None,
    ):
        """Initialize PHI remover.

        Args:
            method: Redaction method to use
            config: Redaction configuration (uses defaults if None)
        """
        if isinstance(method, str):
            method = RedactionMethod(method)

        self.method = method
        self.config = config or RedactionConfig(method=method.value)

    def remove(
        self,
        image_bytes: bytes,
        regions: list[PHIRegion],
    ) -> bytes:
        """Remove PHI from image.

        Args:
            image_bytes: Original image as bytes
            regions: List of PHI regions to redact

        Returns:
            Redacted image as bytes
        """
        # Convert bytes to numpy array
        image_array = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

        if image is None:
            raise ValueError("Failed to decode image from bytes")

        # Apply redaction
        redacted = self._redact_image(image, regions)

        # Convert back to bytes
        success, encoded_image = cv2.imencode(".png", redacted)
        if not success:
            raise ValueError("Failed to encode redacted image")

        return encoded_image.tobytes()

    def remove_from_file(
        self,
        image_path: str,
        regions: list[PHIRegion],
        output_path: str | None = None,
    ) -> bytes:
        """Remove PHI from image file.

        Args:
            image_path: Path to input image
            regions: List of PHI regions to redact
            output_path: Optional path to save redacted image

        Returns:
            Redacted image as bytes
        """
        image = cv2.imread(image_path)

        if image is None:
            raise ValueError(f"Failed to read image from {image_path}")

        # Apply redaction
        redacted = self._redact_image(image, regions)

        # Save if output path provided
        if output_path:
            cv2.imwrite(output_path, redacted)

        # Convert to bytes
        success, encoded_image = cv2.imencode(".png", redacted)
        if not success:
            raise ValueError("Failed to encode redacted image")

        return encoded_image.tobytes()

    def _redact_image(
        self,
        image: np.ndarray,
        regions: list[PHIRegion],
    ) -> np.ndarray:
        """Apply redaction to image.

        Args:
            image: Image as numpy array
            regions: List of PHI regions to redact

        Returns:
            Redacted image
        """
        redacted = image.copy()

        for region in regions:
            redacted = self._redact_region(redacted, region)

        return redacted

    def _redact_region(
        self,
        image: np.ndarray,
        region: PHIRegion,
    ) -> np.ndarray:
        """Redact a single region.

        Args:
            image: Image as numpy array
            region: PHI region to redact

        Returns:
            Image with region redacted
        """
        if region.bbox is None:
            return image

        # Handle both BoundingBox object and tuple
        bbox = region.bbox
        if hasattr(bbox, "x"):
            x, y, w, h = bbox.x, bbox.y, bbox.width, bbox.height
        else:
            x, y, w, h = bbox

        # Apply padding
        padding = self.config.padding
        x = max(0, x - padding)
        y = max(0, y - padding)
        w = min(image.shape[1] - x, w + 2 * padding)
        h = min(image.shape[0] - y, h + 2 * padding)

        # Extract ROI
        roi = image[y : y + h, x : x + w]

        # Apply redaction method
        if self.method == RedactionMethod.REDBOX:
            redacted_roi = self._redbox_region(roi)
        elif self.method == RedactionMethod.BLACKBOX:
            redacted_roi = self._blackbox_region(roi)
        elif self.method == RedactionMethod.PIXELATE:
            redacted_roi = self._pixelate_region(roi)
        else:
            raise ValueError(f"Unknown redaction method: {self.method}")

        # Replace ROI in image
        image[y : y + h, x : x + w] = redacted_roi

        return image

    def _redbox_region(self, roi: np.ndarray) -> np.ndarray:
        """Fill region with red color.

        Args:
            roi: Region of interest

        Returns:
            Red-boxed region
        """
        # Red in BGR format
        color = self.config.redbox_color
        redbox = np.full_like(roi, color, dtype=np.uint8)

        return redbox

    def _blackbox_region(self, roi: np.ndarray) -> np.ndarray:
        """Fill region with solid color.

        Args:
            roi: Region of interest

        Returns:
            Black-boxed region
        """
        # Create solid color box
        color = self.config.blackbox_color
        blackbox = np.full_like(roi, color, dtype=np.uint8)

        return blackbox

    def _pixelate_region(self, roi: np.ndarray) -> np.ndarray:
        """Pixelate a region.

        Args:
            roi: Region of interest

        Returns:
            Pixelated region
        """
        h, w = roi.shape[:2]
        block_size = self.config.pixelate_block_size

        # Resize down
        small_h = max(1, h // block_size)
        small_w = max(1, w // block_size)
        small = cv2.resize(roi, (small_w, small_h), interpolation=cv2.INTER_LINEAR)

        # Resize back up
        pixelated = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)

        return pixelated
