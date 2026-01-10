"""Pytest fixtures for phi-detector-remover tests."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont


@pytest.fixture
def sample_image_bytes() -> bytes:
    """Create a sample image with text for testing."""
    # Create a simple image with some text
    img = Image.new("RGB", (400, 200), color="white")
    draw = ImageDraw.Draw(img)

    # Add some sample text (PHI-like content)
    draw.text((10, 10), "John Doe", fill="black")
    draw.text((10, 40), "john.doe@email.com", fill="black")
    draw.text((10, 70), "555-123-4567", fill="black")
    draw.text((10, 100), "Screen Time", fill="black")  # Should be ignored
    draw.text((10, 130), "Safari", fill="black")  # Should be ignored

    # Convert to bytes
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def sample_image_array(sample_image_bytes: bytes) -> np.ndarray:
    """Convert sample image to numpy array."""
    import cv2

    nparr = np.frombuffer(sample_image_bytes, np.uint8)
    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)


@pytest.fixture
def sample_ocr_result():
    """Create a sample OCR result for testing detectors."""
    from phi_detector_remover.core.models import BoundingBox, OCRResult, OCRWord

    words = [
        OCRWord(
            text="John",
            confidence=0.95,
            bbox=BoundingBox(x=10, y=10, width=40, height=20),
        ),
        OCRWord(
            text="Doe",
            confidence=0.93,
            bbox=BoundingBox(x=55, y=10, width=30, height=20),
        ),
        OCRWord(
            text="john.doe@email.com",
            confidence=0.90,
            bbox=BoundingBox(x=10, y=40, width=150, height=20),
        ),
        OCRWord(
            text="555-123-4567",
            confidence=0.88,
            bbox=BoundingBox(x=10, y=70, width=100, height=20),
        ),
        OCRWord(
            text="Screen",
            confidence=0.95,
            bbox=BoundingBox(x=10, y=100, width=50, height=20),
        ),
        OCRWord(
            text="Time",
            confidence=0.95,
            bbox=BoundingBox(x=65, y=100, width=35, height=20),
        ),
        OCRWord(
            text="Safari",
            confidence=0.96,
            bbox=BoundingBox(x=10, y=130, width=45, height=20),
        ),
    ]

    return OCRResult(
        text="John Doe john.doe@email.com 555-123-4567 Screen Time Safari",
        words=words,
        confidence=0.92,
        engine="tesseract",
    )


@pytest.fixture
def temp_benchmark_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with benchmark data."""
    import json

    # Create some sample images
    for i in range(3):
        img = Image.new("RGB", (200, 100), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), f"Person{i}", fill="black")

        img_path = tmp_path / f"image_{i}.png"
        img.save(img_path)

        # Create annotation file
        annotations = {
            "annotations": [
                {
                    "entity_type": "PERSON",
                    "text": f"Person{i}",
                    "bbox": {"x": 10, "y": 10, "width": 60, "height": 20},
                }
            ]
        }

        ann_path = tmp_path / f"image_{i}.json"
        with open(ann_path, "w") as f:
            json.dump(annotations, f)

    return tmp_path
