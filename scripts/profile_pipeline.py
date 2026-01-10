"""
Full Pipeline Profiling with Real Screenshots

This script profiles the complete pipeline from upload through OCR processing
using real screenshots from the example study (Dagster pipeline source data).

Profiles:
- Upload endpoint latency (by image size/resolution)
- Background processing time (grid detection, bar extraction, OCR)
- End-to-end latency (upload to processed result)
- Memory usage during processing
- Throughput under various concurrency levels

Usage:
    # Start backend first (via docker or directly):
    docker compose -f docker/docker-compose.dev.yml up -d
    # or: uvicorn src.screenshot_processor.web.api.main:app --host 127.0.0.1 --port 8002

    # Run profiling with example study screenshots (default):
    python scripts/profile_pipeline.py

    # Quick test (5 images per resolution):
    python scripts/profile_pipeline.py --quick

    # Full test (all images):
    python scripts/profile_pipeline.py --full

    # Stress test:
    python scripts/profile_pipeline.py --stress

    # Use reference_images instead of example study:
    python scripts/profile_pipeline.py --use-reference-images
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import random
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import polars as pl
from PIL import Image

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Delta Lake table paths for preprocessed screenshots (from Dagster pipeline)
# These screenshots have: device detection, cropping, PHI detection, PHI redaction
DELTA_WAREHOUSE_PATH = Path("D:/Scripts/monorepo/apps/pipeline/data/warehouse")
TECH_IOS_PHI_REDACTED_TABLE = DELTA_WAREHOUSE_PATH / "tech" / "ios" / "tech_ios_04_phi_redacted"

# Fallback: Raw example study screenshot paths (unprocessed)
EXAMPLE_STUDY_RAW_SCREENSHOT_DIR = Path("/path/to/screenshots")


@dataclass
class StageResult:
    """Timing result for a single processing stage."""
    stage: str
    times_ms: list[float] = field(default_factory=list)
    errors: int = 0

    @property
    def count(self) -> int:
        return len(self.times_ms)

    @property
    def mean_ms(self) -> float:
        return statistics.mean(self.times_ms) if self.times_ms else 0

    @property
    def stdev_ms(self) -> float:
        return statistics.stdev(self.times_ms) if len(self.times_ms) > 1 else 0

    @property
    def min_ms(self) -> float:
        return min(self.times_ms) if self.times_ms else 0

    @property
    def max_ms(self) -> float:
        return max(self.times_ms) if self.times_ms else 0

    @property
    def p50_ms(self) -> float:
        if not self.times_ms:
            return 0
        sorted_times = sorted(self.times_ms)
        return sorted_times[len(sorted_times) // 2]

    @property
    def p95_ms(self) -> float:
        if not self.times_ms:
            return 0
        sorted_times = sorted(self.times_ms)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[min(idx, len(sorted_times) - 1)]


@dataclass
class ResolutionResult:
    """Results grouped by image resolution."""
    resolution: str
    width: int
    height: int
    image_count: int = 0
    total_bytes: int = 0
    upload_times_ms: list[float] = field(default_factory=list)
    processing_times_ms: list[float] = field(default_factory=list)
    end_to_end_times_ms: list[float] = field(default_factory=list)
    errors: int = 0
    processing_statuses: dict[str, int] = field(default_factory=lambda: defaultdict(int))


class PipelineProfiler:
    """Profile the complete screenshot processing pipeline."""

    def __init__(
        self,
        api_url: str = "http://localhost:8002/api/v1",
        api_key: str = "dev-upload-key-change-in-production",
        source_dir: Path | None = None,
        use_reference_images: bool = False,
    ):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.use_reference_images = use_reference_images

        if use_reference_images:
            self.source_dir = source_dir or Path(__file__).parent.parent / "reference_images"
        else:
            self.source_dir = None  # Delta table mode - no source dir needed

        # Collect images by resolution
        self.images_by_resolution: dict[str, list[Path]] = defaultdict(list)

        # Store Delta table metadata for participant_id lookup
        self.delta_metadata: dict[str, dict] = {}  # file_path -> row data

        if use_reference_images:
            self._load_reference_images()
        else:
            self._load_example_study_images()

        self.results_by_resolution: dict[str, ResolutionResult] = {}

    def _load_reference_images(self) -> None:
        """Load reference images grouped by resolution (folder-based)."""
        if not self.source_dir.exists():
            print(f"Warning: Reference directory not found: {self.source_dir}")
            return

        for resolution_dir in self.source_dir.iterdir():
            if resolution_dir.is_dir() and "x" in resolution_dir.name:
                resolution = resolution_dir.name
                for img_path in resolution_dir.glob("*.png"):
                    # Skip GRID overlay images
                    if "GRID" not in img_path.name:
                        self.images_by_resolution[resolution].append(img_path)

        total = sum(len(v) for v in self.images_by_resolution.values())
        print(f"Loaded {total} reference images across {len(self.images_by_resolution)} resolutions:")
        for res, images in sorted(self.images_by_resolution.items()):
            print(f"  {res}: {len(images)} images")

    def _load_example_study_images(self) -> None:
        """Load example study screenshots from Delta Lake or raw directory.

        First tries to read from tech_ios_04_phi_redacted Delta table (preprocessed).
        Falls back to raw screenshot directory if Delta table doesn't exist.
        """
        delta_table = TECH_IOS_PHI_REDACTED_TABLE

        if not delta_table.exists():
            print(f"Delta table not found: {delta_table}")
            print("Falling back to raw screenshot directory...")
            self._load_raw_tech_screenshots()
            return

        print(f"Loading preprocessed screenshots from Delta table: {delta_table}")

        try:
            # Read the Delta table
            df = pl.read_delta(str(delta_table))
            print(f"Found {df.height} records in Delta table")

            # Get the file path column - use redacted_file_path (final preprocessed image)
            # Falls back to cropped_file_path if no redaction, then original file_path
            file_paths = []
            for row in df.iter_rows(named=True):
                # Priority: redacted > cropped > original
                if row.get("phi_redacted") and row.get("redacted_file_path"):
                    file_paths.append((Path(row["redacted_file_path"]), row))
                elif row.get("was_cropped") and row.get("cropped_file_path"):
                    file_paths.append((Path(row["cropped_file_path"]), row))
                elif row.get("file_path"):
                    file_paths.append((Path(row["file_path"]), row))

            print(f"Found {len(file_paths)} file paths to process")

            # Filter to existing files and group by resolution (from Delta metadata)
            valid_count = 0
            missing_count = 0
            for file_path, row in file_paths:
                if not file_path.exists():
                    missing_count += 1
                    continue

                # Use resolution from Delta table metadata (width x height)
                width = row.get("width", 0)
                height = row.get("height", 0)
                if width and height:
                    resolution = f"{width}x{height}"
                else:
                    # Fallback: read from image
                    try:
                        with Image.open(file_path) as img:
                            width, height = img.size
                            resolution = f"{width}x{height}"
                    except Exception:
                        continue

                self.images_by_resolution[resolution].append(file_path)
                # Store metadata for participant_id lookup
                self.delta_metadata[str(file_path)] = row
                valid_count += 1

            total = sum(len(v) for v in self.images_by_resolution.values())
            print(f"\nLoaded {total} preprocessed images ({missing_count} files not found)")
            print("Grouped by resolution:")
            for res, images in sorted(self.images_by_resolution.items(), key=lambda x: -len(x[1])):
                print(f"  {res}: {len(images)} images")

            # Show device breakdown
            ipad_count = df.filter(pl.col("is_ipad")).height
            iphone_count = df.filter(pl.col("is_iphone")).height
            phi_redacted_count = df.filter(pl.col("phi_redacted")).height
            cropped_count = df.filter(pl.col("was_cropped")).height
            print("\nPreprocessing summary:")
            print(f"  iPads: {ipad_count} (cropped: {cropped_count})")
            print(f"  iPhones: {iphone_count}")
            print(f"  PHI redacted: {phi_redacted_count}")

        except Exception as e:
            print(f"Error reading Delta table: {e}")
            import traceback
            traceback.print_exc()
            print("Falling back to raw screenshot directory...")
            self._load_raw_tech_screenshots()

    def _load_raw_tech_screenshots(self) -> None:
        """Load raw example study screenshots from network drive (fallback).

        Used when Delta table is not available.
        """
        raw_dir = EXAMPLE_STUDY_RAW_SCREENSHOT_DIR

        if not raw_dir.exists():
            print(f"Error: Raw screenshot directory not found: {raw_dir}")
            print("Make sure the network drive (W:) is mounted.")
            return

        print(f"Scanning raw example study screenshots from: {raw_dir}")

        # Find all PNG files recursively
        all_pngs = list(raw_dir.rglob("*.PNG")) + list(raw_dir.rglob("*.png"))
        # Deduplicate on case-insensitive filesystems
        all_pngs = list(set(all_pngs))
        print(f"Found {len(all_pngs)} total PNG files")

        if not all_pngs:
            return

        # Group by resolution
        print("Grouping images by resolution (this may take a moment)...")
        for i, img_path in enumerate(all_pngs):
            if (i + 1) % 200 == 0:
                print(f"  Processed {i + 1}/{len(all_pngs)}...")
            try:
                with Image.open(img_path) as img:
                    width, height = img.size
                    resolution = f"{width}x{height}"
                    self.images_by_resolution[resolution].append(img_path)
            except Exception:
                pass  # Skip unreadable images

        total = sum(len(v) for v in self.images_by_resolution.values())
        print(f"\nLoaded {total} raw images across {len(self.images_by_resolution)} resolutions:")
        for res, images in sorted(self.images_by_resolution.items(), key=lambda x: -len(x[1])):
            print(f"  {res}: {len(images)} images")

        print("\nWARNING: Using raw screenshots (not preprocessed)")
        print("For production use, run the Dagster pipeline first to apply:")
        print("  - Device detection")
        print("  - iPad cropping")
        print("  - PHI detection and redaction")

    def _make_client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.api_url,
            timeout=120.0,
            headers={"X-API-Key": self.api_key},
        )

    def _make_async_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.api_url,
            timeout=120.0,
            headers={"X-API-Key": self.api_key},
        )

    def _get_image_data(self, path: Path) -> tuple[bytes, str, str]:
        """Load image and compute metadata."""
        data = path.read_bytes()
        b64 = base64.b64encode(data).decode("utf-8")
        sha256 = hashlib.sha256(data).hexdigest()
        return data, b64, sha256

    async def _poll_for_processing(
        self,
        client: httpx.AsyncClient,
        screenshot_id: int,
        timeout_seconds: float = 120.0,  # Increased for HunyuanOCR which takes ~70s
        poll_interval: float = 1.0,
    ) -> tuple[dict | None, float]:
        """Poll until screenshot processing completes."""
        start = time.perf_counter()
        deadline = start + timeout_seconds

        while time.perf_counter() < deadline:
            try:
                # Need auth header for this endpoint
                resp = await client.get(
                    f"/screenshots/{screenshot_id}",
                    headers={"X-Username": "profiler"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    status = data.get("processing_status")
                    if status in ("completed", "failed", "skipped"):
                        elapsed = (time.perf_counter() - start) * 1000
                        return data, elapsed
            except Exception:
                pass

            await asyncio.sleep(poll_interval)

        return None, (time.perf_counter() - start) * 1000

    def _extract_participant_id(self, image_path: Path) -> str:
        """Extract participant ID from Delta metadata or path structure.

        First checks Delta table metadata, then falls back to path parsing.
        """
        # Check Delta metadata first
        path_str = str(image_path)
        if path_str in self.delta_metadata:
            pid = self.delta_metadata[path_str].get("participant_id")
            if pid:
                return pid

        # Fallback: Parse from path structure
        for parent in image_path.parents:
            if "Screen Time Screenshots" in parent.name:
                # Extract P1-XXXX-A from "P1-XXXX-A Screen Time Screenshots"
                parts = parent.name.split(" Screen Time Screenshots")[0]
                return parts
        # Fallback to filename stem
        return f"profile-{image_path.stem[:20]}"

    async def profile_single_upload(
        self,
        image_path: Path,
        resolution: str,
        group_id: str = "profile-test",
    ) -> dict[str, Any]:
        """Profile a single image upload and processing."""
        data, b64, sha256 = self._get_image_data(image_path)

        result = {
            "path": str(image_path),
            "resolution": resolution,
            "size_bytes": len(data),
            "upload_time_ms": 0,
            "processing_time_ms": 0,
            "end_to_end_time_ms": 0,
            "status": "unknown",
            "error": None,
            "extracted_title": None,
            "extracted_total": None,
            "processing_method": None,
        }

        participant_id = self._extract_participant_id(image_path)

        async with self._make_async_client() as client:
            # Upload
            payload = {
                "screenshot": b64,
                "participant_id": participant_id,
                "group_id": group_id,
                "image_type": "screen_time",
                "sha256": sha256,
            }

            start_upload = time.perf_counter()
            try:
                resp = await client.post("/screenshots/upload", json=payload)
                upload_time = (time.perf_counter() - start_upload) * 1000
                result["upload_time_ms"] = upload_time

                if resp.status_code not in (200, 201):
                    result["error"] = f"Upload failed: {resp.status_code}"
                    result["status"] = "upload_error"
                    return result

                upload_data = resp.json()
                screenshot_id = upload_data.get("screenshot_id")

                if not screenshot_id:
                    result["error"] = "No screenshot_id in response"
                    result["status"] = "upload_error"
                    return result

                # Poll for processing completion
                time.perf_counter()
                processed_data, processing_time = await self._poll_for_processing(
                    client, screenshot_id
                )

                if processed_data:
                    result["processing_time_ms"] = processing_time
                    result["status"] = processed_data.get("processing_status", "unknown")
                    result["extracted_title"] = processed_data.get("extracted_title")
                    result["extracted_total"] = processed_data.get("extracted_total")
                    result["processing_method"] = processed_data.get("processing_method")
                else:
                    result["status"] = "timeout"
                    result["error"] = "Processing timeout"

                result["end_to_end_time_ms"] = upload_time + processing_time

            except Exception as e:
                result["error"] = str(e)
                result["status"] = "exception"

        return result

    async def profile_resolution(
        self,
        resolution: str,
        max_images: int = 10,
        group_id: str | None = None,
    ) -> ResolutionResult:
        """Profile uploads for a specific resolution."""
        images = self.images_by_resolution.get(resolution, [])
        if not images:
            print(f"  No images found for resolution {resolution}")
            return ResolutionResult(resolution=resolution, width=0, height=0)

        # Parse dimensions from resolution string
        try:
            width, height = map(int, resolution.split("x"))
        except ValueError:
            width, height = 0, 0

        # Sample images if needed
        if len(images) > max_images:
            images = random.sample(images, max_images)

        result = ResolutionResult(
            resolution=resolution,
            width=width,
            height=height,
            image_count=len(images),
        )

        group = group_id or f"profile-{resolution}-{int(time.time())}"

        print(f"  Processing {len(images)} images at {resolution}...")

        for i, image_path in enumerate(images):
            img_result = await self.profile_single_upload(image_path, resolution, group)

            result.total_bytes += img_result["size_bytes"]

            if img_result["error"]:
                result.errors += 1
            else:
                result.upload_times_ms.append(img_result["upload_time_ms"])
                if img_result["processing_time_ms"] > 0:
                    result.processing_times_ms.append(img_result["processing_time_ms"])
                result.end_to_end_times_ms.append(img_result["end_to_end_time_ms"])

            result.processing_statuses[img_result["status"]] += 1

            # Progress indicator
            if (i + 1) % 5 == 0:
                print(f"    {i + 1}/{len(images)} complete...")

        return result

    async def run_profile(
        self,
        max_images_per_resolution: int = 10,
        resolutions: list[str] | None = None,
    ) -> None:
        """Run profiling across all or specified resolutions."""
        print("\n" + "=" * 80)
        print("PIPELINE PROFILING - Full Upload -> Processing Flow")
        print("=" * 80)
        print(f"\nAPI URL: {self.api_url}")
        print(f"Max images per resolution: {max_images_per_resolution}\n")

        target_resolutions = resolutions or list(self.images_by_resolution.keys())

        for resolution in sorted(target_resolutions):
            if resolution not in self.images_by_resolution:
                print(f"Skipping {resolution} - no images")
                continue

            result = await self.profile_resolution(
                resolution,
                max_images=max_images_per_resolution,
            )
            self.results_by_resolution[resolution] = result

        self._print_results()

    def _print_results(self) -> None:
        """Print profiling results."""
        print("\n" + "=" * 80)
        print("RESULTS BY RESOLUTION")
        print("=" * 80)

        all_upload = []
        all_processing = []
        all_e2e = []

        for resolution in sorted(self.results_by_resolution.keys()):
            result = self.results_by_resolution[resolution]

            if not result.upload_times_ms:
                print(f"\n{resolution}: No successful uploads")
                continue

            all_upload.extend(result.upload_times_ms)
            all_processing.extend(result.processing_times_ms)
            all_e2e.extend(result.end_to_end_times_ms)

            avg_size_kb = (result.total_bytes / result.image_count / 1024) if result.image_count else 0

            print(f"\n{resolution} ({result.image_count} images, avg {avg_size_kb:.0f} KB):")
            print(f"  Upload:      mean={statistics.mean(result.upload_times_ms):.0f}ms, "
                  f"p95={sorted(result.upload_times_ms)[int(len(result.upload_times_ms)*0.95)]:.0f}ms")

            if result.processing_times_ms:
                print(f"  Processing:  mean={statistics.mean(result.processing_times_ms):.0f}ms, "
                      f"p95={sorted(result.processing_times_ms)[int(len(result.processing_times_ms)*0.95)]:.0f}ms")

            print(f"  End-to-End:  mean={statistics.mean(result.end_to_end_times_ms):.0f}ms, "
                  f"p95={sorted(result.end_to_end_times_ms)[int(len(result.end_to_end_times_ms)*0.95)]:.0f}ms")

            print(f"  Statuses:    {dict(result.processing_statuses)}")
            if result.errors:
                print(f"  Errors:      {result.errors}")

        # Overall summary
        print("\n" + "=" * 80)
        print("OVERALL SUMMARY")
        print("=" * 80)

        if all_upload:
            print("\nUpload Latency (all resolutions):")
            print(f"  Count:  {len(all_upload)}")
            print(f"  Mean:   {statistics.mean(all_upload):.0f}ms")
            print(f"  Stdev:  {statistics.stdev(all_upload):.0f}ms" if len(all_upload) > 1 else "")
            print(f"  Min:    {min(all_upload):.0f}ms")
            print(f"  Max:    {max(all_upload):.0f}ms")
            print(f"  P50:    {sorted(all_upload)[len(all_upload)//2]:.0f}ms")
            print(f"  P95:    {sorted(all_upload)[int(len(all_upload)*0.95)]:.0f}ms")

        if all_processing:
            print("\nProcessing Latency (all resolutions):")
            print(f"  Count:  {len(all_processing)}")
            print(f"  Mean:   {statistics.mean(all_processing):.0f}ms")
            print(f"  Stdev:  {statistics.stdev(all_processing):.0f}ms" if len(all_processing) > 1 else "")
            print(f"  Min:    {min(all_processing):.0f}ms")
            print(f"  Max:    {max(all_processing):.0f}ms")
            print(f"  P50:    {sorted(all_processing)[len(all_processing)//2]:.0f}ms")
            print(f"  P95:    {sorted(all_processing)[int(len(all_processing)*0.95)]:.0f}ms")

        if all_e2e:
            print("\nEnd-to-End Latency (upload + processing):")
            print(f"  Count:  {len(all_e2e)}")
            print(f"  Mean:   {statistics.mean(all_e2e):.0f}ms")
            print(f"  P95:    {sorted(all_e2e)[int(len(all_e2e)*0.95)]:.0f}ms")

            # Throughput estimate
            total_time_sec = sum(all_e2e) / 1000
            throughput = len(all_e2e) / total_time_sec if total_time_sec > 0 else 0
            print(f"\nEstimated serial throughput: {throughput:.1f} images/sec")

    async def run_throughput_test(
        self,
        concurrency: int = 5,
        total_uploads: int = 50,
    ) -> None:
        """Test concurrent upload throughput."""
        print("\n" + "=" * 80)
        print(f"THROUGHPUT TEST - {total_uploads} uploads at concurrency {concurrency}")
        print("=" * 80 + "\n")

        # Collect a mix of images across resolutions
        all_images = []
        for resolution, images in self.images_by_resolution.items():
            all_images.extend([(path, resolution) for path in images])

        if len(all_images) < total_uploads:
            # Repeat images if needed
            all_images = all_images * (total_uploads // len(all_images) + 1)

        all_images = random.sample(all_images, total_uploads)

        semaphore = asyncio.Semaphore(concurrency)
        errors = 0

        async def upload_one(idx: int, path: Path, resolution: str) -> float | None:
            nonlocal errors
            async with semaphore:
                try:
                    result = await self.profile_single_upload(
                        path, resolution, f"throughput-{int(time.time())}"
                    )
                    if result["error"]:
                        errors += 1
                        return None
                    return result["end_to_end_time_ms"]
                except Exception:
                    errors += 1
                    return None

        print(f"Starting {total_uploads} concurrent uploads...")
        start = time.perf_counter()

        tasks = [
            upload_one(i, path, res)
            for i, (path, res) in enumerate(all_images)
        ]
        times = await asyncio.gather(*tasks)

        total_time = time.perf_counter() - start

        successful_times = [t for t in times if t is not None]

        print("\nResults:")
        print(f"  Total uploads:  {total_uploads}")
        print(f"  Successful:     {len(successful_times)}")
        print(f"  Failed:         {errors}")
        print(f"  Wall time:      {total_time:.1f}s")
        print(f"  Throughput:     {len(successful_times) / total_time:.1f} uploads/sec")

        if successful_times:
            print(f"  Mean latency:   {statistics.mean(successful_times):.0f}ms")
            print(f"  P95 latency:    {sorted(successful_times)[int(len(successful_times)*0.95)]:.0f}ms")


def main():
    parser = argparse.ArgumentParser(description="Profile the complete screenshot pipeline")
    parser.add_argument(
        "--api-url",
        default="http://localhost:8002/api/v1",
        help="API base URL",
    )
    parser.add_argument(
        "--api-key",
        default="dev-upload-key-change-in-production",
        help="API key for uploads",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick test - 5 images per resolution",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Full test - all images",
    )
    parser.add_argument(
        "--stress",
        action="store_true",
        help="Run throughput stress test",
    )
    parser.add_argument(
        "--max-images",
        type=int,
        default=10,
        help="Max images per resolution (default: 10)",
    )
    parser.add_argument(
        "--resolution",
        type=str,
        help="Test only specific resolution (e.g., 1170x2532)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Concurrency level for stress test (default: 5)",
    )
    parser.add_argument(
        "--use-reference-images",
        action="store_true",
        help="Use reference_images directory instead of example study screenshots",
    )
    parser.add_argument(
        "--source-dir",
        type=str,
        help="Custom source directory for screenshots",
    )

    args = parser.parse_args()

    source_dir = Path(args.source_dir) if args.source_dir else None

    profiler = PipelineProfiler(
        api_url=args.api_url,
        api_key=args.api_key,
        source_dir=source_dir,
        use_reference_images=args.use_reference_images,
    )

    if args.stress:
        asyncio.run(profiler.run_throughput_test(
            concurrency=args.concurrency,
            total_uploads=50,
        ))
    else:
        max_images = 5 if args.quick else (999 if args.full else args.max_images)
        resolutions = [args.resolution] if args.resolution else None

        asyncio.run(profiler.run_profile(
            max_images_per_resolution=max_images,
            resolutions=resolutions,
        ))


if __name__ == "__main__":
    main()
