"""HTTP client for PHI detection and removal service."""

from __future__ import annotations

from typing import BinaryIO

import httpx

from phi_detector_remover.core.detector import PHIRegion
from phi_detector_remover.core.remover import RedactionMethod
from phi_detector_remover.web.schemas import BoundingBox, PHIRegionSchema


class PHIClient:
    """HTTP client for PHI detection and removal service.

    This client allows using the PHI service via HTTP API instead of
    importing the library directly.

    Example:
        >>> client = PHIClient("http://localhost:8000")
        >>> regions = client.detect(image_bytes)
        >>> clean_image = client.remove(image_bytes, regions)
    """

    def __init__(self, base_url: str, timeout: float = 30.0):
        """Initialize PHI client.

        Args:
            base_url: Base URL of PHI service (e.g., 'http://localhost:8000')
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)

    def __enter__(self) -> PHIClient:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    def close(self) -> None:
        """Close HTTP client."""
        self.client.close()

    def detect(self, image_bytes: bytes) -> list[PHIRegion]:
        """Detect PHI in an image.

        Args:
            image_bytes: Image data as bytes

        Returns:
            List of detected PHI regions

        Raises:
            httpx.HTTPError: If request fails
        """
        files = {"file": ("image.png", image_bytes, "image/png")}

        response = self.client.post(
            f"{self.base_url}/api/v1/detect",
            files=files,
        )
        response.raise_for_status()

        data = response.json()

        if not data["success"]:
            raise RuntimeError(f"Detection failed: {data.get('error')}")

        # Convert schemas to PHIRegion objects
        regions = []
        for region_data in data["data"]["regions"]:
            bbox_data = region_data["bbox"]
            region = PHIRegion(
                entity_type=region_data["entity_type"],
                text=region_data["text"],
                score=region_data["score"],
                bbox=(
                    bbox_data["x"],
                    bbox_data["y"],
                    bbox_data["width"],
                    bbox_data["height"],
                ),
                source=region_data.get("source", "presidio"),
            )
            regions.append(region)

        return regions

    def remove(
        self,
        image_bytes: bytes,
        regions: list[PHIRegion],
        method: RedactionMethod | str = "redbox",
    ) -> bytes:
        """Remove PHI from an image.

        Args:
            image_bytes: Image data as bytes
            regions: List of PHI regions to redact
            method: Redaction method ('redbox', 'blackbox', or 'pixelate')

        Returns:
            Redacted image as bytes

        Raises:
            httpx.HTTPError: If request fails
        """
        # Convert regions to JSON
        import json

        regions_data = [
            {
                "entity_type": r.entity_type,
                "text": r.text,
                "score": r.score,
                "bbox": {
                    "x": r.bbox[0],
                    "y": r.bbox[1],
                    "width": r.bbox[2],
                    "height": r.bbox[3],
                },
                "source": r.source,
            }
            for r in regions
        ]

        files = {"file": ("image.png", image_bytes, "image/png")}
        data = {
            "regions": json.dumps(regions_data),
            "method": str(method),
        }

        response = self.client.post(
            f"{self.base_url}/api/v1/remove",
            files=files,
            data=data,
        )
        response.raise_for_status()

        return response.content

    def process(
        self,
        image_bytes: bytes,
        method: RedactionMethod | str = "redbox",
    ) -> tuple[bytes, int]:
        """Detect and remove PHI in one call.

        Args:
            image_bytes: Image data as bytes
            method: Redaction method ('redbox', 'blackbox', or 'pixelate')

        Returns:
            Tuple of (redacted_image_bytes, regions_detected_count)

        Raises:
            httpx.HTTPError: If request fails
        """
        files = {"file": ("image.png", image_bytes, "image/png")}
        data = {"method": str(method)}

        response = self.client.post(
            f"{self.base_url}/api/v1/process",
            files=files,
            data=data,
        )
        response.raise_for_status()

        # Get region count from header
        regions_detected = int(response.headers.get("X-Regions-Detected", "0"))

        return response.content, regions_detected

    def health_check(self) -> dict:
        """Check service health.

        Returns:
            Health status dictionary

        Raises:
            httpx.HTTPError: If request fails
        """
        response = self.client.get(f"{self.base_url}/api/v1/health")
        response.raise_for_status()

        return response.json()

    def get_config(self) -> dict:
        """Get service configuration.

        Returns:
            Configuration dictionary

        Raises:
            httpx.HTTPError: If request fails
        """
        response = self.client.get(f"{self.base_url}/api/v1/config")
        response.raise_for_status()

        data = response.json()

        if not data["success"]:
            raise RuntimeError(f"Failed to get config: {data.get('error')}")

        return data["data"]
