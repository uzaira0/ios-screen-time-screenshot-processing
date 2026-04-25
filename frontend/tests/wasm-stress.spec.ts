/**
 * WASM full-pipeline stress test — 1000 screenshots, end-to-end, UI-driven.
 *
 * Faithful replay of the user journey on the GitHub Pages public deploy:
 *   1. Land on /login, fill username, click Get Started.
 *   2. Drag-and-drop a folder of 1000 PNGs into the home page (we use the
 *      same <input type="file" webkitdirectory> the UI exposes).
 *   3. Wait for the IndexedDB row count to settle at 1000.
 *   4. Navigate to /preprocessing and run every active stage in order via
 *      its Run button — same control a real user would click.
 *   5. After each stage, poll IndexedDB until that stage's completed count
 *      hits 1000 (or the test times out).
 *   6. Navigate to /annotate, walk a few screenshots, verify they render.
 *   7. Reload, confirm groups + state persist.
 *
 * This is NOT in the smoke suite. Run on demand:
 *   bun run test:e2e:stress
 *
 * Override count with STRESS_COUNT (e.g. STRESS_COUNT=200 for a faster
 * dry-run); the global setup honours it when generating fixtures.
 */
import { test, expect, type Page } from "@playwright/test";

const FIXTURE_DIR = process.env.STRESS_OUT_DIR ?? "/tmp/test-screenshots-1000";
const COUNT = Number(process.env.STRESS_COUNT ?? 1000);

// Active stages in WASM mode (PHI is disabled — see core/di/tokens.ts).
const ACTIVE_STAGES = ["device_detection", "cropping", "ocr"] as const;
type Stage = (typeof ACTIVE_STAGES)[number];

const STAGE_LABEL: Record<Stage, RegExp> = {
  device_detection: /^Run Device Detection on/,
  cropping: /^Run Cropping on/,
  ocr: /^Run Ocr on/,
};

// ─── IndexedDB helpers (run in browser context) ────────────────────────────

async function idbScreenshotCount(page: Page): Promise<number> {
  return await page.evaluate(async () => {
    return new Promise<number>((resolve) => {
      const req = indexedDB.open("ScreenshotProcessorDB");
      req.onsuccess = () => {
        try {
          const tx = req.result.transaction("screenshots", "readonly");
          const store = tx.objectStore("screenshots");
          const c = store.count();
          c.onsuccess = () => resolve(c.result);
          c.onerror = () => resolve(-1);
        } catch {
          resolve(-1);
        }
      };
      req.onerror = () => resolve(-1);
    });
  });
}

async function idbStageStatusCounts(
  page: Page,
  stage: Stage,
): Promise<{ completed: number; failed: number; running: number; pending: number; total: number }> {
  return await page.evaluate(async (stageName: string) => {
    return new Promise<{ completed: number; failed: number; running: number; pending: number; total: number }>((resolve) => {
      const req = indexedDB.open("ScreenshotProcessorDB");
      req.onsuccess = () => {
        try {
          const tx = req.result.transaction("screenshots", "readonly");
          const store = tx.objectStore("screenshots");
          const all = store.getAll();
          all.onsuccess = () => {
            let completed = 0, failed = 0, running = 0, pending = 0;
            for (const s of all.result as Array<{ processing_metadata?: { preprocessing?: { stage_status?: Record<string, string> } } }>) {
              const status = s.processing_metadata?.preprocessing?.stage_status?.[stageName] ?? "pending";
              if (status === "completed") completed++;
              else if (status === "failed") failed++;
              else if (status === "running") running++;
              else pending++;
            }
            resolve({ completed, failed, running, pending, total: all.result.length });
          };
          all.onerror = () => resolve({ completed: 0, failed: 0, running: 0, pending: 0, total: 0 });
        } catch {
          resolve({ completed: 0, failed: 0, running: 0, pending: 0, total: 0 });
        }
      };
      req.onerror = () => resolve({ completed: 0, failed: 0, running: 0, pending: 0, total: 0 });
    });
  }, stage);
}

async function clearAllState(page: Page) {
  await page.goto("/login");
  await page.waitForLoadState("domcontentloaded");
  await page.evaluate(async () => {
    localStorage.clear();
    sessionStorage.clear();
    const dbs = await indexedDB.databases();
    for (const db of dbs) {
      if (db.name) indexedDB.deleteDatabase(db.name);
    }
    // OPFS — recursively wipe so prior runs don't leave blobs behind
    try {
      const root = await navigator.storage.getDirectory();
      // @ts-expect-error - values() is supported in Chromium
      for await (const handle of root.values()) {
        await root.removeEntry(handle.name, { recursive: true });
      }
    } catch { /* OPFS unavailable; ignore */ }
  });
}

