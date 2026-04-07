#!/usr/bin/env bash
# =============================================================================
# CLI Benchmark Script
# =============================================================================
# Uses hyperfine to benchmark CLI commands with statistical analysis.
#
# Usage:
#   scripts/benchmark-cli.sh [output-dir]
#
# Requires: hyperfine (cargo install hyperfine)
# Python: Uses Docker backend for project code (image processing needs deps).
#         API latency tests run on host via curl.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

OUT_DIR="${1:-profiling-reports/cli}"
mkdir -p "$OUT_DIR"

# Docker backend exec
DOCKER_EXEC="docker compose --env-file docker/.env -f docker/docker-compose.dev.yml exec -T backend"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_header() { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }
log_ok()     { echo -e "${GREEN}✓${NC} $1"; }
log_warn()   { echo -e "${YELLOW}⚠${NC} $1"; }

if ! command -v hyperfine &>/dev/null; then
    echo "hyperfine not found. Install: cargo install hyperfine"
    exit 1
fi

# =============================================================================
# 1. Python Import Time (Docker backend)
# =============================================================================
log_header "Python Import Time (via Docker)"
hyperfine \
    --warmup 1 \
    --runs 5 \
    --export-json "$OUT_DIR/import-time.json" \
    --export-markdown "$OUT_DIR/import-time.md" \
    -n "screenshot_processor (top-level)" \
    "$DOCKER_EXEC python -c 'import screenshot_processor'" \
    -n "screenshot_processor.core.image_processor" \
    "$DOCKER_EXEC python -c 'import screenshot_processor.core.image_processor'" \
    -n "screenshot_processor.core.ocr" \
    "$DOCKER_EXEC python -c 'import screenshot_processor.core.ocr'" \
    -n "screenshot_processor.core.bar_extraction" \
    "$DOCKER_EXEC python -c 'import screenshot_processor.core.bar_extraction'" \
    2>/dev/null \
    && log_ok "Import time → $OUT_DIR/import-time.json" \
    || log_warn "Import time benchmarks had issues"

# =============================================================================
# 2. Image Processing Pipeline — different image sizes (Docker)
# =============================================================================
log_header "Image Processing Pipeline"

# Create test images inside Docker
$DOCKER_EXEC python -c "
import numpy as np
from PIL import Image
import os
os.makedirs('/tmp/bench-images', exist_ok=True)
for name, size in [('small', (300, 500)), ('medium', (1170, 2532)), ('large', (2340, 5064))]:
    img = np.random.randint(0, 255, (size[1], size[0], 3), dtype=np.uint8)
    Image.fromarray(img).save(f'/tmp/bench-images/{name}.png')
print('Test images created')
" 2>/dev/null

hyperfine \
    --warmup 1 \
    --runs 3 \
    --export-json "$OUT_DIR/pipeline-sizes.json" \
    --export-markdown "$OUT_DIR/pipeline-sizes.md" \
    -n "small (300x500)" \
    "$DOCKER_EXEC python -c \"
from screenshot_processor.core.image_utils import convert_dark_mode, darken_non_white, reduce_color_count
import cv2
img = cv2.imread('/tmp/bench-images/small.png')
img = convert_dark_mode(img)
img = darken_non_white(img)
img = reduce_color_count(img, 2)
\"" \
    -n "medium (1170x2532)" \
    "$DOCKER_EXEC python -c \"
from screenshot_processor.core.image_utils import convert_dark_mode, darken_non_white, reduce_color_count
import cv2
img = cv2.imread('/tmp/bench-images/medium.png')
img = convert_dark_mode(img)
img = darken_non_white(img)
img = reduce_color_count(img, 2)
\"" \
    -n "large (2340x5064)" \
    "$DOCKER_EXEC python -c \"
from screenshot_processor.core.image_utils import convert_dark_mode, darken_non_white, reduce_color_count
import cv2
img = cv2.imread('/tmp/bench-images/large.png')
img = convert_dark_mode(img)
img = darken_non_white(img)
img = reduce_color_count(img, 2)
\"" \
    2>/dev/null \
    && log_ok "Pipeline sizes → $OUT_DIR/pipeline-sizes.json" \
    || log_warn "Pipeline benchmarks had issues"

# Cleanup test images in Docker
$DOCKER_EXEC rm -rf /tmp/bench-images 2>/dev/null || true

# =============================================================================
# 3. API Endpoint Latency (if server is running)
# =============================================================================
log_header "API Endpoint Latency"

API_URL="${API_URL:-http://localhost:8002}"
if curl -s "$API_URL/health" >/dev/null 2>&1; then
    hyperfine \
        --warmup 3 \
        --runs 10 \
        --export-json "$OUT_DIR/api-latency.json" \
        --export-markdown "$OUT_DIR/api-latency.md" \
        -n "/health" \
        "curl -s $API_URL/health" \
        -n "/api/v1/screenshots/stats" \
        "curl -s -H 'X-Username: benchmark' $API_URL/api/v1/screenshots/stats" \
        -n "/api/v1/screenshots/groups" \
        "curl -s -H 'X-Username: benchmark' $API_URL/api/v1/screenshots/groups" \
        -n "/api/v1/screenshots/list?page=1&page_size=10" \
        "curl -s -H 'X-Username: benchmark' '$API_URL/api/v1/screenshots/list?page=1&page_size=10'" \
        2>/dev/null \
        && log_ok "API latency → $OUT_DIR/api-latency.json" \
        || log_warn "API benchmarks had issues"
else
    log_warn "API not running at $API_URL — skipping endpoint benchmarks"
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo -e "${GREEN}Done!${NC} CLI benchmarks saved to: ${BLUE}$OUT_DIR/${NC}"
find "$OUT_DIR" -type f -name "*.md" | while read -r f; do
    echo ""
    echo "=== $(basename "$f") ==="
    cat "$f"
done
