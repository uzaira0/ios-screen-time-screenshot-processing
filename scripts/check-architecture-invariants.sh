#!/usr/bin/env bash
# Architecture invariants the semgrep AST can't cleanly express.
#
# Runs rg over the working tree (not git diff) so it catches violations
# in files not touched in the current commit.
#
# Usage: scripts/check-architecture-invariants.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

red()    { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }

fail=0
note() { red "✗ $*"; fail=1; }

RG=(rg --no-heading -n --color never)

# ══════════════════════════════════════════════════════════════════════
# Rule 1: No pixel-analysis canvas operations in React components
# ══════════════════════════════════════════════════════════════════════
# getImageData/putImageData in components/ means pixel-level analysis
# is happening outside the service layer, bypassing the dual-mode
# abstraction (WASM vs Tauri) and making results inconsistent.
# drawImage for display/rendering is fine and is NOT flagged here.
# ══════════════════════════════════════════════════════════════════════
check_no_pixel_analysis_in_components() {
    local hits
    hits=$("${RG[@]}" \
        --glob '!node_modules/**' \
        --glob '!**/*.test.*' \
        --glob '!**/*.spec.*' \
        -e 'getImageData\(' \
        -e 'putImageData\(' \
        -- frontend/src/components/ frontend/src/hooks/ 2>/dev/null || true)
    if [[ -n "$hits" ]]; then
        note "Pixel-analysis canvas ops (getImageData/putImageData) in components/hooks — use IProcessingService:"
        echo "$hits" >&2
        echo "  ↪ Pixel analysis belongs in wasm/processing/ (accessed via DI container), not UI code." >&2
    fi
}

# ══════════════════════════════════════════════════════════════════════
# Rule 2: Shared constants must not drift
# ══════════════════════════════════════════════════════════════════════
# If any shared/*.json file is newer than the generated outputs, the
# generated constants are stale. This is advisory (the pre-commit hook
# is the hard block); here we emit a warning so pre-push surface it too.
# ══════════════════════════════════════════════════════════════════════
check_shared_constants_drift() {
    local ref_file="src/screenshot_processor/core/generated_constants.py"
    if [[ ! -f "$ref_file" ]]; then
        note "generated_constants.py not found — run: python3 scripts/generate-shared-constants.py"
        return
    fi
    local newest_json
    newest_json=$(find shared/ -name '*.json' -newer "$ref_file" 2>/dev/null | head -1)
    if [[ -n "$newest_json" ]]; then
        note "shared/*.json is newer than generated_constants — run: python3 scripts/generate-shared-constants.py"
    fi
}

# ══════════════════════════════════════════════════════════════════════
# Rule 3: Dexie schema version must never regress
# ══════════════════════════════════════════════════════════════════════
# Dropping a this.version(N) block during conflict resolution causes
# VersionError in every browser that opened the DB at that version.
# Compare highest version in working tree vs origin/main.
# ══════════════════════════════════════════════════════════════════════
check_dexie_version_no_regression() {
    local schema_file="frontend/src/core/implementations/wasm/storage/database/ScreenshotDB.ts"
    [[ -f "$schema_file" ]] || return 0

    local current_max
    current_max=$({ rg --no-heading -o 'this\.version\(([0-9]+)\)' -r '$1' "$schema_file" 2>/dev/null || true; } \
        | sort -n | tail -1)
    [[ -n "$current_max" ]] || return 0

    local main_max
    main_max=$({ git show origin/main:"$schema_file" 2>/dev/null \
        | rg --no-heading -o 'this\.version\(([0-9]+)\)' -r '$1' 2>/dev/null || true; } \
        | sort -n | tail -1)
    [[ -n "$main_max" ]] || return 0

    if (( current_max < main_max )); then
        note "Dexie schema version REGRESSION:"
        echo "  origin/main: v${main_max}  working tree: v${current_max}" >&2
        echo "  ↪ A conflict resolution likely dropped this.version(${main_max}) from ${schema_file}." >&2
        echo "  ↪ Every browser that opened the DB at v${main_max} will throw VersionError on load." >&2
        echo "  ↪ Restore the missing version block — never delete a Dexie version once shipped." >&2
    fi
}

# ══════════════════════════════════════════════════════════════════════
# Rule 4: nosemgrep waiver debt (advisory)
# ══════════════════════════════════════════════════════════════════════
count_nosemgrep_waivers() {
    local total
    total=$({ rg --no-heading -c 'nosemgrep:' src/ frontend/src/ 2>/dev/null || true; } \
        | awk -F: '{sum+=$2} END {print sum+0}')
    if (( total > 0 )); then
        yellow "ℹ nosemgrep waivers: ${total} — track toward zero."
    fi
}

# ── Run all checks ────────────────────────────────────────────────────────
check_no_pixel_analysis_in_components
check_shared_constants_drift
check_dexie_version_no_regression
count_nosemgrep_waivers

if (( fail )); then
    red "Architecture-invariant check failed — see above."
    exit 1
fi

green "✓ architecture invariants: clean"
