"""PHI detection using Presidio and OCR."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerResult

from phi_detector_remover.core.config import PHIDetectorConfig
from phi_detector_remover.core.models import OCRResult
from phi_detector_remover.core.ocr import TesseractEngine
from phi_detector_remover.core.patterns import DEFAULT_PATTERNS, CustomPHIPattern


@dataclass
class PHIRegion:
    """A detected PHI region in an image.

    Attributes:
        entity_type: Type of PHI (e.g., PERSON, EMAIL_ADDRESS, MRN)
        text: The detected text
        score: Confidence score (0.0-1.0)
        bbox: Bounding box as (x, y, width, height)
        source: Detection source ('presidio', 'custom_pattern', 'manual')
    """

    entity_type: str
    text: str
    score: float
    bbox: tuple[int, int, int, int]
    source: str = "presidio"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "entity_type": self.entity_type,
            "text": self.text,
            "score": self.score,
            "bbox": {
                "x": self.bbox[0],
                "y": self.bbox[1],
                "width": self.bbox[2],
                "height": self.bbox[3],
            },
            "source": self.source,
        }


class PHIDetector:
    """PHI detector using Presidio and OCR.

    This class combines OCR text extraction with Presidio's NER-based detection
    and custom pattern matching to identify PHI in images.
    """

    def __init__(self, config: PHIDetectorConfig | None = None):
        """Initialize PHI detector.

        Args:
            config: Detector configuration (uses defaults if None)
        """
        self.config = config or PHIDetectorConfig()
        self.ocr_engine = TesseractEngine(
            lang=self.config.ocr.language,
            psm=self.config.ocr.psm,
            oem=self.config.ocr.oem,
        )
        self.analyzer = self._create_analyzer()

    def _create_analyzer(self) -> AnalyzerEngine:
        """Create Presidio analyzer with custom recognizers.

        Returns:
            Configured AnalyzerEngine
        """
        analyzer = AnalyzerEngine()

        # Add custom pattern recognizers if enabled
        if self.config.custom_patterns.enabled:
            for pattern_name, pattern_regex in self.config.custom_patterns.patterns.items():
                recognizer = PatternRecognizer(
                    supported_entity=pattern_name,
                    patterns=[
                        Pattern(
                            name=pattern_name,
                            regex=pattern_regex,
                            score=0.9,
                        )
                    ],
                )
                analyzer.registry.add_recognizer(recognizer)

        # Add default custom patterns
        for pattern in DEFAULT_PATTERNS.values():
            recognizer = PatternRecognizer(
                supported_entity=pattern.name,
                patterns=[
                    Pattern(
                        name=pattern.name,
                        regex=pattern.pattern.pattern,
                        score=pattern.score,
                    )
                ],
            )
            analyzer.registry.add_recognizer(recognizer)

        return analyzer

    def detect_in_text(self, text: str) -> list[RecognizerResult]:
        """Detect PHI in plain text.

        Args:
            text: Text to analyze

        Returns:
            List of detected PHI entities
        """
        results = self.analyzer.analyze(
            text=text,
            language=self.config.presidio.language,
            entities=self.config.presidio.entities,
            score_threshold=self.config.presidio.score_threshold,
            allow_list=self.config.presidio.allow_list,
        )

        # Filter by deny list
        if self.config.presidio.deny_list:
            filtered_results = []
            for result in results:
                entity_text = text[result.start : result.end]
                if entity_text not in self.config.presidio.deny_list:
                    filtered_results.append(result)
            return filtered_results

        return results

    def detect_in_image(self, image_bytes: bytes) -> list[PHIRegion]:
        """Detect PHI in an image using OCR + Presidio.

        Args:
            image_bytes: Image data as bytes

        Returns:
            List of PHI regions with bounding boxes
        """
        # Extract text with OCR
        ocr_result = self.ocr_engine.extract(image_bytes)

        # Detect PHI in extracted text
        phi_results = self.detect_in_text(ocr_result.text)

        # Map PHI detections to image coordinates
        regions = self._map_to_image_coordinates(phi_results, ocr_result)

        # Merge nearby regions if enabled
        if self.config.merge_nearby_regions:
            regions = self._merge_regions(regions)

        # Filter by minimum area
        regions = [r for r in regions if r.bbox[2] * r.bbox[3] >= self.config.min_bbox_area]

        return regions

    def _map_to_image_coordinates(
        self,
        phi_results: list[RecognizerResult],
        ocr_result: OCRResult,
    ) -> list[PHIRegion]:
        """Map text-based PHI detections to image bounding boxes.

        Args:
            phi_results: PHI detection results from Presidio
            ocr_result: OCR result with word positions

        Returns:
            List of PHI regions with bounding boxes
        """
        regions = []

        for result in phi_results:
            # Find OCR words that overlap with this PHI entity
            entity_text = ocr_result.text[result.start : result.end]

            # Find matching words in OCR result
            matching_words = self._find_matching_words(
                entity_text,
                result.start,
                result.end,
                ocr_result,
            )

            if not matching_words:
                continue

            # Calculate bounding box encompassing all matching words
            bbox = self._calculate_bbox(matching_words)

            region = PHIRegion(
                entity_type=result.entity_type,
                text=entity_text,
                score=result.score,
                bbox=bbox,
                source="presidio",
            )

            regions.append(region)

        return regions

    def _find_matching_words(
        self,
        entity_text: str,
        start_pos: int,
        end_pos: int,
        ocr_result: OCRResult,
    ) -> list[Any]:
        """Find OCR words that match a PHI entity.

        Args:
            entity_text: The PHI entity text
            start_pos: Start position in full text
            end_pos: End position in full text
            ocr_result: OCR result

        Returns:
            List of matching OCR words
        """
        # Simple approach: find words whose text appears in entity_text
        entity_words = entity_text.lower().split()
        matching_words = []

        for word in ocr_result.words:
            if word.text.lower() in entity_words:
                matching_words.append(word)

        return matching_words

    def _calculate_bbox(self, words: list[Any]) -> tuple[int, int, int, int]:
        """Calculate bounding box encompassing multiple words.

        Args:
            words: List of OCR words

        Returns:
            Bounding box as (x, y, width, height)
        """
        if not words:
            return (0, 0, 0, 0)

        # Find min/max coordinates (words have BoundingBox objects)
        min_x = min(w.bbox.x for w in words)
        min_y = min(w.bbox.y for w in words)
        max_x = max(w.bbox.x + w.bbox.width for w in words)
        max_y = max(w.bbox.y + w.bbox.height for w in words)

        return (min_x, min_y, max_x - min_x, max_y - min_y)

    def _merge_regions(self, regions: list[PHIRegion]) -> list[PHIRegion]:
        """Merge overlapping or nearby regions.

        Args:
            regions: List of PHI regions

        Returns:
            List of merged regions
        """
        if not regions:
            return []

        # Sort by x coordinate
        sorted_regions = sorted(regions, key=lambda r: r.bbox[0])

        merged = [sorted_regions[0]]

        for current in sorted_regions[1:]:
            last = merged[-1]

            # Check if regions should be merged
            if self._should_merge(last.bbox, current.bbox):
                # Merge bboxes
                merged_bbox = self._merge_bboxes(last.bbox, current.bbox)

                # Create merged region
                merged_region = PHIRegion(
                    entity_type=f"{last.entity_type}+{current.entity_type}",
                    text=f"{last.text} {current.text}",
                    score=max(last.score, current.score),
                    bbox=merged_bbox,
                    source="merged",
                )

                merged[-1] = merged_region
            else:
                merged.append(current)

        return merged

    def _should_merge(
        self,
        bbox1: tuple[int, int, int, int],
        bbox2: tuple[int, int, int, int],
    ) -> bool:
        """Check if two bounding boxes should be merged.

        Args:
            bbox1: First bounding box (x, y, width, height)
            bbox2: Second bounding box (x, y, width, height)

        Returns:
            True if boxes should be merged
        """
        threshold = self.config.merge_distance_threshold

        # Check horizontal distance
        x1_end = bbox1[0] + bbox1[2]
        x2_start = bbox2[0]
        horizontal_gap = x2_start - x1_end

        # Check vertical overlap
        y1_start, y1_end = bbox1[1], bbox1[1] + bbox1[3]
        y2_start, y2_end = bbox2[1], bbox2[1] + bbox2[3]

        vertical_overlap = not (y1_end < y2_start or y2_end < y1_start)

        return horizontal_gap <= threshold and vertical_overlap

    def _merge_bboxes(
        self,
        bbox1: tuple[int, int, int, int],
        bbox2: tuple[int, int, int, int],
    ) -> tuple[int, int, int, int]:
        """Merge two bounding boxes.

        Args:
            bbox1: First bounding box (x, y, width, height)
            bbox2: Second bounding box (x, y, width, height)

        Returns:
            Merged bounding box
        """
        min_x = min(bbox1[0], bbox2[0])
        min_y = min(bbox1[1], bbox2[1])
        max_x = max(bbox1[0] + bbox1[2], bbox2[0] + bbox2[2])
        max_y = max(bbox1[1] + bbox1[3], bbox2[1] + bbox2[3])

        return (min_x, min_y, max_x - min_x, max_y - min_y)