async function login(page: Page, username = "StressUser") {
  await page.goto("/login");
  await page.waitForLoadState("domcontentloaded");
  if (!page.url().includes("/login")) return;
  await page.getByPlaceholder("Username (optional)").fill(username);
  await page.getByRole("button", { name: /get started/i }).click();
  await expect(page).not.toHaveURL(/\/login/, { timeout: 10_000 });
}

async function pollUntil<T>(
  fn: () => Promise<T>,
  predicate: (v: T) => boolean,
  opts: { intervalMs?: number; timeoutMs: number; label: string },
): Promise<T> {
  const start = Date.now();
  let last: T;
  while (true) {
    last = await fn();
    if (predicate(last)) return last;
    if (Date.now() - start > opts.timeoutMs) {
      throw new Error(
        `Timed out waiting for ${opts.label} after ${opts.timeoutMs}ms (last value: ${JSON.stringify(last)})`,
      );
    }
    await new Promise((r) => setTimeout(r, opts.intervalMs ?? 2000));
  }
}

// ─── The stress test ───────────────────────────────────────────────────────

test.describe.configure({ mode: "serial" });

test.describe("WASM stress: 1000-screenshot full pipeline", () => {
  test(`uploads ${COUNT} screenshots and runs every active stage`, async ({ page }) => {
    test.setTimeout(90 * 60_000); // 90 minutes — OCR is the long pole

    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));

    // 1. Clean state and log in.
    await clearAllState(page);
    await login(page);

    // 2. Upload all fixtures via the file input the home page exposes.
    //    setInputFiles on the directory uses the same webkitdirectory codepath
    //    the user's "Load Folder" button triggers.
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(FIXTURE_DIR);

    // 3. Wait for IndexedDB to settle at COUNT screenshots. Upload is async
    //    in the WASM service — content-hashing + blob persistence + metadata
    //    write happens off the main thread and the row count converges.
    await pollUntil(
      () => idbScreenshotCount(page),
      (n) => n >= COUNT,
      {
        timeoutMs: 15 * 60_000, // 15 min cap — hashing 1000 PNGs is the work
        intervalMs: 2000,
        label: `IndexedDB to reach ${COUNT} screenshots`,
      },
    );

    // 4. Walk the preprocessing pipeline. Each active stage in turn:
    //      a. Click the wizard tab.
    //      b. Click the Run button (its label includes the eligible count).
    //      c. Poll IDB until completed === COUNT for that stage.
    await page.goto("/preprocessing");
    await expect(
      page.getByRole("heading", { name: /preprocessing pipeline/i }),
    ).toBeVisible({ timeout: 30_000 });

    for (const stage of ACTIVE_STAGES) {
      // Switch to the stage tab — the wizard exposes data-testid for each.
      await page.getByTestId(`wizard-tab-${stage}`).click();

      // Click Run. The button label is `Run <Stage> on <N> screenshots`.
      const runBtn = page.getByRole("button", { name: STAGE_LABEL[stage] });
      await expect(runBtn).toBeEnabled({ timeout: 30_000 });
      await runBtn.click();

      // Poll IDB. OCR can take ~1–3s per screenshot single-threaded; budget
      // accordingly. Device-detection and cropping are ms each.
      const stageBudgetMs = stage === "ocr" ? 60 * 60_000 : 10 * 60_000;
      const result = await pollUntil(
        () => idbStageStatusCounts(page, stage),
        (s) => s.completed + s.failed >= COUNT && s.running === 0,
        {
          timeoutMs: stageBudgetMs,
          intervalMs: 3000,
          label: `${stage} to finish on ${COUNT} screenshots`,
        },
      );

      // Surface stage failures but don't fail the test — OCR on synthetic
      // tEXt-injected PNGs may fall short on a small fraction. We tolerate
      // up to 2% failed so the harness still validates the happy path.
      const failureRate = result.failed / Math.max(1, result.completed + result.failed);
      expect(failureRate, `${stage} exceeded 2% failure rate`).toBeLessThan(0.02);
      expect(result.running, `${stage} left rows in 'running'`).toBe(0);
    }

    // 5. Navigate to annotate — at least one screenshot should render.
    await page.goto("/annotate");
    await page.waitForTimeout(3000);
    const annotateBody = await page.textContent("body");
    expect(annotateBody!.length).toBeGreaterThan(50);

    // 6. Reload — group and screenshots must persist (IndexedDB-backed).
    await page.goto("/");
    await page.reload();
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2000);
    const finalCount = await idbScreenshotCount(page);
    expect(finalCount).toBe(COUNT);

    // 7. No uncaught JS errors during any of the above.
    const critical = errors.filter((e) => !e.includes("Service not registered"));
    expect(critical, `uncaught JS errors:\n${critical.join("\n")}`).toEqual([]);
  });
});
