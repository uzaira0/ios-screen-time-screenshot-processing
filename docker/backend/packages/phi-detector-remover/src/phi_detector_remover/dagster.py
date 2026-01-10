"""Dagster integration for PHI detection.

This module provides high-level functions optimized for Dagster pipeline
integration with support for:
- Batch processing with OCR caching
- LLM-based detection with batched API calls
- Polars DataFrame input/output
- Parallel OCR processing

Example usage in Dagster asset:
    >>> from phi_detector_remover.dagster import (
    ...     detect_phi_batch,
    ...     PHIDetectionConfig,
    ... )
    >>>
    >>> @asset
    >>> def phi_detection_results(context, screenshot_catalog: pl.DataFrame):
    ...     config = PHIDetectionConfig(
    ...         llm_endpoint="http://YOUR_LLM_HOST:1234/v1",
    ...         llm_model="gpt-oss-20b",
    ...     )
    ...     return detect_phi_batch(
    ...         catalog=screenshot_catalog,
    ...         file_path_column="file_path",
    ...         config=config,
    ...         cache_dir=Path("/tmp/ocr_cache"),
    ...     )
"""

from __future__ import annotations

import hashlib
import json
import pickle
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import polars as pl

    from phi_detector_remover.core.models import OCRResult


# Global allow_list for known false positives
# These terms will be filtered out regardless of what the LLM returns
GLOBAL_ALLOW_LIST: set[str] = {
    # YouTube variants - "YT" gets flagged as initials/PERSON by LLMs
    "yt kids",
    "yt",
    "youtube",
    "youtube kids",
    # OCR misreads of "YT Kids" - Tesseract often misreads this
    "yrkids",
    "yrkias",
    "vrkias",
    "yvrkias",
    "ytkids",
    "yr kids",
    # Wi-Fi variations
    "wi-fi",
    "wifi",
    "wi",
    # Common app names that get flagged
    "disney",
    "disney+",
    "lingokids",
    "photo booth",
    "screen time",
    "app store",
    "control center",
    "bluetooth",
    # Other common apps with name-like patterns
    "tiktok",
    "instagram",
    "safari",
    "netflix",
    "roblox",
    "minecraft",
    "fortnite",
    "pbs kids",
    "nick jr",
    "siri",
    "alexa",
    "google",
}


@dataclass
class PHIDetectionConfig:
    """Configuration for PHI detection in Dagster pipelines.

    Attributes:
        llm_endpoint: LLM API endpoint (e.g., "http://localhost:1234/v1")
        llm_model: Model name for LLM detection
        llm_batch_size: Number of images per LLM API call
        ocr_workers: Number of parallel OCR workers
        confidence_threshold: Minimum confidence to report
        redact: Whether to save redacted images
        redact_output_dir: Directory for redacted images
        redact_method: Redaction method ("redbox", "blackbox", "pixelate")
    """

    llm_endpoint: str | None = None
    llm_model: str = "gpt-oss-20b"
    llm_batch_size: int = 20
    llm_temperature: float = 0.1
    llm_max_tokens: int = 8192
    ocr_workers: int = 8
    confidence_threshold: float = 0.5
    redact: bool = False
    redact_output_dir: Path | None = None
    redact_method: str = "redbox"

    # Entity types to detect
    detect_entities: list[str] = field(default_factory=lambda: ["PERSON", "EMAIL", "PHONE"])

    # Prompt configuration
    system_prompt: str = """You are a PHI (Protected Health Information) detector analyzing text from iOS screenshots.
Your task is to identify personal names that could identify individuals.

IMPORTANT DISTINCTIONS:
- Personal names are names of real people (e.g., "Sarah", "John Smith", "Muhammad Ali")
- App names are NOT personal names (e.g., "Safari", "YouTube", "Disney+", "Siri", "Mario Kart")
- Device names with personal identifiers contain real names (e.g., "Sarah's iPad" contains "Sarah")

For device names like "Sarah's iPad", extract ONLY the personal name portion ("Sarah"), not the full device name."""

    positive_prompt: str = """## DETECT (return these as PHI):
- Personal names (first names, last names, full names)
- Email addresses containing names
- Phone numbers
- Any text that could identify a specific individual"""

    negative_prompt: str = """## IGNORE (do NOT flag these):
- App names (YouTube, Netflix, Disney+, Safari, TikTok, Instagram, Snapchat, etc.)
- Game character names (Mario, Luigi, Sonic, Pikachu, etc.)
- AI assistant names (Siri, Alexa, Cortana, etc.)
- Brand names and company names
- iOS UI elements (Screen Time, Settings, Control Center, etc.)
- Generic words and common nouns
- OCR artifacts and garbled text
- Times, dates, percentages, durations"""


