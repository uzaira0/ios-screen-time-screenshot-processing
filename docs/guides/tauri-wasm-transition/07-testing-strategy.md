# Chapter 07: Testing Strategy

## 1. Testing Tiers Overview

Not all tests deliver equal value per hour of setup effort. This chapter defines 29 testing types across two tiers:

- **Essential tier (11 types):** These are ship blockers. If any of these fail, the release does not ship. They catch the bugs that reach production.
- **Recommended tier (18 types):** These are added incrementally as the project matures. Each one eliminates a specific class of subtle bugs. Prioritize by the frequency of the bug class in your project's history.

The tiers are not about quality standards -- they are about sequencing. A project with zero tests should implement the Essential tier first, in order, before touching anything in the Recommended tier.

---

## 2. Essential Tier

### 2.1 Unit Tests

| Attribute | Value |
|-----------|-------|
| **What it tests** | Individual functions, classes, and modules in isolation |
| **Tools** | `bun test` (frontend), `pytest` (backend) |
| **Setup effort** | Low (30 min) |
| **Value** | High -- catches logic errors before they compound |
| **Where it runs** | Local + CI |

**Frontend (bun test):**

```typescript
// frontend/src/core/implementations/wasm/processing/__tests__/barExtraction.test.ts
import { describe, test, expect } from "bun:test";
import { extractBarHeights } from "../barExtraction.canvas";

describe("extractBarHeights", () => {
  test("returns 24 values for a valid grid region", () => {
    const imageData = createTestImageData(480, 200);
    const heights = extractBarHeights(imageData, { x: 0, y: 0 }, { x: 480, y: 200 });
    expect(heights).toHaveLength(24);
  });

  test("returns zeros for empty (white) image", () => {
    const imageData = createWhiteImageData(480, 200);
    const heights = extractBarHeights(imageData, { x: 0, y: 0 }, { x: 480, y: 200 });
    expect(heights.every(h => h === 0)).toBe(true);
  });
});
```

```bash
cd frontend && bun test                    # Run all
cd frontend && bun test --watch            # Watch mode
cd frontend && bun test src/core/          # Specific directory
```

**Backend (pytest):**

```python
# tests/unit/test_bar_processor.py
import pytest
from screenshot_processor.core.bar_processor import measure_bar_heights

def test_measure_bar_heights_returns_24_values(sample_grid_image):
    heights = measure_bar_heights(sample_grid_image, roi_bounds)
    assert len(heights) == 24

def test_measure_bar_heights_empty_image():
    empty = np.ones((200, 480, 3), dtype=np.uint8) * 255
    heights = measure_bar_heights(empty, roi_bounds)
    assert all(h == 0 for h in heights)
```

```bash
pytest tests/unit/ -v
pytest tests/unit/test_bar_processor.py::test_name -v   # Single test
```

### 2.2 Integration Tests

| Attribute | Value |
|-----------|-------|
| **What it tests** | Multi-component interactions with real dependencies (database, file system) |
| **Tools** | `pytest` + PostgreSQL (via Docker Compose) |
| **Setup effort** | Medium (1-2 hours) |
| **Value** | High -- catches wiring errors, ORM bugs, transaction issues |
| **Where it runs** | Local + CI (with service containers) |

Integration tests require a running PostgreSQL instance. In CI, use a service container:

```yaml
# .github/workflows/ci.yml
integration-tests:
  runs-on: ubuntu-latest
  services:
    postgres:
      image: postgres:16
      env:
        POSTGRES_USER: screenshot
        POSTGRES_PASSWORD: screenshot
        POSTGRES_DB: screenshot_annotations
      ports: ["5432:5432"]
      options: >-
        --health-cmd pg_isready
        --health-interval 5s
        --health-timeout 5s
        --health-retries 5
  steps:
    - uses: actions/checkout@v4
    - name: Run migrations
      run: alembic upgrade head
      env:
        DATABASE_URL: postgresql+asyncpg://screenshot:screenshot@localhost:5432/screenshot_annotations
    - name: Run integration tests
      run: pytest tests/integration/ -v
```

```python
# tests/integration/test_annotation_workflow.py
@pytest.mark.asyncio
async def test_annotation_submission_updates_consensus(async_client, test_screenshot):
    # Submit first annotation
    response = await async_client.post("/api/v1/annotations/", json={
        "screenshot_id": test_screenshot.id,
        "hourly_values": {"0": 10, "1": 20},
    }, headers={"X-Username": "user1"})
    assert response.status_code == 200

    # Submit second annotation
    response = await async_client.post("/api/v1/annotations/", json={
        "screenshot_id": test_screenshot.id,
        "hourly_values": {"0": 10, "1": 25},
    }, headers={"X-Username": "user2"})
    assert response.status_code == 200

    # Check consensus
    response = await async_client.get(f"/api/v1/consensus/{test_screenshot.id}")
    assert response.json()["status"] in ["agreed", "disputed"]
```

### 2.3 Type Checking

