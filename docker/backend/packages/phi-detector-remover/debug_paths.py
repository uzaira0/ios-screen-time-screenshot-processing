"""Debug image path issues."""

from collections import Counter
from pathlib import Path

RAW_DATA_DIR = Path("/path/to/raw-data")

# Find all images
image_extensions = {".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"}
all_images = []
for ext in image_extensions:
    all_images.extend(RAW_DATA_DIR.rglob(f"*{ext}"))

all_images = [p for p in all_images if p.name != "Thumbs.db" and "PHI" not in str(p)]
print(f"Total images found: {len(all_images)}")

# Check for duplicate paths
path_strs = [str(p) for p in all_images]
unique_paths = set(path_strs)
print(f"Unique paths: {len(unique_paths)}")

if len(path_strs) != len(unique_paths):
    counts = Counter(path_strs)
    dupes = [(p, c) for p, c in counts.items() if c > 1]
    print(f"Duplicates: {len(dupes)}")
    for p, c in dupes[:5]:
        print(f"  {c}x: {p}")

# Check for duplicate file names
names = [p.name for p in all_images]
name_counts = Counter(names)
dupe_names = [(n, c) for n, c in name_counts.items() if c > 1]
print(f"\nDuplicate file names: {len(dupe_names)}")
print(f"Example duplicates:")
for n, c in sorted(dupe_names, key=lambda x: -x[1])[:10]:
    print(f"  {c}x: {n}")

# Check extension case sensitivity
ext_counts = Counter(p.suffix for p in all_images)
print(f"\nExtensions: {dict(ext_counts)}")
