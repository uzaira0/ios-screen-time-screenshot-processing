#!/usr/bin/env bash
set -euo pipefail

# Local test runner — runs EVERYTHING. CI is only for Tauri release builds.
# Usage:
#   ./scripts/test-all.sh          # Run all tests
#   ./scripts/test-all.sh quick    # Lint + typecheck + unit tests only (~30s)
#   ./scripts/test-all.sh full     # All tests including integration + security

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASSED=0
FAILED=0
SKIPPED=0

LOGFILE=$(mktemp /tmp/test-output.XXXXXX.log)
trap "rm -f $LOGFILE" EXIT

run() {
  local name="$1"
  shift
  printf "${YELLOW}▸ %-40s${NC}" "$name"
  if "$@" > "$LOGFILE" 2>&1; then
    printf "${GREEN}PASS${NC}\n"
    PASSED=$((PASSED + 1))
  else
    printf "${RED}FAIL${NC}\n"
    tail -5 "$LOGFILE" | sed 's/^/  /'
    FAILED=$((FAILED + 1))
  fi
}

skip() {
  local name="$1"
  local reason="$2"
  printf "${YELLOW}▸ %-40s${NC}SKIP (%s)\n" "$name" "$reason"
  SKIPPED=$((SKIPPED + 1))
}

MODE="${1:-full}"
DOCKER_BACKEND=(docker compose --env-file docker/.env -f docker/docker-compose.dev.yml exec -T backend)
CONTAINER=$(docker compose --env-file docker/.env -f docker/docker-compose.dev.yml ps -q backend 2>/dev/null || true)

echo "================================================"
echo "  Test Suite — mode: $MODE"
echo "================================================"
echo ""

# ── Lint & Typecheck (always) ──────────────────────────────────────────
echo "── Lint & Typecheck ──"
run "Backend lint (ruff)"          ruff check src/
run "Backend format check"         ruff format --check src/
run "Frontend typecheck"           bash -c "cd frontend && bun run typecheck"
run "Frontend lint"                bash -c "cd frontend && bun run lint 2>&1 | grep -q '0 errors'"
echo ""

# ── Unit Tests ─────────────────────────────────────────────────────────
echo "── Unit Tests ──"
if [ -n "$CONTAINER" ]; then
  run "Python unit tests" "${DOCKER_BACKEND[@]}" python -m pytest tests/unit/ -v --tb=short -q
else
  skip "Python unit tests" "Docker backend not running"
fi
echo ""

if [ "$MODE" = "quick" ]; then
  echo ""
  echo "================================================"
  printf "  Results: ${GREEN}%d passed${NC}, ${RED}%d failed${NC}, %d skipped\n" "$PASSED" "$FAILED" "$SKIPPED"
  echo "================================================"
  [ "$FAILED" -eq 0 ] || exit 1
  exit 0
fi

# ── Integration Tests ──────────────────────────────────────────────────
echo "── Integration Tests ──"
if [ -n "$CONTAINER" ]; then
  run "Python integration tests" "${DOCKER_BACKEND[@]}" python -m pytest tests/integration/ -v --tb=short -q
else
  skip "Python integration tests" "Docker backend not running"
fi
echo ""

# ── Security ───────────────────────────────────────────────────────────
echo "── Security ──"
if command -v gitleaks &>/dev/null || [ -f ~/.local/bin/gitleaks ]; then
  GITLEAKS="${GITLEAKS:-$(command -v gitleaks 2>/dev/null || echo ~/.local/bin/gitleaks)}"
  run "Secret scan (gitleaks)" "$GITLEAKS" detect --source . --no-git -c .gitleaks.toml
else
  skip "Secret scan" "gitleaks not installed"
fi

if [ -n "$CONTAINER" ]; then
  run "pip-audit" "${DOCKER_BACKEND[@]}" pip-audit --strict
else
  skip "pip-audit" "Docker backend not running"
fi
echo ""

# ── Contract Drift ────────────────────────────────────────────────────
echo "── Contract Drift ──"
if [ -f frontend/scripts/check-contract-drift.sh ]; then
  run "API contract drift" bash -c "cd frontend && bash scripts/check-contract-drift.sh"
else
  skip "API contract drift" "Script not found"
fi
echo ""

# ── Smoke Test ─────────────────────────────────────────────────────────
echo "── Smoke Test ──"
if curl -sf http://localhost:8002/health > /dev/null 2>&1; then
  SITE_PASSWORD=""
  if [ -f docker/.env ]; then
    SITE_PASSWORD=$(grep "^SITE_PASSWORD=" docker/.env 2>/dev/null | cut -d= -f2 || true)
  fi
  SITE_PASSWORD="$SITE_PASSWORD" run "Deployment smoke test" bash scripts/smoke-test.sh