| Attribute | Value |
|-----------|-------|
| **What it tests** | Type correctness across the entire codebase |
| **Tools** | `tsc --noEmit` (frontend), `basedpyright` (backend) |
| **Setup effort** | Low (already configured) |
| **Value** | Very high -- catches contract drift, null errors, wrong argument types |
| **Where it runs** | Local + CI |

```bash
# Frontend
cd frontend && npx tsc --noEmit

# Backend
basedpyright src/ tests/
```

CI configuration:

```yaml
type-check:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Frontend type check
      run: cd frontend && npx tsc --noEmit
    - name: Backend type check
      run: basedpyright src/ tests/
```

Type checking is the highest-ROI test in the entire suite. A single `tsc --noEmit` run catches more bugs per second than any other tool.

### 2.4 Linting

| Attribute | Value |
|-----------|-------|
| **What it tests** | Code style, common mistakes, deprecated patterns |
| **Tools** | `eslint` (frontend), `ruff` (backend) |
| **Setup effort** | Low (already configured) |
| **Value** | Medium -- catches style issues and some logic bugs (unused vars, unreachable code) |
| **Where it runs** | Local + CI |

```bash
# Frontend
cd frontend && bun run lint

# Backend
ruff check . && ruff format --check .
```

Ruff is configured in `pyproject.toml`:

```toml
[tool.ruff]
line-length = 120
target-version = "py310"
```

The project has a post-tool-use hook that auto-formats Python files with `ruff format` and `ruff check --fix` on every edit.

### 2.5 E2E Tests

| Attribute | Value |
|-----------|-------|
| **What it tests** | Full user workflows through the browser |
| **Tools** | Playwright |
| **Setup effort** | Medium (2-4 hours for first tests) |
| **Value** | Very high -- catches integration failures invisible to unit tests |
| **Where it runs** | Local + CI |

```typescript
// frontend/tests/e2e/annotation-workflow.spec.ts
import { test, expect } from "@playwright/test";

test("user can annotate a screenshot", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("textbox", { name: "Username" }).fill("testuser");
  await page.getByRole("button", { name: "Login" }).click();

  // Navigate to annotation view
  await page.getByRole("link", { name: "Annotate" }).click();
  await expect(page.getByTestId("screenshot-image")).toBeVisible();

  // Fill hourly values
  await page.getByLabel("Hour 0").fill("10");
  await page.getByLabel("Hour 1").fill("20");

  // Submit
  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page.getByText("Annotation saved")).toBeVisible();
});
```

```bash
cd frontend && bun run test:e2e                # Headless
cd frontend && bun run test:e2e:headed         # Visible browser
cd frontend && bun run test:e2e:ui             # Interactive UI mode
```

CI with Playwright sharding (see Section 8 for full pipeline):

```yaml
e2e-tests:
  runs-on: ubuntu-latest
  strategy:
    matrix:
      shard: [1/4, 2/4, 3/4, 4/4]
  steps:
    - run: bunx playwright test --shard=${{ matrix.shard }}
```

### 2.6 Contract Drift Detection

| Attribute | Value |
|-----------|-------|
| **What it tests** | That frontend TypeScript types match backend Pydantic schemas |
| **Tools** | `openapi-typescript` + `git diff --exit-code` |
| **Setup effort** | Low (15 min) |
| **Value** | Very high -- eliminates runtime type mismatches between frontend and backend |
| **Where it runs** | CI only |

See Chapter 06, Section 5 for the full CI job configuration. The core check:

```bash
cd frontend && bun run generate:api-types
git diff --exit-code frontend/src/types/api-schema.ts
```

If the generated file differs from what is committed, the types are stale. The PR fails with a clear error message.

### 2.7 Security Scanning

| Attribute | Value |
|-----------|-------|
| **What it tests** | Known vulnerabilities in dependencies |
| **Tools** | `npm audit` / `bun audit`, `pip-audit`, `cargo-audit`, Trivy |
| **Setup effort** | Low (30 min) |
| **Value** | High -- catches known CVEs before deployment |
| **Where it runs** | CI (scheduled + on PR) |

```yaml
security-scan:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Frontend dependency audit
      run: cd frontend && npx audit-ci --moderate
      continue-on-error: false

    - name: Backend dependency audit
      run: pip-audit --requirement requirements.txt
      continue-on-error: false

    - name: Rust dependency audit
      run: cargo audit
      working-directory: frontend/src-tauri
      continue-on-error: false

    - name: Container image scan
      uses: aquasecurity/trivy-action@master
      with:
        image-ref: "screenshot-processor:latest"
        severity: "CRITICAL,HIGH"
        exit-code: "1"
```

For a HIPAA-adjacent project handling medical device screenshots, security scanning is essential, not optional.

### 2.8 Accessibility Testing

| Attribute | Value |
|-----------|-------|
| **What it tests** | WCAG compliance, keyboard navigation, screen reader compatibility |
| **Tools** | `@axe-core/playwright` (already a devDependency) |
| **Setup effort** | Low (1 hour) |
| **Value** | Medium-high -- catches a11y violations that affect real users |
| **Where it runs** | CI (as part of E2E suite) |

