"""PHI (Protected Health Information) detection and removal for images.

This package provides modular PHI detection using multiple strategies:
- OCR engines (Tesseract, Hunyuan LVM)
- Text detectors (Presidio NER, regex patterns, local LLMs)
- Vision detectors (Gemma, Hunyuan - analyze images directly)
- Configurable aggregation strategies
- Batch processing for pipeline integration

Quick Start:
    >>> from phi_detector_remover import PHIPipelineBuilder, process_image
    >>>
    >>> # Simple usage
    >>> clean_image, regions = process_image(image_bytes)
    >>>
    >>> # Custom pipeline
    >>> pipeline = (
    ...     PHIPipelineBuilder()
    ...     .with_ocr("tesseract")
    ...     .add_presidio(entities=["PERSON", "EMAIL"])
    ...     .add_regex()
    ...     .union_aggregation()
    ...     .build()
    ... )
    >>> result = pipeline.process(image_bytes)

Pipeline Presets:
    >>> # Fast: Tesseract + Presidio only
    >>> pipeline = PHIPipelineBuilder.fast().build()
    >>>
    >>> # Balanced: Tesseract + Presidio + Regex
    >>> pipeline = PHIPipelineBuilder.balanced().build()
    >>>
    >>> # HIPAA-focused: Lower thresholds, max recall
    >>> pipeline = PHIPipelineBuilder.hipaa_compliant().build()

Batch Processing:
    >>> from phi_detector_remover import BatchProcessor
    >>>
    >>> processor = BatchProcessor(pipeline)
    >>> results_df = processor.process_directory("./screenshots/")
    >>> processor.export_parquet(results_df, "./results.parquet")

Benchmarking:
    >>> from phi_detector_remover import BenchmarkRunner, AnnotatedDataset
    >>>
    >>> dataset = AnnotatedDataset.from_directory("./benchmark_data/")
    >>> runner = BenchmarkRunner(dataset)
    >>> result = runner.evaluate(pipeline)
    >>> print(f"F1 Score: {result.metrics.f1_score:.3f}")
"""

from __future__ import annotations

__version__ = "2.0.0"

# Core models
# Batch processing
from phi_detector_remover.core.batch import (
    BatchProcessor,
    BatchResultsIterator,
    process_images,
)

# Benchmarking
from phi_detector_remover.core.benchmark import (
    AnnotatedDataset,
    BenchmarkRunner,
    compare_pipelines,
)

# Configuration
from phi_detector_remover.core.config import (
    LLMDetectorConfig,
    OCRConfig,
    PHIDetectorConfig,
    PHIPipelineConfig,
    PresidioConfig,
    RedactionConfig,
    RegexConfig,
    VisionDetectorConfig,
)

# Detectors
from phi_detector_remover.core.detectors import (
    PresidioDetector,
    RegexDetector,
    get_text_detector,
    get_vision_detector,
    list_text_detectors,
    list_vision_detectors,
)
from phi_detector_remover.core.models import (
    AggregatedPHIRegion,
    BenchmarkMetrics,
    BenchmarkResult,
    BoundingBox,
    DetectionResult,
    DetectorType,
    EntityType,
    GroundTruthAnnotation,
    OCRResult,
    OCRWord,
    PHIRegion,
    PipelineResult,
)

# OCR engines
from phi_detector_remover.core.ocr import (
    TesseractEngine,
)
from phi_detector_remover.core.ocr import (
    get_engine as get_ocr_engine,
)
from phi_detector_remover.core.ocr import (
    list_engines as list_ocr_engines,
)

# Pipeline builder and executor
from phi_detector_remover.core.pipeline import (
    PHIPipeline,
    PHIPipelineBuilder,
)

# Aggregation strategies
from phi_detector_remover.core.pipeline.aggregator import (
    AggregationStrategy,
    IntersectionAggregator,
    ThresholdAggregator,
    UnionAggregator,
    WeightedVoteAggregator,
    get_aggregator,
)

