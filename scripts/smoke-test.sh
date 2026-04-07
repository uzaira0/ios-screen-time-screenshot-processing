#!/usr/bin/env bash
set -euo pipefail

API_URL="${1:-http://localhost:8002/api/v1}"
SITE_PASSWORD="${SITE_PASSWORD:-}"

echo "Smoke testing ${API_URL}..."

# Build auth headers
AUTH_ARGS=(-H "X-Username: smoke-test")
if [ -n "$SITE_PASSWORD" ]; then
  AUTH_ARGS+=(-H "X-Site-Password: ${SITE_PASSWORD}")
fi

# Health check (strip /api/v1 suffix to reach root health endpoint)
HEALTH_URL="${API_URL%/api/v1}/health"
echo -n "  Health check (${HEALTH_URL})... "
curl -sf "${HEALTH_URL}" > /dev/null && echo "OK" || { echo "FAIL"; exit 1; }

# API responds
echo -n "  Screenshot stats... "
curl -sf "${AUTH_ARGS[@]}" "${API_URL}/screenshots/stats" > /dev/null && echo "OK" || { echo "FAIL"; exit 1; }

# Auth endpoint
echo -n "  Auth endpoint... "
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${AUTH_ARGS[@]}" "${API_URL}/auth/me")
[ "$STATUS" = "200" ] && echo "OK" || { echo "FAIL (HTTP $STATUS)"; exit 1; }

echo "All smoke tests passed."
