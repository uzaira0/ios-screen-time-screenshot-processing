#!/usr/bin/env bash
set -euo pipefail

echo "=== Docker Build Tests ==="

# Hadolint — lint Dockerfiles
if command -v hadolint &>/dev/null; then
  echo -n "  Hadolint (backend Dockerfile)... "
  hadolint docker/backend/Dockerfile && echo "PASS" || echo "FAIL"

  echo -n "  Hadolint (frontend Dockerfile)... "
  hadolint docker/frontend/Dockerfile && echo "PASS" || echo "FAIL"

  echo -n "  Hadolint (frontend dev Dockerfile)... "
  hadolint docker/frontend/Dockerfile.dev && echo "PASS" || echo "FAIL"
else
  echo "  SKIP: hadolint not installed"
fi

# Verify docker-compose configs parse
echo -n "  docker-compose.yml validates... "
docker compose -f docker/docker-compose.yml config > /dev/null 2>&1 && echo "PASS" || echo "FAIL"

echo -n "  docker-compose.dev.yml validates... "
docker compose --env-file docker/.env -f docker/docker-compose.dev.yml config > /dev/null 2>&1 && echo "PASS" || echo "FAIL"

echo -n "  docker-compose.wasm.yml validates... "
docker compose -f docker/docker-compose.wasm.yml config > /dev/null 2>&1 && echo "PASS" || echo "FAIL"

echo "Done."
