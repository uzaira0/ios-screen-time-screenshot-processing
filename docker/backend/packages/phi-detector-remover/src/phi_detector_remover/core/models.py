"""Core data models for PHI detection.

This module contains all dataclasses and Pydantic models used throughout
the package. These are framework-agnostic and can be serialized to JSON/dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DetectorType(StrEnum):
    """Type of detector that produced a result."""

    TEXT = "text"  # Requires OCR first (Presidio, regex, LLM)
    VISION = "vision"  # Analyzes image directly (Gemma, Hunyuan)


class EntityType(StrEnum):
    """Standard PHI entity types.

    Based on HIPAA identifiers plus custom research-specific types.
    """

    # HIPAA Safe Harbor identifiers
    PERSON = "PERSON"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    SSN = "SSN"
    DATE = "DATE"
    AGE = "AGE"
    ADDRESS = "ADDRESS"
    ZIP_CODE = "ZIP_CODE"
    LOCATION = "LOCATION"
    URL = "URL"
    IP_ADDRESS = "IP_ADDRESS"

    # Medical identifiers
    MRN = "MRN"  # Medical Record Number
    MEDICAL_LICENSE = "MEDICAL_LICENSE"
    HEALTH_PLAN_ID = "HEALTH_PLAN_ID"

    # Research-specific
    STUDY_ID = "STUDY_ID"
    PARTICIPANT_ID = "PARTICIPANT_ID"

    # Device identifiers
    DEVICE_ID = "DEVICE_ID"
    SERIAL_NUMBER = "SERIAL_NUMBER"
    MAC_ADDRESS = "MAC_ADDRESS"
    IMEI = "IMEI"

    # Other
    CREDIT_CARD = "CREDIT_CARD"
    DRIVERS_LICENSE = "DRIVERS_LICENSE"
    PASSPORT = "PASSPORT"
    UNKNOWN = "UNKNOWN"


@dataclass
class BoundingBox:
    """Bounding box coordinates in image space.

    Attributes:
        x: Left edge (pixels from left)
        y: Top edge (pixels from top)
        width: Box width in pixels
        height: Box height in pixels
    """

    x: int
    y: int
    width: int
    height: int

    @property
    def area(self) -> int:
        """Calculate bounding box area."""
        return self.width * self.height

    @property
    def center(self) -> tuple[int, int]:
        """Calculate center point."""
        return (self.x + self.width // 2, self.y + self.height // 2)

    def to_tuple(self) -> tuple[int, int, int, int]:
        """Convert to (x, y, width, height) tuple."""
        return (self.x, self.y, self.width, self.height)

    def to_xyxy(self) -> tuple[int, int, int, int]:
        """Convert to (x1, y1, x2, y2) format."""
        return (self.x, self.y, self.x + self.width, self.y + self.height)

    @classmethod
    def from_xyxy(cls, x1: int, y1: int, x2: int, y2: int) -> BoundingBox:
        """Create from (x1, y1, x2, y2) format."""
        return cls(x=x1, y=y1, width=x2 - x1, height=y2 - y1)

    def iou(self, other: BoundingBox) -> float:
        """Calculate Intersection over Union with another box."""
        x1 = max(self.x, other.x)
        y1 = max(self.y, other.y)
        x2 = min(self.x + self.width, other.x + other.width)
        y2 = min(self.y + self.height, other.y + other.height)

        if x2 <= x1 or y2 <= y1:
            return 0.0

        intersection = (x2 - x1) * (y2 - y1)
        union = self.area + other.area - intersection

        return intersection / union if union > 0 else 0.0

    def to_dict(self) -> dict[str, int]:
        """Convert to dictionary."""
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> BoundingBox:
        """Create from dictionary."""
        return cls(x=data["x"], y=data["y"], width=data["width"], height=data["height"])


@dataclass
class OCRWord:
    """A single word detected by OCR.

    Attributes:
        text: The extracted text
        confidence: OCR confidence score (0.0-1.0)
        bbox: Bounding box in image coordinates
    """

    text: str
    confidence: float
    bbox: BoundingBox

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "text": self.text,
            "confidence": self.confidence,
            "bbox": self.bbox.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OCRWord:
        """Create from dictionary."""
        return cls(
            text=data["text"],
            confidence=data["confidence"],
            bbox=BoundingBox.from_dict(data["bbox"]),
        )


@dataclass
class OCRResult:
    """Complete OCR result for an image.

    Attributes:
        text: Full extracted text (space-joined words)
        words: List of individual words with positions
        confidence: Overall confidence score (0.0-1.0)
        engine: Name of OCR engine used
    """

    text: str
    words: list[OCRWord]
    confidence: float
    engine: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "text": self.text,
            "words": [w.to_dict() for w in self.words],
            "confidence": self.confidence,
            "engine": self.engine,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OCRResult:
        """Create from dictionary."""
        return cls(
            text=data["text"],
            words=[OCRWord.from_dict(w) for w in data["words"]],
            confidence=data["confidence"],
            engine=data.get("engine", "unknown"),
        )


@dataclass
class PHIRegion:
    """A detected PHI region in an image.

    Attributes:
        entity_type: Type of PHI (e.g., PERSON, EMAIL, MRN)
        text: The detected text content
        confidence: Detection confidence (0.0-1.0)
        bbox: Bounding box in image coordinates (may be None for text-only)
        source: Which detector found this (e.g., "presidio", "gemma")
    """

    entity_type: str
    text: str
    confidence: float
    bbox: BoundingBox | None = None
    source: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "entity_type": self.entity_type,
            "text": self.text,
            "confidence": self.confidence,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PHIRegion:
        """Create from dictionary."""
        return cls(
            entity_type=data["entity_type"],
            text=data["text"],
            confidence=data["confidence"],
            bbox=BoundingBox.from_dict(data["bbox"]) if data.get("bbox") else None,
            source=data.get("source", "unknown"),
        )

    # Backward compatibility with old tuple-based bbox
    @property
    def bbox_tuple(self) -> tuple[int, int, int, int] | None:
        """Get bbox as (x, y, width, height) tuple."""
        return self.bbox.to_tuple() if self.bbox else None


@dataclass
class DetectionResult:
    """Result from a single detector.

    Attributes:
        detector_name: Name of the detector that produced this result
        detector_type: Whether this is a text or vision detector
        regions: List of detected PHI regions
        processing_time_ms: Time taken for detection in milliseconds
        metadata: Additional detector-specific metadata
    """

    detector_name: str
    detector_type: DetectorType
    regions: list[PHIRegion]
    processing_time_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def region_count(self) -> int:
        """Number of regions detected."""
        return len(self.regions)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "detector_name": self.detector_name,
            "detector_type": self.detector_type.value,
            "regions": [r.to_dict() for r in self.regions],
            "processing_time_ms": self.processing_time_ms,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DetectionResult:
        """Create from dictionary."""
        return cls(
            detector_name=data["detector_name"],
            detector_type=DetectorType(data["detector_type"]),
            regions=[PHIRegion.from_dict(r) for r in data["regions"]],
            processing_time_ms=data.get("processing_time_ms", 0.0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class AggregatedPHIRegion:
    """A PHI region aggregated from multiple detectors.

    Attributes:
        entity_type: Consensus entity type
        text: The detected text
        confidence: Aggregated confidence score
        bbox: Best bounding box (from highest confidence source)
        sources: Which detectors found this region
        source_confidences: Confidence from each detector
        aggregation_method: How this was aggregated
    """

    entity_type: str
    text: str
    confidence: float
    bbox: BoundingBox | None
    sources: list[str]
    source_confidences: dict[str, float]
    aggregation_method: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entity_type": self.entity_type,
            "text": self.text,
            "confidence": self.confidence,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "sources": self.sources,
            "source_confidences": self.source_confidences,
            "aggregation_method": self.aggregation_method,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AggregatedPHIRegion:
        """Create from dictionary."""
        return cls(
            entity_type=data["entity_type"],
            text=data["text"],
            confidence=data["confidence"],
            bbox=BoundingBox.from_dict(data["bbox"]) if data.get("bbox") else None,
            sources=data["sources"],
            source_confidences=data["source_confidences"],
            aggregation_method=data.get("aggregation_method", "unknown"),
        )

    def to_phi_region(self) -> PHIRegion:
        """Convert to simple PHIRegion for redaction."""
        return PHIRegion(
            entity_type=self.entity_type,
            text=self.text,
            confidence=self.confidence,
            bbox=self.bbox,
            source=",".join(self.sources),
        )


@dataclass
class PipelineResult:
    """Complete result from running the PHI detection pipeline.

    Attributes:
        aggregated_regions: Final aggregated PHI regions
        detector_results: Raw results from each detector
        ocr_result: OCR result (if OCR was performed)
        total_processing_time_ms: Total pipeline time
        pipeline_config: Configuration used for this run
    """

    aggregated_regions: list[AggregatedPHIRegion]
    detector_results: dict[str, DetectionResult]
    ocr_result: OCRResult | None
    total_processing_time_ms: float
    pipeline_config: dict[str, Any] = field(default_factory=dict)

    @property
    def region_count(self) -> int:
        """Total number of aggregated regions."""
        return len(self.aggregated_regions)

    @property
    def has_phi(self) -> bool:
        """Whether any PHI was detected."""
        return len(self.aggregated_regions) > 0

    def get_regions_for_redaction(self) -> list[PHIRegion]:
        """Get simple PHIRegion list for redaction."""
        return [r.to_phi_region() for r in self.aggregated_regions]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "aggregated_regions": [r.to_dict() for r in self.aggregated_regions],
            "detector_results": {k: v.to_dict() for k, v in self.detector_results.items()},
            "ocr_result": self.ocr_result.to_dict() if self.ocr_result else None,
            "total_processing_time_ms": self.total_processing_time_ms,
            "pipeline_config": self.pipeline_config,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineResult:
        """Create from dictionary."""
        return cls(
            aggregated_regions=[
                AggregatedPHIRegion.from_dict(r) for r in data["aggregated_regions"]
            ],
            detector_results={
                k: DetectionResult.from_dict(v) for k, v in data["detector_results"].items()
            },
            ocr_result=(
                OCRResult.from_dict(data["ocr_result"]) if data.get("ocr_result") else None
            ),
            total_processing_time_ms=data["total_processing_time_ms"],
            pipeline_config=data.get("pipeline_config", {}),
        )


# ============================================================================
# Benchmark Models
# ============================================================================


@dataclass
class GroundTruthAnnotation:
    """Ground truth PHI annotation for benchmarking.

    Attributes:
        entity_type: Type of PHI
        text: The PHI text
        bbox: Bounding box (if annotated)
    """

    entity_type: str
    text: str
    bbox: BoundingBox | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entity_type": self.entity_type,
            "text": self.text,
            "bbox": self.bbox.to_dict() if self.bbox else None,
        }


@dataclass
class BenchmarkSample:
    """A single sample in a benchmark dataset.

    Attributes:
        image_id: Unique identifier for this sample
        image_path: Path to the image file
        annotations: Ground truth PHI annotations
        metadata: Additional sample metadata
    """

    image_id: str
    image_path: str
    annotations: list[GroundTruthAnnotation]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkMetrics:
    """Metrics from running a benchmark.

    Attributes:
        precision: TP / (TP + FP)
        recall: TP / (TP + FN)
        f1_score: Harmonic mean of precision and recall
        true_positives: Number of correctly detected PHI
        false_positives: Number of incorrectly detected PHI
        false_negatives: Number of missed PHI
        avg_processing_time_ms: Average time per image
        iou_threshold: IoU threshold used for matching (if bbox-based)
    """

    precision: float
    recall: float
    f1_score: float
    true_positives: int
    false_positives: int
    false_negatives: int
    avg_processing_time_ms: float
    iou_threshold: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "precision": self.precision,
            "recall": self.recall,
            "f1_score": self.f1_score,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "avg_processing_time_ms": self.avg_processing_time_ms,
            "iou_threshold": self.iou_threshold,
        }


@dataclass
class BenchmarkResult:
    """Complete benchmark result for a pipeline configuration.

    Attributes:
        pipeline_name: Identifier for the pipeline configuration
        pipeline_config: Configuration used
        metrics: Computed metrics
        per_entity_metrics: Metrics broken down by entity type
        per_sample_results: Detailed results per image (optional)
    """

    pipeline_name: str
    pipeline_config: dict[str, Any]
    metrics: BenchmarkMetrics
    per_entity_metrics: dict[str, BenchmarkMetrics] = field(default_factory=dict)
    per_sample_results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pipeline_name": self.pipeline_name,
            "pipeline_config": self.pipeline_config,
            "metrics": self.metrics.to_dict(),
            "per_entity_metrics": {k: v.to_dict() for k, v in self.per_entity_metrics.items()},
            "per_sample_results": self.per_sample_results,
        }


@dataclass
class BenchmarkComparison:
    """Comparison of multiple pipeline configurations.

    Used to identify simpler pipelines with equivalent performance.

    Attributes:
        results: Results from each pipeline
        baseline_name: Which pipeline is the baseline for comparison
        recommendations: Suggested optimizations based on results
    """

    results: list[BenchmarkResult]
    baseline_name: str | None = None
    recommendations: list[str] = field(default_factory=list)

    def get_pareto_optimal(
        self,
        metric: str = "f1_score",
        time_weight: float = 0.1,
    ) -> list[str]:
        """Find Pareto-optimal pipelines (best trade-off of accuracy vs speed).

        Args:
            metric: Which accuracy metric to use
            time_weight: How much to weight processing time (0-1)

        Returns:
            List of pipeline names on the Pareto frontier
        """
        # Simple Pareto frontier implementation
        scores = []
        for result in self.results:
            accuracy = getattr(result.metrics, metric)
            # Normalize time (lower is better, so we invert)
            time_score = 1.0 / (1.0 + result.metrics.avg_processing_time_ms / 1000)
            combined = (1 - time_weight) * accuracy + time_weight * time_score
            scores.append((result.pipeline_name, combined, accuracy, time_score))

        # Sort by combined score descending
        scores.sort(key=lambda x: x[1], reverse=True)

        # Find Pareto optimal (none dominates in both dimensions)
        pareto = []
        for name, _, acc, time in scores:
            dominated = False
            for other_name, _, other_acc, other_time in scores:
                if (
                    other_acc >= acc
                    and other_time >= time
                    and (other_acc > acc or other_time > time)
                ):
                    dominated = True
                    break
            if not dominated:
                pareto.append(name)

        return pareto

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "results": [r.to_dict() for r in self.results],
            "baseline_name": self.baseline_name,
            "recommendations": self.recommendations,
        }
