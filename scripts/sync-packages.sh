#!/usr/bin/env bash
# =============================================================================
# sync-packages.sh - Sync shared monorepo packages into docker/backend/packages/
# =============================================================================
# Run this when upstream monorepo packages change to update the vendored copies
# used by Dockerfile.dev (standalone dev builds).
#
# Usage:
#   ./scripts/sync-packages.sh                          # default monorepo path
#   ./scripts/sync-packages.sh /path/to/monorepo        # custom path
#   MONOREPO_ROOT=/path/to/monorepo ./scripts/sync-packages.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET_DIR="$APP_ROOT/docker/backend/packages"

# Monorepo root: argument > env var > default
MONOREPO_ROOT="${1:-${MONOREPO_ROOT:-/opt/actions-runner/_work/monorepo/monorepo}}"

PACKAGES=(
    global-pass-honor-username-auth
    fastapi-errors
    fastapi-logging
    fastapi-ratelimit
    db-toolkit
    fastapi-pagination
    fastapi-files
    fastapi-tasks
)

if [ ! -d "$MONOREPO_ROOT/packages" ]; then
    echo "ERROR: Monorepo packages directory not found: $MONOREPO_ROOT/packages"
    echo "Usage: $0 [monorepo-root]"
    exit 1
fi

echo "Syncing shared packages from: $MONOREPO_ROOT/packages/"
echo "Target: $TARGET_DIR/"
echo ""

for pkg in "${PACKAGES[@]}"; do
    src="$MONOREPO_ROOT/packages/$pkg"
    dest="$TARGET_DIR/$pkg"

    if [ ! -d "$src" ]; then
        echo "WARNING: Package not found: $src (skipping)"
        continue
    fi

    # Remove old copy and replace
    rm -rf "$dest"
    cp -r "$src" "$dest"

    # Remove __pycache__ and .pyc files
    find "$dest" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find "$dest" -name "*.pyc" -delete 2>/dev/null || true

    # Strip [tool.uv.sources] workspace references (don't work outside monorepo)
    if [ -f "$dest/pyproject.toml" ]; then
        sed -i '/^\[tool\.uv\.sources\]/,/^$/d' "$dest/pyproject.toml"
    fi

    echo "  Synced: $pkg"
done

echo ""
echo "Done. Synced ${#PACKAGES[@]} packages."
echo "Run 'docker compose -f docker/docker-compose.dev.yml build backend' to rebuild."
