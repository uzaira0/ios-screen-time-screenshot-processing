#!/usr/bin/env python
"""Compare all OCR engines (Tesseract, PaddleOCR, HunyuanOCR) on iOS screenshots.

This script:
1. Discovers screenshots from local data directories
2. Runs Tesseract, PaddleOCR, and HunyuanOCR on each image
3. Outputs a comparison CSV with extracted text and bounding box info

Usage:
    python scripts/compare_all_ocr_engines.py --limit 5
    python scripts/compare_all_ocr_engines.py --output ocr_all_comparison.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np
from PIL import Image


@dataclass
class OCREngineResult:
    """Result from a single OCR engine."""

    text: str
    time_ms: float
    error: str | None
    bbox_count: int  # Number of bounding boxes returned
    has_bboxes: bool  # Whether this engine returns bboxes


@dataclass
class OCRComparisonResult:
    """Result from comparing all OCR engines on a single image."""

    file_path: str
    participant_id: str
    tesseract: OCREngineResult
    paddleocr: OCREngineResult
    hunyuan: OCREngineResult


def extract_participant_id(file_path: Path) -> str:
    """Extract participant ID from file path."""
    path_str = str(file_path)
    match = re.search(r"P\d-\d{4}", path_str)
    return match.group(0) if match else "unknown"


def run_tesseract_ocr(image: np.ndarray) -> OCREngineResult:
    """Run Tesseract OCR on image."""
    start = time.perf_counter()
    try:
        import pytesseract
        from pytesseract import Output

        # Get detailed output with bboxes
        pil_image = Image.fromarray(image)
        data = pytesseract.image_to_data(pil_image, lang="eng", output_type=Output.DICT)

        # Extract text and count bboxes
        text_parts = []
        bbox_count = 0
        for i, text in enumerate(data["text"]):
            if text.strip() and data["conf"][i] > 0:
                text_parts.append(text.strip())
                bbox_count += 1

        elapsed_ms = (time.perf_counter() - start) * 1000
        return OCREngineResult(
            text=" ".join(text_parts),
            time_ms=elapsed_ms,
            error=None,
            bbox_count=bbox_count,
            has_bboxes=True,
        )
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return OCREngineResult(
            text="",
            time_ms=elapsed_ms,
            error=str(e),
            bbox_count=0,
            has_bboxes=True,
        )


def run_paddleocr(
    image_bytes: bytes,
    base_url: str = "http://localhost:8081",
    timeout: int = 120,
) -> OCREngineResult:
    """Run PaddleOCR on image via remote server."""
    start = time.perf_counter()
    try:
        files = [("images", ("image.png", image_bytes, "image/png"))]

        with httpx.Client(timeout=timeout) as client:
            response = client.post(f"{base_url}/ocr", files=files)
            response.raise_for_status()
            data = response.json()

            # Extract text and bbox count from response
            text = data.get("text", "")
            detections = data.get("detections", [])
            bbox_count = len(detections)

            elapsed_ms = (time.perf_counter() - start) * 1000
            return OCREngineResult(
                text=text,
                time_ms=elapsed_ms,
                error=None,
                bbox_count=bbox_count,
                has_bboxes=True,
            )
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return OCREngineResult(
            text="",
            time_ms=elapsed_ms,
            error=str(e),
            bbox_count=0,
            has_bboxes=True,
        )


def run_hunyuan_ocr(
    image_bytes: bytes,
    base_url: str = "http://YOUR_OCR_HOST:8080",
    timeout: int = 120,
) -> OCREngineResult:
    """Run HunyuanOCR on image."""
    start = time.perf_counter()
    try:
        files = [("images", ("image.png", image_bytes, "image/png"))]
        # IMPORTANT: Must pass explicit prompt or model may return "<image>"
        params = {"prompt": "Extract all text from this iOS screenshot"}

        with httpx.Client(timeout=timeout) as client:
            response = client.post(f"{base_url}/ocr", files=files, params=params)
            response.raise_for_status()
            data = response.json()
            text = data.get("text", "").strip()

            elapsed_ms = (time.perf_counter() - start) * 1000
            return OCREngineResult(
                text=text,
                time_ms=elapsed_ms,
                error=None,
                bbox_count=0,  # Hunyuan doesn't return bboxes
                has_bboxes=False,
            )
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return OCREngineResult(
            text="",
            time_ms=elapsed_ms,
            error=str(e),
            bbox_count=0,
            has_bboxes=False,
        )


def check_hunyuan_health(url: str) -> bool:
    """Check if HunyuanOCR endpoint is available."""
    try:
        with httpx.Client(timeout=5) as client:
            response = client.get(f"{url}/health")
            return response.status_code == 200
    except Exception:
        return False


def check_paddleocr_health(url: str) -> bool:
    """Check if PaddleOCR endpoint is available."""
    try:
        with httpx.Client(timeout=5) as client:
            response = client.get(f"{url}/health")
            return response.status_code == 200
    except Exception:
        return False


def process_single_image(
    file_path: Path,
    hunyuan_url: str,
    paddleocr_url: str,
    run_hunyuan: bool = True,
    run_paddle: bool = True,
) -> OCRComparisonResult:
    """Process a single image with all OCR engines."""
    print(f"  Processing: {file_path.name}")

    # Load image
    pil_image = Image.open(file_path).convert("RGB")
    image_array = np.array(pil_image)

    # Get PNG bytes for remote APIs
    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    image_bytes = buffer.getvalue()

    participant_id = extract_participant_id(file_path)

    # Run Tesseract
    print("    - Tesseract...", end=" ", flush=True)
    tesseract_result = run_tesseract_ocr(image_array)
    print(f"{tesseract_result.time_ms:.0f}ms, {tesseract_result.bbox_count} bboxes")

    # Run PaddleOCR (remote server)
    if run_paddle:
        print("    - PaddleOCR...", end=" ", flush=True)
        paddle_result = run_paddleocr(image_bytes, base_url=paddleocr_url)
        status = f"{paddle_result.time_ms:.0f}ms, {paddle_result.bbox_count} bboxes" if not paddle_result.error else f"ERROR: {paddle_result.error[:30]}"
        print(status)
    else:
        paddle_result = OCREngineResult(
            text="", time_ms=0, error="Skipped", bbox_count=0, has_bboxes=True
        )

    # Run HunyuanOCR (remote server)
    if run_hunyuan:
        print("    - HunyuanOCR...", end=" ", flush=True)
        hunyuan_result = run_hunyuan_ocr(image_bytes, base_url=hunyuan_url)
        status = f"{hunyuan_result.time_ms:.0f}ms" if not hunyuan_result.error else f"ERROR: {hunyuan_result.error[:30]}"
        print(f"{status}, no bboxes")
    else:
        hunyuan_result = OCREngineResult(
            text="", time_ms=0, error="Skipped", bbox_count=0, has_bboxes=False
        )

    return OCRComparisonResult(
        file_path=str(file_path),
        participant_id=participant_id,
        tesseract=tesseract_result,
        paddleocr=paddle_result,
        hunyuan=hunyuan_result,
    )


def discover_screenshots(input_dir: Path, limit: int | None = None) -> list[Path]:
    """Discover screenshot files in directory."""
    patterns = ["**/*.png", "**/*.jpg", "**/*.jpeg"]
    files: list[Path] = []

    for pattern in patterns:
        files.extend(input_dir.glob(pattern))

    # Sort and dedupe
    files = sorted(set(files), key=lambda p: str(p))

    # Skip "Do Not Use" directory
    files = [f for f in files if "Do Not Use" not in str(f)]

    if limit:
        files = files[:limit]

    return files


def main():
    parser = argparse.ArgumentParser(
        description="Compare Tesseract, PaddleOCR, and HunyuanOCR on screenshots"
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
        default=Path("ocr_all_comparison.csv"),
        help="Output CSV file (default: ocr_all_comparison.csv)",
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
        "--paddleocr-url",
        type=str,
        default="http://YOUR_OCR_HOST:8081",
        help="PaddleOCR API URL",
    )
    parser.add_argument(
        "--skip-hunyuan",
        action="store_true",
        help="Skip HunyuanOCR (if endpoint not available)",
    )
    parser.add_argument(
        "--skip-paddle",
        action="store_true",
        help="Skip PaddleOCR (if endpoint not available)",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("OCR ENGINE COMPARISON")
    print("=" * 60)

    # Check engine availability
    print("\nChecking engine availability...")

    run_hunyuan = not args.skip_hunyuan
    if run_hunyuan:
        hunyuan_available = check_hunyuan_health(args.hunyuan_url)
        if not hunyuan_available:
            print(f"  WARNING: HunyuanOCR not available at {args.hunyuan_url}")
            run_hunyuan = False
        else:
            print(f"  HunyuanOCR: Available at {args.hunyuan_url}")

    run_paddle = not args.skip_paddle
    if run_paddle:
        paddle_available = check_paddleocr_health(args.paddleocr_url)
        if not paddle_available:
            print(f"  WARNING: PaddleOCR not available at {args.paddleocr_url}")
            run_paddle = False
        else:
            print(f"  PaddleOCR: Available at {args.paddleocr_url}")

    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        print("  Tesseract: Available")
    except Exception:
        print("  ERROR: Tesseract not available!")
        sys.exit(1)

    # Discover screenshots
    print(f"\nDiscovering screenshots in {args.input_dir}...")
    files = discover_screenshots(args.input_dir, limit=args.limit)
    print(f"Found {len(files)} screenshots")

    if not files:
        print("No screenshots found!")
        sys.exit(1)

    # Process images
    print(f"\nProcessing {len(files)} images...")
    results: list[OCRComparisonResult] = []

    for i, file_path in enumerate(files, 1):
        print(f"\n[{i}/{len(files)}]")
        result = process_single_image(
            file_path,
            hunyuan_url=args.hunyuan_url,
            paddleocr_url=args.paddleocr_url,
            run_hunyuan=run_hunyuan,
            run_paddle=run_paddle,
        )
        results.append(result)

    # Write CSV output
    print(f"\nWriting results to {args.output}...")

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "file_path",
            "participant_id",
            # Tesseract
            "tesseract_text",
            "tesseract_time_ms",
            "tesseract_bbox_count",
            "tesseract_error",
            # PaddleOCR
            "paddleocr_text",
            "paddleocr_time_ms",
            "paddleocr_bbox_count",
            "paddleocr_error",
            # HunyuanOCR
            "hunyuan_text",
            "hunyuan_time_ms",
            "hunyuan_error",
        ])

        for r in results:
            writer.writerow([
                r.file_path,
                r.participant_id,
                # Tesseract
                r.tesseract.text[:5000] if r.tesseract.text else "",
                f"{r.tesseract.time_ms:.1f}",
                r.tesseract.bbox_count,
                r.tesseract.error or "",
                # PaddleOCR
                r.paddleocr.text[:5000] if r.paddleocr.text else "",
                f"{r.paddleocr.time_ms:.1f}",
                r.paddleocr.bbox_count,
                r.paddleocr.error or "",
                # HunyuanOCR
                r.hunyuan.text[:5000] if r.hunyuan.text else "",
                f"{r.hunyuan.time_ms:.1f}",
                r.hunyuan.error or "",
            ])

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total screenshots: {len(results)}")

    # Calculate stats per engine
    for name, get_result in [
        ("Tesseract", lambda r: r.tesseract),
        ("PaddleOCR", lambda r: r.paddleocr),
        ("HunyuanOCR", lambda r: r.hunyuan),
    ]:
        engine_results = [get_result(r) for r in results]
        success = sum(1 for e in engine_results if not e.error)
        avg_time = sum(e.time_ms for e in engine_results) / len(engine_results) if engine_results else 0
        total_bboxes = sum(e.bbox_count for e in engine_results)
        has_bboxes = engine_results[0].has_bboxes if engine_results else False

        print(f"\n{name}:")
        print(f"  Success: {success}/{len(results)}")
        print(f"  Avg time: {avg_time:.1f}ms")
        print(f"  Returns bboxes: {'Yes' if has_bboxes else 'No'}")
        if has_bboxes:
            print(f"  Total bboxes: {total_bboxes}")

    print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
