#!/usr/bin/env bash
# Build the full Rust+leptess pipeline as wasm32-unknown-emscripten.
#
# Outputs:
#   frontend/public/pipeline-em/IosScreenTimePipeline.js
#   frontend/public/pipeline-em/IosScreenTimePipeline.wasm
#   frontend/public/pipeline-em/eng.traineddata
#
# Consumed by:
#   frontend/src/core/implementations/wasm/processing/emscripten/pipelineLoader.ts
#   frontend/src/core/implementations/wasm/processing/workers/imageProcessor.worker.emscripten.ts
#
# Pipeline:
#   1. Bootstrap emsdk into $EMSDK_DIR (skipped if already present + activated).
#   2. Build leptonica static lib for wasm32-unknown-emscripten via emcmake.
#   3. Build tesseract static lib for wasm32-unknown-emscripten via emcmake,
#      pointing at the leptonica install we just produced.
#   4. Emit lept.pc + tesseract.pc into a private PKG_CONFIG_PATH so
#      leptonica-sys / tesseract-sys's pkg-config probe resolves to the
#      WASM static libs (the Linux/macOS branch in their build.rs uses
#      pkg_config::Config::new().probe()).
#   5. cargo build --target wasm32-unknown-emscripten --features wasm-emscripten
#      --no-default-features --release --bin pipeline_em.
#   6. Copy & rename the resulting pipeline_em.{js,wasm} to
#      IosScreenTimePipeline.{js,wasm} in frontend/public/pipeline-em/.
#   7. Stage eng.traineddata (uncompressed) alongside.
#
# Idempotent: each step skips its work if the output already exists.
# Force a clean build with `WASM_FORCE_REBUILD=1 ./scripts/build-wasm-emscripten.sh`.

set -euo pipefail

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_ROOT="${WASM_BUILD_ROOT:-$REPO_ROOT/build/wasm-emscripten}"
EMSDK_DIR="${EMSDK_DIR:-$BUILD_ROOT/emsdk}"
EMSDK_VERSION="${EMSDK_VERSION:-3.1.74}"
LEPTONICA_TAG="${LEPTONICA_TAG:-1.84.1}"
TESSERACT_TAG="${TESSERACT_TAG:-5.4.1}"

LEPTONICA_SRC="$BUILD_ROOT/leptonica-src"
LEPTONICA_BUILD="$BUILD_ROOT/leptonica-build"
LEPTONICA_INSTALL="$BUILD_ROOT/leptonica-install"
TESSERACT_SRC="$BUILD_ROOT/tesseract-src"
TESSERACT_BUILD="$BUILD_ROOT/tesseract-build"
TESSERACT_INSTALL="$BUILD_ROOT/tesseract-install"
PKG_CONFIG_DIR="$BUILD_ROOT/pkgconfig"

PIPELINE_OUT_DIR="$REPO_ROOT/frontend/public/pipeline-em"

JOBS="$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)"

log() { printf '\033[34m[wasm-em]\033[0m %s\n' "$*"; }
need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: '$1' is required" >&2
    exit 1
  }
}

# ── Force-clean ───────────────────────────────────────────────────────────────
if [[ "${WASM_FORCE_REBUILD:-0}" == "1" ]]; then
  log "WASM_FORCE_REBUILD=1 → wiping $BUILD_ROOT and $PIPELINE_OUT_DIR"
  rm -rf "$BUILD_ROOT" "$PIPELINE_OUT_DIR"
fi

mkdir -p "$BUILD_ROOT" "$PKG_CONFIG_DIR" "$PIPELINE_OUT_DIR"

# ── Tooling prereqs ───────────────────────────────────────────────────────────
need git
need cmake
need pkg-config
need python3
need rustup

# rustup-managed toolchain must be on PATH (Homebrew rustc has no
# wasm32-unknown-emscripten std).
if [[ -x "$HOME/.cargo/bin/rustc" ]]; then
  export PATH="$HOME/.cargo/bin:$PATH"
fi

if ! rustup target list --installed | grep -q '^wasm32-unknown-emscripten$'; then
  log "rustup target add wasm32-unknown-emscripten"
  rustup target add wasm32-unknown-emscripten
fi

# ── Step 1: emscripten toolchain ──────────────────────────────────────────────
# Prefer a system / Homebrew emscripten since aarch64 macOS does not have
# precompiled emsdk releases (build-from-source via emsdk takes a long time).
# Fall back to emsdk if emcc is not on PATH.
if command -v emcc >/dev/null 2>&1 && command -v emcmake >/dev/null 2>&1; then
  log "using system emscripten: $(command -v emcc)"
