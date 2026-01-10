#!/usr/bin/env bash
# Build and run all 4 OCR binding benchmarks in Docker containers.
# Each container processes images from /tmp/ocr-bench-images/ and outputs JSON lines.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IMG_DIR="/tmp/ocr-bench-images"
OUT_DIR="/opt/ios-screen-time-screenshot-processing/profiling-reports/ocr-benchmark"
mkdir -p "$OUT_DIR"

echo "=== Building benchmark containers ==="

# Build all 4 in parallel
docker build -t ocr-bench-pytesseract -f "$SCRIPT_DIR/Dockerfile.pytesseract" "$SCRIPT_DIR" &
docker build -t ocr-bench-tesseractjs -f "$SCRIPT_DIR/Dockerfile.tesseractjs" "$SCRIPT_DIR" &
docker build -t ocr-bench-leptess -f "$SCRIPT_DIR/Dockerfile.leptess" "$SCRIPT_DIR" &
docker build -t ocr-bench-tesseract-rs -f "$SCRIPT_DIR/Dockerfile.tesseract_rs" "$SCRIPT_DIR" &
wait
echo "All containers built."

echo ""
echo "=== Running benchmarks (10 images × 2 PSM modes × 3 runs each) ==="
echo ""

# Run each binding
echo "--- pytesseract ---"
docker run --rm -v "$IMG_DIR:/images:ro" ocr-bench-pytesseract /images > "$OUT_DIR/raw_pytesseract.jsonl"
echo "  Done: $(wc -l < "$OUT_DIR/raw_pytesseract.jsonl") results"

echo "--- tesseract.js ---"
docker run --rm -v "$IMG_DIR:/images:ro" ocr-bench-tesseractjs /images > "$OUT_DIR/raw_tesseractjs.jsonl"
echo "  Done: $(wc -l < "$OUT_DIR/raw_tesseractjs.jsonl") results"

echo "--- leptess ---"
docker run --rm -v "$IMG_DIR:/images:ro" ocr-bench-leptess /images > "$OUT_DIR/raw_leptess.jsonl"
echo "  Done: $(wc -l < "$OUT_DIR/raw_leptess.jsonl") results"

echo "--- tesseract-rs ---"
docker run --rm -v "$IMG_DIR:/images:ro" ocr-bench-tesseract-rs /images > "$OUT_DIR/raw_tesseract_rs.jsonl"
echo "  Done: $(wc -l < "$OUT_DIR/raw_tesseract_rs.jsonl") results"

echo ""
echo "=== All bindings complete. Running analysis... ==="

# Combine all results
cat "$OUT_DIR"/raw_*.jsonl > "$OUT_DIR/all_results.jsonl"
echo "Total results: $(wc -l < "$OUT_DIR/all_results.jsonl")"

echo "Results in $OUT_DIR/"
