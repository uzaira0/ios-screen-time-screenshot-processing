"""Batch processing utilities for PHI detection.

Provides utilities for:
- Processing multiple images from directories or catalogs
- Exporting results to various formats (Parquet, CSV, JSON)
- Integration with Dagster pipelines via DataFrames
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from phi_detector_remover.core.models import (
    AggregatedPHIRegion,
    PipelineResult,
)

if TYPE_CHECKING:
    import polars as pl

    from phi_detector_remover.core.pipeline import PHIPipeline


class BatchProcessor:
    """Batch processor for PHI detection across multiple images.

    Designed for pipeline integration with Dagster, providing:
    - Processing from directories, file lists, or Polars DataFrames
    - Parallel processing with configurable workers
    - Export to Parquet, CSV, or JSON for downstream consumption
    - Progress tracking and error handling

    Example:
        >>> from phi_detector_remover.core.pipeline import PHIPipelineBuilder
        >>>
        >>> pipeline = PHIPipelineBuilder.balanced().build()
        >>> batch = BatchProcessor(pipeline, max_workers=4)
        >>>
        >>> # Process directory
        >>> results_df = batch.process_directory("./screenshots/", pattern="*.png")
        >>>
        >>> # Export results
        >>> batch.export_parquet(results_df, "./results/phi_detected.parquet")
    """

    def __init__(
        self,
        pipeline: PHIPipeline,
        max_workers: int = 4,
        continue_on_error: bool = True,
    ):
        """Initialize batch processor.

        Args:
            pipeline: Configured PHI detection pipeline
            max_workers: Maximum parallel workers
            continue_on_error: Continue processing if an image fails
        """
        self.pipeline = pipeline
        self.max_workers = max_workers
        self.continue_on_error = continue_on_error

    def process_directory(
        self,
        directory: str | Path,
        pattern: str = "*.png",
        recursive: bool = True,
        output_dir: str | Path | None = None,
        redact: bool = False,
    ) -> pl.DataFrame:
        """Process all matching images in a directory.

        Args:
            directory: Directory to search
            pattern: Glob pattern for image files
            recursive: Search recursively
            output_dir: Optional directory for redacted images
            redact: Whether to save redacted images

        Returns:
            Polars DataFrame with detection results
        """
        import polars as pl

        directory = Path(directory)

        if recursive:
            image_files = list(directory.rglob(pattern))
        else:
            image_files = list(directory.glob(pattern))

        if not image_files:
            return self._empty_results_df()

        return self.process_files(
            files=image_files,
            output_dir=output_dir,
            redact=redact,
        )

    def process_files(
        self,
        files: list[str | Path],
        output_dir: str | Path | None = None,
        redact: bool = False,
    ) -> pl.DataFrame:
        """Process a list of image files.

        Args:
            files: List of file paths
            output_dir: Optional directory for redacted images
            redact: Whether to save redacted images

        Returns:
            Polars DataFrame with detection results
        """
        import polars as pl

        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        results = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(
                    self._process_single_file,
                    Path(f),
                    output_dir,
                    redact,
                ): f
                for f in files
            }

            for future in as_completed(futures):
                file_path = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    if self.continue_on_error:
                        results.append(self._error_result(file_path, str(e)))
                    else:
                        raise

        return pl.DataFrame(results)

    def process_from_catalog(
        self,
        catalog: pl.DataFrame,
        image_path_column: str = "file_path",
        output_dir: str | Path | None = None,
        redact: bool = False,
    ) -> pl.DataFrame:
        """Process images from a catalog DataFrame.

        Designed for integration with Dagster assets that produce
        file catalogs (e.g., ios_screenshots_raw_catalog).

        Args:
            catalog: DataFrame with image file paths
            image_path_column: Column containing file paths
            output_dir: Optional directory for redacted images
            redact: Whether to save redacted images

        Returns:
            DataFrame with detection results joined to catalog
        """
        import polars as pl

        # Extract file paths
        file_paths = catalog[image_path_column].to_list()

        # Process files
        results_df = self.process_files(
            files=file_paths,
            output_dir=output_dir,
            redact=redact,
        )

        # Join results back to catalog
        return catalog.join(
            results_df,
            left_on=image_path_column,
            right_on="file_path",
            how="left",
        )

    def _process_single_file(
        self,
        file_path: Path,
        output_dir: Path | None,
        redact: bool,
    ) -> dict[str, Any]:
        """Process a single image file.

        Args:
            file_path: Path to image
            output_dir: Output directory for redacted image
            redact: Whether to save redacted image

        Returns:
            Result dictionary
        """
        start_time = time.perf_counter()

        # Read image
        image_bytes = file_path.read_bytes()

        # Run detection pipeline
        result = self.pipeline.process(image_bytes)

        # Redact if requested
        redacted_path = None
        if redact and output_dir and result.aggregated_regions:
            from phi_detector_remover.core.remover import PHIRemover

            remover = PHIRemover(method="redbox")
            regions = result.get_regions_for_redaction()
            clean_bytes = remover.remove(image_bytes, regions)

            redacted_path = output_dir / f"redacted_{file_path.name}"
            redacted_path.write_bytes(clean_bytes)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return {
            "file_path": str(file_path),
            "file_name": file_path.name,
            "phi_detected": result.has_phi,
            "region_count": result.region_count,
            "regions": [r.to_dict() for r in result.aggregated_regions],
            "regions_json": json.dumps([r.to_dict() for r in result.aggregated_regions]),
            "detectors_used": list(result.detector_results.keys()),
            "ocr_confidence": result.ocr_result.confidence if result.ocr_result else None,
            "ocr_text": result.ocr_result.text if result.ocr_result else None,
            "processing_time_ms": elapsed_ms,
            "redacted_path": str(redacted_path) if redacted_path else None,
            "error": None,
        }

    def _error_result(
        self,
        file_path: str | Path,
        error_message: str,
    ) -> dict[str, Any]:
        """Create an error result dict."""
        return {
            "file_path": str(file_path),
            "file_name": Path(file_path).name,
            "phi_detected": None,
            "region_count": 0,
            "regions": [],
            "regions_json": "[]",
            "detectors_used": [],
            "ocr_confidence": None,
            "ocr_text": None,
            "processing_time_ms": 0,
            "redacted_path": None,
            "error": error_message,
        }

    def _empty_results_df(self) -> pl.DataFrame:
        """Create empty results DataFrame with correct schema."""
        import polars as pl

        return pl.DataFrame(
            schema={
                "file_path": pl.Utf8,
                "file_name": pl.Utf8,
                "phi_detected": pl.Boolean,
                "region_count": pl.Int64,
                "regions": pl.List(pl.Struct),
                "regions_json": pl.Utf8,
                "detectors_used": pl.List(pl.Utf8),
                "ocr_confidence": pl.Float64,
                "ocr_text": pl.Utf8,
                "processing_time_ms": pl.Float64,
                "redacted_path": pl.Utf8,
                "error": pl.Utf8,
            }
        )

    # ========================================================================
    # Export Methods
    # ========================================================================

    def export_parquet(
        self,
        results: pl.DataFrame,
        path: str | Path,
    ) -> None:
        """Export results to Parquet file.

        Args:
            results: Results DataFrame
            path: Output path
        """
        results.write_parquet(path)

    def export_csv(
        self,
        results: pl.DataFrame,
        path: str | Path,
        include_regions: bool = False,
    ) -> None:
        """Export results to CSV file.

        Args:
            results: Results DataFrame
            path: Output path
            include_regions: Include regions JSON column
        """
        df = results
        if not include_regions:
            df = df.drop("regions", "regions_json")
        df.write_csv(path)

    def export_json(
        self,
        results: pl.DataFrame,
        path: str | Path,
        pretty: bool = True,
    ) -> None:
        """Export results to JSON file.

        Args:
            results: Results DataFrame
            path: Output path
            pretty: Pretty-print JSON
        """
        records = results.to_dicts()

        with open(path, "w") as f:
            if pretty:
                json.dump(records, f, indent=2)
            else:
                json.dump(records, f)

    def export_regions_for_review(
        self,
        results: pl.DataFrame,
        path: str | Path,
    ) -> None:
        """Export regions in a format suitable for human review.

        Creates a JSON file with:
        - Image path
        - All detected regions with bounding boxes
        - Detector sources and confidences

        Useful for building review/annotation UIs.

        Args:
            results: Results DataFrame
            path: Output path
        """
        review_data = []

        for row in results.iter_rows(named=True):
            if row["region_count"] > 0:
                review_data.append(
                    {
                        "image_path": row["file_path"],
                        "image_name": row["file_name"],
                        "regions": row["regions"],
                        "needs_review": True,
                        "reviewed": False,
                        "reviewer_notes": "",
                    }
                )

        with open(path, "w") as f:
            json.dump(review_data, f, indent=2)


class BatchResultsIterator:
    """Iterator for streaming batch processing results.

    Useful for processing large numbers of images without
    loading all results into memory.
    """

    def __init__(
        self,
        processor: BatchProcessor,
        files: list[str | Path],
    ):
        """Initialize results iterator.

        Args:
            processor: Batch processor instance
            files: List of files to process
        """
        self.processor = processor
        self.files = [Path(f) for f in files]
        self._index = 0

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return self

    def __next__(self) -> dict[str, Any]:
        if self._index >= len(self.files):
            raise StopIteration

        file_path = self.files[self._index]
        self._index += 1

        try:
            return self.processor._process_single_file(
                file_path,
                output_dir=None,
                redact=False,
            )
        except Exception as e:
            if self.processor.continue_on_error:
                return self.processor._error_result(file_path, str(e))
            raise

    def __len__(self) -> int:
        return len(self.files)


def process_images(
    images: list[str | Path] | str | Path,
    pattern: str = "*.png",
    pipeline_preset: str = "balanced",
    output_format: str = "parquet",
    output_path: str | Path | None = None,
    **pipeline_kwargs: Any,
) -> pl.DataFrame:
    """Convenience function for batch processing.

    Args:
        images: File paths, directory, or glob pattern
        pattern: Glob pattern if images is a directory
        pipeline_preset: Pipeline preset ("fast", "balanced", "thorough")
        output_format: Output format ("parquet", "csv", "json")
        output_path: Optional output file path
        **pipeline_kwargs: Additional pipeline configuration

    Returns:
        Results DataFrame
    """
    import polars as pl

    from phi_detector_remover.core.pipeline import PHIPipelineBuilder

    # Build pipeline
    if pipeline_preset == "fast":
        builder = PHIPipelineBuilder.fast()
    elif pipeline_preset == "thorough":
        builder = PHIPipelineBuilder.thorough(**pipeline_kwargs)
    else:
        builder = PHIPipelineBuilder.balanced()

    pipeline = builder.build()
    processor = BatchProcessor(pipeline)

    # Determine files to process
    if isinstance(images, (str, Path)):
        path = Path(images)
        if path.is_dir():
            results = processor.process_directory(path, pattern=pattern)
        elif path.is_file():
            results = processor.process_files([path])
        else:
            # Treat as glob pattern
            parent = path.parent
            results = processor.process_directory(parent, pattern=path.name)
    else:
        results = processor.process_files(images)

    # Export if path provided
    if output_path:
        output_path = Path(output_path)
        if output_format == "parquet":
            processor.export_parquet(results, output_path)
        elif output_format == "csv":
            processor.export_csv(results, output_path)
        elif output_format == "json":
            processor.export_json(results, output_path)

    return results