elif command -v brew >/dev/null 2>&1 && brew --prefix emscripten >/dev/null 2>&1 && \
     [[ -x "$(brew --prefix emscripten)/bin/emcc" ]]; then
  log "using Homebrew emscripten: $(brew --prefix emscripten)/bin/emcc"
  export PATH="$(brew --prefix emscripten)/bin:$PATH"
else
  log "no system emscripten — bootstrapping emsdk into $EMSDK_DIR"
  if [[ ! -x "$EMSDK_DIR/emsdk" ]]; then
    git clone --depth=1 https://github.com/emscripten-core/emsdk.git "$EMSDK_DIR"
  fi
  if [[ ! -f "$EMSDK_DIR/upstream/emscripten/emcc" ]] || \
     [[ "$(cat "$EMSDK_DIR/.installed-version" 2>/dev/null)" != "$EMSDK_VERSION" ]]; then
    # `--build=Release` builds from source — needed on platforms without
    # precompiled SDKs (e.g. aarch64-apple-darwin).
    (cd "$EMSDK_DIR" && \
       ./emsdk install --build=Release "$EMSDK_VERSION" && \
       ./emsdk activate --build=Release "$EMSDK_VERSION")
    echo "$EMSDK_VERSION" > "$EMSDK_DIR/.installed-version"
  fi
  # shellcheck disable=SC1091
  source "$EMSDK_DIR/emsdk_env.sh" >/dev/null 2>&1
fi

need emcc
need emconfigure
need emcmake
need emmake

log "emcc: $(emcc --version | head -1)"

# ── Step 2: leptonica ─────────────────────────────────────────────────────────
if [[ ! -d "$LEPTONICA_SRC/.git" ]] || \
   [[ "$(cd "$LEPTONICA_SRC" 2>/dev/null && git describe --tags --always 2>/dev/null)" != "$LEPTONICA_TAG" ]]; then
  log "cloning leptonica $LEPTONICA_TAG"
  rm -rf "$LEPTONICA_SRC"
  git clone --depth=1 --branch "$LEPTONICA_TAG" \
    https://github.com/DanBloomberg/leptonica.git "$LEPTONICA_SRC"
fi

if [[ ! -f "$LEPTONICA_INSTALL/lib/libleptonica.a" ]]; then
  log "configuring leptonica via emcmake"
  rm -rf "$LEPTONICA_BUILD"
  mkdir -p "$LEPTONICA_BUILD"
  (
    cd "$LEPTONICA_BUILD"
    emcmake cmake "$LEPTONICA_SRC" \
      -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX="$LEPTONICA_INSTALL" \
      -DBUILD_SHARED_LIBS=OFF \
      -DBUILD_PROG=OFF \
      -DSW_BUILD=OFF \
      -DENABLE_LTO=OFF \
      -DENABLE_GIF=OFF \
      -DENABLE_JPEG=OFF \
      -DENABLE_TIFF=OFF \
      -DENABLE_WEBP=OFF \
      -DENABLE_OPENJPEG=OFF \
      -DENABLE_PNG=OFF \
      -DENABLE_ZLIB=OFF
  )
  log "building leptonica ($JOBS jobs)"
  emmake cmake --build "$LEPTONICA_BUILD" --parallel "$JOBS"
  log "installing leptonica → $LEPTONICA_INSTALL"
  cmake --install "$LEPTONICA_BUILD"
fi

# ── Step 3: tesseract ─────────────────────────────────────────────────────────
if [[ ! -d "$TESSERACT_SRC/.git" ]] || \
   [[ "$(cd "$TESSERACT_SRC" 2>/dev/null && git describe --tags --always 2>/dev/null)" != "$TESSERACT_TAG" ]]; then
  log "cloning tesseract $TESSERACT_TAG"
  rm -rf "$TESSERACT_SRC"
  git clone --depth=1 --branch "$TESSERACT_TAG" \
    https://github.com/tesseract-ocr/tesseract.git "$TESSERACT_SRC"
fi

