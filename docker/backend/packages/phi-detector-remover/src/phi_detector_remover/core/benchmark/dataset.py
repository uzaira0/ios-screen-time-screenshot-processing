"""Benchmark dataset handling for PHI detection evaluation.

Provides utilities for:
- Loading annotated datasets with ground truth
- Creating annotations from detection results
- Managing benchmark data in various formats
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from phi_detector_remover.core.models import (
    BenchmarkSample,
    BoundingBox,
    GroundTruthAnnotation,
)


@dataclass
class AnnotatedDataset:
    """Dataset of images with ground truth PHI annotations.

    Used for evaluating and comparing pipeline configurations.

    Supports two annotation formats:
    1. JSON sidecar files (image.png -> image.json)
    2. Single annotations file with all samples

    Example:
        >>> dataset = AnnotatedDataset.from_directory("./benchmark_data/")
        >>> for sample in dataset:
        ...     print(f"{sample.image_id}: {len(sample.annotations)} annotations")
    """

    samples: list[BenchmarkSample] = field(default_factory=list)
    name: str = "unnamed"
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.samples)

    def __iter__(self) -> Iterator[BenchmarkSample]:
        return iter(self.samples)

    def __getitem__(self, index: int) -> BenchmarkSample:
        return self.samples[index]

    @property
    def total_annotations(self) -> int:
        """Total number of ground truth annotations."""
        return sum(len(s.annotations) for s in self.samples)

    @property
    def entity_type_counts(self) -> dict[str, int]:
        """Count of annotations by entity type."""
        counts: dict[str, int] = {}
        for sample in self.samples:
            for ann in sample.annotations:
                counts[ann.entity_type] = counts.get(ann.entity_type, 0) + 1
        return counts

    @classmethod
    def from_directory(
        cls,
        directory: str | Path,
        image_pattern: str = "*.png",
        annotation_suffix: str = ".json",
    ) -> AnnotatedDataset:
        """Load dataset from directory with sidecar annotation files.

        Expected structure:
            directory/
                image1.png
                image1.json  # Annotations for image1.png
                image2.png
                image2.json

        Args:
            directory: Directory containing images and annotations
            image_pattern: Glob pattern for image files
            annotation_suffix: Suffix for annotation files

        Returns:
            Loaded dataset
        """
        directory = Path(directory)
        samples = []

        for image_path in sorted(directory.glob(image_pattern)):
            annotation_path = image_path.with_suffix(annotation_suffix)

            annotations = []
            if annotation_path.exists():
                annotations = load_annotations(annotation_path)

            sample = BenchmarkSample(
                image_id=image_path.stem,
                image_path=str(image_path),
                annotations=annotations,
            )
            samples.append(sample)

        return cls(
            samples=samples,
            name=directory.name,
            metadata={"source_directory": str(directory)},
        )

    @classmethod
    def from_annotations_file(
        cls,
        annotations_path: str | Path,
        images_directory: str | Path,
    ) -> AnnotatedDataset:
        """Load dataset from a single annotations file.

        Expected format:
            {
                "dataset_name": "...",
                "samples": [
                    {
                        "image_id": "image1",
                        "image_path": "image1.png",  # Relative to images_directory
                        "annotations": [...]
                    }
                ]
            }

        Args:
            annotations_path: Path to annotations JSON file
            images_directory: Directory containing images

        Returns:
            Loaded dataset
        """
        annotations_path = Path(annotations_path)
        images_directory = Path(images_directory)

        with open(annotations_path) as f:
            data = json.load(f)

        samples = []
        for sample_data in data.get("samples", []):
            # Resolve image path
            image_rel_path = sample_data.get("image_path", f"{sample_data['image_id']}.png")
            image_path = images_directory / image_rel_path

            # Parse annotations
            annotations = []
            for ann_data in sample_data.get("annotations", []):
                bbox = None
                if ann_data.get("bbox"):
                    bbox = BoundingBox.from_dict(ann_data["bbox"])

                annotations.append(
                    GroundTruthAnnotation(
                        entity_type=ann_data["entity_type"],
                        text=ann_data["text"],
                        bbox=bbox,
                    )
                )

            samples.append(
                BenchmarkSample(
                    image_id=sample_data["image_id"],
                    image_path=str(image_path),
                    annotations=annotations,
                    metadata=sample_data.get("metadata", {}),
                )
            )

        return cls(
            samples=samples,
            name=data.get("dataset_name", "unnamed"),
            description=data.get("description", ""),
            metadata=data.get("metadata", {}),
        )

    def to_json(self, path: str | Path) -> None:
        """Save dataset to JSON file.

        Args:
            path: Output path
        """
        data = {
            "dataset_name": self.name,
            "description": self.description,
            "metadata": self.metadata,
            "samples": [
                {
                    "image_id": s.image_id,
                    "image_path": s.image_path,
                    "annotations": [a.to_dict() for a in s.annotations],
                    "metadata": s.metadata,
                }
                for s in self.samples
            ],
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def filter_by_entity_type(self, entity_types: list[str]) -> AnnotatedDataset:
        """Create subset with only specified entity types.

        Args:
            entity_types: Entity types to include

        Returns:
            Filtered dataset
        """
        filtered_samples = []
        for sample in self.samples:
            filtered_anns = [a for a in sample.annotations if a.entity_type in entity_types]
            if filtered_anns:
                filtered_samples.append(
                    BenchmarkSample(
                        image_id=sample.image_id,
                        image_path=sample.image_path,
                        annotations=filtered_anns,
                        metadata=sample.metadata,
                    )
                )

        return AnnotatedDataset(
            samples=filtered_samples,
            name=f"{self.name}_filtered",
            metadata={**self.metadata, "filtered_entities": entity_types},
        )

    def split(
        self,
        train_ratio: float = 0.8,
        seed: int = 42,
    ) -> tuple[AnnotatedDataset, AnnotatedDataset]:
        """Split dataset into train and test sets.

        Args:
            train_ratio: Fraction for training set
            seed: Random seed for reproducibility

        Returns:
            (train_dataset, test_dataset)
        """
        import random

        random.seed(seed)
        indices = list(range(len(self.samples)))
        random.shuffle(indices)

        split_idx = int(len(indices) * train_ratio)
        train_indices = indices[:split_idx]
        test_indices = indices[split_idx:]

        train_samples = [self.samples[i] for i in train_indices]
        test_samples = [self.samples[i] for i in test_indices]

        return (
            AnnotatedDataset(
                samples=train_samples,
                name=f"{self.name}_train",
                metadata={**self.metadata, "split": "train"},
            ),
            AnnotatedDataset(
                samples=test_samples,
                name=f"{self.name}_test",
                metadata={**self.metadata, "split": "test"},
            ),
        )


def load_annotations(path: str | Path) -> list[GroundTruthAnnotation]:
    """Load annotations from a JSON file.

    Expected format:
        {
            "annotations": [
                {
                    "entity_type": "PERSON",
                    "text": "John Doe",
                    "bbox": {"x": 100, "y": 50, "width": 80, "height": 20}
                }
            ]
        }

    Or simply a list:
        [
            {"entity_type": "PERSON", "text": "John Doe", ...}
        ]

    Args:
        path: Path to annotation file

    Returns:
        List of ground truth annotations
    """
    with open(path) as f:
        data = json.load(f)

    if isinstance(data, list):
        ann_list = data
    else:
        ann_list = data.get("annotations", [])

    annotations = []
    for ann_data in ann_list:
        bbox = None
        if ann_data.get("bbox"):
            bbox = BoundingBox.from_dict(ann_data["bbox"])

        annotations.append(
            GroundTruthAnnotation(
                entity_type=ann_data["entity_type"],
                text=ann_data["text"],
                bbox=bbox,
            )
        )

    return annotations


def create_annotation(
    entity_type: str,
    text: str,
    bbox: tuple[int, int, int, int] | dict[str, int] | None = None,
) -> GroundTruthAnnotation:
    """Create a ground truth annotation.

    Convenience function for creating annotations programmatically.

    Args:
        entity_type: PHI entity type
        text: The PHI text
        bbox: Optional bounding box as (x, y, w, h) tuple or dict

    Returns:
        Ground truth annotation
    """
    if bbox is None:
        bbox_obj = None
    elif isinstance(bbox, tuple):
        bbox_obj = BoundingBox(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
    else:
        bbox_obj = BoundingBox.from_dict(bbox)

    return GroundTruthAnnotation(
        entity_type=entity_type,
        text=text,
        bbox=bbox_obj,
    )


def save_annotations(
    annotations: list[GroundTruthAnnotation],
    path: str | Path,
) -> None:
    """Save annotations to JSON file.

    Args:
        annotations: List of annotations
        path: Output path
    """
    data = {"annotations": [a.to_dict() for a in annotations]}

    with open(path, "w") as f:
        json.dump(data, f, indent=2)
