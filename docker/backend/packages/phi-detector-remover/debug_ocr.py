"""Debug OCR failures."""

from pathlib import Path

from phi_detector_remover.core.ocr import TesseractEngine

RAW_DATA_DIR = Path("/path/to/raw-data")

# Find all images
image_extensions = {".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"}
all_images = []
for ext in image_extensions:
    all_images.extend(RAW_DATA_DIR.rglob(f"*{ext}"))

all_images = [p for p in all_images if p.name != "Thumbs.db" and "PHI" not in str(p)]
print(f"Found {len(all_images)} images")

# Test OCR on first 20 images
engine = TesseractEngine()
successes = 0
failures = []

for i, img_path in enumerate(all_images[:20]):
    try:
        image_bytes = img_path.read_bytes()
        result = engine.extract(image_bytes)
        successes += 1
        print(f"[{i + 1}] OK: {img_path.name} ({len(result.text)} chars)")
    except Exception as e:
        failures.append((img_path, str(e)))
        print(f"[{i + 1}] FAIL: {img_path.name} - {e}")

print(f"\nSuccess: {successes}, Failures: {len(failures)}")

if failures:
    print("\nFailed files:")
    for path, err in failures[:5]:
        print(f"  {path}")
        print(f"    Error: {err}")
