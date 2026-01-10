"""Debug cache issue."""

from collections import Counter
from pathlib import Path

RAW_DATA_DIR = Path("/path/to/raw-data")

# Find all images
image_extensions = {".png", ".jpg", ".jpeg"}
all_images = []
for ext in image_extensions:
    all_images.extend(RAW_DATA_DIR.rglob(f"*{ext}"))

all_images = list({str(p): p for p in all_images}.values())
all_images = [p for p in all_images if p.name != "Thumbs.db" and "PHI" not in str(p)]

print(f"Total images: {len(all_images)}")


# Check for duplicate hashes
def get_file_hash(file_path: Path) -> str:
    stat = file_path.stat()
    return f"{file_path.name}_{stat.st_size}_{stat.st_mtime_ns}"


hashes = [get_file_hash(p) for p in all_images]
hash_counts = Counter(hashes)
dupes = [(h, c) for h, c in hash_counts.items() if c > 1]

print(f"Unique hashes: {len(set(hashes))}")
print(f"Duplicate hashes: {len(dupes)}")

if dupes:
    print("\nDuplicate hash examples:")
    for h, c in sorted(dupes, key=lambda x: -x[1])[:10]:
        print(f"  {c}x: {h}")
        # Show which files have this hash
        matching = [p for p in all_images if get_file_hash(p) == h]
        for p in matching[:3]:
            print(f"       {p}")
