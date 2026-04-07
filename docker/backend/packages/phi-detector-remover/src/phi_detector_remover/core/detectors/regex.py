"""Regex-based PHI detector.

Uses custom regex patterns for detecting PHI that may not be caught
by NER models, such as study-specific IDs, device names, WiFi networks, etc.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from phi_detector_remover.core.config import RegexConfig
from phi_detector_remover.core.models import (
    BoundingBox,
    DetectionResult,
    DetectorType,
    PHIRegion,
)
from phi_detector_remover.core.patterns import DEFAULT_PATTERNS

if TYPE_CHECKING:
    from phi_detector_remover.core.models import OCRResult


class RegexDetector:
    """PHI detector using regex pattern matching.

    This detector catches PHI that NER models might miss, including:
    - Device names with personal info ("Kimberly's iPad")
    - WiFi network names ("SmithFamilyWiFi")
    - Study-specific IDs
    - Medical record numbers

    Example:
        >>> detector = RegexDetector(
        ...     config=RegexConfig(use_default_patterns=True)
        ... )
        >>> result = detector.detect(ocr_result)
    """

    def __init__(
        self,
        config: RegexConfig | None = None,
        patterns: dict[str, str] | None = None,
        use_defaults: bool = True,
        use_default_patterns: bool | None = None,  # Alias for compatibility
    ):
        """Initialize regex detector.

        Args:
            config: Regex configuration
            patterns: Custom patterns {name: regex} (convenience param)
            use_defaults: Whether to use default patterns (convenience param)
            use_default_patterns: Alias for use_defaults (for builder compatibility)
        """
        self.config = config or RegexConfig()

        if patterns is not None:
            self.config.custom_patterns = patterns

        # Handle both parameter names for compatibility
        if use_default_patterns is not None:
            use_defaults = use_default_patterns
        if not use_defaults:
            self.config.use_default_patterns = False

        # Compile patterns
        self._compiled_patterns = self._compile_patterns()

    @property
    def name(self) -> str:
        """Detector identifier."""
        return "regex"

    def is_available(self) -> bool:
        """Regex is always available."""
        return True

    def _compile_patterns(self) -> list[tuple[str, re.Pattern, float]]:
        """Compile all regex patterns.

        Returns:
            List of (name, compiled_pattern, score) tuples
        """
        patterns = []

        # Add default patterns if enabled
        if self.config.use_default_patterns:
            for name, pattern in DEFAULT_PATTERNS.items():
                patterns.append((name, pattern.pattern, pattern.score))

        # Add custom patterns
        for name, regex in self.config.custom_patterns.items():
            try:
                compiled = re.compile(regex, re.IGNORECASE)
                patterns.append((name, compiled, self.config.score))
            except re.error as e:
                # Log warning but don't fail
                print(f"Warning: Invalid regex pattern '{name}': {e}")

        return patterns

    def detect(self, ocr_result: OCRResult) -> DetectionResult:
        """Detect PHI using regex patterns.

        Args:
            ocr_result: OCR result with text and word positions

        Returns:
            DetectionResult with detected PHI regions
        """
        start_time = time.perf_counter()

        regions = []
        text = ocr_result.text

        # Check all patterns
        for name, pattern, score in self._compiled_patterns:
            for match in pattern.finditer(text):
                matched_text = match.group()

                bbox = self._find_bbox_for_match(match, ocr_result)

                region = PHIRegion(
                    entity_type=name,
                    text=matched_text,
                    confidence=score,
                    bbox=bbox,
                    source=self.name,
                )
                regions.append(region)

        # Deduplicate overlapping regions
        regions = self._deduplicate_regions(regions)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return DetectionResult(
            detector_name=self.name,
            detector_type=DetectorType.TEXT,
            regions=regions,
            processing_time_ms=elapsed_ms,
            metadata={
                "pattern_count": len(self._compiled_patterns),
                "matches_found": len(regions),
            },
        )

    def _find_bbox_for_match(
        self,
        match: re.Match,
        ocr_result: OCRResult,
    ) -> BoundingBox | None:
        """Find bounding box for a regex match.

        Args:
            match: Regex match object
            ocr_result: OCR result with word positions

        Returns:
            Bounding box or None if not found
        """
        matched_text = match.group()
        matched_words = matched_text.lower().split()

        if not matched_words:
            return None

        # Find OCR words that match
        matching_ocr_words = []
        for word in ocr_result.words:
            if word.text.lower() in matched_words:
                matching_ocr_words.append(word)

        if not matching_ocr_words:
            return None

        # Calculate encompassing bounding box
        min_x = min(w.bbox.x for w in matching_ocr_words)
        min_y = min(w.bbox.y for w in matching_ocr_words)
        max_x = max(w.bbox.x + w.bbox.width for w in matching_ocr_words)
        max_y = max(w.bbox.y + w.bbox.height for w in matching_ocr_words)

        return BoundingBox(
            x=min_x,
            y=min_y,
            width=max_x - min_x,
            height=max_y - min_y,
        )

    def _deduplicate_regions(
        self,
        regions: list[PHIRegion],
    ) -> list[PHIRegion]:
        """Remove duplicate/overlapping regions.

        Keeps the highest confidence region when there's overlap.

        Args:
            regions: List of detected regions

        Returns:
            Deduplicated list
        """
        if len(regions) <= 1:
            return regions

        # Sort by confidence descending
        sorted_regions = sorted(regions, key=lambda r: r.confidence, reverse=True)

        kept = []
        for region in sorted_regions:
            # Check if this region overlaps with any kept region
            is_duplicate = False
            for kept_region in kept:
                if self._regions_overlap(region, kept_region):
                    is_duplicate = True
                    break

            if not is_duplicate:
                kept.append(region)

        return kept

    def _regions_overlap(
        self,
        r1: PHIRegion,
        r2: PHIRegion,
    ) -> bool:
        """Check if two regions overlap significantly.

        Args:
            r1: First region
            r2: Second region

        Returns:
            True if regions overlap
        """
        # Text overlap check
        if r1.text.lower() in r2.text.lower() or r2.text.lower() in r1.text.lower():
            return True

        # Bounding box overlap check
        if r1.bbox and r2.bbox:
            iou = r1.bbox.iou(r2.bbox)
            if iou > 0.5:
                return True

        return False