```typescript
// frontend/tests/accessibility/homepage.spec.ts
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("homepage has no critical accessibility violations", async ({ page }) => {
  await page.goto("/");

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();

  expect(results.violations.filter(v => v.impact === "critical")).toHaveLength(0);
});

test("annotation form is keyboard navigable", async ({ page }) => {
  await page.goto("/annotate/1");

  // Tab through all form fields
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Hour 0")).toBeFocused();

  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Hour 1")).toBeFocused();
});
```

### 2.9 Snapshot Tests

| Attribute | Value |
|-----------|-------|
| **What it tests** | Output stability -- ensures function output does not change unexpectedly |
| **Tools** | `pytest-syrupy` (backend), `bun test` with `toMatchSnapshot` (frontend) |
| **Setup effort** | Low (30 min) |
| **Value** | Medium -- catches unintended changes to data processing output |
| **Where it runs** | Local + CI |

**Backend (syrupy):**

```python
# tests/unit/test_ocr_output.py
def test_extract_title_snapshot(snapshot, sample_title_region):
    result = extract_title(sample_title_region)
    assert result == snapshot
```

Syrupy stores snapshots as `.ambr` files alongside tests. Update with `pytest --snapshot-update`.

**Frontend (bun):**

```typescript
import { test, expect } from "bun:test";

test("grid detection output is stable", () => {
  const result = detectGrid(testImageData);
  expect(result).toMatchSnapshot();
});
```

### 2.10 Contract/API Tests

| Attribute | Value |
|-----------|-------|
| **What it tests** | That the API conforms to its OpenAPI specification |
| **Tools** | Schemathesis |
| **Setup effort** | Medium (1-2 hours) |
| **Value** | High -- finds edge cases in request validation, response schemas |
| **Where it runs** | CI |

Schemathesis reads the OpenAPI spec and generates test cases automatically:

```bash
# Install
pip install schemathesis

# Run against the spec
schemathesis run http://localhost:8002/openapi.json \
  --hypothesis-max-examples=100 \
  --checks all \
  --header "X-Username: testuser"
```

```yaml
api-contract-tests:
  runs-on: ubuntu-latest
  services:
    postgres:
      image: postgres:16
      # ... (same as integration tests)
  steps:
    - name: Start backend
      run: uvicorn src.screenshot_processor.web.api.main:app --host 0.0.0.0 --port 8002 &

    - name: Run Schemathesis
      run: |
        schemathesis run http://localhost:8002/openapi.json \
          --hypothesis-max-examples=50 \
          --checks all \
          --header "X-Username: admin" \
          --exclude-deprecated
```

Schemathesis will find:
- Endpoints that return 500 on valid input
- Response bodies that do not match the declared schema
- Missing required fields in responses
- Incorrect status codes

### 2.11 Property-Based Testing

| Attribute | Value |
|-----------|-------|
| **What it tests** | Invariants that must hold for all inputs, not just hand-picked examples |
| **Tools** | `fast-check` (frontend), `Hypothesis` (backend) |
| **Setup effort** | Medium (2-4 hours) |
| **Value** | High -- finds edge cases humans do not think of |
| **Where it runs** | Local + CI |

**Backend (Hypothesis):**

```python
from hypothesis import given, strategies as st

@given(
    heights=st.lists(st.floats(min_value=0, max_value=100), min_size=24, max_size=24)
)
def test_bar_heights_roundtrip(heights):
    """Bar heights should survive encode/decode without loss."""
    encoded = encode_hourly_data(heights)
    decoded = decode_hourly_data(encoded)
    for original, restored in zip(heights, decoded):
        assert abs(original - restored) < 0.01
```

**Frontend (fast-check):**

```typescript
import fc from "fast-check";
import { test } from "bun:test";

test("hourly data keys are always valid hour strings", () => {
  fc.assert(
    fc.property(
      fc.dictionary(fc.integer({ min: 0, max: 23 }).map(String), fc.float({ min: 0, max: 1440 })),
      (hourlyValues) => {
        const keys = Object.keys(hourlyValues);
        return keys.every(k => {
          const n = parseInt(k, 10);
          return n >= 0 && n <= 23;
        });
      }
    )
  );
});
```

---

## 3. Recommended Tier

### 3.1 Visual Regression Testing

| Attribute | Value |
|-----------|-------|
| **What it tests** | UI appearance changes (layout shifts, color changes, missing elements) |
| **Tools** | Playwright screenshots or Chromatic (Storybook) |
| **Setup effort** | Medium (2-4 hours) |
| **Value** | Medium -- catches CSS regressions invisible to functional tests |
| **Where it runs** | CI |

```typescript
// frontend/tests/visual/annotation-view.spec.ts
import { test, expect } from "@playwright/test";

test("annotation view matches baseline", async ({ page }) => {
  await page.goto("/annotate/1");
  await page.waitForLoadState("networkidle");
  await expect(page).toHaveScreenshot("annotation-view.png", {
    maxDiffPixelRatio: 0.01,
  });
});
```

Update baselines with `bunx playwright test --update-snapshots`.

### 3.2 API Fuzzing

