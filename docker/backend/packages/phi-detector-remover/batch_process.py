"""Batch process screenshot data for PHI detection."""

import json
import os
import pickle
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import httpx

from phi_detector_remover.core.models import BoundingBox, PHIRegion
from phi_detector_remover.core.prompts import get_prompt
from phi_detector_remover.core.remover import PHIRemover

# Setup
RAW_DATA_DIR = Path("/path/to/raw-data")
OUTPUT_DIR = Path("/path/to/redacted-output")
RESULTS_FILE = Path("D:/Scripts/monorepo/packages/phi-detector-remover/phi_detection_results.csv")
OCR_CACHE_FILE = Path("D:/Scripts/monorepo/packages/phi-detector-remover/ocr_cache.pkl")

BATCH_SIZE = 20  # Smaller batches for more reliable JSON responses
LLM_ENDPOINT = "http://YOUR_LLM_HOST:1234/v1/chat/completions"
LLM_MODEL = "gpt-oss-20b"
NUM_WORKERS = min(os.cpu_count() or 4, 8)

# Initialize
remover = PHIRemover(method="redbox")
prompt_template = get_prompt("hipaa")


def get_file_hash(file_path: Path) -> str:
    """Get hash of file for cache key (uses size + mtime for speed)."""
    stat = file_path.stat()
    return f"{file_path.name}_{stat.st_size}_{stat.st_mtime_ns}"


def load_ocr_cache() -> dict:
    """Load OCR cache from disk."""
    if OCR_CACHE_FILE.exists():
        try:
            with open(OCR_CACHE_FILE, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            print(f"  Warning: Could not load cache: {e}")
    return {}


def save_ocr_cache(cache: dict) -> None:
    """Save OCR cache to disk."""
    try:
        with open(OCR_CACHE_FILE, "wb") as f:
            pickle.dump(cache, f)
        print(f"  Cache saved: {len(cache)} entries")
    except Exception as e:
        print(f"  Warning: Could not save cache: {e}")


def ocr_single_image(image_path_str: str) -> tuple[str, dict | None, bytes | None, str | None]:
    """OCR a single image. Run in separate process.

    Args:
        image_path_str: String path to image (not Path object for Windows multiprocessing)

    Returns:
        (path_str, ocr_dict, image_bytes, file_hash)
    """
    from phi_detector_remover.core.ocr import TesseractEngine

    image_path = Path(image_path_str)

    try:
        # Get file hash for caching
        stat = image_path.stat()
        file_hash = f"{image_path.name}_{stat.st_size}_{stat.st_mtime_ns}"

        image_bytes = image_path.read_bytes()

        engine = TesseractEngine()
        ocr_result = engine.extract(image_bytes)

        # Convert to serializable dict
        ocr_dict = {
            "text": ocr_result.text,
            "words": [
                {
                    "text": w.text,
                    "bbox": {
                        "x": w.bbox.x,
                        "y": w.bbox.y,
                        "width": w.bbox.width,
                        "height": w.bbox.height,
                    },
                    "confidence": w.confidence,
                }
                for w in ocr_result.words
            ],
        }
        return image_path_str, ocr_dict, image_bytes, file_hash
    except Exception as e:
        print(f"  OCR error on {image_path.name}: {e}")
        return image_path_str, None, None, None


def call_llm_batch(batch_texts: dict[str, str], retry_count: int = 0) -> dict[str, list[dict]]:
    """Call LLM with multiple texts in one request."""
    batch_content = "\n\n".join(
        f"=== IMAGE {img_id} ===\n{text[:1000]}" for img_id, text in batch_texts.items()
    )

    prompt = f"""{prompt_template.system_prompt}

IMPORTANT: You are analyzing text from MULTIPLE images. For each image, identify PHI.
Output JSON with results grouped by image ID:
{{
    "results": {{
        "IMAGE_ID_1": {{"entities": [...]}},
        "IMAGE_ID_2": {{"entities": []}}
    }}
}}

Only extract actual personal names (like "Sarah", "John", "Smith").
Ignore: app names, UI text, OCR errors, gibberish.

## DETECT:
- Personal names (first names, last names)
- Email addresses
- Phone numbers

## IGNORE:
- App names (YouTube, Netflix, Disney+, Safari, Siri, Mario, etc.)
- iOS UI elements
- OCR garbage/errors
- Generic words

{batch_content}
"""

    try:
        response = httpx.post(
            LLM_ENDPOINT,
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 8192,
            },
            timeout=180.0,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]

        # Parse response - try to extract JSON
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            content = content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            content = content[start:end].strip()

        # Try to fix truncated JSON
        content = content.strip()
        if not content.endswith("}"):
            open_braces = content.count("{") - content.count("}")
            content += "}" * open_braces

        data = json.loads(content)

        if "results" in data:
            return data["results"]
        return {}

    except json.JSONDecodeError as e:
        if retry_count < 2:
            print(f"  JSON parse error, retrying with smaller batch...")
            items = list(batch_texts.items())
            mid = len(items) // 2
            if mid > 0:
                first_half = dict(items[:mid])
                second_half = dict(items[mid:])
                results = {}
                r1 = call_llm_batch(first_half, retry_count + 1)
                r2 = call_llm_batch(second_half, retry_count + 1)
                results.update(r1)
                results.update(r2)
                if r1 or r2:
                    print(f"  Retry succeeded: {len(r1) + len(r2)} images processed")
                return results
        print(f"LLM JSON error: {e}")
        return {}
    except Exception as e:
        print(f"LLM batch error: {e}")
        return {}


