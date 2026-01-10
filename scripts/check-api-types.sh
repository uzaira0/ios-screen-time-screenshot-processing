#!/usr/bin/env bash
# Check if frontend TypeScript types are in sync with backend Pydantic schemas.
#
# Generates a fresh OpenAPI spec from the backend and compares it to the
# committed frontend/openapi.json. If they differ, the types are stale.
#
# Usage:
#   scripts/check-api-types.sh          # exits 1 if stale
#   scripts/check-api-types.sh --fix    # regenerates if stale
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

FIX_MODE=false
if [[ "${1:-}" == "--fix" ]]; then
    FIX_MODE=true
fi

# Check if any schema files changed in this commit
SCHEMA_FILES=(
    "src/screenshot_processor/web/database/schemas.py"
    "src/screenshot_processor/web/api/routes/"
    "src/screenshot_processor/web/api/main.py"
)

# If running as pre-commit, only check staged files
if git diff --cached --name-only 2>/dev/null | grep -qE "schemas\.py|routes/|main\.py"; then
    SCHEMAS_CHANGED=true
else
    SCHEMAS_CHANGED=false
fi

if [[ "$SCHEMAS_CHANGED" == "false" && "$FIX_MODE" == "false" ]]; then
    exit 0  # No schema changes, nothing to check
fi

echo "API schema files changed — checking type sync..."

# Generate fresh spec from the running backend (Docker or direct)
FRESH_SPEC=$(mktemp)
trap 'rm -f "$FRESH_SPEC"' EXIT

# Try Docker first (production), then direct Python
if docker compose --env-file docker/.env -f docker/docker-compose.dev.yml ps -q backend >/dev/null 2>&1; then
    BACKEND_UP=$(docker compose --env-file docker/.env -f docker/docker-compose.dev.yml ps -q backend 2>/dev/null)
    if [[ -n "$BACKEND_UP" ]]; then
        docker compose --env-file docker/.env -f docker/docker-compose.dev.yml exec -T backend python -c "
import sys, json, logging
logging.disable(logging.CRITICAL)
from screenshot_processor.web.api.main import app
app.openapi_schema = None
json.dump(app.openapi(), sys.stdout, indent=2)
" 2>/dev/null | sed '/^\x1b\[/d' > "$FRESH_SPEC"
    fi
fi

# Check if we got a valid spec
if [[ ! -s "$FRESH_SPEC" ]] || ! python3 -c "import json; json.load(open('$FRESH_SPEC'))" 2>/dev/null; then
    echo "WARNING: Could not generate fresh OpenAPI spec (backend not running?)"
    echo "Skipping type drift check. Run 'scripts/check-api-types.sh --fix' with backend running."
    exit 0
fi

# Compare schema components (ignore info/paths metadata that changes frequently)
FRESH_SCHEMAS=$(python3 -c "
import json, sys
spec = json.load(open('$FRESH_SPEC'))
schemas = spec.get('components', {}).get('schemas', {})
json.dump(sorted(schemas.keys()), sys.stdout)
" 2>/dev/null)

CURRENT_SCHEMAS=$(python3 -c "
import json, sys
spec = json.load(open('frontend/openapi.json'))
schemas = spec.get('components', {}).get('schemas', {})
json.dump(sorted(schemas.keys()), sys.stdout)
" 2>/dev/null)

if [[ "$FRESH_SCHEMAS" != "$CURRENT_SCHEMAS" ]]; then
    echo "ERROR: OpenAPI schema keys have changed!"
    echo "  Current: $(echo "$CURRENT_SCHEMAS" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))') schemas"
    echo "  Fresh:   $(echo "$FRESH_SCHEMAS" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))') schemas"

    if [[ "$FIX_MODE" == "true" ]]; then
        echo "Regenerating types..."
        cp "$FRESH_SPEC" frontend/openapi.json
        cd frontend && npx openapi-typescript ./openapi.json -o src/types/api-schema.ts
        echo "Types regenerated. Please stage the updated files."
    else
        echo ""
        echo "Run: bun run generate:api-types   (or: scripts/check-api-types.sh --fix)"
        exit 1
    fi
else
    # Schema keys match, but check for field-level changes in key schemas
    DRIFT=$(python3 -c "
import json
fresh = json.load(open('$FRESH_SPEC')).get('components', {}).get('schemas', {})
current = json.load(open('frontend/openapi.json')).get('components', {}).get('schemas', {})
diffs = []
for name in fresh:
    if name not in current:
        diffs.append(f'  + {name} (new schema)')
    elif json.dumps(fresh[name], sort_keys=True) != json.dumps(current[name], sort_keys=True):
        # Find which properties changed
        fp = set(fresh[name].get('properties', {}).keys())
        cp = set(current[name].get('properties', {}).keys())
        added = fp - cp
        removed = cp - fp
        if added or removed:
            diffs.append(f'  ~ {name}: +{list(added)} -{list(removed)}')
        else:
            diffs.append(f'  ~ {name}: property types/defaults changed')
for name in current:
    if name not in fresh:
        diffs.append(f'  - {name} (removed schema)')
if diffs:
    print('\n'.join(diffs))
" 2>/dev/null)

    if [[ -n "$DRIFT" ]]; then
        echo "ERROR: API type drift detected!"
        echo "$DRIFT"

        if [[ "$FIX_MODE" == "true" ]]; then
            echo "Regenerating types..."
            cp "$FRESH_SPEC" frontend/openapi.json
            cd frontend && npx openapi-typescript ./openapi.json -o src/types/api-schema.ts
            echo "Types regenerated. Please stage the updated files."
        else
            echo ""
            echo "Run: bun run generate:api-types   (or: scripts/check-api-types.sh --fix)"
            exit 1
        fi
    else
        echo "API types are in sync."
    fi
fi
