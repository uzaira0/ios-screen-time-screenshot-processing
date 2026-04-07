"""Debug OCR multiprocessing failures."""

import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


def ocr_single_image(image_path_str: str) -> tuple[str, str | None, str | None]:
    """OCR a single image with full error capture."""
    from phi_detector_remover.core.ocr import TesseractEngine

    image_path = Path(image_path_str)

    try:
        stat = image_path.stat()
        file_hash = f"{image_path.name}_{stat.st_size}_{stat.st_mtime_ns}"

        image_bytes = image_path.read_bytes()

        engine = TesseractEngine()
        ocr_result = engine.extract(image_bytes)

        return image_path_str, "OK", file_hash
    except Exception as e:
        return image_path_str, f"ERROR: {e}\n{traceback.format_exc()}", None


if __name__ == "__main__":
    RAW_DATA_DIR = Path("/path/to/raw-data")

    # Find all images
    image_extensions = {".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"}
    all_images = []
    for ext in image_extensions:
        all_images.extend(RAW_DATA_DIR.rglob(f"*{ext}"))

    all_images = [p for p in all_images if p.name != "Thumbs.db" and "PHI" not in str(p)]
    print(f"Found {len(all_images)} images")

    # Test first 50 with multiprocessing
    test_images = [str(p) for p in all_images[:50]]

    successes = 0
    failures = []

    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(ocr_single_image, path_str): path_str for path_str in test_images
        }

        for future in as_completed(futures):
            try:
                path_str, status, file_hash = future.result()
                if status == "OK":
                    successes += 1
                else:
                    failures.append((path_str, status))
                    print(f"FAIL: {Path(path_str).name}")
            except Exception as e:
                path_str = futures[future]
                failures.append((path_str, f"Future error: {e}"))
                print(f"FUTURE FAIL: {Path(path_str).name} - {e}")

    print(f"\nSuccess: {successes}, Failures: {len(failures)}")

    if failures:
        print("\nFirst 3 failures:")
        for path, err in failures[:3]:
            print(f"\n{Path(path).name}:")
            print(err[:500])
