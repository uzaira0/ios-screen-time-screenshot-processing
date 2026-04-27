#!/usr/bin/env bash
# =============================================================================
# Master Profiling Script
# =============================================================================
# Runs profiling tools across the full stack and generates consolidated reports.
#
# Usage:
#   scripts/profile.sh [category]
#
# Categories:
#   all        - Run everything (default)
#   python     - Python CPU + memory profiling (runs in Docker)
#   complexity - Code complexity analysis (radon + wily)
#   frontend   - Bundle analysis + dead code (Knip)
#   rust       - Binary size + compile time analysis
#   db         - Database query profiling
#   benchmark  - Run pytest-benchmark with comparison (runs in Docker)
#   k6         - API endpoint load profiling
#   import     - Python import time analysis (runs in Docker)
#   features   - Hyperfine feature benchmarks (per-stage, API, Rust) — ranked by slowness
#
# Output: profiling-reports/YYYY-MM-DD_HH-MM/
#
# Python: Uses uv with Python 3.14 for host tools (radon, wily).
#         Uses Docker backend for project code (image processing, OCR, benchmarks).
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

TIMESTAMP="$(date +%Y-%m-%d_%H-%M)"
REPORT_DIR="profiling-reports/$TIMESTAMP"
CATEGORY="${1:-all}"

# Python via uv (--no-project avoids resolving monorepo deps missing on host)
UV="uv run --python 3.14 --no-project"

# Docker backend exec
DOCKER_EXEC="docker compose --env-file docker/.env -f docker/docker-compose.dev.yml exec -T backend"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_header() { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }
log_ok()     { echo -e "${GREEN}✓${NC} $1"; }
log_warn()   { echo -e "${YELLOW}⚠${NC} $1"; }
log_fail()   { echo -e "${RED}✗${NC} $1"; }
log_skip()   { echo -e "${YELLOW}↷${NC} $1 (skipped — tool not installed)"; }

ensure_dir() { mkdir -p "$1"; }

# Check if a uv-managed tool is available
has_uv_tool() { $UV "$1" --version &>/dev/null 2>&1 || $UV python -c "import $1" &>/dev/null 2>&1; }

# Check if a command exists
has() { command -v "$1" &>/dev/null; }

# Check if Docker backend is running
docker_backend_up() {
    $DOCKER_EXEC python -c "print('ok')" &>/dev/null 2>&1
}

# =============================================================================
# Python CPU + Memory Profiling (runs in Docker — needs project imports)
# =============================================================================
run_python() {
    log_header "Python Profiling"
    local out="$REPORT_DIR/python"
    ensure_dir "$out"

    if ! docker_backend_up; then
        log_fail "Docker backend not running. Start with: docker compose --env-file docker/.env -f docker/docker-compose.dev.yml up -d"
        return 1
    fi

    # --- Pyinstrument (call tree) — install in Docker if needed ---
    log_header "Pyinstrument — call tree profiler"
    $DOCKER_EXEC pip install -q pyinstrument 2>/dev/null
    $DOCKER_EXEC python -c "
import pyinstrument, io
p = pyinstrument.Profiler()
p.start()

from screenshot_processor.core.image_utils import convert_dark_mode, darken_non_white, reduce_color_count, scale_up
from screenshot_processor.core.bar_extraction import slice_image
import numpy as np
img = np.random.randint(0, 255, (2532, 1170, 3), dtype=np.uint8)
small = np.random.randint(0, 255, (200, 600, 3), dtype=np.uint8)
for _ in range(5):
    convert_dark_mode(img.copy())
    darken_non_white(img.copy())
    reduce_color_count(small.copy(), 2)
    scale_up(small.copy(), 4)

p.stop()
print(p.output_html())
" > "$out/pyinstrument-report.html" 2>/dev/null \
        && log_ok "Pyinstrument report → $out/pyinstrument-report.html" \
        || log_warn "Pyinstrument completed with warnings"

    # --- Memray (memory flamegraph) ---
    log_header "Memray — memory allocation profiler"
    $DOCKER_EXEC pip install -q memray 2>/dev/null
    $DOCKER_EXEC python -c "
import subprocess, sys
# Run memray as subprocess to get the binary output
sys.exit(subprocess.call([
    sys.executable, '-m', 'memray', 'run', '-o', '/tmp/memray.bin', '--force',
    '-c', '''
from screenshot_processor.core.image_utils import convert_dark_mode, scale_up
from screenshot_processor.core.bar_extraction import compute_bar_alignment_score
import numpy as np
img = np.random.randint(0, 255, (2532, 1170, 3), dtype=np.uint8)
small = np.random.randint(0, 255, (200, 600, 3), dtype=np.uint8)
for _ in range(3):
    convert_dark_mode(img.copy())
    scale_up(small.copy(), 4)
'''
]))
" 2>/dev/null \
    && $DOCKER_EXEC python -m memray flamegraph /tmp/memray.bin -o /tmp/memray-flamegraph.html --force 2>/dev/null \
    && docker compose --env-file docker/.env -f docker/docker-compose.dev.yml cp backend:/tmp/memray-flamegraph.html "$out/memray-flamegraph.html" 2>/dev/null \
    && log_ok "Memray flamegraph → $out/memray-flamegraph.html" \
    || log_warn "Memray completed with warnings"

    # --- Import time analysis ---
    run_import_time "$out"
}

