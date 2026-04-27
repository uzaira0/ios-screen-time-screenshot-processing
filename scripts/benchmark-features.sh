#!/usr/bin/env bash
# =============================================================================
# Feature-Level Hyperfine Benchmarks
# =============================================================================
# Benchmarks every user-facing processing feature independently so slow paths
# are ranked and easy to find.  Run this script whenever you suspect a
# regression or want to compare OCR engines / algorithm variants.
#
# Usage:
#   scripts/benchmark-features.sh [--api-url URL] [--runs N] [output-dir]
#
# Output:
#   profiling-reports/features/{feature}.json  — raw hyperfine JSON
#   profiling-reports/features/summary.md      — ranked wall-time table
#
# Prerequisites:
#   hyperfine, curl, python3 (with screenshot_processor installed), jq
#   Optional: running API at API_URL for endpoint benchmarks
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# ── Args ──────────────────────────────────────────────────────────────────────
API_URL="http://localhost:8002"
RUNS=5
OUT_DIR="profiling-reports/features"

while [[ $# -gt 0 ]]; do
    case $1 in
        --api-url) API_URL="$2"; shift 2 ;;
        --runs)    RUNS="$2";    shift 2 ;;
        *)         OUT_DIR="$1"; shift ;;
    esac
done

mkdir -p "$OUT_DIR"

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

section()  { echo -e "\n${BLUE}${BOLD}━━━ $1 ━━━${NC}"; }
ok()       { echo -e "${GREEN}✓${NC} $1"; }
warn()     { echo -e "${YELLOW}⚠${NC} $1"; }
fail()     { echo -e "${RED}✗${NC} $1"; }

# ── Helpers ───────────────────────────────────────────────────────────────────
FIXTURE_IMG="tests/fixtures/images/IMG_0806 Cropped.png"
FIXTURE_IMG2="tests/fixtures/images/IMG_0807 Cropped.png"
BENCHMARK_RESULTS=()   # accumulates "label mean_ms" pairs for summary

# Run a hyperfine benchmark and record mean ms for summary.
# Usage: run_bench NAME OUTPUT_SLUG WARMUP [hyperfine extra args...]
run_bench() {
    local name="$1"
    local slug="$2"
    local warmup="${3:-1}"
    shift 3
    local out="$OUT_DIR/${slug}.json"

    if hyperfine \
        --warmup "$warmup" \
        --runs "$RUNS" \
        --export-json "$out" \
        "$@" 2>&1; then
        # Extract mean of first command in seconds, convert to ms
        local mean_ms
        mean_ms=$(jq '[.results[].mean] | add / length * 1000 | round' "$out" 2>/dev/null || echo "?")
        BENCHMARK_RESULTS+=("${mean_ms}ms  ${name}")
        ok "${name} → ${mean_ms}ms mean (${out})"
    else
        warn "${name} — benchmark had issues"
    fi
}

api_running() { curl -sf "$API_URL/health" >/dev/null 2>&1; }

# ── Check prerequisites ───────────────────────────────────────────────────────
for cmd in hyperfine jq python3; do
    if ! command -v "$cmd" &>/dev/null; then
        fail "Required tool missing: $cmd"
        exit 1
    fi
done

[[ -f "$FIXTURE_IMG" ]] || { fail "Fixture image not found: $FIXTURE_IMG"; exit 1; }

# =============================================================================
# 1. Python Core Pipeline Stages
# =============================================================================
section "Python — Per-Stage Processing"

HAS_CORE=$(python3 -c "import screenshot_processor.core; print('yes')" 2>/dev/null || echo "no")
if [[ "$HAS_CORE" == "yes" ]]; then
    IMG_PATH="$(realpath "$FIXTURE_IMG")"
    IMG_PATH2="$(realpath "$FIXTURE_IMG2")"

    # 1a. Image normalisation (dark-mode + contrast)
    run_bench "Python: image normalisation" "py-normalise" 2 \
        -n "convert_dark_mode + adjust_contrast" \
        "python3 -c \"
import cv2
from screenshot_processor.core.image_utils import convert_dark_mode, adjust_contrast_brightness
img = cv2.imread('${IMG_PATH}')
img = convert_dark_mode(img)
img = adjust_contrast_brightness(img)
\""

    # 1b. Colour reduction (preprocessing step)
    run_bench "Python: colour reduction" "py-colour-reduce" 2 \
        -n "darken_non_white + reduce_color_count(2)" \
        "python3 -c \"
