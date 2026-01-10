#!/usr/bin/env python3
"""Comprehensive test of HybridOCREngine for ALL iOS screenshot processing use cases.

USAGE:
    # Test with all engines (requires network access to local GPU server)
    python scripts/test_hybrid_all_use_cases.py

    # Test specific image
    python scripts/test_hybrid_all_use_cases.py --image reference_images/sample.png

    # Test offline mode (Tesseract only)
    python scripts/test_hybrid_all_use_cases.py --offline

    # Limit number of test images
    python scripts/test_hybrid_all_use_cases.py --count 3

NETWORK CONFIGURATION:
    Remote engines are on LOCAL NETWORK (not internet):
    - HunyuanOCR: http://YOUR_OCR_HOST:8080 (vLLM endpoint)
    - PaddleOCR:  http://YOUR_OCR_HOST:8081 (Docker container)

    "Offline" = not connected to local network = Tesseract fallback only.

USE CASES COVERED:
    1. GRID ANCHOR DETECTION - Find "12AM" and "60" with bounding boxes
       - Method: extract_text_with_bboxes()
       - Priority: PaddleOCR -> Tesseract (NO HunyuanOCR - it can't return bboxes)
       - REQUIRES bounding boxes for ROI extraction

    2. TITLE EXTRACTION - Extract app name from title region
       - Method: extract_text()
       - Priority: HunyuanOCR -> PaddleOCR -> Tesseract
       - REQUIRES text quality for app name matching

    3. TOTAL USAGE EXTRACTION - Extract duration like "4h 36m"
       - Method: extract_text()
       - Priority: HunyuanOCR -> PaddleOCR -> Tesseract
       - REQUIRES accurate time parsing

    4. DAILY TOTAL PAGE DETECTION - Detect "Daily Total" vs app-specific pages
       - Method: extract_text()
       - Priority: HunyuanOCR -> PaddleOCR -> Tesseract
       - Keyword matching only

    5. FULL IMAGE OCR - Comprehensive text extraction
       - Method: extract_text()
       - Priority: HunyuanOCR -> PaddleOCR -> Tesseract
       - Used for PHI detection in pipeline

Each use case tests all engines individually plus the HybridOCREngine.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from screenshot_processor.core.ocr_engines import HybridOCREngine, PaddleOCRRemoteEngine, TesseractOCREngine
from screenshot_processor.core.ocr_engines.hunyuan_engine import HunyuanOCREngine
from screenshot_processor.core.image_utils import convert_dark_mode, adjust_contrast_brightness


@dataclass
class TestResult:
    """Result from a single test."""
    use_case: str
    engine: str
    success: bool
    time_ms: float
    text: str = ""
    has_bboxes: bool = False
    found_target: bool = False
    error: str | None = None


def load_image(image_path: Path) -> np.ndarray:
    """Load and preprocess image."""
    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"Failed to load image: {image_path}")
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return img_rgb


def preprocess_for_ocr(img: np.ndarray) -> np.ndarray:
    """Apply standard preprocessing for OCR."""
    img = convert_dark_mode(img)
    return img


def preprocess_for_grid_detection(img: np.ndarray) -> np.ndarray:
    """Apply preprocessing for grid anchor detection (matches image_processor.py)."""
    img = convert_dark_mode(img)
    img = adjust_contrast_brightness(img, contrast=2.0, brightness=-220)
    return img


# ============================================================================
# USE CASE 1: Grid Anchor Detection
# Find "12AM" (left anchor) and "60" (right anchor) with bounding boxes
# ============================================================================

def test_grid_anchor_detection(engine, img: np.ndarray, img_path: str) -> TestResult:
    """Test grid anchor detection - needs bboxes to locate anchors."""
    start = time.time()

    try:
        # Preprocess like image_processor.py does
        processed = preprocess_for_grid_detection(img.copy())
        height, width = processed.shape[:2]

        # Split into left and right chunks like perform_ocr() does
        chunk_size = width // 3
        img_left = processed[:, :chunk_size]
        img_right = processed[:, -chunk_size:]

        # Test on left chunk (looking for "12", "AM", "2A")
        if hasattr(engine, 'extract_text_with_bboxes'):
            results = engine.extract_text_with_bboxes(img_left)
        else:
            results = engine.extract_text(img_left)

        elapsed = (time.time() - start) * 1000

        # Check if we found anchors
        all_text = " ".join(r.text for r in results).upper()
        has_bboxes = any(r.bbox is not None for r in results)

        left_anchors = ["12", "AM", "2A"]
        found_left = any(anchor in all_text for anchor in left_anchors)

        # Also test right chunk for "60"
        if hasattr(engine, 'extract_text_with_bboxes'):
            results_right = engine.extract_text_with_bboxes(img_right)
        else:
            results_right = engine.extract_text(img_right)

        right_text = " ".join(r.text for r in results_right).upper()
        found_right = "60" in right_text

        return TestResult(
            use_case="grid_anchor",
            engine=engine.get_engine_name() if hasattr(engine, 'get_engine_name') else type(engine).__name__,
            success=True,
            time_ms=elapsed,
            text=f"Left: {all_text[:50]}... Right: {right_text[:50]}...",
            has_bboxes=has_bboxes,
            found_target=found_left and found_right,
        )
    except Exception as e:
        return TestResult(
            use_case="grid_anchor",
            engine=engine.get_engine_name() if hasattr(engine, 'get_engine_name') else type(engine).__name__,
            success=False,
            time_ms=(time.time() - start) * 1000,
            error=str(e),
        )


# ============================================================================
# USE CASE 2: Title Extraction
# Extract app name from the title region
# ============================================================================

def test_title_extraction(engine, img: np.ndarray, img_path: str) -> TestResult:
    """Test title extraction from the header region."""
    start = time.time()

    try:
        processed = preprocess_for_ocr(img.copy())
        height, width = processed.shape[:2]

        # Title region is typically in top 20% of image
        title_region = processed[int(height * 0.05):int(height * 0.20), :]

        results = engine.extract_text(title_region)
        elapsed = (time.time() - start) * 1000

        all_text = " ".join(r.text for r in results)
        has_bboxes = any(r.bbox is not None for r in results)

        # Check for common title patterns
        has_title = len(all_text.strip()) > 0
        "DAILY" in all_text.upper() or "WEEK" in all_text.upper()

        return TestResult(
            use_case="title",
            engine=engine.get_engine_name() if hasattr(engine, 'get_engine_name') else type(engine).__name__,
            success=True,
            time_ms=elapsed,
            text=all_text[:100],
            has_bboxes=has_bboxes,
            found_target=has_title,
        )
    except Exception as e:
        return TestResult(
            use_case="title",
            engine=engine.get_engine_name() if hasattr(engine, 'get_engine_name') else type(engine).__name__,
            success=False,
            time_ms=(time.time() - start) * 1000,
            error=str(e),
        )


# ============================================================================
# USE CASE 3: Total Usage Extraction
# Extract duration like "4h 36m" or "1h 23m"
# ============================================================================

def test_total_extraction(engine, img: np.ndarray, img_path: str) -> TestResult:
    """Test total usage extraction."""
    start = time.time()

    try:
        processed = preprocess_for_ocr(img.copy())
        height, width = processed.shape[:2]

        # Total region is below title, left side (to avoid "Daily Average" on right)
        total_region = processed[int(height * 0.12):int(height * 0.35), :int(width * 0.5)]

        results = engine.extract_text(total_region)
        elapsed = (time.time() - start) * 1000

        all_text = " ".join(r.text for r in results)
        has_bboxes = any(r.bbox is not None for r in results)

        # Look for time patterns: Xh Ym, Xm, Xh
        time_pattern = r'\d+\s*[hm]'
        found_time = bool(re.search(time_pattern, all_text, re.IGNORECASE))

        return TestResult(
            use_case="total",
            engine=engine.get_engine_name() if hasattr(engine, 'get_engine_name') else type(engine).__name__,
            success=True,
            time_ms=elapsed,
            text=all_text[:100],
            has_bboxes=has_bboxes,
            found_target=found_time,
        )
    except Exception as e:
        return TestResult(
            use_case="total",
            engine=engine.get_engine_name() if hasattr(engine, 'get_engine_name') else type(engine).__name__,
            success=False,
            time_ms=(time.time() - start) * 1000,
            error=str(e),
        )


# ============================================================================
# USE CASE 4: Daily Total Page Detection
# Detect whether this is a "Daily Total" page vs app-specific
# ============================================================================

def test_daily_detection(engine, img: np.ndarray, img_path: str) -> TestResult:
    """Test daily total page detection."""
    start = time.time()

    try:
        processed = preprocess_for_ocr(img.copy())

        results = engine.extract_text(processed)
        elapsed = (time.time() - start) * 1000

        all_text = " ".join(r.text for r in results).upper()

        # Daily page markers (from ocr.py)
        daily_markers = ["WEEK", "DAY", "MOST", "USED", "CATEGORIES", "TODAY", "ENTERTAINMENT", "EDUCATION"]
        app_markers = ["INFO", "DEVELOPER", "RATING", "LIMIT", "AGE", "DAILY", "AVERAGE"]

        daily_count = sum(1 for marker in daily_markers if marker in all_text)
        app_count = sum(1 for marker in app_markers if marker in all_text)


        return TestResult(
            use_case="daily_detection",
            engine=engine.get_engine_name() if hasattr(engine, 'get_engine_name') else type(engine).__name__,
            success=True,
            time_ms=elapsed,
            text=f"daily_markers={daily_count}, app_markers={app_count}",
            has_bboxes=any(r.bbox is not None for r in results),
            found_target=True,  # Always "succeeds" - just detecting type
        )
    except Exception as e:
        return TestResult(
            use_case="daily_detection",
            engine=engine.get_engine_name() if hasattr(engine, 'get_engine_name') else type(engine).__name__,
            success=False,
            time_ms=(time.time() - start) * 1000,
            error=str(e),
        )


# ============================================================================
# USE CASE 5: Full Image OCR (PHI Detection use case from pipeline)
# ============================================================================

def test_full_ocr(engine, img: np.ndarray, img_path: str) -> TestResult:
    """Test full image OCR (used for PHI detection in pipeline)."""
    start = time.time()

    try:
        processed = preprocess_for_ocr(img.copy())

        results = engine.extract_text(processed)
        elapsed = (time.time() - start) * 1000

        all_text = " ".join(r.text for r in results)
        has_bboxes = any(r.bbox is not None for r in results)

        return TestResult(
            use_case="full_ocr",
            engine=engine.get_engine_name() if hasattr(engine, 'get_engine_name') else type(engine).__name__,
            success=True,
            time_ms=elapsed,
            text=f"{len(all_text)} chars extracted",
            has_bboxes=has_bboxes,
            found_target=len(all_text) > 50,  # Should have substantial text
        )
    except Exception as e:
        return TestResult(
            use_case="full_ocr",
            engine=engine.get_engine_name() if hasattr(engine, 'get_engine_name') else type(engine).__name__,
            success=False,
            time_ms=(time.time() - start) * 1000,
            error=str(e),
        )


def run_all_tests(engines: dict, img: np.ndarray, img_path: str) -> list[TestResult]:
    """Run all use case tests for all engines."""
    results = []

    test_funcs = [
        ("Grid Anchor Detection", test_grid_anchor_detection),
        ("Title Extraction", test_title_extraction),
        ("Total Extraction", test_total_extraction),
        ("Daily Page Detection", test_daily_detection),
        ("Full Image OCR", test_full_ocr),
    ]

    for test_name, test_func in test_funcs:
        print(f"\n  {test_name}:")
        for engine_name, engine in engines.items():
            if engine is None:
                continue
            result = test_func(engine, img, img_path)
            results.append(result)

            status = "[OK]" if result.success and result.found_target else "[ERR]" if not result.success else "[--]"
            bbox_indicator = " [bbox]" if result.has_bboxes else ""

            if result.success:
                print(f"    {status} {engine_name}: {result.time_ms:.0f}ms{bbox_indicator}")
                if result.text and len(result.text) < 80:
                    print(f"       -> {result.text}")
            else:
                print(f"    {status} {engine_name}: ERROR - {result.error}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Test HybridOCREngine for all use cases")
    parser.add_argument("--image", type=Path, help="Specific image to test")
    parser.add_argument("--count", type=int, default=3, help="Number of images to test")
    parser.add_argument("--hunyuan-url", default="http://YOUR_OCR_HOST:8080")
    parser.add_argument("--paddleocr-url", default="http://YOUR_OCR_HOST:8081")
    parser.add_argument("--offline", action="store_true", help="Test offline mode (Tesseract only)")
    args = parser.parse_args()

    print("=" * 80)
    print("COMPREHENSIVE HYBRID OCR TEST - ALL USE CASES")
    print("=" * 80)

    # Initialize engines
    engines = {}

    if not args.offline:
        print("\nInitializing engines...")

        # HunyuanOCR
        try:
            hunyuan = HunyuanOCREngine(base_url=args.hunyuan_url)
            if hunyuan.is_available():
                engines["HunyuanOCR"] = hunyuan
                print(f"  [OK] HunyuanOCR available at {args.hunyuan_url}")
            else:
                print("  [--] HunyuanOCR NOT available")
        except Exception as e:
            print(f"  [ERR] HunyuanOCR error: {e}")

        # PaddleOCR
        try:
            paddleocr = PaddleOCRRemoteEngine(base_url=args.paddleocr_url)
            if paddleocr.is_available():
                engines["PaddleOCR"] = paddleocr
                print(f"  [OK] PaddleOCR available at {args.paddleocr_url}")
            else:
                print("  [--] PaddleOCR NOT available")
        except Exception as e:
            print(f"  [ERR] PaddleOCR error: {e}")

    # Tesseract (always available offline)
    try:
        tesseract = TesseractOCREngine()
        if tesseract.is_available():
            engines["Tesseract"] = tesseract
            print("  [OK] Tesseract available (offline fallback)")
        else:
            print("  [--] Tesseract NOT available")
    except Exception as e:
        print(f"  [ERR] Tesseract error: {e}")

    # HybridOCREngine
    if not args.offline:
        engines["Hybrid"] = HybridOCREngine(
            hunyuan_url=args.hunyuan_url,
            paddleocr_url=args.paddleocr_url,
        )
        print(f"  [OK] HybridOCR initialized (available engines: {engines['Hybrid'].get_available_engines()})")
    else:
        engines["Hybrid"] = HybridOCREngine(
            enable_hunyuan=False,
            enable_paddleocr=False,
            enable_tesseract=True,
        )
        print("  [OK] HybridOCR (OFFLINE mode - Tesseract only)")

    if not engines:
        print("\nERROR: No OCR engines available!")
        return

    # Get test images
    if args.image:
        test_images = [args.image]
    else:
        ref_dir = project_root / "reference_images"
        # Get mix of different screenshot types
        test_images = []
        for subdir in ref_dir.iterdir():
            if subdir.is_dir():
                pngs = list(subdir.glob("*.png"))[:1]  # 1 from each resolution
                test_images.extend(pngs)
        test_images = test_images[:args.count]

    print(f"\nTesting {len(test_images)} images across {len(engines)} engines...")
    print("=" * 80)

    all_results = []

    for i, img_path in enumerate(test_images, 1):
        print(f"\n[{i}/{len(test_images)}] {img_path.name}")
        print("-" * 60)

        try:
            img = load_image(img_path)
            height, width = img.shape[:2]
            print(f"  Size: {width}x{height}")

            results = run_all_tests(engines, img, str(img_path))
            all_results.extend(results)

        except Exception as e:
            print(f"  ERROR: {e}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY BY USE CASE")
    print("=" * 80)

    use_cases = ["grid_anchor", "title", "total", "daily_detection", "full_ocr"]
    use_case_names = {
        "grid_anchor": "Grid Anchor Detection (needs bboxes)",
        "title": "Title Extraction",
        "total": "Total Usage Extraction",
        "daily_detection": "Daily Page Detection",
        "full_ocr": "Full Image OCR (PHI detection)",
    }

    for uc in use_cases:
        print(f"\n{use_case_names[uc]}:")
        uc_results = [r for r in all_results if r.use_case == uc]

        for engine_name in engines.keys():
            eng_results = [r for r in uc_results if r.engine == engine_name or engine_name in r.engine]
            if not eng_results:
                continue

            success_count = sum(1 for r in eng_results if r.success and r.found_target)
            total_count = len(eng_results)
            avg_time = sum(r.time_ms for r in eng_results if r.success) / max(1, sum(1 for r in eng_results if r.success))
            has_bbox = any(r.has_bboxes for r in eng_results)

            bbox_str = " [has bboxes]" if has_bbox else ""
            print(f"  {engine_name}: {success_count}/{total_count} found, avg {avg_time:.0f}ms{bbox_str}")

    print("\n" + "=" * 80)
    print("RECOMMENDATIONS BY USE CASE")
    print("=" * 80)
    print("""
1. GRID ANCHOR DETECTION (find "12AM", "60"):
   - Best: PaddleOCR or Tesseract (need bboxes for positions)
   - HybridOCR: Use extract_text_with_bboxes()

2. TITLE EXTRACTION:
   - Best: HunyuanOCR (highest text quality)
   - Fallback: PaddleOCR -> Tesseract
   - HybridOCR: Use extract_text()

3. TOTAL USAGE EXTRACTION ("4h 36m"):
   - Best: HunyuanOCR (best at reading numbers/times)
   - Fallback: Tesseract (with regex normalization)
   - HybridOCR: Use extract_text()

4. DAILY PAGE DETECTION:
   - Any engine works (just keyword matching)
   - HybridOCR: Use extract_text()

5. FULL IMAGE OCR (PHI detection):
   - Best: HunyuanOCR (best quality for sensitive data detection)
   - Fallback: Tesseract for offline
   - HybridOCR: Use extract_text()

OFFLINE MODE (network unavailable):
   - All use cases fall back to Tesseract
   - Grid anchors: Still works (Tesseract has bboxes)
   - Quality: Lower but functional
""")


if __name__ == "__main__":
    main()