if [[ ! -f "$TESSERACT_INSTALL/lib/libtesseract.a" ]]; then
  log "configuring tesseract via emcmake"
  rm -rf "$TESSERACT_BUILD"
  mkdir -p "$TESSERACT_BUILD"
  (
    cd "$TESSERACT_BUILD"
    emcmake cmake "$TESSERACT_SRC" \
      -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX="$TESSERACT_INSTALL" \
      -DBUILD_SHARED_LIBS=OFF \
      -DBUILD_TRAINING_TOOLS=OFF \
      -DBUILD_TESTS=OFF \
      -DENABLE_LTO=OFF \
      -DDISABLED_LEGACY_ENGINE=OFF \
      -DDISABLE_ARCHIVE=ON \
      -DDISABLE_CURL=ON \
      -DGRAPHICS_DISABLED=ON \
      -DLeptonica_DIR="$LEPTONICA_INSTALL/lib/cmake/leptonica" \
      -DCMAKE_PREFIX_PATH="$LEPTONICA_INSTALL"
  )
  log "building tesseract ($JOBS jobs)"
  emmake cmake --build "$TESSERACT_BUILD" --parallel "$JOBS"
  log "installing tesseract → $TESSERACT_INSTALL"
  cmake --install "$TESSERACT_BUILD"
fi

# ── Step 4: pkg-config shims ──────────────────────────────────────────────────
# leptonica-sys / tesseract-sys's macOS+Linux build.rs branches use
# pkg_config::Config::new().probe(...). Point pkg-config at our WASM static libs.
cat > "$PKG_CONFIG_DIR/lept.pc" <<EOF
prefix=$LEPTONICA_INSTALL
libdir=\${prefix}/lib
includedir=\${prefix}/include
Name: leptonica
Description: Leptonica image processing (wasm32-unknown-emscripten)
Version: $LEPTONICA_TAG
Libs: -L\${libdir} -lleptonica
Cflags: -I\${includedir}/leptonica
EOF

cat > "$PKG_CONFIG_DIR/tesseract.pc" <<EOF
prefix=$TESSERACT_INSTALL
libdir=\${prefix}/lib
includedir=\${prefix}/include
Name: tesseract
Description: Tesseract OCR (wasm32-unknown-emscripten)
Version: $TESSERACT_TAG
Requires: lept
Libs: -L\${libdir} -ltesseract
Cflags: -I\${includedir}
EOF

export PKG_CONFIG_PATH="$PKG_CONFIG_DIR:${PKG_CONFIG_PATH:-}"
export PKG_CONFIG_ALLOW_CROSS=1
log "PKG_CONFIG_PATH = $PKG_CONFIG_PATH"

# bindgen runs the host's libclang against the leptonica/tesseract headers
# during cargo build. Those headers `#include <stdio.h>` etc., which the
# host clang can't find under wasm32-unknown-emscripten without an explicit
# --sysroot. Point bindgen at the emscripten sysroot.
EMSCRIPTEN_SYSROOT="$(em-config CACHE 2>/dev/null)/sysroot"
if [[ ! -d "$EMSCRIPTEN_SYSROOT/include" ]]; then
  echo "error: emscripten sysroot not found at $EMSCRIPTEN_SYSROOT" >&2
  exit 1
fi
log "EMSCRIPTEN_SYSROOT = $EMSCRIPTEN_SYSROOT"

# bindgen 0.64, when run inside a cargo build for target=wasm32-unknown-emscripten,
# auto-detects CARGO_CFG_TARGET_* env vars and prepends --target=wasm32-unknown-emscripten
# to its clang invocation. clang then refuses to parse most of Leptonica's
# allheaders.h (Pix struct definitions get treated as forward decls,
# function declarations are silently dropped), producing a 7000-line bindings.rs
# with zero `pub fn` entries. We override by emitting a final
# `--target=$HOST_TRIPLE` in BINDGEN_EXTRA_CLANG_ARGS — clang takes the LAST
# --target= it sees, so this beats bindgen's auto-injection.
HOST_TRIPLE="$(rustc -vV | awk '/^host:/ {print $2}')"
log "BINDGEN host override: $HOST_TRIPLE"

export BINDGEN_EXTRA_CLANG_ARGS=" \
  -I$EMSCRIPTEN_SYSROOT/include \
  -I$LEPTONICA_INSTALL/include \
  -I$TESSERACT_INSTALL/include \
  -DHAVE_LIBJPEG=0 \
  -DHAVE_LIBPNG=0 \
  -DHAVE_LIBTIFF=0 \
  -DHAVE_LIBWEBP=0 \
  -DHAVE_LIBJP2K=0 \
  -DHAVE_LIBGIF=0 \
  -DHAVE_LIBUNGIF=0 \
  -DHAVE_LIBZ=0 \
  --target=$HOST_TRIPLE"