# =============================================================================
# Import Time Analysis (runs in Docker)
# =============================================================================
run_import_time() {
    local out="${1:-$REPORT_DIR/python}"
    ensure_dir "$out"
    log_header "Import Time Analysis"

    if ! docker_backend_up; then
        log_fail "Docker backend not running"
        return 1
    fi

    $DOCKER_EXEC python -X importtime -c "import screenshot_processor" 2> "$out/import-time.txt" \
        && log_ok "Import time → $out/import-time.txt" \
        || log_warn "Import time analysis had warnings"
}

# =============================================================================
# Code Complexity Analysis (runs on host via uv — no project imports needed)
# =============================================================================
run_complexity() {
    log_header "Code Complexity Analysis"
    local out="$REPORT_DIR/complexity"
    ensure_dir "$out"

    # --- Radon ---
    if $UV radon --version &>/dev/null 2>&1; then
        # Cyclomatic complexity
        $UV radon cc src/ -a -s -j > "$out/radon-cc.json" 2>/dev/null \
            && log_ok "Cyclomatic complexity → $out/radon-cc.json"

        # Maintainability index
        $UV radon mi src/ -s -j > "$out/radon-mi.json" 2>/dev/null \
            && log_ok "Maintainability index → $out/radon-mi.json"

        # Halstead metrics
        $UV radon hal src/ -j > "$out/radon-hal.json" 2>/dev/null \
            && log_ok "Halstead metrics → $out/radon-hal.json"

        # Raw metrics (SLOC, comments, blanks)
        $UV radon raw src/ -s -j > "$out/radon-raw.json" 2>/dev/null \
            && log_ok "Raw metrics → $out/radon-raw.json"

        # Summary: worst complexity scores
        echo "=== Top 20 Most Complex Functions ===" > "$out/worst-complexity.txt"
        $UV radon cc src/ -n C -s 2>/dev/null >> "$out/worst-complexity.txt" \
            && log_ok "Worst complexity → $out/worst-complexity.txt"

        # CSV of all complexity scores for tracking over time
        $UV python -c "
import json, csv, sys
with open('$out/radon-cc.json') as f:
    data = json.load(f)
writer = csv.writer(sys.stdout)
writer.writerow(['file', 'type', 'name', 'line', 'complexity', 'grade'])
for filepath, blocks in data.items():
    for b in blocks:
        writer.writerow([filepath, b['type'], b['name'], b['lineno'], b['complexity'], b['rank']])
" > "$out/complexity-all.csv" 2>/dev/null \
            && log_ok "Complexity CSV → $out/complexity-all.csv"
    else
        log_skip "radon"
    fi

    # --- Wily ---
    if $UV wily --version &>/dev/null 2>&1; then
        log_header "Wily — complexity over git history"
        $UV wily build src/ 2>/dev/null \
            && $UV wily report src/screenshot_processor/core/image_processor.py > "$out/wily-image-processor.txt" 2>/dev/null \
            && $UV wily report src/screenshot_processor/core/ocr.py > "$out/wily-ocr.txt" 2>/dev/null \
            && $UV wily report src/screenshot_processor/core/bar_extraction.py > "$out/wily-bar-extraction.txt" 2>/dev/null \
            && log_ok "Wily reports → $out/wily-*.txt" \
            || log_warn "Wily completed with warnings (may need git history)"
    else
        log_skip "wily"
    fi
}