| Attribute | Value |
|-----------|-------|
| **What it tests** | API robustness against malformed, unexpected, and adversarial inputs |
| **Tools** | Schemathesis (extended mode) |
| **Setup effort** | Low (reuses contract test setup) |
| **Value** | Medium-high -- finds crashes on edge-case inputs |
| **Where it runs** | CI (nightly) |

```bash
schemathesis run http://localhost:8002/openapi.json \
  --hypothesis-max-examples=500 \
  --stateful=links \
  --checks all \
  --header "X-Username: admin"
```

The `--stateful=links` flag makes Schemathesis follow OpenAPI links between endpoints, testing multi-step workflows (e.g., create screenshot then annotate it).

### 3.3 Load Testing

| Attribute | Value |
|-----------|-------|
| **What it tests** | Performance under concurrent load, response time degradation |
| **Tools** | k6 or Locust |
| **Setup effort** | Medium (2-4 hours) |
| **Value** | Medium -- important before production deployments |
| **Where it runs** | CI (nightly) or manual |

```javascript
// load-tests/annotation-workflow.js (k6)
import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  stages: [
    { duration: "30s", target: 10 },
    { duration: "1m", target: 50 },
    { duration: "30s", target: 0 },
  ],
  thresholds: {
    http_req_duration: ["p(95)<500"],
  },
};

export default function () {
  const res = http.get("http://localhost:8002/api/v1/screenshots/stats", {
    headers: { "X-Username": "loadtest" },
  });
  check(res, { "status is 200": (r) => r.status === 200 });
  sleep(1);
}
```

```bash
k6 run load-tests/annotation-workflow.js
```

### 3.4 Mutation Testing

| Attribute | Value |
|-----------|-------|
| **What it tests** | Test suite effectiveness -- do your tests actually catch bugs? |
| **Tools** | `mutmut` (Python), `Stryker` (TypeScript) |
| **Setup effort** | Medium (2-4 hours) |
| **Value** | Medium -- reveals tests that pass regardless of correctness |
| **Where it runs** | Local or CI (nightly, slow) |

```bash
# Python
mutmut run --paths-to-mutate src/screenshot_processor/core/bar_processor.py
mutmut results

# TypeScript
npx stryker run
```

Mutation testing modifies your source code (e.g., changes `>` to `>=`, removes a `return` statement) and checks if any test fails. If no test fails, the mutation "survived" -- meaning your tests do not cover that logic.

### 3.5 Performance Regression

| Attribute | Value |
|-----------|-------|
| **What it tests** | Page load performance, Core Web Vitals, rendering performance |
| **Tools** | Lighthouse CI |
| **Setup effort** | Medium (1-2 hours) |
| **Value** | Medium -- prevents slow creep of performance degradation |
| **Where it runs** | CI |

```yaml
lighthouse:
  runs-on: ubuntu-latest
  steps:
    - uses: treosh/lighthouse-ci-action@v12
      with:
        urls: |
          http://localhost:5175/
          http://localhost:5175/annotate/1
        budgetPath: ./lighthouse-budget.json
        uploadArtifacts: true
```

```json
// lighthouse-budget.json
[
  {
    "path": "/",
    "timings": [
      { "metric": "first-contentful-paint", "budget": 2000 },
      { "metric": "interactive", "budget": 5000 }
    ],
    "resourceSizes": [
      { "resourceType": "script", "budget": 500 },
      { "resourceType": "total", "budget": 1500 }
    ]
  }
]
```

### 3.6 Bundle Size Monitoring

| Attribute | Value |
|-----------|-------|
| **What it tests** | JavaScript bundle size does not grow unexpectedly |
| **Tools** | `size-limit` |
| **Setup effort** | Low (30 min) |
| **Value** | Medium -- prevents dependency bloat, important for WASM mode |
| **Where it runs** | CI |

```json
// package.json
{
  "size-limit": [
    { "path": "dist/assets/*.js", "limit": "500 kB", "gzip": true },
    { "path": "dist/assets/*.css", "limit": "50 kB", "gzip": true }
  ]
}
```

```bash
npx size-limit
```

### 3.7 WASM-Specific Testing

| Attribute | Value |
|-----------|-------|
| **What it tests** | Client-side processing correctness, IndexedDB migrations, OPFS blob storage |
| **Tools** | `bun test` + `happy-dom`, Playwright for browser-specific APIs |
| **Setup effort** | Medium (2-4 hours) |
| **Value** | High -- WASM bugs are hard to debug in production |
| **Where it runs** | Local + CI |

**Processing correctness:**

```typescript
// Test that WASM grid detection produces same results as reference
import { detectGrid } from "@/core/implementations/wasm/processing/gridDetection.canvas";

test("grid detection matches reference output", async () => {
  const imageData = await loadTestImage("sample-screen-time.png");
  const result = detectGrid(imageData, "screen_time");

  expect(result.upperLeft.x).toBeCloseTo(referenceOutput.upperLeft.x, 2);
  expect(result.upperLeft.y).toBeCloseTo(referenceOutput.upperLeft.y, 2);
});
```

**IndexedDB migration testing:**

