"""Tests for benchmarking infrastructure."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from phi_detector_remover.core.benchmark.dataset import (
    AnnotatedDataset,
    create_annotation,
    load_annotations,
)
from phi_detector_remover.core.benchmark.metrics import (
    calculate_metrics,
    calculate_per_entity_metrics,
)
from phi_detector_remover.core.models import (
    AggregatedPHIRegion,
    BoundingBox,
    GroundTruthAnnotation,
)


class TestAnnotatedDataset:
    """Tests for AnnotatedDataset."""

    def test_load_from_directory(self, temp_benchmark_dir):
        """Test loading dataset from directory."""
        dataset = AnnotatedDataset.from_directory(temp_benchmark_dir)

        assert len(dataset) == 3
        assert dataset.name == temp_benchmark_dir.name

    def test_total_annotations(self, temp_benchmark_dir):
        """Test counting total annotations."""
        dataset = AnnotatedDataset.from_directory(temp_benchmark_dir)

        assert dataset.total_annotations == 3  # One per image

    def test_entity_type_counts(self, temp_benchmark_dir):
        """Test counting annotations by type."""
        dataset = AnnotatedDataset.from_directory(temp_benchmark_dir)
        counts = dataset.entity_type_counts

        assert "PERSON" in counts
        assert counts["PERSON"] == 3

    def test_iteration(self, temp_benchmark_dir):
        """Test iterating over samples."""
        dataset = AnnotatedDataset.from_directory(temp_benchmark_dir)

        samples = list(dataset)
        assert len(samples) == 3

        for sample in samples:
            assert sample.image_path is not None
            assert len(sample.annotations) >= 0

    def test_save_and_load(self, temp_benchmark_dir, tmp_path):
        """Test saving and loading dataset."""
        dataset = AnnotatedDataset.from_directory(temp_benchmark_dir)

        # Save
        save_path = tmp_path / "dataset.json"
        dataset.to_json(save_path)

        assert save_path.exists()

        # Load
        loaded = AnnotatedDataset.from_annotations_file(
            save_path,
            images_directory=temp_benchmark_dir,
        )

        assert len(loaded) == len(dataset)

    def test_filter_by_entity_type(self, temp_benchmark_dir):
        """Test filtering by entity type."""
        dataset = AnnotatedDataset.from_directory(temp_benchmark_dir)
        filtered = dataset.filter_by_entity_type(["PERSON"])

        assert len(filtered) == 3

    def test_split(self, temp_benchmark_dir):
        """Test train/test split."""
        dataset = AnnotatedDataset.from_directory(temp_benchmark_dir)
        train, test = dataset.split(train_ratio=0.67, seed=42)

        assert len(train) + len(test) == len(dataset)
        assert len(train) >= 1
        assert len(test) >= 1


class TestAnnotations:
    """Tests for annotation utilities."""

    def test_create_annotation(self):
        """Test creating an annotation."""
        ann = create_annotation(
            entity_type="PERSON",
            text="John Doe",
            bbox=(10, 20, 100, 30),
        )

        assert ann.entity_type == "PERSON"
        assert ann.text == "John Doe"
        assert ann.bbox is not None
        assert ann.bbox.x == 10

    def test_create_annotation_no_bbox(self):
        """Test creating annotation without bbox."""
        ann = create_annotation(
            entity_type="EMAIL",
            text="test@example.com",
        )

        assert ann.bbox is None

    def test_load_annotations(self, tmp_path):
        """Test loading annotations from file."""
        # Create annotation file
        data = {
            "annotations": [
                {"entity_type": "PERSON", "text": "John"},
                {"entity_type": "EMAIL", "text": "john@test.com"},
            ]
        }

        ann_path = tmp_path / "test.json"
        with open(ann_path, "w") as f:
            json.dump(data, f)

        annotations = load_annotations(ann_path)

        assert len(annotations) == 2
        assert annotations[0].entity_type == "PERSON"
        assert annotations[1].entity_type == "EMAIL"


class TestMetrics:
    """Tests for metrics calculation."""

    def test_perfect_precision_recall(self):
        """Test metrics with perfect detection."""
        predictions = [
            AggregatedPHIRegion(
                entity_type="PERSON",
                text="John",
                confidence=0.9,
                bbox=BoundingBox(x=10, y=10, width=50, height=20),
                sources=["presidio"],
                source_confidences={"presidio": 0.9},
            )
        ]

        ground_truth = [
            GroundTruthAnnotation(
                entity_type="PERSON",
                text="John",
                bbox=BoundingBox(x=10, y=10, width=50, height=20),
            )
        ]

        metrics = calculate_metrics(predictions, ground_truth)

        assert metrics.precision == 1.0
        assert metrics.recall == 1.0
        assert metrics.f1_score == 1.0
        assert metrics.true_positives == 1
        assert metrics.false_positives == 0
        assert metrics.false_negatives == 0

    def test_no_predictions(self):
        """Test metrics with no predictions."""
        predictions = []
        ground_truth = [GroundTruthAnnotation(entity_type="PERSON", text="John")]

        metrics = calculate_metrics(predictions, ground_truth)

        assert metrics.precision == 1.0  # Vacuously true
        assert metrics.recall == 0.0
        assert metrics.false_negatives == 1

    def test_no_ground_truth(self):
        """Test metrics with no ground truth."""
        predictions = [
            AggregatedPHIRegion(
                entity_type="PERSON",
                text="John",
                confidence=0.9,
                bbox=None,
                sources=["presidio"],
                source_confidences={"presidio": 0.9},
            )
        ]
        ground_truth = []

        metrics = calculate_metrics(predictions, ground_truth)

        assert metrics.recall == 1.0  # Vacuously true
        assert metrics.precision == 0.0
        assert metrics.false_positives == 1

    def test_partial_match(self):
        """Test metrics with partial detection."""
        predictions = [
            AggregatedPHIRegion(
                entity_type="PERSON",
                text="John",
                confidence=0.9,
                bbox=None,
                sources=["presidio"],
                source_confidences={"presidio": 0.9},
            )
        ]

        ground_truth = [
            GroundTruthAnnotation(entity_type="PERSON", text="John"),
            GroundTruthAnnotation(entity_type="EMAIL", text="john@test.com"),
        ]

        metrics = calculate_metrics(predictions, ground_truth)

        assert metrics.true_positives == 1
        assert metrics.false_negatives == 1
        assert metrics.recall == 0.5

    def test_per_entity_metrics(self):
        """Test per-entity type metrics."""
        predictions = [
            AggregatedPHIRegion(
                entity_type="PERSON",
                text="John",
                confidence=0.9,
                bbox=None,
                sources=["presidio"],
                source_confidences={"presidio": 0.9},
            ),
            AggregatedPHIRegion(
                entity_type="EMAIL",
                text="test@test.com",
                confidence=0.85,
                bbox=None,
                sources=["presidio"],
                source_confidences={"presidio": 0.85},
            ),
        ]

        ground_truth = [
            GroundTruthAnnotation(entity_type="PERSON", text="John"),
            GroundTruthAnnotation(entity_type="EMAIL", text="other@test.com"),
        ]

        per_entity = calculate_per_entity_metrics(predictions, ground_truth)

        assert "PERSON" in per_entity
        assert "EMAIL" in per_entity
        assert per_entity["PERSON"].f1_score == 1.0  # Perfect match
