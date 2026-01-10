"""Protocol definitions for extensible PHI detection components.

This module defines the abstract interfaces (protocols) that allow
different implementations to be swapped in:

- OCREngine: Text extraction from images (Tesseract, Hunyuan-OCR, etc.)
- TextDetector: PHI detection from text (Presidio, regex, local LLMs)
- VisionDetector: PHI detection from images directly (Gemma, multimodal LLMs)
- AggregationStrategy: Combining results from multiple detectors
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import numpy as np

if TYPE_CHECKING:
    from phi_detector_remover.core.models import (
        AggregatedPHIRegion,
        DetectionResult,
        OCRResult,
    )


@runtime_checkable
class OCREngine(Protocol):
    """Protocol for OCR text extraction engines.

    Implementations:
    - TesseractEngine: Traditional OCR using Tesseract
    - HunyuanOCREngine: Vision-language model based OCR
    - PaddleOCREngine: PaddlePaddle-based OCR (future)

    Example:
        >>> engine = TesseractEngine(lang="eng")
        >>> result = engine.extract(image_bytes)
        >>> print(result.text)
        >>> for word in result.words:
        ...     print(f"{word.text} at {word.bbox}")
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this OCR engine."""
        ...

    @abstractmethod
    def extract(self, image: bytes | np.ndarray) -> OCRResult:
        """Extract text with word-level bounding boxes from image.

        Args:
            image: Image as bytes or numpy array (BGR format)

        Returns:
            OCRResult with full text and word-level positions
        """
        ...

    def is_available(self) -> bool:
        """Check if this engine is available (dependencies installed).

        Returns:
            True if engine can be used
        """
        return True


@runtime_checkable
class TextDetector(Protocol):
    """Protocol for text-based PHI detection.

    These detectors analyze OCR-extracted text to find PHI entities.
    They require OCR to be run first.

    Implementations:
    - PresidioDetector: Microsoft Presidio NER-based detection
    - RegexDetector: Custom regex pattern matching
    - LLMTextDetector: Local LLM analyzing text (Llama, Mistral, etc.)

    Example:
        >>> detector = PresidioDetector(entities=["PERSON", "EMAIL"])
        >>> ocr_result = ocr_engine.extract(image_bytes)
        >>> detections = detector.detect(ocr_result)
        >>> for d in detections:
        ...     print(f"{d.entity_type}: {d.text} ({d.confidence:.2f})")
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this detector."""
        ...

    @abstractmethod
    def detect(self, ocr_result: OCRResult) -> DetectionResult:
        """Detect PHI entities in OCR-extracted text.

        Args:
            ocr_result: OCR result with text and word positions

        Returns:
            DetectionResult with detected PHI regions
        """
        ...

    def is_available(self) -> bool:
        """Check if this detector is available."""
        return True


@runtime_checkable
class VisionDetector(Protocol):
    """Protocol for vision-based PHI detection.

    These detectors analyze images directly using vision-language models.
    They do NOT require separate OCR - they see the image.

    Implementations:
    - GemmaVisionDetector: Google Gemma multimodal model
    - HunyuanVisionDetector: Tencent Hunyuan multimodal model
    - QwenVisionDetector: Alibaba Qwen-VL model (future)

    Example:
        >>> detector = GemmaVisionDetector(model="gemma-2-2b")
        >>> detections = detector.detect(image_bytes)
        >>> for d in detections:
        ...     print(f"{d.entity_type}: {d.text} ({d.confidence:.2f})")
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this detector."""
        ...

    @abstractmethod
    def detect(self, image: bytes | np.ndarray) -> DetectionResult:
        """Detect PHI entities directly from image.

        Args:
            image: Image as bytes or numpy array

        Returns:
            DetectionResult with detected PHI regions

        Note:
            Vision detectors may return bounding boxes directly from
            the model or may need post-processing to localize text.
        """
        ...

    @property
    def supports_bounding_boxes(self) -> bool:
        """Whether this detector can return bounding box coordinates.

        Some vision models only return entity text without localization.
        In that case, a separate OCR pass may be needed for bbox mapping.
        """
        return False

    def is_available(self) -> bool:
        """Check if this detector is available."""
        return True


@runtime_checkable
class AggregationStrategy(Protocol):
    """Protocol for aggregating results from multiple detectors.

    Different strategies provide different trade-offs:
    - Union: High recall, may have false positives
    - Intersection: High precision, may miss PHI
    - WeightedVote: Balanced, configurable weights
    - Threshold: Include if aggregate confidence > threshold

    Example:
        >>> strategy = WeightedVoteAggregator(
        ...     weights={"presidio": 0.4, "gemma": 0.4, "regex": 0.2}
        ... )
        >>> aggregated = strategy.aggregate(detector_results)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this strategy."""
        ...

    @abstractmethod
    def aggregate(
        self,
        results: dict[str, DetectionResult],
    ) -> list[AggregatedPHIRegion]:
        """Aggregate detection results from multiple detectors.

        Args:
            results: Dict mapping detector name to its DetectionResult

        Returns:
            List of aggregated PHI regions with combined confidence
        """
        ...


@runtime_checkable
class BenchmarkDataset(Protocol):
    """Protocol for benchmark datasets with ground truth annotations.

    Used for evaluating and comparing pipeline configurations.

    Example:
        >>> dataset = AnnotatedScreenshotDataset("./benchmark_data/")
        >>> for sample in dataset:
        ...     image = sample.image
        ...     ground_truth = sample.annotations
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Dataset identifier."""
        ...

    @abstractmethod
    def __len__(self) -> int:
        """Number of samples in dataset."""
        ...

    @abstractmethod
    def __iter__(self):
        """Iterate over (image_bytes, ground_truth_regions) pairs."""
        ...
