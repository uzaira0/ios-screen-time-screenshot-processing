"""
Upload Endpoint Benchmark and Profiling

This script benchmarks the upload endpoints:
- Single upload performance
- Batch upload performance
- Concurrent upload handling
- Memory usage during uploads

Usage:
    python scripts/benchmark_upload.py [--api-url URL] [--api-key KEY] [--iterations N]

Requirements:
    - Running backend server (uvicorn)
    - Test images in tests/fixtures/ directory
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import cProfile
import hashlib
import io
import pstats
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Add src to path for local imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import httpx

# Try to import memory_profiler for memory benchmarks (optional)
try:
    import tracemalloc
    HAS_TRACEMALLOC = True
except ImportError:
    HAS_TRACEMALLOC = False


@dataclass
class BenchmarkResult:
    """Result of a benchmark run."""
    name: str
    iterations: int
    times_ms: list[float] = field(default_factory=list)
    errors: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

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
    def p95_ms(self) -> float:
        if not self.times_ms:
            return 0
        sorted_times = sorted(self.times_ms)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[min(idx, len(sorted_times) - 1)]

    @property
    def success_rate(self) -> float:
        total = len(self.times_ms) + self.errors
        return len(self.times_ms) / total if total > 0 else 0

    def summary(self) -> str:
        lines = [
            f"  {self.name}:",
            f"    Iterations: {self.iterations} ({self.errors} errors)",
            f"    Mean:       {self.mean_ms:.2f}ms",
            f"    Stdev:      {self.stdev_ms:.2f}ms",
            f"    Min/Max:    {self.min_ms:.2f}ms / {self.max_ms:.2f}ms",
            f"    P95:        {self.p95_ms:.2f}ms",
            f"    Success:    {self.success_rate * 100:.1f}%",
        ]
        for key, value in self.extra.items():
            lines.append(f"    {key}: {value}")
        return "\n".join(lines)


def create_test_image(width: int = 1125, height: int = 2436) -> bytes:
    """Create a minimal valid PNG image for testing."""
    # Minimal 1x1 transparent PNG
    # For realistic testing, we create a larger placeholder
    import struct
    import zlib

    def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk = chunk_type + data
        crc = zlib.crc32(chunk) & 0xffffffff
        return struct.pack(">I", len(data)) + chunk + struct.pack(">I", crc)

    # PNG signature
    signature = b'\x89PNG\r\n\x1a\n'

    # IHDR chunk
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = png_chunk(b'IHDR', ihdr_data)

    # IDAT chunk (compressed image data - all white)
    raw_data = b''
    for y in range(height):
        raw_data += b'\x00'  # Filter byte
        raw_data += b'\xff\xff\xff' * width  # RGB white

    compressed = zlib.compress(raw_data, 1)  # Low compression for speed
    idat = png_chunk(b'IDAT', compressed)

    # IEND chunk
    iend = png_chunk(b'IEND', b'')

    return signature + ihdr + idat + iend


def load_fixture_image() -> bytes | None:
    """Load a real test image from fixtures if available."""
    fixture_paths = [
        Path(__file__).parent.parent / "tests" / "fixtures" / "sample_screenshot.png",
        Path(__file__).parent.parent / "data" / "test_image.png",
    ]

    for path in fixture_paths:
        if path.exists():
            return path.read_bytes()

    return None


class UploadBenchmark:
    """Benchmark suite for upload endpoints."""

    def __init__(
        self,
        api_url: str = "http://localhost:8001/api/v1",
        api_key: str = "dev-upload-key-change-in-production",
        group_id: str = "benchmark-test",
    ):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.group_id = group_id
        self.results: list[BenchmarkResult] = []

        # Load or create test image
        self.test_image = load_fixture_image()
        if self.test_image is None:
            print("No fixture image found, generating synthetic image...")
            self.test_image = create_test_image()

        self.test_image_b64 = base64.b64encode(self.test_image).decode("utf-8")
        self.test_image_sha256 = hashlib.sha256(self.test_image).hexdigest()

        print(f"Test image size: {len(self.test_image):,} bytes ({len(self.test_image_b64):,} base64)")

    def _make_client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.api_url,
            timeout=60.0,
            headers={"X-API-Key": self.api_key},
        )

    def _make_async_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.api_url,
            timeout=60.0,
            headers={"X-API-Key": self.api_key},
        )

    def benchmark_health_check(self, iterations: int = 10) -> BenchmarkResult:
        """Benchmark health check endpoint as baseline."""
        result = BenchmarkResult(name="Health Check", iterations=iterations)

        # Health endpoint is at root, not under /api/v1
        health_url = self.api_url.replace("/api/v1", "").rstrip("/") + "/health"

        with httpx.Client(timeout=10.0) as client:
            for _ in range(iterations):
                try:
                    start = time.perf_counter()
                    resp = client.get(health_url)
                    elapsed = (time.perf_counter() - start) * 1000

                    if resp.status_code == 200:
                        result.times_ms.append(elapsed)
                    else:
                        result.errors += 1
                except Exception:
                    result.errors += 1

        self.results.append(result)
        return result

    def benchmark_single_upload(
        self,
        iterations: int = 10,
        with_checksum: bool = True,
    ) -> BenchmarkResult:
        """Benchmark single screenshot upload."""
        name = f"Single Upload ({'with' if with_checksum else 'without'} checksum)"
        result = BenchmarkResult(name=name, iterations=iterations)

        with self._make_client() as client:
            for i in range(iterations):
                payload = {
                    "screenshot": self.test_image_b64,
                    "participant_id": f"bench-{i}",
                    "group_id": self.group_id,
                    "image_type": "screen_time",
                }

                if with_checksum:
                    payload["sha256"] = self.test_image_sha256

                try:
                    start = time.perf_counter()
                    resp = client.post("/screenshots/upload", json=payload)
                    elapsed = (time.perf_counter() - start) * 1000

                    if resp.status_code in (200, 201):
                        result.times_ms.append(elapsed)
                        data = resp.json()
                        if i == 0:
                            result.extra["first_response"] = {
                                "screenshot_id": data.get("screenshot_id"),
                                "processing_queued": data.get("processing_queued"),
                            }
                    else:
                        result.errors += 1
                        if result.errors == 1:
                            result.extra["first_error"] = resp.text[:200]
                except Exception as e:
                    result.errors += 1
                    if result.errors == 1:
                        result.extra["first_exception"] = str(e)

        self.results.append(result)
        return result

    def benchmark_batch_upload(
        self,
        batch_size: int = 10,
        iterations: int = 5,
    ) -> BenchmarkResult:
        """Benchmark batch upload endpoint."""
        result = BenchmarkResult(
            name=f"Batch Upload ({batch_size} images)",
            iterations=iterations,
        )

        # Prepare batch items
        screenshots = []
        for j in range(batch_size):
            screenshots.append({
                "screenshot": self.test_image_b64,
                "participant_id": f"batch-{j}",
                "sha256": self.test_image_sha256,
            })

        with self._make_client() as client:
            for i in range(iterations):
                payload = {
                    "group_id": f"{self.group_id}-batch-{i}",
                    "image_type": "screen_time",
                    "screenshots": screenshots,
                }

                try:
                    start = time.perf_counter()
                    resp = client.post("/screenshots/upload/batch", json=payload)
                    elapsed = (time.perf_counter() - start) * 1000

                    if resp.status_code in (200, 201):
                        result.times_ms.append(elapsed)
                        data = resp.json()
                        if i == 0:
                            result.extra["batch_results"] = {
                                "successful": data.get("successful_count"),
                                "failed": data.get("failed_count"),
                                "duplicates": data.get("duplicate_count"),
                            }
                    else:
                        result.errors += 1
                        if result.errors == 1:
                            result.extra["first_error"] = resp.text[:200]
                except Exception as e:
                    result.errors += 1
                    if result.errors == 1:
                        result.extra["first_exception"] = str(e)

        # Calculate per-image time
        if result.times_ms:
            result.extra["per_image_mean_ms"] = result.mean_ms / batch_size

        self.results.append(result)
        return result

    async def benchmark_concurrent_uploads(
        self,
        concurrency: int = 5,
        total_uploads: int = 20,
    ) -> BenchmarkResult:
        """Benchmark concurrent upload performance."""
        result = BenchmarkResult(
            name=f"Concurrent Uploads ({concurrency} parallel, {total_uploads} total)",
            iterations=total_uploads,
        )

        semaphore = asyncio.Semaphore(concurrency)

        async def upload_one(idx: int, client: httpx.AsyncClient) -> float | None:
            async with semaphore:
                payload = {
                    "screenshot": self.test_image_b64,
                    "participant_id": f"concurrent-{idx}",
                    "group_id": f"{self.group_id}-concurrent",
                    "image_type": "screen_time",
                    "sha256": self.test_image_sha256,
                }

                try:
                    start = time.perf_counter()
                    resp = await client.post("/screenshots/upload", json=payload)
                    elapsed = (time.perf_counter() - start) * 1000

                    if resp.status_code in (200, 201):
                        return elapsed
                except Exception:
                    pass
                return None

        async with self._make_async_client() as client:
            start_all = time.perf_counter()
            tasks = [upload_one(i, client) for i in range(total_uploads)]
            times = await asyncio.gather(*tasks)
            total_time = (time.perf_counter() - start_all) * 1000

        for t in times:
            if t is not None:
                result.times_ms.append(t)
            else:
                result.errors += 1

        result.extra["total_wall_time_ms"] = total_time
        result.extra["throughput_per_sec"] = total_uploads / (total_time / 1000) if total_time > 0 else 0

        self.results.append(result)
        return result

    def benchmark_with_memory(self, iterations: int = 5) -> BenchmarkResult:
        """Benchmark upload with memory tracking."""
        if not HAS_TRACEMALLOC:
            print("tracemalloc not available, skipping memory benchmark")
            return BenchmarkResult(name="Memory Benchmark (skipped)", iterations=0)

        result = BenchmarkResult(name="Single Upload (with memory)", iterations=iterations)
        memory_peaks = []

        with self._make_client() as client:
            for i in range(iterations):
                tracemalloc.start()

                payload = {
                    "screenshot": self.test_image_b64,
                    "participant_id": f"mem-{i}",
                    "group_id": f"{self.group_id}-mem",
                    "image_type": "screen_time",
                }

                try:
                    start = time.perf_counter()
                    resp = client.post("/screenshots/upload", json=payload)
                    elapsed = (time.perf_counter() - start) * 1000

                    current, peak = tracemalloc.get_traced_memory()
                    tracemalloc.stop()

                    if resp.status_code in (200, 201):
                        result.times_ms.append(elapsed)
                        memory_peaks.append(peak / 1024 / 1024)  # MB
                    else:
                        result.errors += 1
                except Exception:
                    tracemalloc.stop()
                    result.errors += 1

        if memory_peaks:
            result.extra["memory_peak_mb"] = {
                "mean": statistics.mean(memory_peaks),
                "max": max(memory_peaks),
            }

        self.results.append(result)
        return result

    def profile_upload(self, output_file: str | None = None) -> str:
        """Profile a single upload with cProfile."""
        profiler = cProfile.Profile()

        with self._make_client() as client:
            payload = {
                "screenshot": self.test_image_b64,
                "participant_id": "profile-test",
                "group_id": f"{self.group_id}-profile",
                "image_type": "screen_time",
            }

            profiler.enable()
            client.post("/screenshots/upload", json=payload)
            profiler.disable()

        # Format stats
        stream = io.StringIO()
        stats = pstats.Stats(profiler, stream=stream)
        stats.sort_stats("cumulative")
        stats.print_stats(30)

        profile_output = stream.getvalue()

        if output_file:
            Path(output_file).write_text(profile_output)
            print(f"Profile saved to {output_file}")

        return profile_output

    def run_all(
        self,
        iterations: int = 10,
        include_concurrent: bool = True,
        include_memory: bool = True,
    ) -> None:
        """Run all benchmarks."""
        print("\n" + "=" * 70)
        print("UPLOAD ENDPOINT BENCHMARK SUITE")
        print("=" * 70 + "\n")

        print(f"API URL: {self.api_url}")
        print(f"Group ID: {self.group_id}")
        print(f"Test image: {len(self.test_image):,} bytes\n")

        # Health check baseline
        print("Running: Health Check...")
        self.benchmark_health_check(iterations=iterations)

        # Single uploads
        print("Running: Single Upload (with checksum)...")
        self.benchmark_single_upload(iterations=iterations, with_checksum=True)

        print("Running: Single Upload (without checksum)...")
        self.benchmark_single_upload(iterations=iterations, with_checksum=False)

        # Batch uploads
        for batch_size in [5, 10, 30]:
            print(f"Running: Batch Upload ({batch_size} images)...")
            self.benchmark_batch_upload(batch_size=batch_size, iterations=3)

        # Concurrent uploads
        if include_concurrent:
            print("Running: Concurrent Uploads...")
            asyncio.run(self.benchmark_concurrent_uploads(concurrency=5, total_uploads=20))

        # Memory benchmark
        if include_memory:
            print("Running: Memory Benchmark...")
            self.benchmark_with_memory(iterations=5)

        # Print results
        print("\n" + "=" * 70)
        print("RESULTS")
        print("=" * 70 + "\n")

        for result in self.results:
            print(result.summary())
            print()

        # Summary comparison
        print("=" * 70)
        print("COMPARISON SUMMARY")
        print("=" * 70 + "\n")

        single_with = next((r for r in self.results if "with checksum" in r.name), None)
        single_without = next((r for r in self.results if "without checksum" in r.name), None)
        batch_10 = next((r for r in self.results if "10 images" in r.name), None)

        if single_with and single_without:
            overhead = single_with.mean_ms - single_without.mean_ms
            print(f"Checksum overhead: {overhead:+.2f}ms ({overhead / single_without.mean_ms * 100:+.1f}%)")

        if single_with and batch_10:
            single_time_for_10 = single_with.mean_ms * 10
            batch_time = batch_10.mean_ms
            savings = single_time_for_10 - batch_time
            print(f"Batch vs 10x Single: {savings:.0f}ms savings ({savings / single_time_for_10 * 100:.1f}% faster)")

        concurrent = next((r for r in self.results if "Concurrent" in r.name), None)
        if concurrent and single_with:
            speedup = (single_with.mean_ms * concurrent.iterations) / concurrent.extra.get("total_wall_time_ms", 1)
            print(f"Concurrent speedup: {speedup:.1f}x")

    def run_stress_tests(self) -> None:
        """Run stress tests to find optimal concurrency and batch parameters."""
        print("\n" + "=" * 70)
        print("STRESS TEST SUITE - Finding Optimal Parameters")
        print("=" * 70 + "\n")

        print(f"API URL: {self.api_url}")
        print(f"Test image: {len(self.test_image):,} bytes\n")

        # Test different concurrency levels
        print("=" * 70)
        print("1. CONCURRENCY LEVEL OPTIMIZATION")
        print("=" * 70 + "\n")

        concurrency_results = []
        for concurrency in [1, 2, 5, 10, 15, 20, 30, 50]:
            print(f"Testing concurrency={concurrency}...")
            result = asyncio.run(
                self.benchmark_concurrent_uploads(
                    concurrency=concurrency,
                    total_uploads=50,
                )
            )
            wall_time = result.extra.get("total_wall_time_ms", 0)
            throughput = result.extra.get("throughput_per_sec", 0)
            error_rate = result.errors / (result.iterations + result.errors) * 100
            concurrency_results.append({
                "concurrency": concurrency,
                "wall_time_ms": wall_time,
                "throughput": throughput,
                "mean_latency_ms": result.mean_ms,
                "p95_latency_ms": result.p95_ms,
                "error_rate": error_rate,
            })

        print("\nConcurrency Results:")
        print("-" * 80)
        print(f"{'Concurrency':>12} {'Wall Time':>12} {'Throughput':>12} {'Mean Lat':>12} {'P95 Lat':>12} {'Errors':>10}")
        print("-" * 80)
        for r in concurrency_results:
            print(f"{r['concurrency']:>12} {r['wall_time_ms']:>10.0f}ms {r['throughput']:>10.1f}/s {r['mean_latency_ms']:>10.1f}ms {r['p95_latency_ms']:>10.1f}ms {r['error_rate']:>9.1f}%")

        # Find optimal concurrency (highest throughput with <5% errors)
        valid_results = [r for r in concurrency_results if r["error_rate"] < 5]
        if valid_results:
            optimal = max(valid_results, key=lambda x: x["throughput"])
            print(f"\n[OPTIMAL] Concurrency: {optimal['concurrency']} ({optimal['throughput']:.1f} uploads/sec)")

        # Test different batch sizes
        print("\n" + "=" * 70)
        print("2. BATCH SIZE OPTIMIZATION")
        print("=" * 70 + "\n")

        batch_results = []
        for batch_size in [5, 10, 20, 30, 50, 60]:
            print(f"Testing batch_size={batch_size}...")
            self.results = []  # Reset results
            result = self.benchmark_batch_upload(batch_size=batch_size, iterations=3)
            per_image = result.extra.get("per_image_mean_ms", result.mean_ms / batch_size)
            error_rate = result.errors / (result.iterations + result.errors) * 100
            batch_results.append({
                "batch_size": batch_size,
                "total_time_ms": result.mean_ms,
                "per_image_ms": per_image,
                "p95_ms": result.p95_ms,
                "error_rate": error_rate,
            })

        print("\nBatch Size Results:")
        print("-" * 70)
        print(f"{'Batch Size':>12} {'Total Time':>12} {'Per Image':>12} {'P95':>12} {'Errors':>10}")
        print("-" * 70)
        for r in batch_results:
            print(f"{r['batch_size']:>12} {r['total_time_ms']:>10.0f}ms {r['per_image_ms']:>10.1f}ms {r['p95_ms']:>10.0f}ms {r['error_rate']:>9.1f}%")

        # Find optimal batch size (lowest per-image time with <5% errors)
        valid_results = [r for r in batch_results if r["error_rate"] < 5]
        if valid_results:
            optimal = min(valid_results, key=lambda x: x["per_image_ms"])
            print(f"\n[OPTIMAL] Batch size: {optimal['batch_size']} ({optimal['per_image_ms']:.1f}ms/image)")

        # Sustained load test
        print("\n" + "=" * 70)
        print("3. SUSTAINED LOAD TEST (100 uploads)")
        print("=" * 70 + "\n")

        print("Running sustained load test...")
        start_time = time.perf_counter()
        result = asyncio.run(
            self.benchmark_concurrent_uploads(
                concurrency=10,
                total_uploads=100,
            )
        )
        total_time = (time.perf_counter() - start_time) * 1000

        print("\nSustained Load Results:")
        print("  Total uploads: 100")
        print(f"  Total time: {total_time:.0f}ms ({total_time/1000:.1f}s)")
        print(f"  Throughput: {100 / (total_time/1000):.1f} uploads/sec")
        print(f"  Mean latency: {result.mean_ms:.1f}ms")
        print(f"  P95 latency: {result.p95_ms:.1f}ms")
        print(f"  Errors: {result.errors}")
        print(f"  Success rate: {result.success_rate * 100:.1f}%")

        # Summary recommendations
        print("\n" + "=" * 70)
        print("RECOMMENDATIONS")
        print("=" * 70 + "\n")

        print("Based on stress test results:")
        print("  - Use batch uploads for bulk operations (lower per-image overhead)")
        print("  - Set rate limits based on sustained throughput capacity")
        print("  - Monitor P95 latency for SLA compliance")


def main():
    parser = argparse.ArgumentParser(description="Benchmark upload endpoints")
    parser.add_argument(
        "--api-url",
        default="http://localhost:8001/api/v1",
        help="API base URL",
    )
    parser.add_argument(
        "--api-key",
        default="dev-upload-key-change-in-production",
        help="API key for uploads",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=10,
        help="Number of iterations per benchmark",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Run profiler on single upload",
    )
    parser.add_argument(
        "--profile-output",
        default=None,
        help="File to save profile output",
    )
    parser.add_argument(
        "--skip-concurrent",
        action="store_true",
        help="Skip concurrent upload benchmark",
    )
    parser.add_argument(
        "--skip-memory",
        action="store_true",
        help="Skip memory benchmark",
    )
    parser.add_argument(
        "--stress",
        action="store_true",
        help="Run stress tests to find optimal parameters",
    )

    args = parser.parse_args()

    benchmark = UploadBenchmark(
        api_url=args.api_url,
        api_key=args.api_key,
    )

    if args.profile:
        print("\n" + "=" * 70)
        print("UPLOAD PROFILING")
        print("=" * 70 + "\n")
        profile_output = benchmark.profile_upload(args.profile_output)
        print(profile_output)
    elif args.stress:
        benchmark.run_stress_tests()
    else:
        benchmark.run_all(
            iterations=args.iterations,
            include_concurrent=not args.skip_concurrent,
            include_memory=not args.skip_memory,
        )


if __name__ == "__main__":
    main()