# =============================================================================
# Frontend Profiling
# =============================================================================
run_frontend() {
    log_header "Frontend Profiling"
    local out="$REPORT_DIR/frontend"
    ensure_dir "$out"

    local fe_dir="$PROJECT_ROOT/frontend"

    # --- Bundle analysis (ANALYZE=1 build) ---
    if [ -f "$fe_dir/package.json" ]; then
        log_header "Vite Bundle Analysis"
        if grep -q "visualizer" "$fe_dir/vite.config.ts" 2>/dev/null; then
            (cd "$fe_dir" && ANALYZE=1 npx vite build 2>/dev/null) \
                && mv "$fe_dir/dist/stats.html" "$out/bundle-treemap.html" 2>/dev/null \
                && log_ok "Bundle treemap → $out/bundle-treemap.html" \
                || log_warn "Bundle analysis: treemap not generated (run inside Docker with bun)"
        else
            log_warn "Bundle visualizer not configured in vite.config.ts"
        fi
    fi

    # --- Knip (dead code) ---
    if [ -f "$fe_dir/knip.json" ]; then
        log_header "Knip — unused files, deps, exports"
        (cd "$fe_dir" && npx knip 2>/dev/null) > "$out/knip-report.txt" 2>&1 \
            && log_ok "Knip report → $out/knip-report.txt" \
            || log_warn "Knip found issues (check report)"
    else
        log_skip "knip (no knip.json found)"
    fi

    # --- TypeScript type-check timing ---
    log_header "TypeScript type-check timing"
    if has npx; then
        local ts_start ts_end ts_dur
        ts_start=$(date +%s%N)
        (cd "$fe_dir" && npx tsc --noEmit 2>/dev/null) \
            && ts_end=$(date +%s%N) \
            && ts_dur=$(( (ts_end - ts_start) / 1000000 )) \
            && echo "TypeScript type-check: ${ts_dur}ms" > "$out/tsc-timing.txt" \
            && log_ok "TSC timing → $out/tsc-timing.txt (${ts_dur}ms)" \
            || log_warn "TypeScript type-check had errors"
    fi
}

# =============================================================================
# Rust Profiling
# =============================================================================
run_rust() {
    log_header "Rust Profiling"
    local out="$REPORT_DIR/rust"
    ensure_dir "$out"

    local tauri_dir="$PROJECT_ROOT/frontend/src-tauri"
    if [ ! -f "$tauri_dir/Cargo.toml" ]; then
        log_warn "No Cargo.toml found at $tauri_dir"
        return 0
    fi

    # --- cargo build --timings ---
    log_header "Cargo Build Timings"
    (cd "$tauri_dir" && cargo build --timings 2>/dev/null) \
        && cp "$tauri_dir/target/cargo-timings/cargo-timing.html" "$out/cargo-timings.html" 2>/dev/null \
        && log_ok "Cargo timings → $out/cargo-timings.html" \
        || log_warn "Cargo build timings had issues (may need system libs for Tauri)"

    # --- cargo-bloat ---
    if has cargo-bloat; then
        log_header "Cargo Bloat — binary size breakdown"
        (cd "$tauri_dir" && cargo bloat --release -n 30 2>/dev/null) > "$out/cargo-bloat.txt" \
            && log_ok "Cargo bloat → $out/cargo-bloat.txt" \
            || log_warn "Cargo bloat had issues"
    else
        log_skip "cargo-bloat"
    fi

    # --- Criterion benchmarks (requires Tauri system libs: webkit2gtk-4.1, libsoup-3.0) ---
    if [ -d "$tauri_dir/benches" ]; then
        log_header "Criterion Benchmarks"
        if pkg-config --exists "javascriptcoregtk-4.1" 2>/dev/null; then
            (cd "$tauri_dir" && PKG_CONFIG_PATH=/usr/lib64/pkgconfig cargo bench 2>/dev/null) > "$out/criterion-output.txt" \
                && log_ok "Criterion benchmarks → $out/criterion-output.txt" \
                || log_warn "Criterion benchmarks had issues"
        else
            log_warn "Criterion benchmarks skipped — requires webkit2gtk-4.1 + libsoup-3.0 (Fedora/Ubuntu only, not RHEL 9)"
        fi
    fi
}