def find_bbox_for_text(text: str, words: list[dict]) -> BoundingBox | None:
    """Find bounding box for detected text."""
    text_lower = text.lower().strip()
    text_words = text_lower.split()

    if not text_words:
        return None

    first_target = text_words[0]

    for i, word in enumerate(words):
        word_lower = word["text"].lower()

        if not (word_lower.startswith(first_target) or first_target.startswith(word_lower)):
            continue

        matched_words = [word]
        match_found = True

        for k, target_word in enumerate(text_words[1:], start=1):
            next_idx = i + k
            if next_idx >= len(words):
                match_found = False
                break

            next_word = words[next_idx]
            next_lower = next_word["text"].lower()

            if not (next_lower.startswith(target_word) or target_word.startswith(next_lower)):
                match_found = False
                break

            matched_words.append(next_word)

        if match_found and len(matched_words) == len(text_words):
            min_x = min(w["bbox"]["x"] for w in matched_words)
            min_y = min(w["bbox"]["y"] for w in matched_words)
            max_x = max(w["bbox"]["x"] + w["bbox"]["width"] for w in matched_words)
            max_y = max(w["bbox"]["y"] + w["bbox"]["height"] for w in matched_words)

            return BoundingBox(x=min_x, y=min_y, width=max_x - min_x, height=max_y - min_y)

    return None


