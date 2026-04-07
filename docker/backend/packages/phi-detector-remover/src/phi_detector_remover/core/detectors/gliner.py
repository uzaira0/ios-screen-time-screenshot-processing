"""GLiNER-based PHI detector.

Uses GLiNER (Generalist Lightweight NER) for zero-shot entity detection.
Higher accuracy than Presidio on edge cases (F1=0.98), configurable entity labels.

Install: pip install gliner

Usage:
    >>> detector = GLiNERDetector(labels=["person_name", "phone_number", "email"])
    >>> result = detector.detect(ocr_result)
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from phi_detector_remover.core.models import (
    BoundingBox,
    DetectionResult,
    DetectorType,
    PHIRegion,
)

if TYPE_CHECKING:
    from phi_detector_remover.core.models import OCRResult

logger = logging.getLogger(__name__)

# Default PHI labels for screen time screenshots
DEFAULT_PHI_LABELS = [
    "person_name",
    # "email" excluded - doesn't appear on Screen Time screenshots
    # "phone_number" excluded - doesn't appear on Screen Time screenshots
    # "address" excluded - false positives on app/game names (e.g. "Crossy Road")
    # "date_of_birth" excluded - doesn't appear on Screen Time screenshots
]


class GLiNERDetector:
    """PHI detector using GLiNER zero-shot NER.

    GLiNER detects entities by specifying labels at runtime — no training needed.
    Uses a BERT-base transformer model (~250MB) with optional ONNX quantization.

    Attributes:
        labels: Entity types to detect
        threshold: Minimum confidence score (0.0-1.0)
        model_name: HuggingFace model ID

    Example:
        >>> detector = GLiNERDetector(
        ...     labels=["person_name", "email", "phone_number"],
        ...     threshold=0.3,
        ... )
        >>> result = detector.detect(ocr_result)
    """

    def __init__(
        self,
        labels: list[str] | None = None,
        threshold: float = 0.3,
        model_name: str = "urchade/gliner_multi_pii-v1",
    ):
        self.labels = labels or DEFAULT_PHI_LABELS
        self.threshold = threshold
        self.model_name = model_name
        self._model = None

    @property
    def name(self) -> str:
        return "gliner"

    def is_available(self) -> bool:
        try:
            from gliner import GLiNER  # noqa: F401

            return True
        except ImportError:
            return False

    def _get_model(self):
        """Lazy-load the GLiNER model."""
        if self._model is None:
            from gliner import GLiNER

            logger.info("Loading GLiNER model: %s", self.model_name)
            self._model = GLiNER.from_pretrained(self.model_name)
            logger.info("GLiNER model loaded")
        return self._model

    def detect(self, ocr_result: OCRResult) -> DetectionResult:
        """Detect PHI entities in OCR-extracted text using GLiNER.

        Args:
            ocr_result: OCR result with text and word positions

        Returns:
            DetectionResult with detected PHI regions
        """
        start_time = time.perf_counter()

        model = self._get_model()
        text = ocr_result.text

        # Run GLiNER prediction
        entities = model.predict_entities(text, self.labels, threshold=self.threshold)

        # Convert to PHIRegion with bounding boxes
        regions = []
        for entity in entities:
            entity_text = entity["text"]
            entity_type = entity["label"].upper().replace(" ", "_")
            confidence = entity["score"]
            start_pos = entity["start"]
            end_pos = entity["end"]

            # Find bounding box from OCR words
            bbox = self._find_bbox_for_span(
                start_pos, end_pos, ocr_result
            )

            region = PHIRegion(
                entity_type=entity_type,
                text=entity_text,
                confidence=confidence,
                bbox=bbox,
                source=self.name,
            )
            regions.append(region)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return DetectionResult(
            detector_name=self.name,
            detector_type=DetectorType.TEXT,
            regions=regions,
            processing_time_ms=elapsed_ms,
            metadata={
                "model": self.model_name,
                "labels": self.labels,
                "threshold": self.threshold,
                "entities_found": len(regions),
            },
        )

    def _find_bbox_for_span(
        self,
        start: int,
        end: int,
        ocr_result: OCRResult,
    ) -> BoundingBox:
        """Find bounding box for a character span in the OCR text.

        Maps character positions back to word-level bounding boxes
        by tracking cumulative character offsets.
        """
        if not ocr_result.words:
            return BoundingBox(x=0, y=0, width=0, height=0)

        # Build character offset map
        current_pos = 0
        matching_words = []

        for word in ocr_result.words:
            word_start = current_pos
            word_end = current_pos + len(word.text)

            # Check overlap with entity span
            if word_end > start and word_start < end:
                matching_words.append(word)

            current_pos = word_end + 1  # +1 for space separator

        if not matching_words:
            return BoundingBox(x=0, y=0, width=0, height=0)

        # Merge bounding boxes of matching words
        min_x = min(w.bbox.x for w in matching_words)
        min_y = min(w.bbox.y for w in matching_words)
        max_x = max(w.bbox.x + w.bbox.width for w in matching_words)
        max_y = max(w.bbox.y + w.bbox.height for w in matching_words)

        return BoundingBox(
            x=min_x,
            y=min_y,
            width=max_x - min_x,
            height=max_y - min_y,
        )