# ── Step 5: cargo build ───────────────────────────────────────────────────────
EXPORTED_FNS='_pipeline_alloc,_pipeline_free,_pipeline_process,_pipeline_detect_grid,_pipeline_extract_ocr,_malloc,_free'
EXPORTED_RUNTIME='ccall,cwrap,FS,HEAPU8,HEAPU32'

LINK_ARGS=(
  "-sEXPORTED_FUNCTIONS=$EXPORTED_FNS"
  "-sEXPORTED_RUNTIME_METHODS=$EXPORTED_RUNTIME"
  "-sMODULARIZE=1"
  "-sEXPORT_NAME=IosScreenTimePipeline"
  "-sENVIRONMENT=web,worker"
  "-sALLOW_MEMORY_GROWTH=1"
  "-sFORCE_FILESYSTEM=1"
  "-sINITIAL_MEMORY=64MB"
  "-sMAXIMUM_MEMORY=2GB"
  "-sSTACK_SIZE=5MB"
  "-O3"
)

# Build RUSTFLAGS = "-Clink-arg=-sFOO -Clink-arg=-sBAR ..."
RUSTFLAGS_BUILD=""
for arg in "${LINK_ARGS[@]}"; do
  RUSTFLAGS_BUILD+=" -Clink-arg=$arg"
done

# Note: do NOT set -sDISABLE_EXCEPTION_CATCHING=0 / -sNO_DISABLE_EXCEPTION_CATCHING
# — emcc 5.0.6 defaults to -fwasm-exceptions, which is mutually exclusive with
# the JS-side catch-everything path. The default native-wasm exception mode
# handles the C++ exceptions tesseract throws.

log "cargo build --target wasm32-unknown-emscripten (release)"
(
  cd "$REPO_ROOT/crates/processing"
  RUSTFLAGS="$RUSTFLAGS_BUILD" \
    cargo build \
      --release \
      --target wasm32-unknown-emscripten \
      --no-default-features \
      --features wasm-emscripten \
      --bin pipeline_em
)

CARGO_OUT="$REPO_ROOT/target/wasm32-unknown-emscripten/release"
WASM_FILE="$CARGO_OUT/pipeline_em.wasm"
JS_FILE="$CARGO_OUT/pipeline_em.js"

if [[ ! -f "$WASM_FILE" ]] || [[ ! -f "$JS_FILE" ]]; then
  echo "error: cargo did not produce $WASM_FILE / $JS_FILE" >&2
  exit 1
fi

# ── Step 6: stage artifacts ───────────────────────────────────────────────────
cp "$JS_FILE"   "$PIPELINE_OUT_DIR/IosScreenTimePipeline.js"
cp "$WASM_FILE" "$PIPELINE_OUT_DIR/IosScreenTimePipeline.wasm"

# Patch the JS glue to reference the renamed wasm file.
# Emscripten emits `var wasmBinaryFile = "pipeline_em.wasm"` (or similar);
# rewrite to "IosScreenTimePipeline.wasm".
python3 - "$PIPELINE_OUT_DIR/IosScreenTimePipeline.js" <<'PY'
import sys, re, pathlib
p = pathlib.Path(sys.argv[1])
text = p.read_text()
# Replace any explicit reference to pipeline_em.wasm with the renamed file.
new = re.sub(r"pipeline_em\.wasm", "IosScreenTimePipeline.wasm", text)
if new != text:
    p.write_text(new)
    print(f"[wasm-em] rewrote pipeline_em.wasm → IosScreenTimePipeline.wasm in {p.name}")
else:
    print(f"[wasm-em] no rewrite needed in {p.name}")
PY

# ── Step 7: traineddata ───────────────────────────────────────────────────────
TESSDATA_GZ="$REPO_ROOT/frontend/public/eng.traineddata.gz"
TESSDATA_OUT="$PIPELINE_OUT_DIR/eng.traineddata"
if [[ ! -f "$TESSDATA_OUT" ]]; then
  if [[ -f "$TESSDATA_GZ" ]]; then
    log "ungzipping eng.traineddata.gz → $TESSDATA_OUT"
    gunzip -kc "$TESSDATA_GZ" > "$TESSDATA_OUT"
  else
    log "downloading eng.traineddata"
    curl -fsSL \
      "https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata" \
      -o "$TESSDATA_OUT"
  fi
fi

# ── Done ──────────────────────────────────────────────────────────────────────
log "artifacts ready in $PIPELINE_OUT_DIR:"
ls -la "$PIPELINE_OUT_DIR" | tail -n +2
