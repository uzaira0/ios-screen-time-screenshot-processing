#!/usr/bin/env python3
"""OCR Binding Benchmark — compares pytesseract, Tesseract.js, leptess, tesseract-rs.

Run inside Docker backend (has Tesseract + all uploaded images):
    python scripts/benchmark-ocr.py

For each uploaded image in uploads/:
  For each available binding:
    1. Extract full text (PSM 3 + PSM 6)
    2. Extract word-level bounding boxes (where supported)
    3. Record: text output, bbox list, latency_ms, peak_memory_kb

Output:
  profiling-reports/ocr-benchmark/results.json
  profiling-reports/ocr-benchmark/similarity_matrix.md
  profiling-reports/ocr-benchmark/summary.md
"""

from __future__ import annotations

import json
import os
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

UPLOADS_DIR = Path(os.environ.get("UPLOADS_DIR", "uploads"))
OUTPUT_DIR = Path("profiling-reports/ocr-benchmark")
NUM_RUNS = 3  # median of N runs
MAX_IMAGES = 20  # cap for speed; set 0 for all
PSM_MODES = [3, 6]

# ---------------------------------------------------------------------------
# Binding wrappers
# ---------------------------------------------------------------------------


class BenchmarkResult:
    """Single OCR run result."""

    def __init__(
        self,
        binding: str,
        image_path: str,
        psm: int,
        text: str,
        bboxes: list[dict] | None,
        latency_ms: float,
        peak_memory_kb: int,
    ):
        self.binding = binding
        self.image_path = image_path
        self.psm = psm
        self.text = text
        self.bboxes = bboxes
        self.latency_ms = latency_ms
        self.peak_memory_kb = peak_memory_kb

    def to_dict(self) -> dict:
        return {
            "binding": self.binding,
            "image": self.image_path,
            "psm": self.psm,
            "text": self.text,
            "bbox_count": len(self.bboxes) if self.bboxes else 0,
            "latency_ms": round(self.latency_ms, 2),
            "peak_memory_kb": self.peak_memory_kb,
        }