```typescript
// Test that DB schema upgrades preserve data
import { ScreenshotDB } from "@/core/implementations/wasm/storage/database/ScreenshotDB";

test("version 5 migration renames status to annotation_status", async () => {
  // Create v4 database with old schema
  const oldDb = new Dexie("TestDB");
  oldDb.version(4).stores({ screenshots: "++id, status" });
  await oldDb.table("screenshots").add({ id: 1, status: "completed" });
  oldDb.close();

  // Open with new schema
  const newDb = new ScreenshotDB();
  const screenshot = await newDb.screenshots.get(1);
  expect(screenshot.annotation_status).toBe("annotated");
  expect(screenshot.status).toBeUndefined();
});
```

### 3.8 Rust/Tauri Unit Tests

| Attribute | Value |
|-----------|-------|
| **What it tests** | Tauri commands, Rust business logic, plugin integrations |
| **Tools** | `cargo test` |
| **Setup effort** | Low (built into Rust toolchain) |
| **Value** | High -- Rust panics crash the entire app |
| **Where it runs** | Local + CI |

```rust
// src-tauri/src/commands.rs
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_screenshot_metadata() {
        let meta = parse_metadata("screenshot-2024-01-15.png");
        assert_eq!(meta.date, "2024-01-15");
    }

    #[tokio::test]
    async fn test_file_system_read() {
        let content = read_screenshot("/tmp/test.png").await;
        assert!(content.is_ok());
    }
}
```

```bash
cd frontend/src-tauri && cargo test
```

### 3.9 Docker Image Scanning

| Attribute | Value |
|-----------|-------|
| **What it tests** | OS-level vulnerabilities in container images |
| **Tools** | Trivy |
| **Setup effort** | Low (15 min) |
| **Value** | Medium-high -- catches CVEs in base images and system libraries |
| **Where it runs** | CI |

```yaml
docker-scan:
  runs-on: ubuntu-latest
  steps:
    - name: Build image
      run: docker build -f docker/backend/Dockerfile -t backend:scan .

    - name: Scan with Trivy
      uses: aquasecurity/trivy-action@master
      with:
        image-ref: "backend:scan"
        severity: "CRITICAL,HIGH"
        exit-code: "1"
        ignore-unfixed: true
```

### 3.10 Database Migration Testing

| Attribute | Value |
|-----------|-------|
| **What it tests** | Alembic migrations apply cleanly and are reversible |
| **Tools** | Alembic + pytest |
| **Setup effort** | Low (30 min) |
| **Value** | High -- broken migrations cause production outages |
| **Where it runs** | CI |

```python
# tests/integration/test_migrations.py
import pytest
from alembic import command
from alembic.config import Config

@pytest.fixture
def alembic_config():
    config = Config("alembic.ini")
    return config

def test_upgrade_downgrade_cycle(alembic_config, empty_database):
    """Test that all migrations can be applied and reversed."""
    # Upgrade to head
    command.upgrade(alembic_config, "head")

    # Downgrade to base
    command.downgrade(alembic_config, "base")

    # Upgrade again (ensures idempotency)
    command.upgrade(alembic_config, "head")
```

```bash
# Manual verification
alembic upgrade head && alembic downgrade -1 && alembic upgrade head
```

### 3.11 Cross-Implementation Parity Testing

| Attribute | Value |
|-----------|-------|
| **What it tests** | That Python backend and WASM frontend produce identical results for the same input |
| **Tools** | Custom test harness comparing outputs |
| **Setup effort** | High (4-8 hours) |
| **Value** | Very high -- ensures mode switching does not produce different data |
| **Where it runs** | CI |

This is specific to dual-mode architectures. The Python `slice_image()` and the WASM `barExtraction.canvas.ts` must produce the same hourly values for the same screenshot.

```python
# tests/parity/test_processing_parity.py
import json
import subprocess

def test_bar_extraction_parity(sample_screenshot_path):
    """Python and WASM bar extraction must produce same output."""
    # Run Python extraction
    python_result = extract_bars_python(sample_screenshot_path)

    # Run WASM extraction via Playwright
    wasm_result = json.loads(subprocess.check_output([
        "bunx", "playwright", "test",
        "tests/parity/wasm-extract.spec.ts",
        "--reporter=json",
    ]))

    for hour in range(24):
        python_val = python_result[str(hour)]
        wasm_val = wasm_result[str(hour)]
        assert abs(python_val - wasm_val) < 1.0, (
            f"Hour {hour}: Python={python_val}, WASM={wasm_val}"
        )
```

### 3.12 WebSocket Integration Testing

| Attribute | Value |
|-----------|-------|
| **What it tests** | Real-time event broadcasting, connection lifecycle, reconnection |
| **Tools** | pytest + `websockets` library, or Playwright |
| **Setup effort** | Medium (2-4 hours) |
| **Value** | Medium -- WebSocket bugs are intermittent and hard to reproduce |
| **Where it runs** | CI |