def _get_file_hash(file_path: Path) -> str:
    """Get hash of file for cache key (uses name + size + mtime for speed)."""
    stat = file_path.stat()
    return f"{file_path.name}_{stat.st_size}_{stat.st_mtime_ns}"


def _get_content_hash(file_path: Path) -> str:
    """Get content-based hash for cache key (slower but handles duplicates)."""
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _ocr_single_image(args: tuple[str, bool]) -> tuple[str, dict | None, str | None]:
    """OCR a single image. Run in separate process.

    Args:
        args: Tuple of (image_path_str, use_content_hash)

    Returns:
        (path_str, ocr_dict, file_hash)
    """
    from phi_detector_remover.core.ocr import TesseractEngine

    image_path_str, use_content_hash = args
    image_path = Path(image_path_str)

    try:
        # Get file hash for caching
        if use_content_hash:
            file_hash = _get_content_hash(image_path)
        else:
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
            "confidence": ocr_result.confidence,
        }
        return image_path_str, ocr_dict, file_hash
    except Exception as e:
        print(f"  OCR error on {image_path.name}: {e}")
        return image_path_str, None, None


def _call_llm_batch(
    batch_texts: dict[str, str],
    config: PHIDetectionConfig,
    retry_count: int = 0,
) -> dict[str, list[dict]]:
    """Call LLM with multiple texts in one request.

    Args:
        batch_texts: Dict of {image_id: ocr_text}
        config: Detection configuration
        retry_count: Current retry attempt

    Returns:
        Dict of {image_id: [{"text": ..., "type": ...}, ...]}
    """
    import httpx

    if not config.llm_endpoint:
        return {}

    batch_content = "\n\n".join(
        f"=== IMAGE {img_id} ===\n{text[:1000]}" for img_id, text in batch_texts.items()
    )

    prompt = f"""{config.system_prompt}

IMPORTANT: You are analyzing text from MULTIPLE images. For each image, identify PHI.
Output JSON with results grouped by image ID:
{{
    "results": {{
        "IMAGE_ID_1": {{"entities": [{{"text": "name", "type": "PERSON"}}]}},
        "IMAGE_ID_2": {{"entities": []}}
    }}
}}

{config.positive_prompt}

{config.negative_prompt}

{batch_content}
"""

    try:
        endpoint = config.llm_endpoint.rstrip("/") + "/chat/completions"
        response = httpx.post(
            endpoint,
            json={
                "model": config.llm_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": config.llm_temperature,
                "max_tokens": config.llm_max_tokens,
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

    except json.JSONDecodeError:
        if retry_count < 2:
            # Retry with smaller batch
            items = list(batch_texts.items())
            mid = len(items) // 2
            if mid > 0:
                first_half = dict(items[:mid])
                second_half = dict(items[mid:])
                results = {}
                r1 = _call_llm_batch(first_half, config, retry_count + 1)
                r2 = _call_llm_batch(second_half, config, retry_count + 1)
                results.update(r1)
                results.update(r2)
                return results
        return {}
    except Exception as e:
        print(f"LLM batch error: {e}")
        return {}


def _find_bbox_for_text(text: str, words: list[dict]) -> dict | None:
    """Find bounding box for detected text by matching consecutive words."""
    from phi_detector_remover.core.models import BoundingBox

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

            return {"x": min_x, "y": min_y, "width": max_x - min_x, "height": max_y - min_y}

    return None


def detect_phi_batch(
    catalog: pl.DataFrame | list[Path] | list[str],
    file_path_column: str = "file_path",
    config: PHIDetectionConfig | None = None,
    cache_dir: Path | None = None,
    use_content_hash: bool = False,
    progress_callback: callable | None = None,
) -> pl.DataFrame:
    """Detect PHI in a batch of images.

    This is the main entry point for Dagster pipeline integration.
    Uses parallel OCR and batched LLM calls for efficiency.

    Args:
        catalog: Either a Polars DataFrame with file paths, or a list of paths
        file_path_column: Column name containing file paths (if DataFrame)
        config: Detection configuration
        cache_dir: Directory for OCR cache (optional)
        use_content_hash: Use content-based hash for cache (handles duplicates)
        progress_callback: Optional callback(current, total, message)

    Returns:
        Polars DataFrame with columns:
        - file_path: Original file path
        - phi_detected: Boolean indicating PHI found
        - phi_entities: List of detected entities as JSON
        - phi_count: Number of PHI entities detected
        - ocr_text: Extracted OCR text
        - processing_time_ms: Time to process this image

    Example:
        >>> config = PHIDetectionConfig(
        ...     llm_endpoint="http://YOUR_LLM_HOST:1234/v1",
        ...     llm_model="gpt-oss-20b",
        ... )
        >>> results = detect_phi_batch(
        ...     catalog=screenshot_df,
        ...     file_path_column="file_path",
        ...     config=config,
        ... )
    """
    import polars as pl

    config = config or PHIDetectionConfig()

    # Extract file paths
    if isinstance(catalog, pl.DataFrame):
        file_paths = [Path(p) for p in catalog[file_path_column].to_list()]
    else:
        file_paths = [Path(p) for p in catalog]

    # Load OCR cache
    ocr_cache: dict[str, dict] = {}
    cache_file = cache_dir / "ocr_cache.pkl" if cache_dir else None
    if cache_file and cache_file.exists():
        try:
            with open(cache_file, "rb") as f:
                ocr_cache = pickle.load(f)
        except Exception:
            pass

    # Step 1: OCR with caching
    ocr_results: dict[str, dict] = {}
    images_to_ocr: list[Path] = []

    for file_path in file_paths:
        if use_content_hash:
            file_hash = _get_content_hash(file_path)
        else:
            file_hash = _get_file_hash(file_path)

        if file_hash in ocr_cache:
            ocr_results[str(file_path)] = ocr_cache[file_hash]
        else:
            images_to_ocr.append(file_path)

    if progress_callback:
        progress_callback(len(ocr_results), len(file_paths), "Cache hits")

    # Run OCR in parallel
    if images_to_ocr:
        completed = 0
        args_list = [(str(p), use_content_hash) for p in images_to_ocr]

        with ProcessPoolExecutor(max_workers=config.ocr_workers) as executor:
            futures = {executor.submit(_ocr_single_image, args): args[0] for args in args_list}

            for future in as_completed(futures):
                completed += 1
                if progress_callback and completed % 50 == 0:
                    progress_callback(
                        len(ocr_results) + completed,
                        len(file_paths),
                        f"OCR progress: {completed}/{len(images_to_ocr)}",
                    )

                try:
                    path_str, ocr_dict, file_hash = future.result()
                    if ocr_dict is not None and file_hash is not None:
                        ocr_results[path_str] = ocr_dict
                        ocr_cache[file_hash] = ocr_dict
                except Exception as e:
                    print(f"OCR future error: {e}")

        # Save updated cache
        if cache_file:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                with open(cache_file, "wb") as f:
                    pickle.dump(ocr_cache, f)
            except Exception:
                pass

    # Step 2: LLM detection in batches
    all_results: list[dict[str, Any]] = []
    image_paths = list(ocr_results.keys())
    batch_size = config.llm_batch_size

    for batch_start in range(0, len(image_paths), batch_size):
        batch_end = min(batch_start + batch_size, len(image_paths))
        batch_paths = image_paths[batch_start:batch_end]

        if progress_callback:
            batch_num = batch_start // batch_size + 1
            total_batches = (len(image_paths) + batch_size - 1) // batch_size
            progress_callback(
                batch_start,
                len(image_paths),
                f"LLM batch {batch_num}/{total_batches}",
            )

        # Build batch texts
        batch_texts = {}
        for path in batch_paths:
            img_id = Path(path).name
            batch_texts[img_id] = ocr_results[path]["text"][:1000]

        # Call LLM
        start_time = time.perf_counter()
        llm_results = _call_llm_batch(batch_texts, config) if config.llm_endpoint else {}
        batch_time_ms = (time.perf_counter() - start_time) * 1000

        # Process results
        for path in batch_paths:
            img_id = Path(path).name
            ocr_data = ocr_results[path]

            entities = llm_results.get(img_id, [])
            if isinstance(entities, dict):
                entities = entities.get("entities", [])

            # Normalize entities and filter by allow_list
            normalized_entities = []
            for entity in entities:
                if isinstance(entity, str):
                    entity = {"text": entity, "type": "PERSON"}
                if isinstance(entity, dict) and entity.get("text"):
                    text = entity.get("text", "")
                    # Skip if text matches allow_list (case-insensitive)
                    if text.lower().strip() in GLOBAL_ALLOW_LIST:
                        continue
                    # Find bounding box
                    bbox = _find_bbox_for_text(text, ocr_data["words"])
                    # Skip if bbox is too large (likely a chart or image, not text)
                    # PHI text should never be wider than 350px or taller than 60px
                    if bbox:
                        if bbox.get("width", 0) > 350 or bbox.get("height", 0) > 60:
                            continue
                    normalized_entities.append(
                        {
                            "text": text,
                            "type": entity.get("type", "PERSON"),
                            "confidence": entity.get("confidence", 0.9),
                            "bbox": bbox,
                        }
                    )

            all_results.append(
                {
                    "file_path": path,
                    "phi_detected": len(normalized_entities) > 0,
                    "phi_entities": json.dumps(normalized_entities),
                    "phi_count": len(normalized_entities),
                    "ocr_text": ocr_data["text"],
                    "ocr_confidence": ocr_data["confidence"],
                    "processing_time_ms": batch_time_ms / len(batch_paths),
                }
            )

    # Step 3: Redact if requested
    if config.redact and config.redact_output_dir:
        from phi_detector_remover.core.models import BoundingBox, PHIRegion
        from phi_detector_remover.core.remover import PHIRemover

        remover = PHIRemover(method=config.redact_method)

        for result in all_results:
            if not result["phi_detected"]:
                continue

            entities = json.loads(result["phi_entities"])
            regions = []
            for entity in entities:
                if entity.get("bbox"):
                    bbox = BoundingBox(**entity["bbox"])
                    region = PHIRegion(
                        entity_type=entity["type"],
                        text=entity["text"],
                        confidence=entity.get("confidence", 0.9),
                        bbox=bbox,
                        source="llm",
                    )
                    regions.append(region)

            if regions:
                file_path = Path(result["file_path"])
                image_bytes = file_path.read_bytes()
                redacted_bytes = remover.remove(image_bytes, regions)

                output_path = config.redact_output_dir / file_path.name
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(redacted_bytes)
                result["redacted_path"] = str(output_path)

    return pl.DataFrame(all_results)


def detect_phi_single(
    image_path: Path | str,
    config: PHIDetectionConfig | None = None,
) -> dict[str, Any]:
    """Detect PHI in a single image.

    Convenience function for processing individual images.

    Args:
        image_path: Path to image file
        config: Detection configuration

    Returns:
        Dict with detection results
    """
    import polars as pl

    results = detect_phi_batch(
        catalog=[image_path],
        config=config,
    )
    return results.to_dicts()[0]


# Export for easy import
__all__ = [
    "PHIDetectionConfig",
    "detect_phi_batch",
    "detect_phi_single",
]
