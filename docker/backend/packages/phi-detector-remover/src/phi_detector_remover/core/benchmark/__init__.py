"""Benchmarking infrastructure for PHI detection pipelines.

This module provides:
- Benchmark datasets with ground truth annotations
- Pipeline evaluation against ground truth
- Comparison of multiple pipeline configurations
- Recommendations for optimal pipeline selection

Usage:
    >>> from phi_detector_remover.core.benchmark import (
    ...     BenchmarkRunner,
    ...     AnnotatedDataset,
    ...     compare_pipelines,
    ... )
    >>>
    >>> dataset = AnnotatedDataset.from_directory("./benchmark_data/")
    >>> runner = BenchmarkRunner(dataset)
    >>>
    >>> # Evaluate a single pipeline
    >>> result = runner.evaluate(pipeline)
    >>> print(f"F1 Score: {result.metrics.f1_score:.3f}")
    >>>
    >>> # Compare multiple pipelines
    >>> comparison = compare_pipelines(
    ...     dataset=dataset,
    ...     pipelines={"fast": fast_pipeline, "thorough": thorough_pipeline}
    ... )
    >>> print(comparison.recommendations)
"""

from phi_detector_remover.core.benchmark.dataset import (
    AnnotatedDataset,
    create_annotation,
    load_annotations,
)
from phi_detector_remover.core.benchmark.metrics import (
    calculate_metrics,
    calculate_per_entity_metrics,
)
from phi_detector_remover.core.benchmark.runner import (
    BenchmarkRunner,
    compare_pipelines,
)

__all__ = [
    "AnnotatedDataset",
    "BenchmarkRunner",
    "calculate_metrics",
    "calculate_per_entity_metrics",
    "compare_pipelines",
    "create_annotation",
    "load_annotations",
]