import cv2
from screenshot_processor.core.image_utils import darken_non_white, reduce_color_count
img = cv2.imread('${IMG_PATH}')
img = darken_non_white(img)
img = reduce_color_count(img, 2)
\""

    # 1c. Grid detection (line-based strategy)
    run_bench "Python: grid detection" "py-grid-detect" 1 \
        -n "detect_grid_bounds (line-based)" \
        "python3 -c \"
import cv2
from screenshot_processor.core.image_processor import detect_grid_bounds
img = cv2.imread('${IMG_PATH}')
detect_grid_bounds(img, method='line_based')
\" 2>/dev/null" \
        -n "detect_grid_bounds (lookup)" \
        "python3 -c \"
import cv2
from screenshot_processor.core.image_processor import detect_grid_bounds
img = cv2.imread('${IMG_PATH}')
detect_grid_bounds(img, method='lookup')
\" 2>/dev/null"

    # 1d. Bar extraction (after grid is known)
    run_bench "Python: bar extraction (slice_image)" "py-bar-extract" 2 \
        -n "slice_image" \
        "python3 -c \"
import cv2
import numpy as np
from screenshot_processor.core.bar_extraction import slice_image
from screenshot_processor.core.interfaces import GridBounds
img = cv2.imread('${IMG_PATH}')
h, w = img.shape[:2]
gb = GridBounds(upper_left=(int(w*0.05), int(h*0.25)), lower_right=(int(w*0.95), int(h*0.55)))
slice_image(img, gb)
\" 2>/dev/null"

    # 1e. Alignment score (called after every slice)
    run_bench "Python: alignment score" "py-alignment" 2 \
        -n "compute_bar_alignment_score" \
        "python3 -c \"
import numpy as np
from screenshot_processor.core.bar_extraction import compute_bar_alignment_score
values = np.random.uniform(0, 60, 24).tolist()
compute_bar_alignment_score(values, 24)
\" 2>/dev/null"

    # 1f. Full pipeline (grid + bars + OCR)
    run_bench "Python: full pipeline" "py-full-pipeline" 1 \
        -n "process_image (${FIXTURE_IMG##*/})" \
        "python3 -c \"
from screenshot_processor.core.image_processor import process_image
result = process_image('${IMG_PATH}')
\" 2>/dev/null" \
        -n "process_image (${FIXTURE_IMG2##*/})" \
        "python3 -c \"
from screenshot_processor.core.image_processor import process_image
result = process_image('${IMG_PATH2}')
\" 2>/dev/null"

    # 1g. OCR engines — title extraction
    run_bench "Python: OCR title extraction" "py-ocr-title" 1 \
        -n "Tesseract (local)" \
        "python3 -c \"
import cv2
from screenshot_processor.core.ocr_engines.tesseract_engine import TesseractEngine
from screenshot_processor.core.ocr import extract_title
img = cv2.imread('${IMG_PATH}')
engine = TesseractEngine()
extract_title(img, engine)
\" 2>/dev/null"

else
    warn "screenshot_processor not importable — skipping Python stage benchmarks"
fi

# =============================================================================
# 2. Rust Criterion Benchmarks (cargo bench)
# =============================================================================
section "Rust — Criterion Benchmarks"

RUST_BENCH_DIR="frontend/src-tauri"
if [[ -d "$RUST_BENCH_DIR/benches" ]]; then
    CARGO_BENCH_OUT="$OUT_DIR/cargo-bench.txt"
    echo "[benchmark-features] Running cargo bench (output → $CARGO_BENCH_OUT)..."
    if cargo bench --manifest-path "$RUST_BENCH_DIR/Cargo.toml" 2>&1 | tee "$CARGO_BENCH_OUT" | \
       grep -E "test|bench|ns/iter|μs/iter|ms/iter" | head -30; then
        ok "Rust Criterion benchmarks → $CARGO_BENCH_OUT"
        # Extract key metrics for summary
        while IFS= read -r line; do
            if [[ "$line" =~ ([a-z_/]+)[[:space:]]+\.\.\.[[:space:]]bench:[[:space:]]+([0-9,]+)[[:space:]]+(ns|μs|ms) ]]; then
                name="${BASH_REMATCH[1]}"
                val="${BASH_REMATCH[2]//,/}"
                unit="${BASH_REMATCH[3]}"
                case "$unit" in
                    ns) ms=$(echo "scale=3; $val / 1000000" | bc) ;;
                    μs) ms=$(echo "scale=3; $val / 1000" | bc) ;;
                    ms) ms="$val" ;;
                esac
                BENCHMARK_RESULTS+=("${ms}ms  Rust/criterion: ${name}")
            fi
        done < "$CARGO_BENCH_OUT"
    else
        warn "cargo bench failed (leptonica missing?)"
    fi
fi

# =============================================================================
# 3. API Endpoint Latency
# =============================================================================
section "API Endpoints"

