"""Device detection and iPad cropping for preprocessing pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DeviceDetectionResult:
    """Result of iOS device detection."""

    detected: bool
    device_category: str  # iphone, ipad, unknown
    device_model: str | None
    confidence: float
    is_ipad: bool
    is_iphone: bool
    orientation: str  # portrait, landscape, unknown
    width: int = 0
    height: int = 0


def detect_device(image_path: Path | str) -> DeviceDetectionResult:
    """Detect iOS device type from screenshot dimensions.

    Uses ios-device-detector if installed, falls back to unknown.
    """
    image_path = Path(image_path)

    try:
        from ios_device_detector import DeviceDetector  # pyright: ignore[reportMissingImports]

        detector = DeviceDetector()
        result = detector.detect_from_file(str(image_path))

        width = 0
        height = 0
        if result.detected_dimensions:
            width = result.detected_dimensions.width
            height = result.detected_dimensions.height

        return DeviceDetectionResult(
            detected=result.detected,
            device_category=result.device_category.value
            if hasattr(result.device_category, "value")
            else str(result.device_category),
            device_model=result.device_model,
            confidence=result.confidence,
            is_ipad=result.is_ipad,
            is_iphone=result.is_iphone,
            orientation=result.orientation.value if hasattr(result.orientation, "value") else str(result.orientation),
            width=width,
            height=height,
        )
    except ImportError:
        logger.debug("ios-device-detector not installed, skipping device detection")
        return DeviceDetectionResult(
            detected=False,
            device_category="unknown",
            device_model=None,
            confidence=0.0,
            is_ipad=False,
            is_iphone=False,
            orientation="unknown",
        )
    except Exception as e:
        logger.warning("Device detection failed", extra={"error": str(e)})
        return DeviceDetectionResult(
            detected=False,
            device_category="unknown",
            device_model=f"error: {e}",
            confidence=0.0,
            is_ipad=False,
            is_iphone=False,
            orientation="unknown",
        )


def crop_screenshot_if_ipad(
    image_bytes: bytes,
    device: DeviceDetectionResult,
) -> tuple[bytes, bool, bool, bool]:
    """Crop iPad sidebar if needed. Returns (bytes, was_cropped, was_patched, had_error)."""
    try:
        import cv2
        import numpy as np
        from ipad_screenshot_cropper import crop_screenshot, should_process_image  # pyright: ignore[reportMissingImports]

        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return image_bytes, False, False, False

        check = should_process_image(img)
        if not check.should_process:
            return image_bytes, False, False, False

        result = crop_screenshot(image_bytes, device=check.device)
        _, buffer = cv2.imencode(".png", result.cropped_image)
        cropped_bytes = buffer.tobytes()
        return cropped_bytes, True, result.was_patched, False

    except ImportError:
        logger.debug("ipad-screenshot-cropper not installed, skipping cropping")
        return image_bytes, False, False, False
    except Exception as e:
        logger.warning("iPad cropping failed", extra={"error": str(e)})
        return image_bytes, False, False, True
