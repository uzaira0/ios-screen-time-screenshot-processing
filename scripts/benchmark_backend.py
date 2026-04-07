"""
Backend Processing Pipeline Benchmark
"""

import time
import statistics
import sys

sys.path.insert(0, "src")

import cv2


def benchmark_function(func, *args, iterations=5, **kwargs):
    times = []
    result = None
    for _ in range(iterations):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    return {"mean": statistics.mean(times), "stdev": statistics.stdev(times) if len(times) > 1 else 0, "result": result}


def run_benchmarks(image_path: str):
    print(f"\n{'=' * 60}")
    print("BACKEND PROCESSING BENCHMARK")
    print(f"Image: {image_path}")
    print(f"{'=' * 60}\n")

    results = {}

    # 1. Image Loading
    print("1. IMAGE LOADING")
    stats = benchmark_function(cv2.imread, image_path)
    results["cv2_load"] = stats
    print(f"   cv2.imread: {stats['mean']:.2f}ms")
    img = stats["result"]
    print(f"   Image size: {img.shape[1]}x{img.shape[0]}")

    # 2. Dark Mode Conversion
    print("\n2. DARK MODE CONVERSION")
    from screenshot_processor.core.image_utils import convert_dark_mode

    stats = benchmark_function(convert_dark_mode, img.copy())
    results["dark_mode"] = stats
    print(f"   convert_dark_mode: {stats['mean']:.2f}ms")
    img_converted = stats["result"]

    # 3. OCR - Title Detection
    print("\n3. OCR - TITLE DETECTION")
    from screenshot_processor.core.ocr import find_screenshot_title

    stats = benchmark_function(find_screenshot_title, img_converted, iterations=3)
    results["ocr_title"] = stats
    print(f"   find_screenshot_title: {stats['mean']:.2f}ms")

    # 4. OCR - Total Detection
    print("\n4. OCR - TOTAL DETECTION")
    from screenshot_processor.core.ocr import find_screenshot_total_usage

    stats = benchmark_function(find_screenshot_total_usage, img_converted, iterations=3)
    results["ocr_total"] = stats
    print(f"   find_screenshot_total_usage: {stats['mean']:.2f}ms")

    # 5. Bar Value Extraction (Pixel Analysis only - no OCR)
    print("\n5. BAR VALUE EXTRACTION (pixel analysis)")
    from screenshot_processor.core.bar_extraction import slice_image

    upper_left_x, upper_left_y = 39, 1058
    roi_width, roi_height = 906, 299
    stats = benchmark_function(
        slice_image, img_converted, upper_left_x, upper_left_y, roi_width, roi_height, iterations=10
    )
    results["bar_extraction"] = stats
    print(f"   slice_image: {stats['mean']:.2f}ms")
    row, _, _ = stats["result"]
    print(f"   Result: {len(row)} values, total={sum(row)}min")

    # 6. Full Pipeline
    print("\n6. FULL PIPELINE (with OCR)")
    from screenshot_processor.core.image_processor import process_image

    stats = benchmark_function(process_image, image_path, False, True, iterations=3)
    results["full_pipeline"] = stats
    print(f"   process_image: {stats['mean']:.2f}ms")

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")

    total = results["full_pipeline"]["mean"]
    ocr_time = results["ocr_title"]["mean"] + results["ocr_total"]["mean"]
    non_ocr = results["cv2_load"]["mean"] + results["dark_mode"]["mean"] + results["bar_extraction"]["mean"]

    print(f"\n   FULL PIPELINE:     {total:8.0f}ms (100%)")
    print(
        f"   ├─ OCR Title:      {results['ocr_title']['mean']:8.0f}ms ({results['ocr_title']['mean'] / total * 100:4.1f}%)"
    )
    print(
        f"   ├─ OCR Total:      {results['ocr_total']['mean']:8.0f}ms ({results['ocr_total']['mean'] / total * 100:4.1f}%)"
    )
    print(
        f"   ├─ Image Load:     {results['cv2_load']['mean']:8.0f}ms ({results['cv2_load']['mean'] / total * 100:4.1f}%)"
    )
    print(
        f"   ├─ Dark Mode:      {results['dark_mode']['mean']:8.0f}ms ({results['dark_mode']['mean'] / total * 100:4.1f}%)"
    )
    print(
        f"   └─ Bar Extraction: {results['bar_extraction']['mean']:8.0f}ms ({results['bar_extraction']['mean'] / total * 100:4.1f}%)"
    )

    print(f"\n   OCR TOTAL:         {ocr_time:8.0f}ms ({ocr_time / total * 100:4.1f}%)")
    print(f"   NON-OCR:           {non_ocr:8.0f}ms ({non_ocr / total * 100:4.1f}%)")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHT")
    print(f"{'=' * 60}")
    print("\n   When grid is adjusted manually, we SKIP OCR.")
    print(f"   Grid adjustment should only take: ~{non_ocr:.0f}ms")
    print(f"   vs full pipeline with OCR:        ~{total:.0f}ms")
    print(f"   Speedup: {total / non_ocr:.1f}x faster")

    return results


if __name__ == "__main__":
    import glob

    images = glob.glob("data/SAMPLE-001 Cropped/SAMPLE-001_T1_10-2-23/*.png")
    for img_path in images:
        if "IMG_0776" in img_path:
            run_benchmarks(img_path)
            break