if __name__ == "__main__":
    print(f"Using batched LLM detection (batch size: {BATCH_SIZE}, OCR workers: {NUM_WORKERS})")

    # Find all images (lowercase only - Windows is case-insensitive)
    image_extensions = {".png", ".jpg", ".jpeg"}
    all_images = []
    for ext in image_extensions:
        all_images.extend(RAW_DATA_DIR.rglob(f"*{ext}"))

    # Deduplicate (in case of any remaining dupes)
    all_images = list({str(p): p for p in all_images}.values())

    # Filter out Thumbs.db and already processed
    all_images = [p for p in all_images if p.name != "Thumbs.db" and "PHI" not in str(p)]
    print(f"Found {len(all_images)} images to process")

    # Load OCR cache
    ocr_cache = load_ocr_cache()
    print(f"  Loaded OCR cache: {len(ocr_cache)} entries")

    # Step 1: OCR (with caching)
    print(f"\nStep 1: Running OCR on images ({NUM_WORKERS} workers)...")
    ocr_results = {}
    image_bytes_cache = {}

    # Check which images need OCR
    images_to_ocr = []
    for img_path in all_images:
        file_hash = get_file_hash(img_path)
        if file_hash in ocr_cache:
            # Use cached result
            ocr_results[str(img_path)] = ocr_cache[file_hash]
            image_bytes_cache[str(img_path)] = img_path.read_bytes()
        else:
            images_to_ocr.append(img_path)

    print(f"  Cache hits: {len(ocr_results)}, need OCR: {len(images_to_ocr)}")

    if images_to_ocr:
        completed = 0
        # Convert to strings for Windows multiprocessing
        image_paths_str = [str(p) for p in images_to_ocr]

        failed_count = 0
        with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
            futures = {
                executor.submit(ocr_single_image, path_str): path_str
                for path_str in image_paths_str
            }

            for future in as_completed(futures):
                completed += 1
                if completed % 100 == 0:
                    print(
                        f"  OCR progress: {completed}/{len(images_to_ocr)} (failed: {failed_count})"
                    )

                try:
                    path_str, ocr_dict, image_bytes, file_hash = future.result()
                    if ocr_dict is not None and file_hash is not None:
                        ocr_results[path_str] = ocr_dict
                        image_bytes_cache[path_str] = image_bytes
                        ocr_cache[file_hash] = ocr_dict
                    else:
                        failed_count += 1
                except Exception as e:
                    failed_count += 1
                    print(f"  Future error: {e}")

        print(f"  OCR failed: {failed_count} images")

        # Save updated cache
        save_ocr_cache(ocr_cache)

    print(f"  OCR complete: {len(ocr_results)} images")

    # Step 2: Batch LLM detection
    print(f"\nStep 2: Running LLM detection in batches of {BATCH_SIZE}...")
    results = []
    phi_found_count = 0
    image_paths = list(ocr_results.keys())

    for batch_start in range(0, len(image_paths), BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, len(image_paths))
        batch_paths = image_paths[batch_start:batch_end]

        print(
            f"  Processing batch {batch_start // BATCH_SIZE + 1}/{(len(image_paths) + BATCH_SIZE - 1) // BATCH_SIZE} ({batch_start + 1}-{batch_end})..."
        )

        # Build batch texts
        batch_texts = {}
        for path in batch_paths:
            img_id = Path(path).name
            batch_texts[img_id] = ocr_results[path]["text"][:1000]

        # Call LLM
        llm_results = call_llm_batch(batch_texts)

        # Process results
        for path in batch_paths:
            img_id = Path(path).name
            image_path = Path(path)

            names = llm_results.get(img_id, [])
            # Handle both list of names and dict with entities
            if isinstance(names, dict):
                names = names.get("entities", [])
                names = [e.get("text", e) if isinstance(e, dict) else e for e in names]

            if not names:
                continue

            # Find bounding boxes and create regions
            all_regions = []
            words = ocr_results[path]["words"]

            for name in names:
                if not name or not isinstance(name, str):
                    continue
                text = name

                bbox = find_bbox_for_text(text, words)
                if bbox:
                    region = PHIRegion(
                        entity_type="PERSON",
                        text=text,
                        confidence=0.9,
                        bbox=bbox,
                        source="llm:gpt-oss-20b",
                    )
                    all_regions.append(region)

            if all_regions:
                phi_found_count += 1

                # Record result
                results.append(
                    {
                        "file": path,
                        "regions": [
                            {"type": r.entity_type, "text": r.text, "confidence": r.confidence}
                            for r in all_regions
                        ],
                    }
                )

                # Save redacted image
                rel_path = image_path.relative_to(RAW_DATA_DIR)
                output_path = OUTPUT_DIR / rel_path
                output_path = output_path.with_suffix(".png")
                output_path.parent.mkdir(parents=True, exist_ok=True)

                image_bytes = image_bytes_cache[path]
                redacted_bytes = remover.remove(image_bytes, all_regions)
                output_path.write_bytes(redacted_bytes)

                print(f"    PHI in {img_id}: {[r.text for r in all_regions]}")

    # Save results as CSV
    import csv

    with open(RESULTS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["file", "phi_text", "entity_type", "confidence"])
        for result in results:
            file_path = result["file"]
            for region in result["regions"]:
                writer.writerow(
                    [
                        file_path,
                        region["text"],
                        region["type"],
                        region["confidence"],
                    ]
                )

    print()
    print("=" * 60)
    print(f"COMPLETE: {len(all_images)} images processed")
    print(f"PHI found in {phi_found_count} images")
    print(f"Results saved to: {RESULTS_FILE}")
    print(f"Redacted images saved to: {OUTPUT_DIR}")
