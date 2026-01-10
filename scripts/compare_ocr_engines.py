#!/usr/bin/env python
"""Compare OCR engines (Tesseract vs HunyuanOCR) on iOS screenshots.

This script:
1. Discovers screenshots from local data directories or Delta Lake tables
2. Runs both Tesseract and HunyuanOCR on each image
3. Outputs a comparison CSV with extracted text from both engines

Usage:
    # Compare first 10 screenshots from local data
    python scripts/compare_ocr_engines.py --limit 10

    # Compare all screenshots, output to specific file
    python scripts/compare_ocr_engines.py --output ocr_comparison.csv

    # Use specific directory
    python scripts/compare_ocr_engines.py --input-dir ./data/SAMPLE-001\ Cropped

    # Read from Delta Lake catalog (if available)
    python scripts/compare_ocr_engines.py --from-delta
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import httpx
from PIL import Image


@dataclass
class OCRComparisonResult:
    """Result from comparing OCR engines on a single image."""

    file_path: str
    participant_id: str
    tesseract_text: str
    tesseract_time_ms: float
    tesseract_error: str | None
    hunyuan_text: str
    hunyuan_time_ms: float
    hunyuan_error: str | None
    text_match: bool
    similarity_score: float


def extract_participant_id(file_path: Path) -> str:
    """Extract participant ID from file path."""
    path_str = str(file_path)
    # Look for P3-XXXX pattern
    import re

    match = re.search(r"P\d-\d{4}", path_str)
    return match.group(0) if match else "unknown"


def run_tesseract_ocr(image_bytes: bytes) -> tuple[str, float, str | None]:
    """Run Tesseract OCR on image bytes.

    Returns:
        Tuple of (text, time_ms, error)
    """
    start = time.perf_counter()
    try:
        import pytesseract

        image = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(image, lang="eng")
        elapsed_ms = (time.perf_counter() - start) * 1000
        return text.strip(), elapsed_ms, None
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return "", elapsed_ms, str(e)


def run_hunyuan_ocr(
    image_bytes: bytes,
    base_url: str = "http://YOUR_OCR_HOST:8080",
    timeout: int = 120,
) -> tuple[str, float, str | None]:
    """Run HunyuanOCR on image bytes.

    Returns:
        Tuple of (text, time_ms, error)
    """
    start = time.perf_counter()
    try:
        files = [("images", ("image.png", image_bytes, "image/png"))]
        # IMPORTANT: Must pass explicit prompt or model may return "<image>"
        params = {"prompt": "Extract all text from this iOS screenshot"}
        with httpx.Client(timeout=timeout) as client:
            response = client.post(f"{base_url}/ocr", files=files, params=params)
            response.raise_for_status()
            data = response.json()
            text = data.get("text", "")
            elapsed_ms = (time.perf_counter() - start) * 1000
            return text.strip(), elapsed_ms, None
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return "", elapsed_ms, str(e)


def calculate_similarity(text1: str, text2: str) -> float:
    """Calculate simple similarity score between two texts.

    Uses Jaccard similarity on word sets.
    """
    if not text1 and not text2:
        return 1.0
    if not text1 or not text2:
        return 0.0

    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())

    if not words1 and not words2:
        return 1.0

    intersection = words1 & words2
    union = words1 | words2

    return len(intersection) / len(union) if union else 0.0


def process_single_image(
    file_path: Path,
    hunyuan_url: str,
) -> OCRComparisonResult:
    """Process a single image with both OCR engines."""
    print(f"Processing: {file_path.name}")

    # Read image
    image_bytes = file_path.read_bytes()
    participant_id = extract_participant_id(file_path)

    # Run Tesseract
    tess_text, tess_time, tess_error = run_tesseract_ocr(image_bytes)

    # Run HunyuanOCR
    hunyuan_text, hunyuan_time, hunyuan_error = run_hunyuan_ocr(
        image_bytes, base_url=hunyuan_url
    )

    # Calculate similarity
    similarity = calculate_similarity(tess_text, hunyuan_text)
    text_match = similarity > 0.8

    return OCRComparisonResult(
        file_path=str(file_path),
        participant_id=participant_id,
        tesseract_text=tess_text,
        tesseract_time_ms=tess_time,
        tesseract_error=tess_error,
        hunyuan_text=hunyuan_text,
        hunyuan_time_ms=hunyuan_time,
        hunyuan_error=hunyuan_error,
        text_match=text_match,
        similarity_score=similarity,
    )


def discover_screenshots(input_dir: Path, limit: int | None = None) -> list[Path]:
    """Discover screenshot files in directory."""
    patterns = ["**/*.png", "**/*.jpg", "**/*.jpeg"]
    files: list[Path] = []

    for pattern in patterns:
        files.extend(input_dir.glob(pattern))

    # Sort by name for consistency
    files = sorted(set(files), key=lambda p: str(p))

    # Skip "Do Not Use" directory
    files = [f for f in files if "Do Not Use" not in str(f)]

    if limit:
        files = files[:limit]

    return files


def check_hunyuan_health(url: str) -> bool:
    """Check if HunyuanOCR endpoint is available."""
    try:
        with httpx.Client(timeout=5) as client:
            response = client.get(f"{url}/health")
            return response.status_code == 200
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Compare Tesseract and HunyuanOCR on screenshots"
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data"),
        help="Directory containing screenshots (default: data/)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("ocr_comparison.csv"),
        help="Output CSV file (default: ocr_comparison.csv)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of screenshots to process",
    )
    parser.add_argument(
        "--hunyuan-url",
        type=str,
        default="http://YOUR_OCR_HOST:8080",
        help="HunyuanOCR API URL",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel workers (default: 1 for rate limiting)",
    )
    parser.add_argument(
        "--from-delta",
        action="store_true",
        help="Read file paths from Delta Lake catalog instead of local directory",
    )

    args = parser.parse_args()

    # Check HunyuanOCR availability
    print(f"Checking HunyuanOCR at {args.hunyuan_url}...")
    if not check_hunyuan_health(args.hunyuan_url):
        print("WARNING: HunyuanOCR endpoint not available!")
        print("HunyuanOCR results will show errors.")
    else:
        print("HunyuanOCR endpoint is healthy.")

    # Discover screenshots
    if args.from_delta:
        print("Delta Lake mode not yet implemented - using local directory")
        # TODO: Read from Delta Lake catalog
        # from deltalake import DeltaTable
        # dt = DeltaTable("../pipeline/data/warehouse/tech/ios_raw_catalog")
        # df = dt.to_pandas()
        # files = [Path(p) for p in df["file_path"]]

    print(f"Discovering screenshots in {args.input_dir}...")
    files = discover_screenshots(args.input_dir, limit=args.limit)
    print(f"Found {len(files)} screenshots")

    if not files:
        print("No screenshots found!")
        sys.exit(1)

    # Process images
    results: list[OCRComparisonResult] = []

    if args.workers == 1:
        # Sequential processing (respects rate limiting)
        for i, file_path in enumerate(files, 1):
            print(f"[{i}/{len(files)}] ", end="")
            result = process_single_image(file_path, args.hunyuan_url)
            results.append(result)
    else:
        # Parallel processing
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(process_single_image, fp, args.hunyuan_url): fp
                for fp in files
            }
            for i, future in enumerate(as_completed(futures), 1):
                print(f"[{i}/{len(files)}] ", end="")
                result = future.result()
                results.append(result)

    # Write CSV output
    print(f"\nWriting results to {args.output}...")

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "file_path",
                "participant_id",
                "tesseract_text",
                "tesseract_time_ms",
                "tesseract_error",
                "hunyuan_text",
                "hunyuan_time_ms",
                "hunyuan_error",
                "text_match",
                "similarity_score",
            ]
        )

        for r in results:
            writer.writerow(
                [
                    r.file_path,
                    r.participant_id,
                    r.tesseract_text[:5000] if r.tesseract_text else "",  # Truncate
                    f"{r.tesseract_time_ms:.1f}",
                    r.tesseract_error or "",
                    r.hunyuan_text[:5000] if r.hunyuan_text else "",  # Truncate
                    f"{r.hunyuan_time_ms:.1f}",
                    r.hunyuan_error or "",
                    r.text_match,
                    f"{r.similarity_score:.3f}",
                ]
            )

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total screenshots: {len(results)}")

    tess_success = sum(1 for r in results if not r.tesseract_error)
    hunyuan_success = sum(1 for r in results if not r.hunyuan_error)
    print(f"Tesseract success: {tess_success}/{len(results)}")
    print(f"HunyuanOCR success: {hunyuan_success}/{len(results)}")

    if results:
        avg_tess_time = sum(r.tesseract_time_ms for r in results) / len(results)
        avg_hunyuan_time = sum(r.hunyuan_time_ms for r in results) / len(results)
        avg_similarity = sum(r.similarity_score for r in results) / len(results)
        matches = sum(1 for r in results if r.text_match)

        print(f"Avg Tesseract time: {avg_tess_time:.1f}ms")
        print(f"Avg HunyuanOCR time: {avg_hunyuan_time:.1f}ms")
        print(f"Avg similarity score: {avg_similarity:.3f}")
        print(f"High similarity matches (>0.8): {matches}/{len(results)}")

    print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
