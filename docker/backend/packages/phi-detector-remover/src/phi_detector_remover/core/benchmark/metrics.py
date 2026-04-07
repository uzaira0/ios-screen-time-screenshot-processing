"""Metrics calculation for PHI detection benchmarking.

Provides standard evaluation metrics:
- Precision, Recall, F1 Score
- Per-entity type breakdown
- Bounding box IoU-based matching
"""

from __future__ import annotations

from phi_detector_remover.core.models import (
    AggregatedPHIRegion,
    BenchmarkMetrics,
    BoundingBox,
    GroundTruthAnnotation,
)


def calculate_metrics(
    predictions: list[AggregatedPHIRegion],
    ground_truth: list[GroundTruthAnnotation],
    iou_threshold: float = 0.5,
    text_match: bool = True,
) -> BenchmarkMetrics:
    """Calculate precision, recall, and F1 score.

    Matching logic:
    1. If both have bounding boxes, use IoU threshold
    2. If text_match=True, also match by text content
    3. Entity types must match

    Args:
        predictions: Detected PHI regions
        ground_truth: Ground truth annotations
        iou_threshold: IoU threshold for bbox matching
        text_match: Also consider text content matching

    Returns:
        Calculated benchmark metrics
    """
    if not ground_truth:
        # No ground truth - all predictions are false positives
        return BenchmarkMetrics(
            precision=0.0 if predictions else 1.0,
            recall=1.0,  # Vacuously true
            f1_score=0.0 if predictions else 1.0,
            true_positives=0,
            false_positives=len(predictions),
            false_negatives=0,
            avg_processing_time_ms=0.0,
            iou_threshold=iou_threshold,
        )

    if not predictions:
        # No predictions - all ground truth are false negatives
        return BenchmarkMetrics(
            precision=1.0,  # Vacuously true
            recall=0.0,
            f1_score=0.0,
            true_positives=0,
            false_positives=0,
            false_negatives=len(ground_truth),
            avg_processing_time_ms=0.0,
            iou_threshold=iou_threshold,
        )

    # Match predictions to ground truth
    matched_gt = set()
    matched_pred = set()

    for i, pred in enumerate(predictions):
        for j, gt in enumerate(ground_truth):
            if j in matched_gt:
                continue

            if _regions_match(pred, gt, iou_threshold, text_match):
                matched_gt.add(j)
                matched_pred.add(i)
                break

    true_positives = len(matched_pred)
    false_positives = len(predictions) - true_positives
    false_negatives = len(ground_truth) - len(matched_gt)

    precision = (
        true_positives / (true_positives + false_positives)
        if (true_positives + false_positives) > 0
        else 0.0
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if (true_positives + false_negatives) > 0
        else 0.0
    )
    f1_score = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return BenchmarkMetrics(
        precision=precision,
        recall=recall,
        f1_score=f1_score,
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        avg_processing_time_ms=0.0,  # Set by caller
        iou_threshold=iou_threshold,
    )


def calculate_per_entity_metrics(
    predictions: list[AggregatedPHIRegion],
    ground_truth: list[GroundTruthAnnotation],
    iou_threshold: float = 0.5,
    text_match: bool = True,
) -> dict[str, BenchmarkMetrics]:
    """Calculate metrics broken down by entity type.

    Args:
        predictions: Detected PHI regions
        ground_truth: Ground truth annotations
        iou_threshold: IoU threshold for bbox matching
        text_match: Also consider text content matching

    Returns:
        Dict mapping entity type to metrics
    """
    # Get all entity types
    entity_types = set()
    for pred in predictions:
        entity_types.add(pred.entity_type)
    for gt in ground_truth:
        entity_types.add(gt.entity_type)

    # Calculate metrics for each entity type
    per_entity = {}
    for entity_type in entity_types:
        entity_preds = [p for p in predictions if p.entity_type == entity_type]
        entity_gt = [g for g in ground_truth if g.entity_type == entity_type]

        metrics = calculate_metrics(
            entity_preds,
            entity_gt,
            iou_threshold=iou_threshold,
            text_match=text_match,
        )
        per_entity[entity_type] = metrics

    return per_entity


def _regions_match(
    pred: AggregatedPHIRegion,
    gt: GroundTruthAnnotation,
    iou_threshold: float,
    text_match: bool,
) -> bool:
    """Check if prediction matches ground truth.

    Args:
        pred: Predicted region
        gt: Ground truth annotation
        iou_threshold: IoU threshold for bbox matching
        text_match: Also consider text content matching

    Returns:
        True if regions match
    """
    # Entity type must match (or be compatible)
    if not _entity_types_compatible(pred.entity_type, gt.entity_type):
        return False

    # Try bounding box match
    if pred.bbox and gt.bbox:
        iou = pred.bbox.iou(gt.bbox)
        if iou >= iou_threshold:
            return True

    # Try text match
    if text_match:
        pred_text = pred.text.lower().strip()
        gt_text = gt.text.lower().strip()

        # Exact match
        if pred_text == gt_text:
            return True

        # Substring match (for partial detections)
        if len(pred_text) >= 3 and len(gt_text) >= 3:
            if pred_text in gt_text or gt_text in pred_text:
                return True

    return False


def _entity_types_compatible(pred_type: str, gt_type: str) -> bool:
    """Check if entity types are compatible.

    Handles cases where detectors may use different names
    for the same entity type.

    Args:
        pred_type: Predicted entity type
        gt_type: Ground truth entity type

    Returns:
        True if types are compatible
    """
    # Exact match
    if pred_type.upper() == gt_type.upper():
        return True

    # Handle merged types (e.g., "PERSON+EMAIL")
    if "+" in pred_type:
        pred_parts = pred_type.upper().split("+")
        if gt_type.upper() in pred_parts:
            return True

    # Common aliases
    aliases = {
        "PERSON": ["NAME", "PERSON_NAME", "FULL_NAME"],
        "EMAIL": ["EMAIL_ADDRESS", "E_MAIL"],
        "PHONE": ["PHONE_NUMBER", "TELEPHONE"],
        "SSN": ["US_SSN", "SOCIAL_SECURITY"],
        "DATE": ["DATE_TIME", "DOB", "DATE_OF_BIRTH"],
        "ADDRESS": ["LOCATION", "STREET_ADDRESS"],
        "DEVICE_NAME": ["DEVICE", "DEVICE_ID"],
        "WIFI_NAME": ["WIFI", "NETWORK_NAME"],
    }

    pred_upper = pred_type.upper()
    gt_upper = gt_type.upper()

    for canonical, alias_list in aliases.items():
        all_names = [canonical] + alias_list
        if pred_upper in all_names and gt_upper in all_names:
            return True

    return False


def calculate_iou(box1: BoundingBox, box2: BoundingBox) -> float:
    """Calculate Intersection over Union for two bounding boxes.

    Args:
        box1: First bounding box
        box2: Second bounding box

    Returns:
        IoU value (0.0 to 1.0)
    """
    return box1.iou(box2)


def summarize_metrics(metrics: BenchmarkMetrics) -> str:
    """Create a human-readable summary of metrics.

    Args:
        metrics: Benchmark metrics

    Returns:
        Formatted summary string
    """
    return (
        f"Precision: {metrics.precision:.3f} | "
        f"Recall: {metrics.recall:.3f} | "
        f"F1: {metrics.f1_score:.3f} | "
        f"TP: {metrics.true_positives} | "
        f"FP: {metrics.false_positives} | "
        f"FN: {metrics.false_negatives}"
    )
