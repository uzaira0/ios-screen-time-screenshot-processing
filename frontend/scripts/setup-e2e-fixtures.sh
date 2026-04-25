#!/usr/bin/env bash
# Populate /tmp/test-screenshots/ with the fixture PNGs that the WASM E2E
# suite (tests/wasm-smoke.spec.ts) uploads via the webkitdirectory input.
#
# Idempotent: safe to re-run. Exits 0 on success, nonzero on missing source.
set -euo pipefail

# Resolve repo root from this script's location: scripts/ lives at frontend/scripts/.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SRC_DIR="$REPO_ROOT/tests/fixtures/images"
DEST_DIR="/tmp/test-screenshots"

if [[ ! -d "$SRC_DIR" ]]; then
  echo "error: fixture source $SRC_DIR not found" >&2
  exit 1
fi

mkdir -p "$DEST_DIR"

# Copy all PNGs; rsync-style overwrite is fine since fixtures are small.
shopt -s nullglob
count=0
for src in "$SRC_DIR"/*.png; do
  cp -f "$src" "$DEST_DIR/"
  count=$((count + 1))
done

if [[ $count -eq 0 ]]; then
  echo "error: no *.png found under $SRC_DIR" >&2
  exit 1
fi

echo "populated $DEST_DIR ($count files)"