```python
# tests/integration/test_websocket.py
import asyncio
import websockets

async def test_annotation_broadcast(running_server):
    async with websockets.connect("ws://localhost:8002/api/v1/ws") as ws:
        # Submit annotation via HTTP
        await submit_annotation(screenshot_id=1, user="testuser")

        # Should receive broadcast within 2 seconds
        message = await asyncio.wait_for(ws.recv(), timeout=2.0)
        data = json.loads(message)
        assert data["type"] == "annotation_submitted"
```

### 3.13 Tauri Update Signing Verification

| Attribute | Value |
|-----------|-------|
| **What it tests** | That Tauri auto-update bundles are correctly signed and verifiable |
| **Tools** | `tauri signer` + custom verification script |
| **Setup effort** | Medium (1-2 hours) |
| **Value** | High -- unsigned updates are a security risk |
| **Where it runs** | CI (on release builds) |

```bash
# Verify the update bundle signature
tauri signer verify \
  --signature target/release/bundle/macos/app.tar.gz.sig \
  --public-key tauri-update.pub \
  target/release/bundle/macos/app.tar.gz
```

### 3.14 Fuzz Tests

| Attribute | Value |
|-----------|-------|
| **What it tests** | Robustness against random/malformed input data |
| **Tools** | `cargo-fuzz` (Rust), `atheris` (Python) |
| **Setup effort** | Medium (2-4 hours) |
| **Value** | Medium -- finds panics and crashes on unexpected input |
| **Where it runs** | CI (nightly) |

```rust
// src-tauri/fuzz/fuzz_targets/parse_metadata.rs
#![no_main]
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    if let Ok(s) = std::str::from_utf8(data) {
        let _ = parse_screenshot_metadata(s);
    }
});
```

```bash
cd frontend/src-tauri && cargo fuzz run parse_metadata -- -max_total_time=60
```

### 3.15 Golden File Tests

| Attribute | Value |
|-----------|-------|
| **What it tests** | That processing output for known inputs matches expected output files |
| **Tools** | pytest + golden files in `tests/fixtures/` |
| **Setup effort** | Low (1 hour) |
| **Value** | Medium-high -- catches regressions in the processing pipeline |
| **Where it runs** | Local + CI |

```python
# tests/unit/test_golden_files.py
import json

GOLDEN_DIR = Path("tests/fixtures/golden")

@pytest.mark.parametrize("image_name", [
    "screen_time_basic.png",
    "screen_time_dark_mode.png",
    "battery_ipad.png",
])
def test_processing_matches_golden(image_name):
    image_path = Path("tests/fixtures/images") / image_name
    golden_path = GOLDEN_DIR / f"{image_name}.json"

    result = process_screenshot(str(image_path))
    expected = json.loads(golden_path.read_text())

    assert result["hourly_values"] == expected["hourly_values"]
    assert result["title"] == expected["title"]
```

Update golden files: `pytest tests/unit/test_golden_files.py --update-golden`.

### 3.16 Dead Code Detection

| Attribute | Value |
|-----------|-------|
| **What it tests** | Unused exports, unreachable code, orphaned files |
| **Tools** | `knip` (TypeScript), `vulture` (Python) |
| **Setup effort** | Low (30 min) |
| **Value** | Low-medium -- reduces codebase size and cognitive load |
| **Where it runs** | CI |

```bash
# TypeScript
npx knip

# Python
vulture src/ --min-confidence 80
```

### 3.17 Dependency Analysis

| Attribute | Value |
|-----------|-------|
| **What it tests** | Circular dependencies, dependency depth, import health |
| **Tools** | `madge` (TypeScript), `importlab` (Python) |
| **Setup effort** | Low (30 min) |
| **Value** | Low-medium -- catches circular imports before they cause runtime issues |
| **Where it runs** | CI |

```bash
# Find circular dependencies in TypeScript
npx madge --circular --extensions ts,tsx frontend/src/

# Generate dependency graph
npx madge --image graph.svg frontend/src/core/
```

### 3.18 Benchmark Tests

| Attribute | Value |
|-----------|-------|
| **What it tests** | Performance of critical code paths over time |
| **Tools** | `pytest-benchmark` (Python), `bun test` with timing (frontend) |
| **Setup effort** | Medium (1-2 hours) |
| **Value** | Medium -- prevents performance regressions in hot paths |
| **Where it runs** | CI (with baseline comparison) |

```python
# tests/benchmarks/test_processing_performance.py
def test_bar_extraction_performance(benchmark, sample_image):
    result = benchmark(measure_bar_heights, sample_image, roi_bounds)
    assert len(result) == 24
    # benchmark automatically tracks min, max, mean, stddev
```

```bash
pytest tests/benchmarks/ --benchmark-compare --benchmark-autosave
```

---

## 4. Testing DI Containers

The service container pattern makes testing straightforward: each implementation can be tested in isolation by constructing it directly, without bootstrapping the full container.

**Test server implementations against a real API:**

```typescript
import { APIScreenshotService } from "@/core/implementations/server/APIScreenshotService";

test("APIScreenshotService.getById returns screenshot", async () => {
  const service = new APIScreenshotService("http://localhost:8002/api/v1");
  const screenshot = await service.getById(1);
  expect(screenshot.id).toBe(1);
});
```

