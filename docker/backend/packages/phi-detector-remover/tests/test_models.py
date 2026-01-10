"""Tests for core data models."""

from __future__ import annotations

import pytest

from phi_detector_remover.core.models import (
    AggregatedPHIRegion,
    BoundingBox,
    DetectionResult,
    DetectorType,
    OCRResult,
    OCRWord,
    PHIRegion,
    PipelineResult,
)


class TestBoundingBox:
    """Tests for BoundingBox model."""

    def test_create_bbox(self):
        """Test basic bbox creation."""
        bbox = BoundingBox(x=10, y=20, width=100, height=50)

        assert bbox.x == 10
        assert bbox.y == 20
        assert bbox.width == 100
        assert bbox.height == 50

    def test_area(self):
        """Test area calculation."""
        bbox = BoundingBox(x=0, y=0, width=100, height=50)
        assert bbox.area == 5000

    def test_center(self):
        """Test center calculation."""
        bbox = BoundingBox(x=0, y=0, width=100, height=50)
        assert bbox.center == (50, 25)

    def test_to_tuple(self):
        """Test tuple conversion."""
        bbox = BoundingBox(x=10, y=20, width=100, height=50)
        assert bbox.to_tuple() == (10, 20, 100, 50)

    def test_to_xyxy(self):
        """Test xyxy format conversion."""
        bbox = BoundingBox(x=10, y=20, width=100, height=50)
        assert bbox.to_xyxy() == (10, 20, 110, 70)

    def test_from_xyxy(self):
        """Test creation from xyxy format."""
        bbox = BoundingBox.from_xyxy(10, 20, 110, 70)
        assert bbox.x == 10
        assert bbox.y == 20
        assert bbox.width == 100
        assert bbox.height == 50

    def test_iou_no_overlap(self):
        """Test IoU with non-overlapping boxes."""
        box1 = BoundingBox(x=0, y=0, width=50, height=50)
        box2 = BoundingBox(x=100, y=100, width=50, height=50)

        assert box1.iou(box2) == 0.0

    def test_iou_full_overlap(self):
        """Test IoU with identical boxes."""
        box1 = BoundingBox(x=0, y=0, width=50, height=50)
        box2 = BoundingBox(x=0, y=0, width=50, height=50)

        assert box1.iou(box2) == 1.0

    def test_iou_partial_overlap(self):
        """Test IoU with partial overlap."""
        box1 = BoundingBox(x=0, y=0, width=100, height=100)
        box2 = BoundingBox(x=50, y=50, width=100, height=100)

        # Intersection: 50x50 = 2500
        # Union: 100*100 + 100*100 - 2500 = 17500
        # IoU: 2500 / 17500 ≈ 0.143
        assert 0.14 < box1.iou(box2) < 0.15

    def test_to_dict_from_dict(self):
        """Test serialization round-trip."""
        bbox = BoundingBox(x=10, y=20, width=100, height=50)
        data = bbox.to_dict()
        restored = BoundingBox.from_dict(data)

        assert restored.x == bbox.x
        assert restored.y == bbox.y
        assert restored.width == bbox.width
        assert restored.height == bbox.height


class TestPHIRegion:
    """Tests for PHIRegion model."""

    def test_create_region(self):
        """Test basic region creation."""
        bbox = BoundingBox(x=10, y=10, width=100, height=20)
        region = PHIRegion(
            entity_type="PERSON",
            text="John Doe",
            confidence=0.95,
            bbox=bbox,
            source="presidio",
        )

        assert region.entity_type == "PERSON"
        assert region.text == "John Doe"
        assert region.confidence == 0.95
        assert region.source == "presidio"

    def test_region_without_bbox(self):
        """Test region without bounding box."""
        region = PHIRegion(
            entity_type="EMAIL",
            text="test@example.com",
            confidence=0.9,
        )

        assert region.bbox is None
        assert region.bbox_tuple is None

    def test_to_dict_from_dict(self):
        """Test serialization round-trip."""
        bbox = BoundingBox(x=10, y=10, width=100, height=20)
        region = PHIRegion(
            entity_type="PERSON",
            text="John Doe",
            confidence=0.95,
            bbox=bbox,
            source="presidio",
        )

        data = region.to_dict()
        restored = PHIRegion.from_dict(data)

        assert restored.entity_type == region.entity_type
        assert restored.text == region.text
        assert restored.confidence == region.confidence
        assert restored.bbox.x == region.bbox.x


class TestDetectionResult:
    """Tests for DetectionResult model."""

    def test_create_result(self):
        """Test basic result creation."""
        regions = [
            PHIRegion(entity_type="PERSON", text="John", confidence=0.9),
            PHIRegion(entity_type="EMAIL", text="test@test.com", confidence=0.85),
        ]

        result = DetectionResult(
            detector_name="presidio",
            detector_type=DetectorType.TEXT,
            regions=regions,
            processing_time_ms=50.0,
        )

        assert result.detector_name == "presidio"
        assert result.region_count == 2
        assert result.processing_time_ms == 50.0

    def test_empty_result(self):
        """Test result with no detections."""
        result = DetectionResult(
            detector_name="regex",
            detector_type=DetectorType.TEXT,
            regions=[],
        )

        assert result.region_count == 0


class TestOCRResult:
    """Tests for OCRResult model."""

    def test_create_ocr_result(self, sample_ocr_result):
        """Test OCR result creation."""
        assert sample_ocr_result.engine == "tesseract"
        assert len(sample_ocr_result.words) == 7
        assert sample_ocr_result.confidence == 0.92

    def test_to_dict_from_dict(self, sample_ocr_result):
        """Test serialization round-trip."""
        data = sample_ocr_result.to_dict()
        restored = OCRResult.from_dict(data)

        assert restored.text == sample_ocr_result.text
        assert len(restored.words) == len(sample_ocr_result.words)
        assert restored.confidence == sample_ocr_result.confidence


class TestPipelineResult:
    """Tests for PipelineResult model."""

    def test_has_phi(self):
        """Test PHI detection flag."""
        # With regions
        result_with_phi = PipelineResult(
            aggregated_regions=[
                AggregatedPHIRegion(
                    entity_type="PERSON",
                    text="John",
                    confidence=0.9,
                    bbox=None,
                    sources=["presidio"],
                    source_confidences={"presidio": 0.9},
                )
            ],
            detector_results={},
            ocr_result=None,
            total_processing_time_ms=100.0,
        )

        assert result_with_phi.has_phi is True
        assert result_with_phi.region_count == 1

        # Without regions
        result_without_phi = PipelineResult(
            aggregated_regions=[],
            detector_results={},
            ocr_result=None,
            total_processing_time_ms=50.0,
        )

        assert result_without_phi.has_phi is False
        assert result_without_phi.region_count == 0
