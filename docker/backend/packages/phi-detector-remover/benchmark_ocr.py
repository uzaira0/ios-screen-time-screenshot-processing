"""Benchmark OCR performance."""

import time
from pathlib import Path

from phi_detector_remover.core.ocr import TesseractEngine

# Setup
RAW_DATA_DIR = Path("/path/to/raw-data")

# Find first 10 images
image_extensions = {".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"}
all_images = []
for ext in image_extensions:
    all_images.extend(RAW_DATA_DIR.rglob(f"*{ext}"))
all_images = [p for p in all_images if p.name != "Thumbs.db" and "PHI" not in str(p)][:10]

print(f"Benchmarking OCR on {len(all_images)} images...")

engine = TesseractEngine()

times = []
for i, image_path in enumerate(all_images):
    start = time.perf_counter()

    # Read file
    t1 = time.perf_counter()
    image_bytes = image_path.read_bytes()
    read_time = time.perf_counter() - t1

    # OCR
    t2 = time.perf_counter()
    ocr_result = engine.extract(image_bytes)
    ocr_time = time.perf_counter() - t2

    total = time.perf_counter() - start
    times.append(total)

    file_size_mb = len(image_bytes) / 1024 / 1024
    print(
        f"[{i + 1}] {image_path.name}: {file_size_mb:.2f}MB, read={read_time:.2f}s, ocr={ocr_time:.2f}s, total={total:.2f}s"
    )

avg = sum(times) / len(times)
print(f"\nAverage: {avg:.2f}s per image")
print(f"Estimated total for 1992 images: {avg * 1992 / 60:.1f} minutes")
