"""HTTP client for iOS device detection service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class DetectionResult:
    """Detection result from the service."""

    detected: bool
    confidence: float
    device_model: str
    device_category: str
    device_family: str
    orientation: str
    scale_factor: int
    detected_dimensions: dict[str, int] | None = None
    expected_dimensions: dict[str, int] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_iphone(self) -> bool:
        return self.device_category == "iphone"

    @property
    def is_ipad(self) -> bool:
        return self.device_category == "ipad"


@dataclass
class DeviceProfile:
    """Device profile from the service."""

    profile_id: str
    model_name: str
    display_name: str
    category: str
    family: str
    screen_width_points: int
    screen_height_points: int
    scale_factor: int
    screenshot_width: int
    screenshot_height: int
    aspect_ratio: float


class DeviceDetectorClient:
    """Sync HTTP client for iOS device detection service."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> "DeviceDetectorClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def health_check(self) -> dict[str, Any]:
        """Check service health."""
        response = self.client.get("/api/v1/health")
        response.raise_for_status()
        return response.json()

    def detect(self, width: int, height: int) -> DetectionResult:
        """
        Detect iOS device from dimensions.

        Args:
            width: Image width in pixels
            height: Image height in pixels

        Returns:
            DetectionResult with device information
        """
        response = self.client.post(
            "/api/v1/detect",
            json={"width": width, "height": height},
        )
        response.raise_for_status()
        data = response.json()

        return DetectionResult(
            detected=data["detected"],
            confidence=data["confidence"],
            device_model=data["device_model"],
            device_category=data["device_category"],
            device_family=data["device_family"],
            orientation=data["orientation"],
            scale_factor=data["scale_factor"],
            detected_dimensions=data.get("detected_dimensions"),
            expected_dimensions=data.get("expected_dimensions"),
            metadata=data.get("metadata", {}),
        )

    def detect_batch(
        self, dimensions: list[tuple[int, int]]
    ) -> list[DetectionResult]:
        """
        Detect iOS devices for multiple dimension pairs.

        Args:
            dimensions: List of (width, height) tuples

        Returns:
            List of DetectionResult objects
        """
        payload = {
            "dimensions": [
                {"width": w, "height": h} for w, h in dimensions
            ]
        }
        response = self.client.post("/api/v1/detect/batch", json=payload)
        response.raise_for_status()
        data = response.json()

        return [
            DetectionResult(
                detected=r["detected"],
                confidence=r["confidence"],
                device_model=r["device_model"],
                device_category=r["device_category"],
                device_family=r["device_family"],
                orientation=r["orientation"],
                scale_factor=r["scale_factor"],
                detected_dimensions=r.get("detected_dimensions"),
                expected_dimensions=r.get("expected_dimensions"),
                metadata=r.get("metadata", {}),
            )
            for r in data["results"]
        ]

    def check_category(self, width: int, height: int) -> dict[str, Any]:
        """
        Quick category check for dimensions.

        Args:
            width: Image width in pixels
            height: Image height in pixels

        Returns:
            Dictionary with category information
        """
        response = self.client.post(
            "/api/v1/category",
            json={"width": width, "height": height},
        )
        response.raise_for_status()
        return response.json()

    def list_profiles(self) -> list[DeviceProfile]:
        """List all supported device profiles."""
        response = self.client.get("/api/v1/profiles")
        response.raise_for_status()
        data = response.json()

        return [
            DeviceProfile(
                profile_id=p["profile_id"],
                model_name=p["model_name"],
                display_name=p["display_name"],
                category=p["category"],
                family=p["family"],
                screen_width_points=p["screen_width_points"],
                screen_height_points=p["screen_height_points"],
                scale_factor=p["scale_factor"],
                screenshot_width=p["screenshot_width"],
                screenshot_height=p["screenshot_height"],
                aspect_ratio=p["aspect_ratio"],
            )
            for p in data["profiles"]
        ]

    def get_profile(self, profile_id: str) -> DeviceProfile:
        """Get a specific device profile."""
        response = self.client.get(f"/api/v1/profiles/{profile_id}")
        response.raise_for_status()
        p = response.json()

        return DeviceProfile(
            profile_id=p["profile_id"],
            model_name=p["model_name"],
            display_name=p["display_name"],
            category=p["category"],
            family=p["family"],
            screen_width_points=p["screen_width_points"],
            screen_height_points=p["screen_height_points"],
            scale_factor=p["scale_factor"],
            screenshot_width=p["screenshot_width"],
            screenshot_height=p["screenshot_height"],
            aspect_ratio=p["aspect_ratio"],
        )


class AsyncDeviceDetectorClient:
    """Async HTTP client for iOS device detection service."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "AsyncDeviceDetectorClient":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def health_check(self) -> dict[str, Any]:
        """Check service health."""
        response = await self.client.get("/api/v1/health")
        response.raise_for_status()
        return response.json()

    async def detect(self, width: int, height: int) -> DetectionResult:
        """Detect iOS device from dimensions."""
        response = await self.client.post(
            "/api/v1/detect",
            json={"width": width, "height": height},
        )
        response.raise_for_status()
        data = response.json()

        return DetectionResult(
            detected=data["detected"],
            confidence=data["confidence"],
            device_model=data["device_model"],
            device_category=data["device_category"],
            device_family=data["device_family"],
            orientation=data["orientation"],
            scale_factor=data["scale_factor"],
            detected_dimensions=data.get("detected_dimensions"),
            expected_dimensions=data.get("expected_dimensions"),
            metadata=data.get("metadata", {}),
        )

    async def detect_batch(
        self, dimensions: list[tuple[int, int]]
    ) -> list[DetectionResult]:
        """Detect iOS devices for multiple dimension pairs."""
        payload = {
            "dimensions": [
                {"width": w, "height": h} for w, h in dimensions
            ]
        }
        response = await self.client.post("/api/v1/detect/batch", json=payload)
        response.raise_for_status()
        data = response.json()

        return [
            DetectionResult(
                detected=r["detected"],
                confidence=r["confidence"],
                device_model=r["device_model"],
                device_category=r["device_category"],
                device_family=r["device_family"],
                orientation=r["orientation"],
                scale_factor=r["scale_factor"],
                detected_dimensions=r.get("detected_dimensions"),
                expected_dimensions=r.get("expected_dimensions"),
                metadata=r.get("metadata", {}),
            )
            for r in data["results"]
        ]
