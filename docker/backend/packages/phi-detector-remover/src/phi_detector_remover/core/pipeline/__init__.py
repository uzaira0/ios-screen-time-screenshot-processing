"""Pipeline orchestration for PHI detection.

This module provides:
- PHIPipelineBuilder: Fluent API for building detection pipelines
- PHIPipeline: Executes configured detection pipeline
- Aggregation strategies for combining detector results

Usage:
    >>> from phi_detector_remover.core.pipeline import PHIPipelineBuilder
    >>>
    >>> pipeline = (
    ...     PHIPipelineBuilder()
    ...     .with_ocr("tesseract")
    ...     .add_text_detector("presidio", entities=["PERSON", "EMAIL"])
    ...     .add_text_detector("regex")
    ...     .add_vision_detector("gemma", model="gemma-2-2b")
    ...     .with_aggregation("union")
    ...     .parallel()
    ...     .build()
    ... )
    >>>
    >>> result = pipeline.process(image_bytes)
"""

from phi_detector_remover.core.pipeline.aggregator import (
    AggregationStrategy,
    IntersectionAggregator,
    ThresholdAggregator,
    UnionAggregator,
    WeightedVoteAggregator,
    get_aggregator,
)
from phi_detector_remover.core.pipeline.builder import PHIPipelineBuilder
from phi_detector_remover.core.pipeline.executor import PHIPipeline

__all__ = [
    "PHIPipelineBuilder",
    "PHIPipeline",
    "AggregationStrategy",
    "UnionAggregator",
    "IntersectionAggregator",
    "WeightedVoteAggregator",
    "ThresholdAggregator",
    "get_aggregator",
]