**Test WASM implementations against IndexedDB:**

```typescript
import { WASMScreenshotService } from "@/core/implementations/wasm/WASMScreenshotService";

test("WASMScreenshotService.getById returns screenshot from IndexedDB", async () => {
  // Seed test data
  await db.screenshots.add({ id: 1, annotation_status: "pending", /* ... */ });

  const service = new WASMScreenshotService();
  const screenshot = await service.getById(1);
  expect(screenshot.id).toBe(1);
  expect(screenshot.annotation_status).toBe("pending");
});
```

**Mock storage for processing tests:**

```typescript
import { WASMProcessingService } from "@/core/implementations/wasm/WASMProcessingService";

test("processing service extracts hourly data", async () => {
  const service = new WASMProcessingService();
  // The processing service operates on ImageData, not storage
  const imageData = await loadTestImageData("sample.png");
  const result = await service.processImage(imageData, "screen_time");
  expect(Object.keys(result.hourlyData)).toHaveLength(24);
});
```

**Test the container itself:**

```typescript
import { ServiceContainer } from "@/core/di/Container";
import { TOKENS } from "@/core/di/tokens";

test("container resolves registered singleton", () => {
  const container = new ServiceContainer();
  const mockService = { getById: async () => ({}) };
  container.registerSingleton(TOKENS.SCREENSHOT_SERVICE, mockService);

  const resolved = container.resolve(TOKENS.SCREENSHOT_SERVICE);
  expect(resolved).toBe(mockService); // Same instance
});

test("container throws for unregistered service", () => {
  const container = new ServiceContainer();
  expect(() => container.resolve("NONEXISTENT")).toThrow("Service not registered");
});
```

---

## 5. Testing WASM Workers

Web Workers communicate via `postMessage`. Testing them requires separating the **logic** (testable as pure functions) from the **message protocol** (testable as integration).

### Test functions directly

The processing functions in `gridDetection.canvas.ts`, `barExtraction.canvas.ts`, and `ocr.canvas.ts` are importable modules. They do not depend on the Worker runtime:

```typescript
// These are pure functions that operate on ImageData
import { detectGridAnchors } from "@/core/implementations/wasm/processing/gridDetection.canvas";
import { extractBarHeights } from "@/core/implementations/wasm/processing/barExtraction.canvas";

test("detectGridAnchors finds 12AM marker", async () => {
  const imageData = await loadTestImageData("screen-time-grid.png");
  const anchors = await detectGridAnchors(imageData, "screen_time");
  expect(anchors).not.toBeNull();
  expect(anchors!.upperLeft.x).toBeGreaterThan(0);
});
```

### Test message protocol separately

The worker message types are defined in `processing/workers/types.ts`. Test that message serialization/deserialization works:

```typescript
import type { WorkerMessage, ProcessImagePayload } from "@/core/implementations/wasm/processing/workers/types";

test("worker message payload is structurally valid", () => {
  const message: WorkerMessage = {
    type: "PROCESS_IMAGE",
    id: "test-123",
    payload: {
      imageData: new ImageData(100, 100),
      imageType: "screen_time",
    } satisfies ProcessImagePayload,
  };

  // Verify the message can be serialized (structured clone algorithm)
  expect(message.type).toBe("PROCESS_IMAGE");
  expect(message.id).toBe("test-123");
});
```

### Test Worker integration in Playwright

For full Worker integration tests, use Playwright (which runs in a real browser):

```typescript
// frontend/tests/e2e/wasm-processing.spec.ts
test("WASM mode processes a screenshot end-to-end", async ({ page }) => {
  await page.goto("/?mode=wasm");

  // Upload an image
  const fileChooser = page.waitForEvent("filechooser");
  await page.getByText("Upload").click();
  const chooser = await fileChooser;
  await chooser.setFiles("tests/fixtures/sample-screen-time.png");

  // Wait for processing
  await expect(page.getByText("Processing complete")).toBeVisible({ timeout: 30000 });

  // Verify hourly data was extracted
  await expect(page.getByLabel("Hour 0")).not.toHaveValue("");
});
```

---

## 6. Testing Tauri Features

Tauri adds a native shell around the web app. Testing requires three strategies:

### Mock Tauri APIs for the React layer

The `@tauri-apps/api` modules are JavaScript wrappers around IPC calls. In unit tests, mock them:

```typescript
// frontend/src/__tests__/setup.ts
import { vi } from "vitest";

// Mock Tauri APIs for unit tests
vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
}));

vi.mock("@tauri-apps/plugin-dialog", () => ({
  open: vi.fn(),
  save: vi.fn(),
  message: vi.fn(),
}));

vi.mock("@tauri-apps/plugin-fs", () => ({
  readFile: vi.fn(),
  writeFile: vi.fn(),
  exists: vi.fn(),
}));
```

```typescript
import { invoke } from "@tauri-apps/api/core";

test("save-to-disk command is invoked with correct path", async () => {
  const mockInvoke = invoke as ReturnType<typeof vi.fn>;
  mockInvoke.mockResolvedValue({ success: true });

  await saveScreenshot(screenshotData, "/tmp/output.png");

  expect(mockInvoke).toHaveBeenCalledWith("save_file", {
    path: "/tmp/output.png",
    data: expect.any(Uint8Array),
  });
});
```

