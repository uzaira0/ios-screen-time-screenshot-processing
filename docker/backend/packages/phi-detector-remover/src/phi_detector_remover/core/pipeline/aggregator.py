"""Aggregation strategies for combining results from multiple detectors.

Different strategies provide different trade-offs between precision and recall:
- Union: Maximum recall (catches everything, may have false positives)
- Intersection: Maximum precision (only consensus, may miss PHI)
- Weighted Vote: Balanced approach with configurable detector weights
- Threshold: Include if aggregate confidence exceeds threshold
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from phi_detector_remover.core.models import (
    AggregatedPHIRegion,
    BoundingBox,
    DetectionResult,
    PHIRegion,
)


class AggregationStrategy(ABC):
    """Base class for aggregation strategies."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy identifier."""
        ...

    @abstractmethod
    def aggregate(
        self,
        results: dict[str, DetectionResult],
    ) -> list[AggregatedPHIRegion]:
        """Aggregate results from multiple detectors.

        Args:
            results: Dict mapping detector name to its DetectionResult

        Returns:
            List of aggregated PHI regions
        """
        ...


class UnionAggregator(AggregationStrategy):
    """Union aggregation - include all detected regions.

    High recall strategy: any region detected by any detector is included.
    Good for HIPAA compliance where missing PHI is worse than false positives.

    Overlapping regions from different detectors are merged.
    """

    def __init__(self, iou_threshold: float = 0.5):
        """Initialize union aggregator.

        Args:
            iou_threshold: IoU threshold for merging overlapping regions
        """
        self.iou_threshold = iou_threshold

    @property
    def name(self) -> str:
        return "union"

    def aggregate(
        self,
        results: dict[str, DetectionResult],
    ) -> list[AggregatedPHIRegion]:
        """Aggregate by taking union of all detections."""
        all_regions: list[tuple[str, PHIRegion]] = []

        for detector_name, result in results.items():
            for region in result.regions:
                all_regions.append((detector_name, region))

        if not all_regions:
            return []

        # Merge overlapping regions
        aggregated = []
        used = set()

        for i, (det1, reg1) in enumerate(all_regions):
            if i in used:
                continue

            # Find all overlapping regions
            overlapping = [(det1, reg1)]
            used.add(i)

            for j, (det2, reg2) in enumerate(all_regions):
                if j in used:
                    continue
                if self._regions_overlap(reg1, reg2):
                    overlapping.append((det2, reg2))
                    used.add(j)

            # Merge overlapping regions
            merged = self._merge_regions(overlapping)
            aggregated.append(merged)

        return aggregated

    def _regions_overlap(self, r1: PHIRegion, r2: PHIRegion) -> bool:
        """Check if two regions overlap."""
        # Text overlap
        if r1.text.lower() == r2.text.lower():
            return True
        if r1.text.lower() in r2.text.lower() or r2.text.lower() in r1.text.lower():
            return True

        # Bounding box overlap
        if r1.bbox and r2.bbox:
            if r1.bbox.iou(r2.bbox) >= self.iou_threshold:
                return True

        return False

    def _merge_regions(
        self,
        regions: list[tuple[str, PHIRegion]],
    ) -> AggregatedPHIRegion:
        """Merge overlapping regions into one."""
        sources = [det for det, _ in regions]
        confidences = {det: reg.confidence for det, reg in regions}

        # Use highest confidence region's details
        best_det, best_reg = max(regions, key=lambda x: x[1].confidence)

        # Merge bounding boxes
        bboxes = [reg.bbox for _, reg in regions if reg.bbox]
        merged_bbox = self._merge_bboxes(bboxes) if bboxes else None

        return AggregatedPHIRegion(
            entity_type=best_reg.entity_type,
            text=best_reg.text,
            confidence=max(confidences.values()),
            bbox=merged_bbox,
            sources=list(set(sources)),
            source_confidences=confidences,
            aggregation_method=self.name,
        )

    def _merge_bboxes(self, bboxes: list[BoundingBox]) -> BoundingBox:
        """Merge multiple bounding boxes into encompassing box."""
        min_x = min(b.x for b in bboxes)
        min_y = min(b.y for b in bboxes)
        max_x = max(b.x + b.width for b in bboxes)
        max_y = max(b.y + b.height for b in bboxes)

        return BoundingBox(
            x=min_x,
            y=min_y,
            width=max_x - min_x,
            height=max_y - min_y,
        )


