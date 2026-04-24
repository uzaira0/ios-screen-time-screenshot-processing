# WASM Canvas Parity Handoff

Work stream: align the TypeScript/Canvas 2D WASM pipeline with the Rust reference implementation, add test infrastructure, and fix pre-existing test/type failures.

## Commits (newest first)

| SHA | Summary |
|-----|---------|
| `0977090` | fix(test): root bunfig.toml — `bun test` from repo root no longer picks up Playwright specs |
| `6778ce7` | fix(tests): pre-existing test failures, TS errors, new unit + parity tests |
| `fa0cf8e` | fix(wasm): three parity bugs from full Rust sweep |
| `96d740e` | test(wasm): unit tests for anchor coordinate fallback |
| `dca1d2f` | fix(wasm): `findRightAnchor` nested-loop fallback from Rust |
| `f194bc9` | fix(processing): canvas parity fixes, golden e2e tests, clean warnings |

---

## Bugs Fixed

### 1. `findLeftAnchor` / `findRightAnchor` — nested-loop fallback (`dca1d2f`, `f194bc9`)

**File:** `frontend/src/core/implementations/wasm/processing/gridDetection.canvas.ts`

Both functions search for horizontal then vertical lines to place OCR anchor points. The original code had sequential (not nested) loops, so when no horizontal line was found the fallback expression still subtracted `movingIndex` from zero: `y + (null||0) - movingIndex + 1` → off by ~99px.

**Rust reference:** `find_left_anchor` / `find_right_anchor` in `crates/processing/src/grid_detection/ocr_anchored.rs`.

**Fix:** Nest the vertical-line search inside the horizontal-found branch. Fallbacks:
- No horizontal → `(x - BUFFER, y + h)` for left; `(x - BUFFER, y)` for right
- Horizontal found, no vertical → `x - BUFFER` for x in both cases

**Tests:** `gridDetection.test.ts` — 14 tests including regressions asserting old bogus values (`y - 99`, `x - 124`) are gone.

---

### 2. `findGridEdges` cluster selection — boundary-nearest, not first/last (`fa0cf8e`)

**File:** `frontend/src/core/implementations/wasm/processing/lineBasedDetection.canvas.ts`

Gray vertical-line clusters were selected as `clusters[0]` and `clusters[last]` (first and last). When gray UI chrome appears at the image extremes, those outlier clusters would be chosen as the grid edges instead of the real grid lines.

**Rust reference:** `find_grid_edges` in `crates/processing/src/grid_detection/line_based.rs` — uses nearest-to-boundary-window selection.

**Fix:** Reduce over all clusters picking the one with minimum distance to `xStart` (left) and `xEnd` (right):
```typescript
export function selectBoundaryClusters(clusters, xStart, xEnd) { ... }
```

**Tests:** `lineBasedDetection.test.ts` — 10 tests. Key regression: clusters `[5, 83, 721, 795]` with window `[50, 750]` returns `{left: 83, right: 721}` not `{left: 5, right: 795}`.

---

### 3. `isDailyTotalPage` double-counting (`fa0cf8e`)

**File:** `frontend/src/core/implementations/wasm/processing/ocr.canvas.ts`

The old code joined all OCR words into one string then counted substring matches. "TODAY" contains both "DAY" and "TODAY" → counted as 2 daily markers instead of 1, skewing the daily-vs-app classification.

**Rust reference:** `is_daily_total_page` in `crates/processing/src/ocr.rs` — iterates words, breaks after first match per word per category.

**Fix:** Per-word loop with `break` after first match:
```typescript
export function classifyPageWords(words) { ... }
```

**Tests:** `ocr.test.ts` — 11 tests. Key regression: `[{text: "TODAY"}]` → `dailyCount: 1` not `2`.

---

### 4. Title crop height — `infoHeight * 7` → `* 4` (`fa0cf8e`)

**File:** `frontend/src/core/implementations/wasm/processing/ocr.canvas.ts`

The title crop region was 7× the info text height, causing it to extend below the app title and pick up unrelated text. Rust uses `info.h * 4`.

---

### 5. `findRightAnchor` — identical to left anchor bug (`dca1d2f`)

Same nested-loop pattern as bug #1, applied independently to the right anchor. Fixed separately after the left anchor fix was committed.

---

## Test Infrastructure Changes

### New test files

