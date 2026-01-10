#!/usr/bin/env python3
"""Test script for HybridOCREngine across all use cases.

Tests:
1. Full image OCR (text extraction)
2. Title extraction region
3. Total usage extraction region
4. Fallback behavior when engines fail
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from screenshot_processor.core.ocr_engines import HybridOCREngine
from screenshot_processor.core.image_utils import convert_dark_mode


def load_image(image_path: Path) -> np.ndarray:
    """Load and preprocess image."""
    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"Failed to load image: {image_path}")

    # Convert BGR to RGB
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # Convert dark mode if needed
    img_rgb = convert_dark_mode(img_rgb)

    return img_rgb


def extract_title_region(img: np.ndarray) -> np.ndarray:
    """Extract the title region (top portion where app name appears)."""
    height, width = img.shape[:2]
    # Title is typically in top 15% of image, center portion
    title_region = img[int(height * 0.08):int(height * 0.18), int(width * 0.15):int(width * 0.85)]
    return title_region


def extract_total_region(img: np.ndarray) -> np.ndarray:
    """Extract the total usage region (where time totals appear)."""
    height, width = img.shape[:2]
    # Total is typically below title, in the center-left area
    total_region = img[int(height * 0.15):int(height * 0.30), int(width * 0.05):int(width * 0.50)]
    return total_region


def extract_grid_region(img: np.ndarray) -> np.ndarray:
    """Extract the bar graph region (where hourly data is shown)."""
    height, width = img.shape[:2]
    # Grid is typically in the middle portion
    grid_region = img[int(height * 0.25):int(height * 0.55), int(width * 0.05):int(width * 0.95)]
    return grid_region


def test_engine_on_image(engine: HybridOCREngine, img: np.ndarray, region_name: str) -> dict:
    """Test engine on a specific image region."""
    start_time = time.time()

    try:
        results = engine.extract_text(img)
        elapsed = time.time() - start_time

        # Combine all text
        full_text = " ".join(r.text for r in results)

        return {
            "success": True,
            "engine_used": engine.last_engine_used,
            "time_ms": elapsed * 1000,
            "text": full_text[:200] + "..." if len(full_text) > 200 else full_text,
            "num_results": len(results),
            "has_bboxes": any(r.bbox is not None for r in results),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "time_ms": (time.time() - start_time) * 1000,
        }


def test_with_bboxes(engine: HybridOCREngine, img: np.ndarray) -> dict:
    """Test extract_text_with_bboxes method."""
    start_time = time.time()

    try:
        results = engine.extract_text_with_bboxes(img)
        elapsed = time.time() - start_time

        return {
            "success": True,
            "engine_used": engine.last_engine_used,
            "time_ms": elapsed * 1000,
            "num_results": len(results),
            "has_bboxes": any(r.bbox is not None for r in results),
            "bbox_count": sum(1 for r in results if r.bbox is not None),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "time_ms": (time.time() - start_time) * 1000,
        }


def main():
    parser = argparse.ArgumentParser(description="Test HybridOCREngine")
    parser.add_argument("--image", type=Path, help="Specific image to test")
    parser.add_argument("--count", type=int, default=5, help="Number of images to test")
    parser.add_argument("--hunyuan-url", default="http://YOUR_OCR_HOST:8080")
    parser.add_argument("--paddleocr-url", default="http://YOUR_OCR_HOST:8081")
    parser.add_argument("--disable-hunyuan", action="store_true", help="Disable HunyuanOCR")
    parser.add_argument("--disable-paddleocr", action="store_true", help="Disable PaddleOCR")
    parser.add_argument("--disable-tesseract", action="store_true", help="Disable Tesseract")
    args = parser.parse_args()

    print("=" * 80)
    print("HYBRID OCR ENGINE TEST")
    print("=" * 80)

    # Create hybrid engine
    engine = HybridOCREngine(
        hunyuan_url=args.hunyuan_url,
        paddleocr_url=args.paddleocr_url,
        enable_hunyuan=not args.disable_hunyuan,
        enable_paddleocr=not args.disable_paddleocr,
        enable_tesseract=not args.disable_tesseract,
    )

    print("\nEngine Configuration:")
    print(f"  HunyuanOCR: {'enabled' if not args.disable_hunyuan else 'disabled'} ({args.hunyuan_url})")
    print(f"  PaddleOCR: {'enabled' if not args.disable_paddleocr else 'disabled'} ({args.paddleocr_url})")
    print(f"  Tesseract: {'enabled' if not args.disable_tesseract else 'disabled'}")
    print(f"\nAvailable engines: {engine.get_available_engines()}")

    # Get test images
    if args.image:
        test_images = [args.image]
    else:
        # Find reference images
        ref_dir = project_root / "reference_images"
        test_images = list(ref_dir.glob("**/*.png"))[:args.count]

        if not test_images:
            print("No test images found!")
            return

    print(f"\nTesting on {len(test_images)} images...")
    print("=" * 80)

    # Track statistics
    stats = {
        "full_image": {"total": 0, "success": 0, "engines": {}},
        "title_region": {"total": 0, "success": 0, "engines": {}},
        "total_region": {"total": 0, "success": 0, "engines": {}},
        "with_bboxes": {"total": 0, "success": 0, "engines": {}},
    }

    for i, image_path in enumerate(test_images, 1):
        print(f"\n[{i}/{len(test_images)}] {image_path.name}")
        print("-" * 60)

        try:
            img = load_image(image_path)
            height, width = img.shape[:2]
            print(f"  Image size: {width}x{height}")

            # Test 1: Full image OCR
            print("\n  1. Full Image OCR:")
            result = test_engine_on_image(engine, img, "full_image")
            stats["full_image"]["total"] += 1
            if result["success"]:
                stats["full_image"]["success"] += 1
                eng = result["engine_used"]
                stats["full_image"]["engines"][eng] = stats["full_image"]["engines"].get(eng, 0) + 1
                print(f"     Engine: {result['engine_used']}")
                print(f"     Time: {result['time_ms']:.0f}ms")
                print(f"     Results: {result['num_results']} items, bboxes: {result['has_bboxes']}")
                print(f"     Text: {result['text'][:100]}...")
            else:
                print(f"     ERROR: {result['error']}")

            # Test 2: Title region
            print("\n  2. Title Region OCR:")
            title_img = extract_title_region(img)
            result = test_engine_on_image(engine, title_img, "title_region")
            stats["title_region"]["total"] += 1
            if result["success"]:
                stats["title_region"]["success"] += 1
                eng = result["engine_used"]
                stats["title_region"]["engines"][eng] = stats["title_region"]["engines"].get(eng, 0) + 1
                print(f"     Engine: {result['engine_used']}")
                print(f"     Time: {result['time_ms']:.0f}ms")
                print(f"     Text: {result['text']}")
            else:
                print(f"     ERROR: {result['error']}")

            # Test 3: Total region
            print("\n  3. Total Region OCR:")
            total_img = extract_total_region(img)
            result = test_engine_on_image(engine, total_img, "total_region")
            stats["total_region"]["total"] += 1
            if result["success"]:
                stats["total_region"]["success"] += 1
                eng = result["engine_used"]
                stats["total_region"]["engines"][eng] = stats["total_region"]["engines"].get(eng, 0) + 1
                print(f"     Engine: {result['engine_used']}")
                print(f"     Time: {result['time_ms']:.0f}ms")
                print(f"     Text: {result['text']}")
            else:
                print(f"     ERROR: {result['error']}")

            # Test 4: With bboxes preference
            print("\n  4. OCR with Bounding Box Preference:")
            result = test_with_bboxes(engine, img)
            stats["with_bboxes"]["total"] += 1
            if result["success"]:
                stats["with_bboxes"]["success"] += 1
                eng = result["engine_used"]
                stats["with_bboxes"]["engines"][eng] = stats["with_bboxes"]["engines"].get(eng, 0) + 1
                print(f"     Engine: {result['engine_used']}")
                print(f"     Time: {result['time_ms']:.0f}ms")
                print(f"     Results: {result['num_results']} items, {result['bbox_count']} with bboxes")
            else:
                print(f"     ERROR: {result['error']}")

        except Exception as e:
            print(f"  ERROR loading image: {e}")

    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    for test_name, test_stats in stats.items():
        if test_stats["total"] > 0:
            success_rate = test_stats["success"] / test_stats["total"] * 100
            print(f"\n{test_name}:")
            print(f"  Success rate: {test_stats['success']}/{test_stats['total']} ({success_rate:.1f}%)")
            print("  Engine usage:")
            for eng, count in sorted(test_stats["engines"].items(), key=lambda x: -x[1]):
                pct = count / test_stats["success"] * 100 if test_stats["success"] > 0 else 0
                print(f"    {eng}: {count} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