class IntersectionAggregator(AggregationStrategy):
    """Intersection aggregation - only include regions detected by all detectors.

    High precision strategy: only consensus regions are included.
    Good when false positives are costly (e.g., redacting too much).

    Requires at least `min_detectors` to agree on a region.
    """

    def __init__(
        self,
        min_detectors: int = 2,
        iou_threshold: float = 0.5,
    ):
        """Initialize intersection aggregator.

        Args:
            min_detectors: Minimum detectors that must agree
            iou_threshold: IoU threshold for matching regions
        """
        self.min_detectors = min_detectors
        self.iou_threshold = iou_threshold

    @property
    def name(self) -> str:
        return "intersection"

    def aggregate(
        self,
        results: dict[str, DetectionResult],
    ) -> list[AggregatedPHIRegion]:
        """Aggregate by taking intersection of detections."""
        if len(results) < self.min_detectors:
            # Not enough detectors to meet threshold
            return []

        # Collect all regions by detector
        detector_regions: dict[str, list[PHIRegion]] = {
            name: result.regions for name, result in results.items()
        }

        # Find regions that appear in multiple detectors
        aggregated = []
        processed_texts = set()

        for det1, regions1 in detector_regions.items():
            for reg1 in regions1:
                if reg1.text.lower() in processed_texts:
                    continue

                # Find matching regions in other detectors
                matches = [(det1, reg1)]

                for det2, regions2 in detector_regions.items():
                    if det2 == det1:
                        continue
                    for reg2 in regions2:
                        if self._regions_match(reg1, reg2):
                            matches.append((det2, reg2))
                            break

                # Check if enough detectors agree
                if len(matches) >= self.min_detectors:
                    merged = self._merge_matches(matches)
                    aggregated.append(merged)
                    processed_texts.add(reg1.text.lower())

        return aggregated

    def _regions_match(self, r1: PHIRegion, r2: PHIRegion) -> bool:
        """Check if two regions match (same PHI)."""
        # Text match (fuzzy)
        if r1.text.lower() == r2.text.lower():
            return True

        # Partial text match
        t1, t2 = r1.text.lower(), r2.text.lower()
        if len(t1) > 3 and len(t2) > 3:
            if t1 in t2 or t2 in t1:
                return True

        # Bounding box match
        if r1.bbox and r2.bbox:
            if r1.bbox.iou(r2.bbox) >= self.iou_threshold:
                return True

        return False

    def _merge_matches(
        self,
        matches: list[tuple[str, PHIRegion]],
    ) -> AggregatedPHIRegion:
        """Merge matching regions from different detectors."""
        sources = [det for det, _ in matches]
        confidences = {det: reg.confidence for det, reg in matches}

        # Average confidence
        avg_confidence = sum(confidences.values()) / len(confidences)

        # Use most common entity type
        entity_types = [reg.entity_type for _, reg in matches]
        entity_type = max(set(entity_types), key=entity_types.count)

        # Best text (longest, as it may be most complete)
        best_text = max((reg.text for _, reg in matches), key=len)

        # Merge bboxes
        bboxes = [reg.bbox for _, reg in matches if reg.bbox]
        merged_bbox = None
        if bboxes:
            min_x = min(b.x for b in bboxes)
            min_y = min(b.y for b in bboxes)
            max_x = max(b.x + b.width for b in bboxes)
            max_y = max(b.y + b.height for b in bboxes)
            merged_bbox = BoundingBox(x=min_x, y=min_y, width=max_x - min_x, height=max_y - min_y)

        return AggregatedPHIRegion(
            entity_type=entity_type,
            text=best_text,
            confidence=avg_confidence,
            bbox=merged_bbox,
            sources=sources,
            source_confidences=confidences,
            aggregation_method=self.name,
        )


