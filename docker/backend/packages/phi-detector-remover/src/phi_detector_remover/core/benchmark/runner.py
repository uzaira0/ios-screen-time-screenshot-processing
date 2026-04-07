"""Benchmark runner for evaluating PHI detection pipelines.

Provides:
- Single pipeline evaluation
- Multi-pipeline comparison
- Pareto-optimal pipeline identification
- Recommendations for pipeline selection
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from phi_detector_remover.core.benchmark.dataset import AnnotatedDataset
from phi_detector_remover.core.benchmark.metrics import (
    calculate_metrics,
    calculate_per_entity_metrics,
    summarize_metrics,
)
from phi_detector_remover.core.models import (
    BenchmarkComparison,
    BenchmarkMetrics,
    BenchmarkResult,
)

if TYPE_CHECKING:
    from phi_detector_remover.core.pipeline import PHIPipeline


class BenchmarkRunner:
    """Runner for evaluating PHI detection pipelines.

    Evaluates pipelines against ground truth datasets to measure
    precision, recall, and F1 score.

    Example:
        >>> dataset = AnnotatedDataset.from_directory("./benchmark/")
        >>> runner = BenchmarkRunner(dataset)
        >>>
        >>> result = runner.evaluate(pipeline, name="my_pipeline")
        >>> print(f"F1 Score: {result.metrics.f1_score:.3f}")
    """

    def __init__(
        self,
        dataset: AnnotatedDataset,
        iou_threshold: float = 0.5,
        text_match: bool = True,
    ):
        """Initialize benchmark runner.

        Args:
            dataset: Annotated dataset with ground truth
            iou_threshold: IoU threshold for bbox matching
            text_match: Also consider text content matching
        """
        self.dataset = dataset
        self.iou_threshold = iou_threshold
        self.text_match = text_match

    def evaluate(
        self,
        pipeline: PHIPipeline,
        name: str = "pipeline",
        save_predictions: bool = False,
        predictions_dir: str | Path | None = None,
    ) -> BenchmarkResult:
        """Evaluate a pipeline against the dataset.

        Args:
            pipeline: Pipeline to evaluate
            name: Name for this pipeline configuration
            save_predictions: Save predictions to files
            predictions_dir: Directory for predictions

        Returns:
            Benchmark result with metrics
        """
        all_predictions = []
        all_ground_truth = []
        per_sample_results = []
        total_time_ms = 0.0

        for sample in self.dataset:
            # Read image
            image_bytes = Path(sample.image_path).read_bytes()

            # Run pipeline
            start_time = time.perf_counter()
            result = pipeline.process(image_bytes)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            total_time_ms += elapsed_ms

            # Collect predictions and ground truth
            predictions = result.aggregated_regions
            ground_truth = sample.annotations

            all_predictions.extend(predictions)
            all_ground_truth.extend(ground_truth)

            # Calculate per-sample metrics
            sample_metrics = calculate_metrics(
                predictions,
                ground_truth,
                iou_threshold=self.iou_threshold,
                text_match=self.text_match,
            )

            per_sample_results.append(
                {
                    "image_id": sample.image_id,
                    "image_path": sample.image_path,
                    "predictions": [p.to_dict() for p in predictions],
                    "ground_truth": [g.to_dict() for g in ground_truth],
                    "metrics": sample_metrics.to_dict(),
                    "processing_time_ms": elapsed_ms,
                }
            )

            # Save predictions if requested
            if save_predictions and predictions_dir:
                self._save_predictions(
                    sample.image_id,
                    predictions,
                    predictions_dir,
                )

        # Calculate overall metrics
        overall_metrics = calculate_metrics(
            all_predictions,
            all_ground_truth,
            iou_threshold=self.iou_threshold,
            text_match=self.text_match,
        )
        # Update average processing time
        avg_time = total_time_ms / len(self.dataset) if self.dataset else 0.0
        overall_metrics = BenchmarkMetrics(
            precision=overall_metrics.precision,
            recall=overall_metrics.recall,
            f1_score=overall_metrics.f1_score,
            true_positives=overall_metrics.true_positives,
            false_positives=overall_metrics.false_positives,
            false_negatives=overall_metrics.false_negatives,
            avg_processing_time_ms=avg_time,
            iou_threshold=self.iou_threshold,
        )

        # Calculate per-entity metrics
        per_entity_metrics = calculate_per_entity_metrics(
            all_predictions,
            all_ground_truth,
            iou_threshold=self.iou_threshold,
            text_match=self.text_match,
        )

        return BenchmarkResult(
            pipeline_name=name,
            pipeline_config=pipeline._get_config_summary(),
            metrics=overall_metrics,
            per_entity_metrics=per_entity_metrics,
            per_sample_results=per_sample_results,
        )

    def _save_predictions(
        self,
        image_id: str,
        predictions: list,
        output_dir: str | Path,
    ) -> None:
        """Save predictions to JSON file."""
        import json

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / f"{image_id}_predictions.json"
        with open(output_path, "w") as f:
            json.dump(
                [p.to_dict() for p in predictions],
                f,
                indent=2,
            )


def compare_pipelines(
    dataset: AnnotatedDataset,
    pipelines: dict[str, PHIPipeline],
    iou_threshold: float = 0.5,
    text_match: bool = True,
) -> BenchmarkComparison:
    """Compare multiple pipeline configurations.

    Evaluates each pipeline and provides:
    - Comparative metrics
    - Pareto-optimal pipelines (best accuracy/speed trade-off)
    - Recommendations

    Args:
        dataset: Annotated dataset
        pipelines: Dict mapping name to pipeline
        iou_threshold: IoU threshold for matching
        text_match: Also consider text matching

    Returns:
        Comparison results with recommendations

    Example:
        >>> comparison = compare_pipelines(
        ...     dataset=dataset,
        ...     pipelines={
        ...         "fast": PHIPipelineBuilder.fast().build(),
        ...         "balanced": PHIPipelineBuilder.balanced().build(),
        ...         "thorough": PHIPipelineBuilder.thorough().build(),
        ...     }
        ... )
        >>> print(comparison.recommendations)
    """
    runner = BenchmarkRunner(
        dataset=dataset,
        iou_threshold=iou_threshold,
        text_match=text_match,
    )

    results = []
    for name, pipeline in pipelines.items():
        result = runner.evaluate(pipeline, name=name)
        results.append(result)

    # Generate recommendations
    recommendations = _generate_recommendations(results)

    # Identify baseline (highest F1)
    baseline = max(results, key=lambda r: r.metrics.f1_score)

    return BenchmarkComparison(
        results=results,
        baseline_name=baseline.pipeline_name,
        recommendations=recommendations,
    )


def _generate_recommendations(results: list[BenchmarkResult]) -> list[str]:
    """Generate recommendations based on benchmark results.

    Identifies:
    - Best overall pipeline
    - Fastest pipeline with acceptable accuracy
    - Pipelines that may be redundant

    Args:
        results: Benchmark results to analyze

    Returns:
        List of recommendation strings
    """
    if not results:
        return ["No pipelines to compare."]

    recommendations = []

    # Sort by F1 score
    by_f1 = sorted(results, key=lambda r: r.metrics.f1_score, reverse=True)
    best_f1 = by_f1[0]

    # Sort by speed
    by_speed = sorted(results, key=lambda r: r.metrics.avg_processing_time_ms)
    fastest = by_speed[0]

    recommendations.append(
        f"Best accuracy: '{best_f1.pipeline_name}' with F1={best_f1.metrics.f1_score:.3f}"
    )

    recommendations.append(
        f"Fastest: '{fastest.pipeline_name}' at {fastest.metrics.avg_processing_time_ms:.1f}ms/image"
    )

    # Find fastest with acceptable accuracy (>= 90% of best F1)
    threshold_f1 = best_f1.metrics.f1_score * 0.90
    acceptable = [r for r in by_speed if r.metrics.f1_score >= threshold_f1]

    if acceptable and acceptable[0].pipeline_name != best_f1.pipeline_name:
        rec = acceptable[0]
        speedup = best_f1.metrics.avg_processing_time_ms / rec.metrics.avg_processing_time_ms
        recommendations.append(
            f"Recommended: '{rec.pipeline_name}' - "
            f"{speedup:.1f}x faster with only {(1 - rec.metrics.f1_score / best_f1.metrics.f1_score) * 100:.1f}% accuracy loss"
        )

    # Identify potentially redundant pipelines
    # (slower but same or worse accuracy)
    for r in results:
        for other in results:
            if r.pipeline_name == other.pipeline_name:
                continue
            if (
                r.metrics.f1_score <= other.metrics.f1_score
                and r.metrics.avg_processing_time_ms > other.metrics.avg_processing_time_ms * 1.2
            ):
                recommendations.append(
                    f"Consider removing '{r.pipeline_name}': "
                    f"'{other.pipeline_name}' is faster with equal/better accuracy"
                )
                break

    # Check for recall vs precision trade-offs
    high_recall = max(results, key=lambda r: r.metrics.recall)
    high_precision = max(results, key=lambda r: r.metrics.precision)

    if high_recall.pipeline_name != high_precision.pipeline_name:
        recommendations.append(
            f"For HIPAA compliance (max recall): '{high_recall.pipeline_name}' "
            f"(recall={high_recall.metrics.recall:.3f})"
        )
        recommendations.append(
            f"For minimal false positives: '{high_precision.pipeline_name}' "
            f"(precision={high_precision.metrics.precision:.3f})"
        )

    return recommendations


def print_comparison_report(comparison: BenchmarkComparison) -> None:
    """Print a formatted comparison report.

    Args:
        comparison: Benchmark comparison results
    """
    print("\n" + "=" * 70)
    print("PHI Detection Pipeline Benchmark Report")
    print("=" * 70)

    print("\n## Results by Pipeline\n")
    print(f"{'Pipeline':<20} {'Precision':>10} {'Recall':>10} {'F1':>10} {'Time (ms)':>12}")
    print("-" * 62)

    for result in sorted(comparison.results, key=lambda r: r.metrics.f1_score, reverse=True):
        m = result.metrics
        print(
            f"{result.pipeline_name:<20} "
            f"{m.precision:>10.3f} "
            f"{m.recall:>10.3f} "
            f"{m.f1_score:>10.3f} "
            f"{m.avg_processing_time_ms:>12.1f}"
        )

    print("\n## Recommendations\n")
    for i, rec in enumerate(comparison.recommendations, 1):
        print(f"{i}. {rec}")

    print("\n## Pareto-Optimal Pipelines\n")
    pareto = comparison.get_pareto_optimal()
    print(f"Best trade-off between accuracy and speed: {', '.join(pareto)}")

    print("\n" + "=" * 70)