| File | Tests | What it covers |
|------|-------|----------------|
| `processing/__tests__/gridDetection.test.ts` | 14 | `computeLeftAnchorCoords`, `computeRightAnchorCoords` — all fallback paths + regressions |
| `processing/__tests__/lineBasedDetection.test.ts` | 10 | `selectBoundaryClusters` — boundary-nearest selection + regressions |
| `processing/__tests__/ocr.test.ts` | 11 | `classifyPageWords` — per-word counting, case-insensitivity, regressions |
| `processing/__tests__/rustParity.test.ts` | 44 | Locks exact Rust golden values (hourly values, totals, grid bounds, alignment scores) for all 4 fixture images |
| `preprocessing/__tests__/recentConfigHelpers.test.ts` | 24 | Pre-existing; was 9 failing, now all pass |

**Total:** 103 tests, 0 fail, 0 skip.

### Exported pure helpers (for testability)

- `computeLeftAnchorCoords(x, y, h, lineRow, movingIndex, lineCol, vMovingIndex)` — `gridDetection.canvas.ts`
- `computeRightAnchorCoords(x, y, lineRow, movingIndex, lineCol, vMovingIndex)` — `gridDetection.canvas.ts`
- `selectBoundaryClusters(clusters, xStart, xEnd)` — `lineBasedDetection.canvas.ts`
- `classifyPageWords(words)` — `ocr.canvas.ts`

These are pure coordinate/classification functions with no canvas or Tesseract dependency — they can be `import`ed and tested in any bun/node environment.

### `bun test` scoping fixed

`bun test` previously picked up all 29 Playwright `.spec.ts` files in `frontend/tests/` and failed immediately. Fixed by:
- `bunfig.toml` at repo root: `root = "./frontend/src"`
- `bunfig.toml` in `frontend/`: `root = "./src"`
- `package.json` scripts updated: `"test": "bun test src/"`, `"test:watch": "bun test src/ --watch"`

Playwright tests remain run via `bun run test:e2e` (unchanged).

### TypeScript errors fixed (pre-existing)

- `imageProcessor.worker.emscripten.ts:83` — `exactOptionalPropertyTypes` violation: spread conditional properties instead of passing `{ prop: T | undefined }`
- `tauri.ts:14` — `invoke<T>()` type argument on an `any`-typed import: moved to return-value cast

`bun run tsc --noEmit` now exits clean.

---

## Rust Golden Snapshots (reference values)

Located in `crates/processing/tests/snapshots/`. Regenerate with:
```
UPDATE_GOLDEN=1 cargo test --test golden_pipeline --no-default-features
```

| Image | Hourly values (non-zero hours) | Total | Grid bounds (UL→LR) |
|-------|-------------------------------|-------|---------------------|
| IMG_0806 | h17=15, h18=37, h19=24, h20=11, h21=3 | 90 | (83,811)→(721,991) |
| IMG_0807 | h17=13, h18=37 | 50 | (83,394)→(721,574) |
| IMG_0808 | h19=22, h20=10 | 32 | (84,394)→(722,574) |
| IMG_0809 | h19=1 | 1 | (84,394)→(722,574) |

All fixtures: `detection_method: "line_based"`, `is_daily_total: false`, alignment score > 0.95.

---

## What Was Verified Equivalent (no code changes needed)

After full sweep of all canvas modules against their Rust counterparts:

| Module | Verdict |
|--------|---------|
| `barExtraction.canvas.ts` | Equivalent — top-down counter-reset ≡ Rust bottom-up last-white scan |
| `imageUtils.canvas.ts` | Equivalent — `removeAllBut` uses sqrt vs squared distance (mathematically identical for comparisons), `darkenNonWhite`/`adjustContrastBrightness`/`isClose`/`reduceColorCount` all match |
| `boundaryOptimizer.canvas.ts` | Equivalent — `computeBarTotalDirect` ≡ `compute_bar_total_from_scaled`, `preprocessForExtraction` ≡ `preprocess_for_optimizer`; `maxShift` defaults to 5 so optimizer runs on every image |

---

## What Full WASM End-to-End Parity Requires

The pure algorithmic helpers above are unit-tested. Full pixel-level parity — running the TS pipeline on the actual fixture PNG files and comparing hourly values to the Rust golden snapshots — requires a browser canvas context and is covered by the Playwright WASM smoke tests in `frontend/tests/wasm-smoke.spec.ts`.

To run those:
```bash
cd frontend
bun run test:e2e tests/wasm-smoke.spec.ts
```
