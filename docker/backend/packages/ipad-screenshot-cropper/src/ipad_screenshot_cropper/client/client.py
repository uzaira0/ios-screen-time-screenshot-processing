"""HTTP client for iPad screenshot cropper service."""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

import httpx
import numpy as np

from ..core import DeviceModel
from ..web.schemas import (
    CropResponse,
    DetectDeviceResponse,
    DeviceProfilesResponse,
    HealthResponse,
    ProcessingCheckResponse,
)


class CropperClient:
    """HTTP client for iPad screenshot cropper service.

    This client provides a convenient interface to interact with the cropper service API.

    Example:
        >>> client = CropperClient("http://localhost:8000")
        >>>
        >>> # Check health
        >>> health = client.health()
        >>> print(f"Service status: {health.status}")
        >>>
        >>> # Crop screenshot
        >>> response = client.crop_screenshot("screenshot.png")
        >>> print(f"Device: {response.device.model}")
        >>>
        >>> # Get cropped image
        >>> image_data = client.crop_screenshot_image("screenshot.png")
        >>> with open("cropped.png", "wb") as f:
        ...     f.write(image_data)
    """

    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 30.0):
        """Initialize the client.

        Args:
            base_url: Base URL of the cropper service
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def close(self):
        """Close the HTTP client."""
        self.client.close()

    def health(self) -> HealthResponse:
        """Check service health.

        Returns:
            HealthResponse with service status

        Raises:
            httpx.HTTPError: If request fails
        """
        response = self.client.get("/api/v1/health")
        response.raise_for_status()
        return HealthResponse(**response.json())

    def crop_screenshot(self, image_source: str | Path | bytes | BinaryIO) -> CropResponse:
        """Crop a screenshot and get JSON response.

        Args:
            image_source: Path to image file, image bytes, or file-like object

        Returns:
            CropResponse with cropping results

        Raises:
            httpx.HTTPError: If request fails
        """
        files = self._prepare_file(image_source, "file")

        try:
            response = self.client.post("/api/v1/crop", files=files)
            response.raise_for_status()
            return CropResponse(**response.json())
        finally:
            # Close file if we opened it
            if isinstance(image_source, (str, Path)):
                files["file"][1].close()

    def crop_screenshot_image(self, image_source: str | Path | bytes | BinaryIO) -> bytes:
        """Crop a screenshot and get image bytes.

        Args:
            image_source: Path to image file, image bytes, or file-like object

        Returns:
            Cropped image as PNG bytes

        Raises:
            httpx.HTTPError: If request fails
        """
        files = self._prepare_file(image_source, "file")

        try:
            response = self.client.post("/api/v1/crop", files=files, params={"return_image": True})
            response.raise_for_status()
            return response.content
        finally:
            # Close file if we opened it
            if isinstance(image_source, (str, Path)):
                files["file"][1].close()

    def detect_device(self, image_source: str | Path | bytes | BinaryIO) -> DetectDeviceResponse:
        """Detect device type from screenshot.

        Args:
            image_source: Path to image file, image bytes, or file-like object

        Returns:
            DetectDeviceResponse with device information

        Raises:
            httpx.HTTPError: If request fails
        """
        files = self._prepare_file(image_source, "file")

        try:
            response = self.client.post("/api/v1/detect-device", files=files)
            response.raise_for_status()
            return DetectDeviceResponse(**response.json())
        finally:
            # Close file if we opened it
            if isinstance(image_source, (str, Path)):
                files["file"][1].close()

    def should_process(
        self, image_source: str | Path | bytes | BinaryIO
    ) -> ProcessingCheckResponse:
        """Check if an image should be processed.

        Args:
            image_source: Path to image file, image bytes, or file-like object

        Returns:
            ProcessingCheckResponse with decision and reason

        Raises:
            httpx.HTTPError: If request fails
        """
        files = self._prepare_file(image_source, "file")

        try:
            response = self.client.post("/api/v1/should-process", files=files)
            response.raise_for_status()
            return ProcessingCheckResponse(**response.json())
        finally:
            # Close file if we opened it
            if isinstance(image_source, (str, Path)):
                files["file"][1].close()

    def get_device_profiles(self) -> DeviceProfilesResponse:
        """Get list of supported device profiles.

        Returns:
            DeviceProfilesResponse with all supported profiles

        Raises:
            httpx.HTTPError: If request fails
        """
        response = self.client.get("/api/v1/device-profiles")
        response.raise_for_status()
        return DeviceProfilesResponse(**response.json())

    @staticmethod
    def _prepare_file(image_source: str | Path | bytes | BinaryIO, field_name: str) -> dict:
        """Prepare file for upload.

        Args:
            image_source: Image source (path, bytes, or file-like)
            field_name: Form field name

        Returns:
            Dictionary suitable for httpx files parameter
        """
        if isinstance(image_source, bytes):
            return {field_name: ("image.png", image_source, "image/png")}
        elif isinstance(image_source, (str, Path)):
            return {field_name: open(image_source, "rb")}
        else:
            # Assume file-like object
            return {field_name: image_source}


class AsyncCropperClient:
    """Async HTTP client for iPad screenshot cropper service.

    This client provides an async interface to interact with the cropper service API.

    Example:
        >>> async with AsyncCropperClient("http://localhost:8000") as client:
        ...     health = await client.health()
        ...     print(f"Service status: {health.status}")
        ...
        ...     response = await client.crop_screenshot("screenshot.png")
        ...     print(f"Device: {response.device.model}")
    """

    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 30.0):
        """Initialize the async client.

        Args:
            base_url: Base URL of the cropper service
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def health(self) -> HealthResponse:
        """Check service health.

        Returns:
            HealthResponse with service status

        Raises:
            httpx.HTTPError: If request fails
        """
        response = await self.client.get("/api/v1/health")
        response.raise_for_status()
        return HealthResponse(**response.json())

    async def crop_screenshot(self, image_source: str | Path | bytes | BinaryIO) -> CropResponse:
        """Crop a screenshot and get JSON response.

        Args:
            image_source: Path to image file, image bytes, or file-like object

        Returns:
            CropResponse with cropping results

        Raises:
            httpx.HTTPError: If request fails
        """
        files = CropperClient._prepare_file(image_source, "file")

        try:
            response = await self.client.post("/api/v1/crop", files=files)
            response.raise_for_status()
            return CropResponse(**response.json())
        finally:
            # Close file if we opened it
            if isinstance(image_source, (str, Path)):
                files["file"][1].close()

    async def crop_screenshot_image(self, image_source: str | Path | bytes | BinaryIO) -> bytes:
        """Crop a screenshot and get image bytes.

        Args:
            image_source: Path to image file, image bytes, or file-like object

        Returns:
            Cropped image as PNG bytes

        Raises:
            httpx.HTTPError: If request fails
        """
        files = CropperClient._prepare_file(image_source, "file")

        try:
            response = await self.client.post(
                "/api/v1/crop", files=files, params={"return_image": True}
            )
            response.raise_for_status()
            return response.content
        finally:
            # Close file if we opened it
            if isinstance(image_source, (str, Path)):
                files["file"][1].close()

    async def detect_device(
        self, image_source: str | Path | bytes | BinaryIO
    ) -> DetectDeviceResponse:
        """Detect device type from screenshot.

        Args:
            image_source: Path to image file, image bytes, or file-like object

        Returns:
            DetectDeviceResponse with device information

        Raises:
            httpx.HTTPError: If request fails
        """
        files = CropperClient._prepare_file(image_source, "file")

        try:
            response = await self.client.post("/api/v1/detect-device", files=files)
            response.raise_for_status()
            return DetectDeviceResponse(**response.json())
        finally:
            # Close file if we opened it
            if isinstance(image_source, (str, Path)):
                files["file"][1].close()

    async def should_process(
        self, image_source: str | Path | bytes | BinaryIO
    ) -> ProcessingCheckResponse:
        """Check if an image should be processed.

        Args:
            image_source: Path to image file, image bytes, or file-like object

        Returns:
            ProcessingCheckResponse with decision and reason

        Raises:
            httpx.HTTPError: If request fails
        """
        files = CropperClient._prepare_file(image_source, "file")

        try:
            response = await self.client.post("/api/v1/should-process", files=files)
            response.raise_for_status()
            return ProcessingCheckResponse(**response.json())
        finally:
            # Close file if we opened it
            if isinstance(image_source, (str, Path)):
                files["file"][1].close()

    async def get_device_profiles(self) -> DeviceProfilesResponse:
        """Get list of supported device profiles.

        Returns:
            DeviceProfilesResponse with all supported profiles

        Raises:
            httpx.HTTPError: If request fails
        """
        response = await self.client.get("/api/v1/device-profiles")
        response.raise_for_status()
        return DeviceProfilesResponse(**response.json())
