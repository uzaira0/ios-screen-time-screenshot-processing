#!/usr/bin/env python3
"""Upload screenshots to ios-screen-time-screenshot-processing.

Uses batch uploads with concurrency for optimal performance.

Usage:
    # Upload all images (uses batch endpoint)
    python upload_test_images.py --api-key KEY --source-dir /path/to/screenshots

    # Upload with custom settings
    python upload_test_images.py --api-key KEY --batch-size 30 --concurrency 2

    # Sequential single uploads (slower, for debugging)
    python upload_test_images.py --api-key KEY --sequential

Environment variables:
    UPLOAD_API_KEY - API key for uploads
"""

import argparse
import asyncio
import base64
import hashlib
import os
import re
import sys
import time
from pathlib import Path

import httpx

# Default configuration
DEFAULT_BASE_URL = "http://YOUR_SERVER_HOST/api/v1"
DEFAULT_SOURCE_DIR = r"/path/to/screenshots"


def extract_participant_id(file_path: Path) -> str:
    """Extract participant ID from file path."""
    path_str = str(file_path)
    match = re.search(r"P1-(\d{4})(?:-[A-Z])?", path_str)
    if match:
        return f"P1-{match.group(1)}-A"
    return "P1-0000-A"


def prepare_batch_item(file_path: Path) -> dict:
    """Prepare a single item for batch upload."""
    image_bytes = file_path.read_bytes()
    return {
        "screenshot": base64.b64encode(image_bytes).decode("utf-8"),
        "participant_id": extract_participant_id(file_path),
        "sha256": hashlib.sha256(image_bytes).hexdigest(),
        "filename": file_path.name,
    }


async def upload_batch(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    items: list[dict],
    group_id: str,
) -> tuple[int, int, list[str]]:
    """Upload a batch of screenshots. Returns (success, failed, errors)."""
    payload = {
        "group_id": group_id,
        "image_type": "screen_time",
        "screenshots": items,
    }

    try:
        response = await client.post(
            f"{base_url}/screenshots/upload/batch",
            json=payload,
            headers={"X-API-Key": api_key},
            timeout=120,
        )
        response.raise_for_status()
        result = response.json()
        success = result.get("successful_count", 0) + result.get("duplicate_count", 0)
        failed = result.get("failed_count", 0)
        return success, failed, []
    except httpx.HTTPStatusError as e:
        return 0, len(items), [f"HTTP {e.response.status_code}: {e.response.text[:100]}"]
    except Exception as e:
        return 0, len(items), [str(e)[:100]]


async def upload_with_batches(
    files: list[Path],
    base_url: str,
    api_key: str,
    group_id: str,
    batch_size: int = 30,
    concurrency: int = 2,
) -> tuple[int, int]:
    """Upload files using batch endpoint with concurrency."""
    print(f"Uploading {len(files)} screenshots to group '{group_id}'")
    print(f"  Batch size: {batch_size}, Concurrency: {concurrency}")

    # Prepare all items (this can be slow for large datasets)
    print("Preparing images...")
    items = []
    for i, f in enumerate(files):
        items.append(prepare_batch_item(f))
        if (i + 1) % 100 == 0:
            print(f"  Prepared {i + 1}/{len(files)}...")

    # Split into batches
    batches = [items[i:i + batch_size] for i in range(0, len(items), batch_size)]
    print(f"  Total batches: {len(batches)}")

    semaphore = asyncio.Semaphore(concurrency)
    total_success = 0
    total_failed = 0
    all_errors = []
    completed = 0
    start_time = time.perf_counter()

    async def upload_one_batch(batch: list[dict], batch_num: int):
        nonlocal total_success, total_failed, completed, all_errors
        async with semaphore:
            async with httpx.AsyncClient() as client:
                success, failed, errors = await upload_batch(
                    client, base_url, api_key, batch, group_id
                )
                total_success += success
                total_failed += failed
                all_errors.extend(errors)
                completed += 1

                elapsed = time.perf_counter() - start_time
                rate = total_success / elapsed if elapsed > 0 else 0
                print(f"[{completed}/{len(batches)}] Uploaded {total_success} so far... ({rate:.1f} img/sec)")

    tasks = [upload_one_batch(b, i) for i, b in enumerate(batches)]
    await asyncio.gather(*tasks)

    return total_success, total_failed


def upload_sequential(
    files: list[Path],
    base_url: str,
    api_key: str,
    group_id: str,
) -> tuple[int, int]:
    """Upload files one at a time (slower, for debugging)."""
    print(f"Uploading {len(files)} screenshots sequentially...")

    success_count = 0
    fail_count = 0

    with httpx.Client(timeout=60) as client:
        for i, file_path in enumerate(files, 1):
            participant_id = extract_participant_id(file_path)
            image_bytes = file_path.read_bytes()

            payload = {
                "screenshot": base64.b64encode(image_bytes).decode("utf-8"),
                "participant_id": participant_id,
                "group_id": group_id,
                "image_type": "screen_time",
                "sha256": hashlib.sha256(image_bytes).hexdigest(),
            }

            try:
                response = client.post(
                    f"{base_url}/screenshots/upload",
                    json=payload,
                    headers={"X-API-Key": api_key},
                )
                response.raise_for_status()
                success_count += 1
            except Exception as e:
                fail_count += 1
                print(f"  [{i}] Error: {e}")

            if i % 50 == 0:
                print(f"[{i}/{len(files)}] Uploaded {success_count} so far...")

    return success_count, fail_count


def main():
    parser = argparse.ArgumentParser(description="Upload screenshots with optimal performance")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("UPLOAD_API_KEY"),
        help="API key for uploads (or set UPLOAD_API_KEY env var)",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL for API (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--source-dir",
        default=DEFAULT_SOURCE_DIR,
        help="Directory containing screenshots",
    )
    parser.add_argument(
        "--group-id",
        default="TECH-iOS-20260110",
        help="Group ID for uploads",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Max images to upload (default: all)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Images per batch (default: 50, max: 60)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Concurrent batch uploads (default: 5)",
    )
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Use sequential single uploads (slower)",
    )
    args = parser.parse_args()

    if not args.api_key:
        print("ERROR: API key required. Use --api-key or set UPLOAD_API_KEY env var")
        sys.exit(1)

    source_dir = Path(args.source_dir)
    if not source_dir.exists():
        print(f"ERROR: Source directory not found: {source_dir}")
        sys.exit(1)

    # Find image files
    files = []
    for ext in ["*.png", "*.PNG", "*.jpg", "*.JPG", "*.jpeg", "*.JPEG"]:
        files.extend(source_dir.rglob(ext))

    if args.count:
        files = files[:args.count]

    print(f"Found {len(files)} image files")

    if not files:
        print("No image files found!")
        sys.exit(1)

    start_time = time.perf_counter()

    if args.sequential:
        success, failed = upload_sequential(
            files, args.base_url, args.api_key, args.group_id
        )
    else:
        success, failed = asyncio.run(upload_with_batches(
            files, args.base_url, args.api_key, args.group_id,
            batch_size=min(args.batch_size, 60),
            concurrency=args.concurrency,
        ))

    elapsed = time.perf_counter() - start_time
    rate = success / elapsed if elapsed > 0 else 0

    print(f"\nDone! Uploaded: {success}, Failed: {failed}")
    print(f"Total time: {elapsed:.1f}s ({rate:.1f} images/sec)")


if __name__ == "__main__":
    main()