# =============================================================================
# Database Profiling
# =============================================================================
run_db() {
    log_header "Database Profiling"
    "$SCRIPT_DIR/profile-db.sh" "$REPORT_DIR/db" \
        || log_warn "Database profiling had issues"
}

# =============================================================================
# pytest-benchmark (runs in Docker — needs project imports)
# =============================================================================
run_benchmark() {
    log_header "pytest-benchmark"
    local out="$REPORT_DIR/benchmark"
    ensure_dir "$out"

    if ! docker_backend_up; then
        log_fail "Docker backend not running"
        return 1
    fi

    # Ensure pytest-benchmark is installed in Docker
    $DOCKER_EXEC pip install -q pytest-benchmark 2>/dev/null

    # Copy test files into the container (tests/ is not mounted)
    docker compose --env-file docker/.env -f docker/docker-compose.dev.yml cp \
        tests/benchmark/. backend:/app/tests/benchmark/ 2>/dev/null

    # Run benchmarks
    $DOCKER_EXEC python -m pytest tests/benchmark/ --benchmark-only \
        --benchmark-json="/tmp/pytest-benchmark.json" \
        -q 2>/dev/null \
        && docker compose --env-file docker/.env -f docker/docker-compose.dev.yml cp \
            backend:/tmp/pytest-benchmark.json "$out/pytest-benchmark.json" 2>/dev/null \
        && log_ok "Benchmark results → $out/pytest-benchmark.json" \
        || log_warn "Some benchmarks failed"

    # Generate compact CSV summary from JSON (name, min_ms, mean_ms, max_ms, ops_per_sec)
    if [ -f "$out/pytest-benchmark.json" ]; then
        $UV python -c "
import json, csv, sys
with open('$out/pytest-benchmark.json') as f:
    data = json.load(f)
writer = csv.writer(sys.stdout)
writer.writerow(['test', 'min_ms', 'mean_ms', 'max_ms', 'stddev_ms', 'ops_per_sec', 'rounds'])
for b in sorted(data['benchmarks'], key=lambda x: x['stats']['mean']):
    s = b['stats']
    writer.writerow([
        b['name'].split('::')[-1],
        f'{s[\"min\"]*1000:.3f}', f'{s[\"mean\"]*1000:.3f}',
        f'{s[\"max\"]*1000:.3f}', f'{s[\"stddev\"]*1000:.3f}',
        f'{s[\"ops\"]:.1f}', s['rounds'],
    ])
" > "$out/benchmark-summary.csv" 2>/dev/null \
            && log_ok "Benchmark CSV → $out/benchmark-summary.csv"
    fi
}

# =============================================================================
# k6 Endpoint Profiling
# =============================================================================
run_k6() {
    log_header "k6 API Endpoint Profiling"
    local out="$REPORT_DIR/api"
    ensure_dir "$out"

    if has k6; then
        # Source SITE_PASSWORD from docker/.env if available
        local site_pw=""
        if [ -f "$PROJECT_ROOT/docker/.env" ]; then
            site_pw=$(grep '^SITE_PASSWORD=' "$PROJECT_ROOT/docker/.env" 2>/dev/null | cut -d= -f2- || true)
        fi
        local k6_exit=0
        k6 run --out json="$out/k6-results.json" \
            --env "SITE_PASSWORD=${site_pw}" \
            tests/load/profile-endpoints.js 2>/dev/null || k6_exit=$?
        if [ -f "$out/k6-results.json" ]; then
            log_ok "k6 results → $out/k6-results.json"
            [ "$k6_exit" -ne 0 ] && log_warn "Some k6 thresholds were crossed (check report)"
        else
            log_warn "k6 profiling failed (is the API running?)"
        fi
    else
        log_skip "k6"
    fi
}