# Prompt templates for LLM/LVM
from phi_detector_remover.core.prompts import (
    PHIDetectionPrompt,
    PromptStyle,
    get_prompt,
)

# Remover (image redaction)
from phi_detector_remover.core.remover import PHIRemover, RedactionMethod

# Dagster integration (high-level batch processing)
from phi_detector_remover.dagster import (
    PHIDetectionConfig,
    detect_phi_batch,
    detect_phi_single,
)

__all__ = [
    # Version
    "__version__",
    # Core models
    "AggregatedPHIRegion",
    "BenchmarkMetrics",
    "BenchmarkResult",
    "BoundingBox",
    "DetectionResult",
    "DetectorType",
    "EntityType",
    "GroundTruthAnnotation",
    "OCRResult",
    "OCRWord",
    "PHIRegion",
    "PipelineResult",
    # Configuration
    "LLMDetectorConfig",
    "OCRConfig",
    "PHIDetectorConfig",
    "PHIPipelineConfig",
    "PresidioConfig",
    "RedactionConfig",
    "RegexConfig",
    "VisionDetectorConfig",
    # Prompts
    "PHIDetectionPrompt",
    "PromptStyle",
    "get_prompt",
    # Pipeline
    "PHIPipeline",
    "PHIPipelineBuilder",
    # Aggregation
    "AggregationStrategy",
    "IntersectionAggregator",
    "ThresholdAggregator",
    "UnionAggregator",
    "WeightedVoteAggregator",
    "get_aggregator",
    # Batch processing
    "BatchProcessor",
    "BatchResultsIterator",
    "process_images",
    # Benchmarking
    "AnnotatedDataset",
    "BenchmarkRunner",
    "compare_pipelines",
    # Remover
    "PHIRemover",
    "RedactionMethod",
    # OCR
    "TesseractEngine",
    "get_ocr_engine",
    "list_ocr_engines",
    # Detectors
    "PresidioDetector",
    "RegexDetector",
    "get_text_detector",
    "get_vision_detector",
    "list_text_detectors",
    "list_vision_detectors",
    # Convenience functions
    "process_image",
    # Dagster integration
    "PHIDetectionConfig",
    "detect_phi_batch",
    "detect_phi_single",
]


def process_image(
    image_bytes: bytes,
    removal_method: RedactionMethod | str = "redbox",
    pipeline_preset: str = "balanced",
) -> tuple[bytes, list[PHIRegion]]:
    """Detect and remove PHI from an image in one call.

    This is a convenience function for quick processing.
    For more control, use PHIPipelineBuilder.

    Args:
        image_bytes: Image data as bytes
        removal_method: Redaction method ('redbox', 'blackbox', or 'pixelate')
        pipeline_preset: Pipeline preset ('fast', 'balanced', 'hipaa_compliant')

    Returns:
        Tuple of (cleaned_image_bytes, detected_regions)

    Example:
        >>> image_data = Path("screenshot.png").read_bytes()
        >>> clean_image, regions = process_image(image_data, "redbox")
        >>> Path("clean.png").write_bytes(clean_image)
        >>> print(f"Removed {len(regions)} PHI regions")
    """
    # Build pipeline based on preset
    if pipeline_preset == "fast":
        builder = PHIPipelineBuilder.fast()
    elif pipeline_preset == "hipaa_compliant":
        builder = PHIPipelineBuilder.hipaa_compliant()
    else:
        builder = PHIPipelineBuilder.balanced()

    pipeline = builder.build()

    # Process image
    result = pipeline.process(image_bytes)

    # Get regions for redaction
    regions = result.get_regions_for_redaction()

    if not regions:
        return image_bytes, []

    # Remove PHI
    remover = PHIRemover(method=removal_method)
    clean_image = remover.remove(image_bytes, regions)

    return clean_image, regions
