"""Presidio-based PHI detector.

Uses Microsoft Presidio's NER models for entity detection.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from phi_detector_remover.core.config import PresidioConfig
from phi_detector_remover.core.models import (
    BoundingBox,
    DetectionResult,
    DetectorType,
    PHIRegion,
)

if TYPE_CHECKING:
    from phi_detector_remover.core.models import OCRResult


class PresidioDetector:
    """PHI detector using Microsoft Presidio.

    Presidio uses NER (Named Entity Recognition) models to detect
    various types of PHI including names, emails, phone numbers, etc.

    Attributes:
        config: Presidio configuration (includes allow_list for filtering)

    Example:
        >>> detector = PresidioDetector(
        ...     config=PresidioConfig(
        ...         entities=["PERSON", "EMAIL"],
        ...         allow_list=["Safari", "Instagram"]  # Known false positives
        ...     )
        ... )
        >>> result = detector.detect(ocr_result)
    """

    def __init__(
        self,
        config: PresidioConfig | None = None,
        entities: list[str] | None = None,
        score_threshold: float | None = None,
        allow_list: list[str] | None = None,
    ):
        """Initialize Presidio detector.

        Args:
            config: Full Presidio configuration
            entities: Override entities to detect (convenience param)
            score_threshold: Override score threshold (convenience param)
            allow_list: Terms to ignore (convenience param)
        """
        self.config = config or PresidioConfig()

        # Allow overriding via convenience params
        if entities is not None:
            self.config.entities = entities
        if score_threshold is not None:
            self.config.score_threshold = score_threshold
        if allow_list is not None:
            self.config.allow_list = allow_list

        self._analyzer = None

    @property
    def name(self) -> str:
        """Detector identifier."""
        return "presidio"

    def is_available(self) -> bool:
        """Check if Presidio is available."""
        try:
            from presidio_analyzer import AnalyzerEngine

            return True
        except ImportError:
            return False

    def _get_analyzer(self):
        """Lazy-load the Presidio analyzer."""
        if self._analyzer is None:
            from presidio_analyzer import AnalyzerEngine

            self._analyzer = AnalyzerEngine()
        return self._analyzer

    def detect(self, ocr_result: OCRResult) -> DetectionResult:
        """Detect PHI entities in OCR-extracted text.

        Args:
            ocr_result: OCR result with text and word positions

        Returns:
            DetectionResult with detected PHI regions
        """
        start_time = time.perf_counter()

        analyzer = self._get_analyzer()

        # Run Presidio analysis (allow_list is handled by Presidio)
        results = analyzer.analyze(
            text=ocr_result.text,
            language=self.config.language,
            entities=self.config.entities,
            score_threshold=self.config.score_threshold,
            allow_list=self.config.allow_list,
        )

        # Convert to PHIRegion with bounding boxes
        regions = []
        for result in results:
            entity_text = ocr_result.text[result.start : result.end]

            # Find bounding box from OCR words
            bbox = self._find_bbox_for_text(
                entity_text,
                result.start,
                result.end,
                ocr_result,
            )

            region = PHIRegion(
                entity_type=result.entity_type,
                text=entity_text,
                confidence=result.score,
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
                "entities_searched": self.config.entities,
                "score_threshold": self.config.score_threshold,
                "results_count": len(regions),
            },
        )

    def _find_bbox_for_text(
        self,
        text: str,
        start_pos: int,
        end_pos: int,
        ocr_result: OCRResult,
    ) -> BoundingBox | None:
        """Find bounding box for detected text using character position mapping.

        Uses start/end character positions to find the corresponding OCR words,
        then combines their bounding boxes.

        Args:
            text: The detected PHI text
            start_pos: Start character position in full text
            end_pos: End character position in full text
            ocr_result: OCR result with word positions

        Returns:
            Bounding box encompassing the text, or None if not found
        """
        # Build character position to word index mapping
        # OCR text is space-joined words, so we track positions
        char_to_word_idx: dict[int, int] = {}
        current_pos = 0

        for idx, word in enumerate(ocr_result.words):
            word_start = current_pos
            word_end = current_pos + len(word.text)

            # Map each character position to this word index
            for pos in range(word_start, word_end):
                char_to_word_idx[pos] = idx

            # Move past word + space
            current_pos = word_end + 1  # +1 for space separator

        # Find word indices that overlap with [start_pos, end_pos)
        matching_indices: set[int] = set()
        for pos in range(start_pos, end_pos):
            if pos in char_to_word_idx:
                matching_indices.add(char_to_word_idx[pos])

        if not matching_indices:
            # Fallback: try substring matching for edge cases
            return self._find_bbox_by_substring(text, ocr_result)

        # Get the actual words
        matching_words = [ocr_result.words[i] for i in sorted(matching_indices)]

        # Calculate bounding box encompassing all matching words
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

    def _find_bbox_by_substring(
        self,
        text: str,
        ocr_result: OCRResult,
    ) -> BoundingBox | None:
        """Fallback: find bbox by looking for consecutive word sequence.

        Args:
            text: The text to find
            ocr_result: OCR result with word positions

        Returns:
            Bounding box or None
        """
        text_lower = text.lower().strip()

        # Try to find as a substring match in consecutive words
        for i, word in enumerate(ocr_result.words):
            # Check if this word starts our target text
            if text_lower.startswith(word.text.lower()):
                # Try to match consecutive words
                matched_words = [word]
                combined_text = word.text.lower()

                for j in range(i + 1, len(ocr_result.words)):
                    next_word = ocr_result.words[j]
                    combined_text += " " + next_word.text.lower()
                    matched_words.append(next_word)

                    # Check if we've matched the full text
                    if text_lower in combined_text or combined_text.startswith(text_lower):
                        # Found it - return combined bbox
                        min_x = min(w.bbox.x for w in matched_words)
                        min_y = min(w.bbox.y for w in matched_words)
                        max_x = max(w.bbox.x + w.bbox.width for w in matched_words)
                        max_y = max(w.bbox.y + w.bbox.height for w in matched_words)

                        return BoundingBox(
                            x=min_x,
                            y=min_y,
                            width=max_x - min_x,
                            height=max_y - min_y,
                        )

                    # Stop if combined is longer than target
                    if len(combined_text) > len(text_lower) + 10:
                        break

            # Also check for partial word match (e.g., "Sarah" in "Sarah's")
            elif text_lower in word.text.lower():
                return word.bbox

        return None

    def detect_in_text(self, text: str) -> list[dict]:
        """Detect PHI in plain text (without OCR context).

        Convenience method for text-only detection.

        Args:
            text: Text to analyze

        Returns:
            List of detected entities as dicts
        """
        analyzer = self._get_analyzer()

        results = analyzer.analyze(
            text=text,
            language=self.config.language,
            entities=self.config.entities,
            score_threshold=self.config.score_threshold,
            allow_list=self.config.allow_list,
        )

        entities = []
        for result in results:
            entity_text = text[result.start : result.end]

            entities.append(
                {
                    "text": entity_text,
                    "type": result.entity_type,
                    "confidence": result.score,
                    "start": result.start,
                    "end": result.end,
                }
            )

        return entities