# =============================================================================
# Summary
# =============================================================================
generate_summary() {
    log_header "Generating Summary"
    local summary="$REPORT_DIR/summary.txt"

    cat > "$summary" <<SUMMARY
=============================================================================
  Profiling Report — $TIMESTAMP
=============================================================================

Generated: $(date)
Project:   iOS Screen Time Screenshot Processing
Category:  $CATEGORY

SUMMARY

    # List all generated files
    echo "" >> "$summary"
    echo "Generated Files:" >> "$summary"
    echo "----------------" >> "$summary"
    find "$REPORT_DIR" -type f | sort | while read -r f; do
        local size
        size=$(du -h "$f" | cut -f1)
        echo "  $size  ${f#$REPORT_DIR/}" >> "$summary"
    done

    # Append complexity summary if available
    if [ -f "$REPORT_DIR/complexity/worst-complexity.txt" ]; then
        echo "" >> "$summary"
        echo "=== Complexity Hotspots ===" >> "$summary"
        head -30 "$REPORT_DIR/complexity/worst-complexity.txt" >> "$summary"
    fi

    # Append import time top offenders
    if [ -f "$REPORT_DIR/python/import-time.txt" ]; then
        echo "" >> "$summary"
        echo "=== Slowest Imports (top 10) ===" >> "$summary"
        sort -t'|' -k2 -rn "$REPORT_DIR/python/import-time.txt" 2>/dev/null \
            | head -10 >> "$summary" || true
    fi

    echo "" >> "$summary"
    echo "==============================================================================" >> "$summary"
    log_ok "Summary → $summary"
}

# =============================================================================
# Feature-level hyperfine benchmarks
# =============================================================================
run_features() {
    log_header "Feature Benchmarks (hyperfine)"
    local out="$REPORT_DIR/features"
    mkdir -p "$out"
    if command -v hyperfine &>/dev/null; then
        scripts/benchmark-features.sh --runs 5 "$out" \
            && log_ok "Feature benchmarks → $out/summary.md" \
            || log_warn "Feature benchmarks had issues (see $out/)"
    else
        log_warn "hyperfine not found — skipping (cargo install hyperfine)"
    fi
}

# =============================================================================
# Main
# =============================================================================
main() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║              Performance Profiling Suite                     ║"
    echo "║                                                              ║"
    echo "║  Category: $CATEGORY"
    echo "║  Output:   $REPORT_DIR/"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    ensure_dir "$REPORT_DIR"

    case "$CATEGORY" in
        all)
            run_python
            run_complexity
            run_frontend
            run_rust
            run_db
            run_benchmark
            run_k6
            run_features
            ;;
        python)     run_python ;;
        complexity) run_complexity ;;
        frontend)   run_frontend ;;
        rust)       run_rust ;;
        db)         run_db ;;
        benchmark)  run_benchmark ;;
        k6)         run_k6 ;;
        import)     run_import_time "$REPORT_DIR/python" ;;
        features)   run_features ;;
        *)
            echo "Unknown category: $CATEGORY"
            echo "Valid: all, python, complexity, frontend, rust, db, benchmark, k6, import, features"
            exit 1
            ;;
    esac

    # Compress large outputs
    compress_reports

    generate_summary

    echo ""
    echo -e "${GREEN}Done!${NC} Reports saved to: ${BLUE}$REPORT_DIR/${NC}"
    echo ""
    local total_files
    total_files=$(find "$REPORT_DIR" -type f | wc -l)
    echo "  $total_files files generated"
    du -sh "$REPORT_DIR" | awk '{print "  Total size: " $1}'
}

# =============================================================================
# Compress large report files
# =============================================================================
compress_reports() {
    log_header "Compressing Reports"
    local compressed=0

    # Gzip JSON files > 1MB (k6 output can be 100MB+)
    while IFS= read -r f; do
        gzip -9 "$f" && compressed=$((compressed + 1))
        log_ok "Gzipped $(basename "$f") → $(du -h "${f}.gz" | cut -f1)"
    done < <(find "$REPORT_DIR" -name "*.json" -size +1M 2>/dev/null)

    # Gzip HTML reports > 1MB
    while IFS= read -r f; do
        gzip -9 "$f" && compressed=$((compressed + 1))
        log_ok "Gzipped $(basename "$f") → $(du -h "${f}.gz" | cut -f1)"
    done < <(find "$REPORT_DIR" -name "*.html" -size +1M 2>/dev/null)

    [ "$compressed" -eq 0 ] && log_ok "No files needed compression"
}

main "$@"