if api_running; then
    AUTH_HEADER='-H "X-Username: benchmark-runner"'

    # 3a. Read-only endpoints (hot path)
    run_bench "API: /health" "api-health" 3 \
        -n "/health" \
        "curl -sf ${API_URL}/health"

    run_bench "API: list endpoints (read)" "api-read" 3 \
        -n "/screenshots/stats" \
        "curl -sf -H 'X-Username: benchmark-runner' ${API_URL}/api/v1/screenshots/stats" \
        -n "/screenshots/groups" \
        "curl -sf -H 'X-Username: benchmark-runner' ${API_URL}/api/v1/screenshots/groups" \
        -n "/screenshots/list?page=1&page_size=10" \
        "curl -sf -H 'X-Username: benchmark-runner' '${API_URL}/api/v1/screenshots/list?page=1&page_size=10'" \
        -n "/screenshots/next" \
        "curl -sf -H 'X-Username: benchmark-runner' ${API_URL}/api/v1/screenshots/next"

    # 3b. Admin endpoints
    run_bench "API: admin endpoints" "api-admin" 3 \
        -n "/admin/users" \
        "curl -sf -H 'X-Username: admin' ${API_URL}/api/v1/admin/users" \
        -n "/auth/me" \
        "curl -sf -H 'X-Username: benchmark-runner' ${API_URL}/api/v1/auth/me"

    # 3c. Preprocessing summary (DB aggregation)
    run_bench "API: preprocessing summary (aggregation)" "api-preprocess-summary" 3 \
        -n "/screenshots/preprocessing-summary" \
        "curl -sf -H 'X-Username: benchmark-runner' ${API_URL}/api/v1/screenshots/preprocessing-summary"

    # 3d. CSV export (serialisation)
    run_bench "API: CSV export" "api-export" 2 \
        -n "/screenshots/export/csv" \
        "curl -sf -H 'X-Username: benchmark-runner' '${API_URL}/api/v1/screenshots/export/csv?limit=50' -o /dev/null"

    # 3e. WebSocket connection setup (connect + close)
    run_bench "API: WebSocket connect" "api-ws" 3 \
        -n "WebSocket connect + disconnect" \
        "python3 -c \"
import asyncio, websockets
async def ping():
    async with websockets.connect('${API_URL/http/ws}/api/v1/ws/benchmark-runner') as ws:
        await ws.recv()
asyncio.run(ping())
\" 2>/dev/null" || true

else
    warn "API not running at $API_URL — skipping endpoint benchmarks"
    warn "Start with: docker compose -f docker/docker-compose.dev.yml up -d"
fi

# =============================================================================
# 4. File Upload Throughput
# =============================================================================
section "File Upload"

if api_running && [[ -f "$FIXTURE_IMG" ]]; then
    UPLOAD_KEY="${UPLOAD_API_KEY:-$(grep UPLOAD_API_KEY docker/.env 2>/dev/null | cut -d= -f2 || echo '')}"
    if [[ -n "$UPLOAD_KEY" ]]; then
        # multipart upload
        run_bench "API: image upload (multipart)" "api-upload-multipart" 1 \
            -n "upload ${FIXTURE_IMG##*/} (${RUNS} runs)" \
            "curl -sf -H 'X-Username: benchmark-runner' \
                -F 'file=@${FIXTURE_IMG}' \
                ${API_URL}/api/v1/screenshots/upload/browser -o /dev/null"
    else
        warn "UPLOAD_API_KEY not set — skipping upload benchmarks"
    fi
fi

# =============================================================================
# 5. Summary (ranked by mean duration)
# =============================================================================
section "Summary — Ranked by Mean Duration"

SUMMARY_FILE="$OUT_DIR/summary.md"
{
    echo "# Feature Benchmark Summary"
    echo ""
    echo "Generated: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    echo "Runs per benchmark: $RUNS"
    echo ""
    echo "| Mean | Feature |"
    echo "|------|---------|"
} > "$SUMMARY_FILE"

if (( ${#BENCHMARK_RESULTS[@]} > 0 )); then
    # Sort numerically by the ms value (first field)
    printf '%s\n' "${BENCHMARK_RESULTS[@]}" | \
        sort -n | \
        while IFS= read -r line; do
            echo "| $line |" >> "$SUMMARY_FILE"
        done
fi

echo "" >> "$SUMMARY_FILE"
echo "Individual JSON results in: \`$OUT_DIR/\`" >> "$SUMMARY_FILE"

cat "$SUMMARY_FILE"
echo ""
ok "All done. Detailed results in: ${BLUE}$OUT_DIR/${NC}"
