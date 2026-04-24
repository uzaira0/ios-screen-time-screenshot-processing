#!/usr/bin/env bash
# Tier 1 WASM build — compile crates/processing (minus OCR) to
# wasm32-unknown-unknown via wasm-pack/wasm-bindgen, output into
# frontend/src/wasm/pkg/ for the frontend to import.
#
# Consumed by:
#   - `bun run wasm:build` from frontend/ (dev convenience)
#   - .github/workflows/deploy-gh-pages.yml (production build on Pages)
#
# OCR is not included in this artifact; the JS side still orchestrates
# Tesseract.js for raw OCR and passes word lists back into the Rust side
# for normalization. The full leptess-in-WASM path is Tier 2
# (scripts/build-wasm-emscripten.sh).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

log() { printf '\033[34m[wasm-bindgen]\033[0m %s\n' "$*"; }

# ── Toolchain prerequisites ───────────────────────────────────────────────────
# wasm-pack requires a rustup-managed toolchain so it can locate the
# wasm32-unknown-unknown target's sysroot. If a Homebrew rustc is on PATH ahead
# of rustup's, wasm-pack will error with "target not found in sysroot". Force
# rustup's cargo/rustc to the front of PATH when available.
if [[ -d "$HOME/.cargo/bin" && -x "$HOME/.cargo/bin/rustc" ]]; then
  export PATH="$HOME/.cargo/bin:$PATH"
fi

if ! command -v cargo >/dev/null; then
  echo "error: cargo not found. Install Rust: https://rustup.rs" >&2
  exit 1
fi

if ! rustup target list --installed 2>/dev/null | grep -q '^wasm32-unknown-unknown$'; then
  log "installing wasm32-unknown-unknown target"
  rustup target add wasm32-unknown-unknown
fi

if ! command -v wasm-pack >/dev/null; then
  log "installing wasm-pack (cargo install)"
  cargo install wasm-pack --locked
fi

# ── Build ─────────────────────────────────────────────────────────────────────
OUT_DIR="$REPO_ROOT/frontend/src/wasm/pkg"
rm -rf "$OUT_DIR"

log "wasm-pack build (release, --features wasm, target=web) → $OUT_DIR"
wasm-pack build \
  "$REPO_ROOT/crates/processing" \
  --target web \
  --out-dir "$OUT_DIR" \
  --out-name ios_screen_time_image_pipeline \
  --release \
  --no-default-features \
  --features wasm

# ── Post-process ──────────────────────────────────────────────────────────────
if command -v wasm-opt >/dev/null; then
  WASM_FILE="$OUT_DIR/ios_screen_time_image_pipeline_bg.wasm"
  if [[ -f "$WASM_FILE" ]]; then
    SIZE_BEFORE=$(wc -c <"$WASM_FILE" | tr -d ' ')
    log "wasm-opt -Oz on $WASM_FILE (before: $SIZE_BEFORE bytes)"
    wasm-opt -Oz --enable-bulk-memory --enable-nontrapping-float-to-int \
      "$WASM_FILE" -o "$WASM_FILE.opt"
    mv "$WASM_FILE.opt" "$WASM_FILE"
    SIZE_AFTER=$(wc -c <"$WASM_FILE" | tr -d ' ')
    log "wasm-opt done (after: $SIZE_AFTER bytes)"
  fi
else
  log "wasm-opt not installed; skipping size pass (optional, saves ~20%)"
fi

# Strip wasm-pack's generated package.json / README / LICENSE — they pollute the
# frontend dir and aren't consumed by our bundler.
rm -f "$OUT_DIR/.gitignore" "$OUT_DIR/package.json" "$OUT_DIR/README.md" \
      "$OUT_DIR/LICENSE_APACHE" "$OUT_DIR/LICENSE_MIT"

log "artifacts ready in $OUT_DIR:"
ls -la "$OUT_DIR" | tail -n +2