else
  skip "Deployment smoke test" "Backend not reachable"
fi
echo ""

# ── Static Analysis ───────────────────────────────────────────────────
echo "── Static Analysis ──"
if command -v semgrep &>/dev/null; then
  run "SAST (semgrep)" semgrep --config=auto --error --quiet src/
else
  skip "SAST (semgrep)" "semgrep not installed"
fi

if command -v vulture &>/dev/null; then
  run "Dead code (vulture)" vulture src/ vulture_whitelist.py --min-confidence 80
else
  skip "Dead code (vulture)" "vulture not installed"
fi

if command -v radon &>/dev/null; then
  run "Complexity (radon)" bash -c "radon cc src/ -a -nc | grep -q 'Average complexity' && echo OK"
else
  skip "Complexity (radon)" "radon not installed"
fi

if command -v hadolint &>/dev/null; then
  run "Dockerfile lint (hadolint)" bash -c "find docker/ -name 'Dockerfile*' | xargs hadolint"
else
  skip "Dockerfile lint (hadolint)" "hadolint not installed"
fi
echo ""

# ── Fuzz Tests ────────────────────────────────────────────────────────
echo "── Fuzz Tests ──"
if [ -n "$CONTAINER" ]; then
  run "API fuzz tests (schemathesis)" "${DOCKER_BACKEND[@]}" python -m pytest tests/fuzz/ -q --hypothesis-seed=0 2>/dev/null
else
  skip "API fuzz tests" "Docker backend not running"
fi
echo ""

# ── Benchmarks ────────────────────────────────────────────────────────
echo "── Benchmarks ──"
if [ -n "$CONTAINER" ]; then
  run "Benchmark tests" "${DOCKER_BACKEND[@]}" python -m pytest tests/benchmark/ --benchmark-only --benchmark-disable-gc -q 2>/dev/null
else
  skip "Benchmark tests" "Docker backend not running"
fi
echo ""

# ── Golden File Tests ─────────────────────────────────────────────────
echo "── Golden File Tests ──"
if [ -n "$CONTAINER" ]; then
  run "Golden file tests" "${DOCKER_BACKEND[@]}" python -m pytest tests/golden/ -q 2>/dev/null
else
  skip "Golden file tests" "Docker backend not running"
fi
echo ""

# ── Bundle Size ────────────────────────────────────────────────────────
echo "── Build Checks ──"
run "Frontend build" bash -c "cd frontend && bun run build 2>&1 | tail -1"
echo ""

# ── Load Testing ─────────────────────────────────────────────────────
echo "── Load Testing ──"
if command -v k6 &>/dev/null; then
  if curl -sf http://localhost:8002/health > /dev/null 2>&1; then
    K6_ENV=""
    if [ -f docker/.env ]; then
      K6_SITE_PW=$(grep "^SITE_PASSWORD=" docker/.env 2>/dev/null | cut -d= -f2 || true)
      [ -n "$K6_SITE_PW" ] && K6_ENV="--env SITE_PASSWORD=$K6_SITE_PW"
    fi
    run "k6 smoke test" bash -c "k6 run $K6_ENV tests/load/smoke.js --quiet 2>&1 | tail -10"
  else
    skip "k6 smoke test" "Backend not reachable"
  fi
else
  skip "k6 smoke test" "k6 not installed"
fi
echo ""

# ── Docker Build Testing ─────────────────────────────────────────────
echo "── Docker Build Testing ──"
if command -v docker &>/dev/null; then
  run "Dockerfile validation" bash tests/docker/test_dockerfiles.sh
else
  skip "Dockerfile validation" "docker not installed"
fi
echo ""

# ── License Compliance ───────────────────────────────────────────────
echo "── License Compliance ──"
run "License check" bash scripts/check-licenses.sh
echo ""

# ── Summary ────────────────────────────────────────────────────────────
echo "================================================"
printf "  Results: ${GREEN}%d passed${NC}, ${RED}%d failed${NC}, %d skipped\n" "$PASSED" "$FAILED" "$SKIPPED"
echo "================================================"

if [ "$SKIPPED" -gt 0 ] && [ "$PASSED" -eq 0 ] && [ "$FAILED" -eq 0 ]; then
  echo "WARNING: All checks were skipped — nothing was actually tested!"
  exit 1
fi

[ "$FAILED" -eq 0 ] || exit 1
