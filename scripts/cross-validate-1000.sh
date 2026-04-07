#!/usr/bin/env bash
# Cross-validate Rust vs Python on 1000 images.
# Runs Python in backend container, Rust in rust-tauri-ocr container,
# then compares with a Python analysis script.
set -euo pipefail

cd /opt/ios-screen-time-screenshot-processing

OUT_DIR="profiling-reports/cross-validation"
mkdir -p "$OUT_DIR"

echo "=== Step 1: Pick 1000 random images ==="
docker compose --env-file docker/.env -f docker/docker-compose.dev.yml exec -T backend python3 -c "
import os, random
imgs = []
for root, _, files in os.walk('/app/uploads'):
    for f in sorted(files):
        if f.lower().endswith(('.png', '.jpg', '.jpeg')):
            imgs.append(os.path.join(root, f))
random.seed(42)
random.shuffle(imgs)
for p in imgs[:1000]:
    print(p)
" > "$OUT_DIR/image_paths.txt"
echo "  $(wc -l < "$OUT_DIR/image_paths.txt") images selected"

echo ""
echo "=== Step 2: Run Python pipeline on 1000 images ==="
docker compose --env-file docker/.env -f docker/docker-compose.dev.yml exec -T backend python3 -c "
import json, sys, time
from screenshot_processor.core.image_processor import load_and_validate_image
from screenshot_processor.core.bar_extraction import slice_image
from screenshot_processor.core.line_based_detection import LineBasedDetector

detector = LineBasedDetector.default()
paths = [l.strip() for l in sys.stdin if l.strip()]
results = []

for i, path in enumerate(paths):
    if i % 100 == 0: print(f'  [{i}/{len(paths)}]...', file=sys.stderr)
    t0 = time.perf_counter()
    try:
        img = load_and_validate_image(path)
        h, w = img.shape[:2]
        result = detector.detect(img, resolution=f'{w}x{h}')
        if result.success:
            b = result.bounds
            row, _, _ = slice_image(img, b.x, b.y, b.width, b.height)
            ms = (time.perf_counter() - t0) * 1000
            hourly_str = ','.join(f'{v:.1f}' for v in row[:24])
            results.append(json.dumps({
                'path': path, 'ok': True,
                'bounds': f'{b.x},{b.y},{b.width},{b.height}',
                'hourly': hourly_str, 'total': round(sum(row[:24]),1), 'ms': round(ms,1)
            }))
        else:
            ms = (time.perf_counter() - t0) * 1000
            results.append(json.dumps({'path': path, 'ok': False, 'err': (result.error or '')[:80], 'ms': round(ms,1)}))
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        results.append(json.dumps({'path': path, 'ok': False, 'err': str(e)[:80], 'ms': round(ms,1)}))

print('\n'.join(results))
" < "$OUT_DIR/image_paths.txt" > "$OUT_DIR/python_results.jsonl" 2>&1
echo "  $(wc -l < "$OUT_DIR/python_results.jsonl") Python results"

echo ""
echo "=== Step 3: Build Rust bench binary with JSON output ==="
# Build the Rust binary that processes a list of paths and outputs JSON
docker run --rm \
  -v /opt/ios-screen-time-screenshot-processing/frontend/src-tauri:/app \
  rust-tauri-ocr \
  cargo build --release --example bench_pipeline 2>&1 | tail -3

echo ""
echo "=== Step 4: Run Rust pipeline on 1000 images ==="
# Mount the uploads volume so Rust can read the same images
UPLOADS_VOLUME=$(docker compose --env-file docker/.env -f docker/docker-compose.dev.yml exec -T backend sh -c 'df /app/uploads | tail -1 | awk "{print \$1}"')
echo "  Uploads on: $UPLOADS_VOLUME"

docker run --rm \
  -v /opt/ios-screen-time-screenshot-processing/frontend/src-tauri:/app \
  -v "$OUT_DIR:/out" \
  --volumes-from "$(docker compose --env-file docker/.env -f docker/docker-compose.dev.yml ps -q backend)" \
  rust-tauri-ocr \
  sh -c '
    while IFS= read -r path; do
      result=$(/app/target/release/examples/bench_pipeline --json-single "$path" 2>/dev/null || echo "{\"path\":\"$path\",\"ok\":false}")
      echo "$result"
    done < /out/image_paths.txt
  ' > "$OUT_DIR/rust_results.jsonl" 2>&1
echo "  $(wc -l < "$OUT_DIR/rust_results.jsonl") Rust results"

echo ""
echo "=== Step 5: Compare results ==="
python3 scripts/cross-validate-compare.py "$OUT_DIR"
