"""Image patching logic for handling short screenshots.

This module handles screenshots that are shorter than the required height by adding
patch images to the top or bottom to ensure proper cropping.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import cv2
import numpy as np

try:
    from importlib.resources import files
except ImportError:
    from importlib_resources import files

from .config import AssetConfig
from .exceptions import AssetNotFoundError, ImageProcessingError


class ImagePatcher:
    """Handles patching of images to ensure minimum height."""

    def __init__(self, asset_config: AssetConfig | None = None):
        """Initialize the image patcher.

        Args:
            asset_config: Asset configuration (uses defaults if not provided)
        """
        self.asset_config = asset_config or AssetConfig()
        self._bottom_patch_image: np.ndarray | None = None
        self._top_patch_image: np.ndarray | None = None

    def _get_asset_path(self, asset_filename: str) -> Path:
        """Get the path to an asset file using importlib.resources.

        Args:
            asset_filename: Name of the asset file

        Returns:
            Path to the asset file

        Raises:
            AssetNotFoundError: If asset file cannot be found
        """
        try:
            assets_path = files("ipad_screenshot_cropper.assets")
            asset_file = assets_path / asset_filename
            if hasattr(asset_file, "is_file") and asset_file.is_file():
                return Path(str(asset_file))

            # Fallback to string path for older Python versions
            return Path(str(asset_file))
        except Exception as e:
            raise AssetNotFoundError(f"Could not locate asset '{asset_filename}': {e}") from e

    def _load_patch_image(self, location: Literal["top", "bottom"]) -> np.ndarray:
        """Load a patch image from assets.

        Args:
            location: Which patch image to load ('top' or 'bottom')

        Returns:
            Loaded patch image as numpy array

        Raises:
            AssetNotFoundError: If patch image cannot be loaded
        """
        if location == "bottom":
            if self._bottom_patch_image is None:
                path = self._get_asset_path(self.asset_config.bottom_patch_image)
                self._bottom_patch_image = cv2.imread(str(path))
                if self._bottom_patch_image is None:
                    raise AssetNotFoundError(f"Failed to load bottom patch image from {path}")
            return self._bottom_patch_image
        else:
            if self._top_patch_image is None:
                path = self._get_asset_path(self.asset_config.top_patch_image)
                self._top_patch_image = cv2.imread(str(path))
                if self._top_patch_image is None:
                    raise AssetNotFoundError(f"Failed to load top patch image from {path}")
            return self._top_patch_image

    def patch_image(
        self,
        image: np.ndarray,
        min_height: int = 2160,
        location: Literal["top", "bottom"] = "bottom",
    ) -> np.ndarray:
        """Patch an image to ensure minimum height.

        This handles screenshots that are shorter than the required height by adding
        a patch image to the top or bottom.

        Args:
            image: The image to patch
            min_height: Minimum required height
            location: Where to add the patch ('top' or 'bottom')

        Returns:
            Patched image (or original if no patching needed)

        Raises:
            ImageProcessingError: If image cannot be patched
        """
        try:
            curr_height, curr_width, _ = image.shape

            if curr_height >= min_height:
                return image

            if location == "bottom":
                return self._patch_image_bottom(image, curr_height, curr_width, min_height)
            else:
                return self._patch_image_top(image, curr_height, curr_width, min_height)

        except Exception as e:
            raise ImageProcessingError(f"Error patching image: {e}") from e

    def _patch_image_bottom(
        self, current_image: np.ndarray, curr_height: int, curr_width: int, min_height: int
    ) -> np.ndarray:
        """Patch image at the bottom."""
        patching_image = self._load_patch_image("bottom")
        adjusted_patch_height = min_height - curr_height

        # Resize patching image width if needed (for iPad Pro 12.9" which is wider)
        patch_height, patch_width = patching_image.shape[:2]
        if patch_width != curr_width:
            patching_image = cv2.resize(
                patching_image, (curr_width, patch_height), interpolation=cv2.INTER_LINEAR
            )

        adjusted_patching_image = patching_image[:adjusted_patch_height, :curr_width]

        new_image = np.zeros((min_height, curr_width, 3), dtype=np.uint8)
        new_image[:curr_height, :] = current_image
        new_image[curr_height:, :] = adjusted_patching_image

        return new_image

    def _patch_image_top(
        self, current_image: np.ndarray, curr_height: int, curr_width: int, min_height: int
    ) -> np.ndarray:
        """Patch image at the top."""
        patching_image = self._load_patch_image("top")

        # Resize patching image width if needed (for iPad Pro 12.9" which is wider)
        patch_height, patch_width = patching_image.shape[:2]
        if patch_width != curr_width:
            patching_image = cv2.resize(
                patching_image, (curr_width, patch_height), interpolation=cv2.INTER_LINEAR
            )

        cut_height = min_height - 2160
        adjusted_patch_height = min_height - curr_height + cut_height
        adjusted_patching_image = patching_image[:adjusted_patch_height, -curr_width:]

        new_image = np.zeros((2160, curr_width, 3), dtype=np.uint8)
        new_image[:adjusted_patch_height, :] = adjusted_patching_image
        current_image_cut = current_image[cut_height:, :]
        new_image[adjusted_patch_height:, :] = current_image_cut

        return new_image