### Use `#[cfg(test)]` for Rust commands

```rust
// src-tauri/src/commands.rs

#[tauri::command]
pub async fn process_screenshot(path: String) -> Result<ProcessingResult, String> {
    let image = load_image(&path).map_err(|e| e.to_string())?;
    Ok(extract_data(&image))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_process_screenshot_valid_path() {
        let result = process_screenshot("/tmp/test-screenshot.png".to_string()).await;
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_process_screenshot_invalid_path() {
        let result = process_screenshot("/nonexistent/path.png".to_string()).await;
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("No such file"));
    }
}
```

### Test the full Tauri app with WebDriver

For full E2E testing of the Tauri app (including native menus, file dialogs, window management), use `tauri-driver` with WebDriver:

```bash
# Start tauri-driver
cargo install tauri-driver
tauri-driver &

# Run WebDriver tests
cd frontend && bunx wdio run wdio.conf.ts
```

This is the most expensive test setup. Reserve it for critical native-specific workflows (file drag-and-drop, auto-update, native notifications).

---

## 7. CI Pipeline Design

A well-structured CI pipeline runs tests in parallel where possible, with service containers for database-dependent tests.

```yaml
# .github/workflows/ci.yml
name: CI

on:
  pull_request:
  push:
    branches: [main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  # ─── Fast checks (< 1 min each) ─── run in parallel
  frontend-typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: oven-sh/setup-bun@v2
      - run: cd frontend && bun install --frozen-lockfile
      - run: cd frontend && npx tsc --noEmit

  frontend-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: oven-sh/setup-bun@v2
      - run: cd frontend && bun install --frozen-lockfile
      - run: cd frontend && bun run lint

  backend-typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[web,dev]"
      - run: basedpyright src/ tests/

  backend-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install ruff
      - run: ruff check . && ruff format --check .

  contract-drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - uses: oven-sh/setup-bun@v2
      - run: pip install -e ".[web]"
      - run: cd frontend && bun install --frozen-lockfile
      - run: cd frontend && bun run generate:api-types
      - run: git diff --exit-code frontend/src/types/api-schema.ts

  # ─── Unit tests (< 2 min each) ─── run in parallel
  frontend-unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: oven-sh/setup-bun@v2
      - run: cd frontend && bun install --frozen-lockfile
      - run: cd frontend && bun test

  backend-unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[web,dev]"
      - run: pytest tests/unit/ -v

  rust-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
      - run: cd frontend/src-tauri && cargo test

  # ─── Integration tests (need services) ───
  backend-integration:
    runs-on: ubuntu-latest
    needs: [backend-typecheck, backend-lint, backend-unit]
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: screenshot
          POSTGRES_PASSWORD: screenshot
          POSTGRES_DB: screenshot_annotations
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[web,dev]"
      - run: alembic upgrade head
      - run: pytest tests/integration/ -v

  # ─── E2E tests (sharded, need full stack) ───
  e2e:
    runs-on: ubuntu-latest
    needs: [frontend-typecheck, frontend-lint, frontend-unit, backend-integration]
    strategy:
      fail-fast: false
      matrix:
        shard: [1/4, 2/4, 3/4, 4/4]
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: screenshot
          POSTGRES_PASSWORD: screenshot
          POSTGRES_DB: screenshot_annotations
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: oven-sh/setup-bun@v2
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }

      - name: Install dependencies
        run: |
          pip install -e ".[web,dev]"
          cd frontend && bun install --frozen-lockfile
          bunx playwright install --with-deps chromium

      - name: Start backend
        run: |
          alembic upgrade head
          uvicorn src.screenshot_processor.web.api.main:app --host 0.0.0.0 --port 8002 &

      - name: Run E2E tests (shard ${{ matrix.shard }})
        run: cd frontend && bunx playwright test --shard=${{ matrix.shard }}

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report-${{ strategy.job-index }}
          path: frontend/playwright-report/

  # ─── Security (runs in parallel with everything) ───
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: cd frontend && npx audit-ci --moderate
      - run: pip install pip-audit && pip-audit --requirement requirements.txt
```

### Key design decisions

1. **Fast checks run first, in parallel.** Type checking, linting, and contract drift complete in under a minute each. If any fail, developers get feedback before the slower tests even start.

2. **Integration tests depend on fast checks.** No point running a 5-minute database test if the code does not type-check.

3. **E2E tests are sharded.** Four parallel runners each execute 1/4 of the test suite. Total wall time is ~1/4 of sequential execution.

4. **`fail-fast: false` on E2E shards.** If shard 1 fails, shards 2-4 still run. This gives a complete picture of failures rather than hiding subsequent problems behind the first failure.

5. **Security scanning runs independently.** It does not block or depend on any other job. It can also run on a schedule (nightly) for thorough scans.

6. **Artifacts are uploaded on failure.** Playwright traces, screenshots, and reports are available for debugging even after the CI job completes.