class WeightedVoteAggregator(AggregationStrategy):
    """Weighted voting aggregation.

    Each detector has a weight, and regions are scored by
    weighted sum of detector confidences.

    Useful when some detectors are more reliable than others.
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        default_weight: float = 1.0,
        threshold: float = 0.5,
        iou_threshold: float = 0.5,
    ):
        """Initialize weighted vote aggregator.

        Args:
            weights: Dict mapping detector name to weight
            default_weight: Weight for detectors not in weights dict
            threshold: Minimum weighted score to include region
            iou_threshold: IoU threshold for matching regions
        """
        self.weights = weights or {}
        self.default_weight = default_weight
        self.threshold = threshold
        self.iou_threshold = iou_threshold

    @property
    def name(self) -> str:
        return "weighted_vote"

    def aggregate(
        self,
        results: dict[str, DetectionResult],
    ) -> list[AggregatedPHIRegion]:
        """Aggregate using weighted voting."""
        # Normalize weights
        total_weight = sum(self.weights.get(det, self.default_weight) for det in results.keys())

        if total_weight == 0:
            return []

        # Collect all regions with their weighted scores
        all_regions: list[tuple[str, PHIRegion, float]] = []

        for det_name, result in results.items():
            weight = self.weights.get(det_name, self.default_weight)
            normalized_weight = weight / total_weight

            for region in result.regions:
                weighted_score = region.confidence * normalized_weight
                all_regions.append((det_name, region, weighted_score))

        if not all_regions:
            return []

        # Group overlapping regions and calculate combined scores
        aggregated = []
        used = set()

        for i, (det1, reg1, score1) in enumerate(all_regions):
            if i in used:
                continue

            # Find overlapping regions
            group = [(det1, reg1, score1)]
            used.add(i)

            for j, (det2, reg2, score2) in enumerate(all_regions):
                if j in used:
                    continue
                if self._regions_overlap(reg1, reg2):
                    group.append((det2, reg2, score2))
                    used.add(j)

            # Calculate combined weighted score
            combined_score = sum(s for _, _, s in group)

            if combined_score >= self.threshold:
                merged = self._merge_group(group, combined_score)
                aggregated.append(merged)

        return aggregated

    def _regions_overlap(self, r1: PHIRegion, r2: PHIRegion) -> bool:
        """Check if regions overlap."""
        if r1.text.lower() == r2.text.lower():
            return True
        if r1.bbox and r2.bbox and r1.bbox.iou(r2.bbox) >= self.iou_threshold:
            return True
        return False

    def _merge_group(
        self,
        group: list[tuple[str, PHIRegion, float]],
        combined_score: float,
    ) -> AggregatedPHIRegion:
        """Merge a group of overlapping regions."""
        sources = [det for det, _, _ in group]
        confidences = {det: reg.confidence for det, reg, _ in group}

        # Use highest individual confidence region's details
        best_det, best_reg, _ = max(group, key=lambda x: x[1].confidence)

        # Merge bboxes
        bboxes = [reg.bbox for _, reg, _ in group if reg.bbox]
        merged_bbox = None
        if bboxes:
            min_x = min(b.x for b in bboxes)
            min_y = min(b.y for b in bboxes)
            max_x = max(b.x + b.width for b in bboxes)
            max_y = max(b.y + b.height for b in bboxes)
            merged_bbox = BoundingBox(x=min_x, y=min_y, width=max_x - min_x, height=max_y - min_y)

        return AggregatedPHIRegion(
            entity_type=best_reg.entity_type,
            text=best_reg.text,
            confidence=min(combined_score, 1.0),  # Cap at 1.0
            bbox=merged_bbox,
            sources=list(set(sources)),
            source_confidences=confidences,
            aggregation_method=self.name,
        )


class ThresholdAggregator(AggregationStrategy):
    """Threshold-based aggregation.

    Include regions where the maximum confidence across
    all detectors exceeds a threshold.

    Simple strategy that works well when detector confidences are calibrated.
    """

    def __init__(
        self,
        confidence_threshold: float = 0.7,
        iou_threshold: float = 0.5,
    ):
        """Initialize threshold aggregator.

        Args:
            confidence_threshold: Minimum confidence to include
            iou_threshold: IoU threshold for merging regions
        """
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold

    @property
    def name(self) -> str:
        return "threshold"

    def aggregate(
        self,
        results: dict[str, DetectionResult],
    ) -> list[AggregatedPHIRegion]:
        """Aggregate by filtering to high-confidence regions."""
        # Collect all regions above threshold
        high_conf_regions: list[tuple[str, PHIRegion]] = []

        for det_name, result in results.items():
            for region in result.regions:
                if region.confidence >= self.confidence_threshold:
                    high_conf_regions.append((det_name, region))

        if not high_conf_regions:
            return []

        # Merge overlapping high-confidence regions
        aggregated = []
        used = set()

        for i, (det1, reg1) in enumerate(high_conf_regions):
            if i in used:
                continue

            group = [(det1, reg1)]
            used.add(i)

            for j, (det2, reg2) in enumerate(high_conf_regions):
                if j in used:
                    continue
                if self._regions_overlap(reg1, reg2):
                    group.append((det2, reg2))
                    used.add(j)

            merged = self._merge_group(group)
            aggregated.append(merged)

        return aggregated

    def _regions_overlap(self, r1: PHIRegion, r2: PHIRegion) -> bool:
        """Check if regions overlap."""
        if r1.text.lower() == r2.text.lower():
            return True
        if r1.bbox and r2.bbox and r1.bbox.iou(r2.bbox) >= self.iou_threshold:
            return True
        return False

    def _merge_group(
        self,
        group: list[tuple[str, PHIRegion]],
    ) -> AggregatedPHIRegion:
        """Merge a group of regions."""
        sources = [det for det, _ in group]
        confidences = {det: reg.confidence for det, reg in group}

        best_det, best_reg = max(group, key=lambda x: x[1].confidence)

        bboxes = [reg.bbox for _, reg in group if reg.bbox]
        merged_bbox = None
        if bboxes:
            min_x = min(b.x for b in bboxes)
            min_y = min(b.y for b in bboxes)
            max_x = max(b.x + b.width for b in bboxes)
            max_y = max(b.y + b.height for b in bboxes)
            merged_bbox = BoundingBox(x=min_x, y=min_y, width=max_x - min_x, height=max_y - min_y)

        return AggregatedPHIRegion(
            entity_type=best_reg.entity_type,
            text=best_reg.text,
            confidence=max(confidences.values()),
            bbox=merged_bbox,
            sources=list(set(sources)),
            source_confidences=confidences,
            aggregation_method=self.name,
        )


# ============================================================================
# Factory Function
# ============================================================================


def get_aggregator(
    strategy: str,
    **kwargs: Any,
) -> AggregationStrategy:
    """Get an aggregation strategy by name.

    Args:
        strategy: Strategy name ("union", "intersection", "weighted", "threshold")
        **kwargs: Strategy-specific configuration

    Returns:
        Configured aggregation strategy

    Raises:
        ValueError: If strategy name is unknown
    """
    strategies = {
        "union": UnionAggregator,
        "intersection": IntersectionAggregator,
        "weighted": WeightedVoteAggregator,
        "weighted_vote": WeightedVoteAggregator,
        "threshold": ThresholdAggregator,
    }

    if strategy.lower() not in strategies:
        available = ", ".join(strategies.keys())
        raise ValueError(f"Unknown aggregation strategy: {strategy}. Available: {available}")

    return strategies[strategy.lower()](**kwargs)
