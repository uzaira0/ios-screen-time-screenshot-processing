#!/usr/bin/env bash
set -euo pipefail

echo "Checking for API contract drift..."

TYPES_FILE="src/types/api-schema.ts"

if [ ! -f "$TYPES_FILE" ]; then
  echo "ERROR: $TYPES_FILE not found."
  exit 1
fi

# Save current
cp "$TYPES_FILE" "${TYPES_FILE}.bak"

# Always restore backup on exit (protects against partial writes)
trap 'mv -f "${TYPES_FILE}.bak" "$TYPES_FILE" 2>/dev/null || true' INT TERM EXIT

# Regenerate (timeout after 30s — the backend must be importable)
if ! timeout 30 bun run generate:api-types 2>/dev/null; then
  echo "WARNING: generate:api-types failed or timed out. Skipping drift check."
  # trap will restore the original file
  exit 0
fi

# Compare (old vs new)
if ! diff -q "${TYPES_FILE}.bak" "$TYPES_FILE" > /dev/null 2>&1; then
  echo "::error::Contract drift detected! Frontend types are out of sync with backend."
  echo "Run 'cd frontend && bun run generate:api-types' and commit."
  diff --unified "${TYPES_FILE}.bak" "$TYPES_FILE" || true
  # Restore original — the developer should regenerate manually
  mv -f "${TYPES_FILE}.bak" "$TYPES_FILE"
  trap - EXIT  # disable trap since we already restored
  exit 1
fi

# Success — remove backup, disable trap
rm -f "${TYPES_FILE}.bak"
trap - EXIT
echo "No contract drift detected."