def _get_rss_kb() -> int:
    """Get current RSS in KB (Linux, via /proc/self/statm)."""
    try:
        with open("/proc/self/statm") as f:
            pages = int(f.read().split()[1])  # resident pages
        return pages * (os.sysconf("SC_PAGE_SIZE") // 1024)
    except (FileNotFoundError, ValueError):
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


# --- pytesseract ---


def _bench_pytesseract(img: np.ndarray, psm: int) -> tuple[str, list[dict] | None]:
    """Run pytesseract and return (text, bboxes)."""
    from pytesseract import Output, pytesseract

    config = f"--psm {psm}"

    # Text extraction
    text = pytesseract.image_to_string(img, config=config)

    # Bounding boxes (word-level)
    data = pytesseract.image_to_data(img, config=config, output_type=Output.DICT)
    bboxes = []
    for i in range(len(data["text"])):
        if data["text"][i].strip():
            bboxes.append(
                {
                    "text": data["text"][i],
                    "x": data["left"][i],
                    "y": data["top"][i],
                    "w": data["width"][i],
                    "h": data["height"][i],
                    "conf": data["conf"][i],
                }
            )

    return text.strip(), bboxes


# --- Tesseract.js (via Node subprocess) ---

TESSERACT_JS_SCRIPT = """
const Tesseract = require('tesseract.js');
const fs = require('fs');

const [imagePath, psm] = process.argv.slice(2);

(async () => {
  const worker = await Tesseract.createWorker('eng');
  await worker.setParameters({ tessedit_pageseg_mode: psm });

  const { data } = await worker.recognize(imagePath);

  const result = {
    text: data.text.trim(),
    bboxes: data.words.map(w => ({
      text: w.text,
      x: w.bbox.x0,
      y: w.bbox.y0,
      w: w.bbox.x1 - w.bbox.x0,
      h: w.bbox.y1 - w.bbox.y0,
      conf: w.confidence,
    })),
  };

  console.log(JSON.stringify(result));
  await worker.terminate();
})();
"""


def _bench_tesseract_js(image_path: str, psm: int) -> tuple[str, list[dict] | None]:
    """Run Tesseract.js via Node subprocess."""
    # Write temp script
    script_path = "/tmp/bench_tjs.js"
    with open(script_path, "w") as f:
        f.write(TESSERACT_JS_SCRIPT)

    try:
        result = subprocess.run(
            ["node", script_path, image_path, str(psm)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return f"ERROR: {result.stderr[:200]}", None

        data = json.loads(result.stdout)
        return data["text"], data.get("bboxes")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        return f"ERROR: {e}", None


# --- leptess (Rust, via compiled binary) ---


def _bench_leptess(image_path: str, psm: int) -> tuple[str, list[dict] | None]:
    """Run leptess benchmark binary if available."""
    binary = Path("frontend/src-tauri/target/release/bench_leptess")
    if not binary.exists():
        binary = Path("target/release/bench_leptess")
    if not binary.exists():
        return "NOT_AVAILABLE", None

    try:
        result = subprocess.run(
            [str(binary), image_path, str(psm)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return f"ERROR: {result.stderr[:200]}", None
        data = json.loads(result.stdout)
        return data["text"], data.get("bboxes")
    except Exception as e:
        return f"ERROR: {e}", None


# --- tesseract-rs (Rust, via compiled binary) ---


def _bench_tesseract_rs(image_path: str, psm: int) -> tuple[str, list[dict] | None]:
    """Run tesseract-rs benchmark binary if available."""
    binary = Path("frontend/src-tauri/target/release/bench_tesseract_rs")
    if not binary.exists():
        binary = Path("target/release/bench_tesseract_rs")
    if not binary.exists():
        return "NOT_AVAILABLE", None

    try:
        result = subprocess.run(
            [str(binary), image_path, str(psm)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return f"ERROR: {result.stderr[:200]}", None
        data = json.loads(result.stdout)
        return data["text"], data.get("bboxes")
    except Exception as e:
        return f"ERROR: {e}", None


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

BINDINGS = {
    "pytesseract": lambda img, path, psm: _bench_pytesseract(img, psm),
    "tesseract_js": lambda img, path, psm: _bench_tesseract_js(path, psm),
    "leptess": lambda img, path, psm: _bench_leptess(path, psm),
    "tesseract_rs": lambda img, path, psm: _bench_tesseract_rs(path, psm),
}


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr_row.append(min(curr_row[j] + 1, prev_row[j + 1] + 1, prev_row[j] + cost))
        prev_row = curr_row

    return prev_row[-1]


def _normalized_similarity(s1: str, s2: str) -> float:
    """Normalized Levenshtein similarity (1.0 = identical)."""
    if not s1 and not s2:
        return 1.0
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    return 1.0 - _levenshtein_distance(s1, s2) / max_len


def _bbox_iou(bboxes1: list[dict], bboxes2: list[dict]) -> float:
    """Compute average IoU between two sets of bounding boxes (greedy matching)."""
    if not bboxes1 or not bboxes2:
        return 0.0

    def _iou(b1: dict, b2: dict) -> float:
        x1 = max(b1["x"], b2["x"])
        y1 = max(b1["y"], b2["y"])
        x2 = min(b1["x"] + b1["w"], b2["x"] + b2["w"])
        y2 = min(b1["y"] + b1["h"], b2["y"] + b2["h"])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = b1["w"] * b1["h"]
        area2 = b2["w"] * b2["h"]
        union = area1 + area2 - inter
        return inter / union if union > 0 else 0.0

    total_iou = 0.0
    used = set()
    for b1 in bboxes1:
        best_iou = 0.0
        best_idx = -1
        for j, b2 in enumerate(bboxes2):
            if j in used:
                continue
            iou = _iou(b1, b2)
            if iou > best_iou:
                best_iou = iou
                best_idx = j
        if best_idx >= 0:
            used.add(best_idx)
            total_iou += best_iou

    return total_iou / max(len(bboxes1), len(bboxes2))


def find_images() -> list[Path]:
    """Find uploaded images to benchmark."""
    extensions = {".png", ".jpg", ".jpeg", ".webp"}
    images = []
    for f in sorted(UPLOADS_DIR.rglob("*")):
        if f.suffix.lower() in extensions and f.is_file():
            images.append(f)
    if MAX_IMAGES > 0:
        images = images[:MAX_IMAGES]
    return images


def run_benchmark() -> dict:
    """Run the full benchmark suite."""
    images = find_images()
    if not images:
        print(f"No images found in {UPLOADS_DIR}")
        sys.exit(1)

    print(f"Benchmarking {len(images)} images across {len(BINDINGS)} bindings")

    all_results: list[dict] = []
    per_binding_texts: dict[str, list[str]] = {b: [] for b in BINDINGS}
    per_binding_bboxes: dict[str, list[list[dict]]] = {b: [] for b in BINDINGS}
    per_binding_latencies: dict[str, list[float]] = {b: [] for b in BINDINGS}

    for img_idx, img_path in enumerate(images):
        print(f"\n[{img_idx + 1}/{len(images)}] {img_path.name}")
        img = cv2.imread(str(img_path))
        if img is None:
            print(f"  SKIP: could not load")
            continue

        for binding_name, bench_fn in BINDINGS.items():
            for psm in PSM_MODES:
                latencies = []
                last_text = ""
                last_bboxes = None

                for run in range(NUM_RUNS):
                    mem_before = _get_rss_kb()
                    t0 = time.perf_counter()
                    text, bboxes = bench_fn(img, str(img_path), psm)
                    elapsed_ms = (time.perf_counter() - t0) * 1000
                    mem_after = _get_rss_kb()

                    latencies.append(elapsed_ms)
                    last_text = text
                    last_bboxes = bboxes

                median_latency = statistics.median(latencies)
                result = BenchmarkResult(
                    binding=binding_name,
                    image_path=str(img_path),
                    psm=psm,
                    text=last_text,
                    bboxes=last_bboxes,
                    latency_ms=median_latency,
                    peak_memory_kb=mem_after - mem_before if mem_after > mem_before else 0,
                )
                all_results.append(result.to_dict())

                if psm == PSM_MODES[0]:  # track for similarity matrix
                    per_binding_texts[binding_name].append(last_text)
                    per_binding_bboxes[binding_name].append(last_bboxes or [])
                    per_binding_latencies[binding_name].append(median_latency)

                status = "OK" if not last_text.startswith("ERROR") and last_text != "NOT_AVAILABLE" else last_text[:40]
                print(f"  {binding_name} PSM{psm}: {median_latency:.0f}ms [{status}]")

    # Compute similarity matrix
    binding_names = list(BINDINGS.keys())
    similarity_matrix: dict[str, dict[str, float]] = {}
    bbox_iou_matrix: dict[str, dict[str, float]] = {}

    for b1 in binding_names:
        similarity_matrix[b1] = {}
        bbox_iou_matrix[b1] = {}
        for b2 in binding_names:
            texts1 = per_binding_texts[b1]
            texts2 = per_binding_texts[b2]
            if texts1 and texts2 and len(texts1) == len(texts2):
                sims = [_normalized_similarity(t1, t2) for t1, t2 in zip(texts1, texts2)]
                similarity_matrix[b1][b2] = round(statistics.mean(sims), 4)

                bboxes1 = per_binding_bboxes[b1]
                bboxes2 = per_binding_bboxes[b2]
                ious = [_bbox_iou(bb1, bb2) for bb1, bb2 in zip(bboxes1, bboxes2)]
                bbox_iou_matrix[b1][b2] = round(statistics.mean(ious), 4)
            else:
                similarity_matrix[b1][b2] = 0.0
                bbox_iou_matrix[b1][b2] = 0.0

    # Compute per-binding summary stats
    summary_stats = {}
    for b in binding_names:
        lats = per_binding_latencies[b]
        available_texts = [t for t in per_binding_texts[b] if not t.startswith("ERROR") and t != "NOT_AVAILABLE"]
        summary_stats[b] = {
            "available": len(available_texts) > 0,
            "images_processed": len(available_texts),
            "total_images": len(per_binding_texts[b]),
            "median_latency_ms": round(statistics.median(lats), 1) if lats else 0,
            "mean_latency_ms": round(statistics.mean(lats), 1) if lats else 0,
            "p95_latency_ms": round(sorted(lats)[int(len(lats) * 0.95)] if lats else 0, 1),
            "has_bboxes": any(bb for bb in per_binding_bboxes[b]),
        }

    return {
        "results": all_results,
        "similarity_matrix": similarity_matrix,
        "bbox_iou_matrix": bbox_iou_matrix,
        "summary_stats": summary_stats,
        "config": {
            "num_runs": NUM_RUNS,
            "max_images": MAX_IMAGES,
            "psm_modes": PSM_MODES,
            "num_images": len(images),
        },
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def write_results(data: dict) -> None:
    """Write benchmark results to files."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Raw JSON
    with open(OUTPUT_DIR / "results.json", "w") as f:
        json.dump(data, f, indent=2)

    # Similarity matrix markdown
    bindings = list(data["similarity_matrix"].keys())
    with open(OUTPUT_DIR / "similarity_matrix.md", "w") as f:
        f.write("# OCR Text Similarity Matrix\n\n")
        f.write("Normalized Levenshtein similarity (1.0 = identical output)\n\n")
        f.write("| | " + " | ".join(bindings) + " |\n")
        f.write("|" + "---|" * (len(bindings) + 1) + "\n")
        for b1 in bindings:
            row = [f"{data['similarity_matrix'][b1].get(b2, 0):.3f}" for b2 in bindings]
            f.write(f"| **{b1}** | " + " | ".join(row) + " |\n")

        f.write("\n## Bounding Box IoU Matrix\n\n")
        f.write("| | " + " | ".join(bindings) + " |\n")
        f.write("|" + "---|" * (len(bindings) + 1) + "\n")
        for b1 in bindings:
            row = [f"{data['bbox_iou_matrix'][b1].get(b2, 0):.3f}" for b2 in bindings]
            f.write(f"| **{b1}** | " + " | ".join(row) + " |\n")

    # Summary markdown
    stats = data["summary_stats"]
    with open(OUTPUT_DIR / "summary.md", "w") as f:
        f.write("# OCR Benchmark Summary\n\n")
        f.write(f"Images tested: {data['config']['num_images']}\n")
        f.write(f"Runs per image: {data['config']['num_runs']} (median taken)\n\n")

        f.write("## Per-Binding Results\n\n")
        f.write("| Binding | Available | Images | Median ms | Mean ms | P95 ms | Bboxes |\n")
        f.write("|---------|-----------|--------|-----------|---------|--------|--------|\n")
        for b, s in stats.items():
            avail = "Yes" if s["available"] else "No"
            bbox = "Yes" if s["has_bboxes"] else "No"
            f.write(
                f"| {b} | {avail} | {s['images_processed']}/{s['total_images']} | "
                f"{s['median_latency_ms']} | {s['mean_latency_ms']} | {s['p95_latency_ms']} | {bbox} |\n"
            )

        f.write("\n## Recommendation\n\n")
        # Auto-generate recommendation based on data
        available = {b: s for b, s in stats.items() if s["available"]}
        if not available:
            f.write("No bindings were available for testing.\n")
        else:
            # Rank by: has_bboxes (required), then latency
            ranked = sorted(
                available.items(),
                key=lambda x: (not x[1]["has_bboxes"], x[1]["median_latency_ms"]),
            )
            winner = ranked[0]
            f.write(f"**Recommended binding: `{winner[0]}`**\n\n")
            f.write("Criteria (in priority order):\n")
            f.write("1. Bbox support (required for OCR-anchored grid detection)\n")
            f.write("2. Text accuracy (similarity to pytesseract baseline)\n")
            f.write("3. Latency (lower is better)\n")
            f.write("4. Build complexity (self-contained > system deps)\n\n")

            for b, s in ranked:
                sim = data["similarity_matrix"].get("pytesseract", {}).get(b, "N/A")
                f.write(f"- **{b}**: {s['median_latency_ms']}ms median, bboxes={'yes' if s['has_bboxes'] else 'no'}, ")
                f.write(f"similarity to pytesseract: {sim}\n")

    print(f"\nResults written to {OUTPUT_DIR}/")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    data = run_benchmark()
    write_results(data)
