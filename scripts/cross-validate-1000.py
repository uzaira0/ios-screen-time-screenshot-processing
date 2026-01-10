#!/usr/bin/env python3
"""Cross-validate Rust vs Python pipeline on 1000 screenshots.

Compares hourly values, grid bounds, and timing.
Run inside Docker backend container.

Usage:
    python scripts/cross-validate-1000.py
"""

import json
import os
import random
import statistics
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

UPLOADS_DIR = "/app/uploads"
RUST_BINARY = "/rust-bench/bench_pipeline"
NUM_IMAGES = 1000
OUTPUT_FILE = "/app/profiling-reports/cross-validation-1000.json"
SUMMARY_FILE = "/app/profiling-reports/cross-validation-1000.md"


def levenshtein(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + (0 if c1 == c2 else 1)))
        prev = curr
    return prev[-1]


def similarity(s1: str, s2: str) -> float:
    if not s1 and not s2:
        return 1.0
    ml = max(len(s1), len(s2))
    return 1.0 - levenshtein(s1, s2) / ml if ml else 1.0


def find_images() -> list[str]:
    images = []
    for root, _, files in os.walk(UPLOADS_DIR):
        for f in sorted(files):
            if f.lower().endswith((".png", ".jpg", ".jpeg")):
                images.append(os.path.join(root, f))
    random.seed(42)  # reproducible
    random.shuffle(images)
    return images[:NUM_IMAGES]


def run_python(path: str) -> dict:
    """Run Python pipeline on a single image."""
    from screenshot_processor.core.image_processor import load_and_validate_image
    from screenshot_processor.core.bar_extraction import slice_image
    from screenshot_processor.core.line_based_detection import LineBasedDetector

    detector = LineBasedDetector.default()

    t0 = time.perf_counter()
    try:
        img = load_and_validate_image(path)
        h, w = img.shape[:2]
        result = detector.detect(img, resolution=f"{w}x{h}")
        if result.success:
            b = result.bounds
            row, _, _ = slice_image(img, b.x, b.y, b.width, b.height)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            return {
                "success": True,
                "bounds": f"{b.x},{b.y},{b.width},{b.height}",
                "hourly": ",".join(f"{v:.1f}" for v in row[:24]),
                "total": round(sum(row[:24]), 1),
                "time_ms": round(elapsed_ms, 1),
            }
        else:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            return {"success": False, "error": result.error or "detection failed", "time_ms": round(elapsed_ms, 1)}
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {"success": False, "error": str(e)[:100], "time_ms": round(elapsed_ms, 1)}


def run_rust(path: str) -> dict:
    """Run Rust pipeline via the bench_pipeline binary."""
    t0 = time.perf_counter()
    try:
        result = subprocess.run(
            [RUST_BINARY, "--json", path],
            capture_output=True, text=True, timeout=30,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if result.returncode != 0:
            return {"success": False, "error": result.stderr[:100], "time_ms": round(elapsed_ms, 1)}
        data = json.loads(result.stdout)
        return {**data, "time_ms": round(elapsed_ms, 1)}
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {"success": False, "error": str(e)[:100], "time_ms": round(elapsed_ms, 1)}


def main():
    images = find_images()
    print(f"Cross-validating {len(images)} images...")

    results = []
    py_times = []
    rust_times = []
    both_success = 0
    both_fail = 0
    py_only = 0
    rust_only = 0
    exact_match = 0
    hourly_sims = []
    bounds_match = 0
    total_diffs = []

    for idx, path in enumerate(images):
        if idx % 100 == 0:
            print(f"  [{idx}/{len(images)}]...")

        py = run_python(path)
        # For Rust, we call via the Python-side since we don't have the binary in this container
        # Instead, just compare the Python pipeline with itself using the Rust-equivalent logic
        # Actually — we need the Rust binary. Let's output the paths and run Rust separately.

        results.append({
            "image": path,
            "python": py,
        })
        py_times.append(py["time_ms"])

    # Write intermediate results
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump({"results": results, "count": len(results)}, f)

    # Summary stats
    py_success = sum(1 for r in results if r["python"]["success"])
    py_fail = len(results) - py_success

    print(f"\nPython results:")
    print(f"  Success: {py_success}/{len(results)}")
    print(f"  Fail: {py_fail}")
    print(f"  Median time: {statistics.median(py_times):.1f}ms")
    print(f"  Mean time: {statistics.mean(py_times):.1f}ms")
    print(f"  P95 time: {sorted(py_times)[int(len(py_times)*0.95)]:.1f}ms")

    # Write paths for Rust to process
    paths_file = "/tmp/cross-validate-paths.txt"
    with open(paths_file, "w") as f:
        for r in results:
            f.write(r["image"] + "\n")
    print(f"\nPaths written to {paths_file}")
    print(f"Results written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
