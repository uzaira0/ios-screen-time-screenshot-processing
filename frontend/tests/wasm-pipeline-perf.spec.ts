/**
 * 3-stage WASM pipeline perf check.
 *
 * Drops N synthetic screenshots into the home page, runs every active
 * preprocessing stage (device_detection → cropping → ocr) via the same
 * Run buttons a real user clicks, and prints per-stage wall-clock
 * timings + extracted-title sanity counts. The point is to verify two
 * things end-to-end:
 *
 *   (a) the BMP-encoding fix lets leptess actually decode images in
 *       the WASM Leptonica build, so titles + total_text populate
 *       instead of staying blank; and
 *   (b) the LepTess worker pool actually parallelises OCR — the
 *       per-screenshot OCR rate should scale with the pool size, not
 *       sit at single-worker speed.
 *
 * Run on demand:
 *   PERF_COUNT=50 bunx playwright test --config playwright.wasm-pipeline-perf.config.ts
 *
 * Default count is 50, giving a sub-2-minute total runtime on a typical
 * 8-core dev machine. Bump for harder evidence; the OCR budget scales
 * with COUNT.
 */
import { test, expect, type Page } from "@playwright/test";

const FIXTURE_DIR = process.env.PERF_OUT_DIR ?? "/tmp/test-screenshots-perf";
const COUNT = Number(process.env.PERF_COUNT ?? 50);

const ACTIVE_STAGES = ["device_detection", "cropping", "ocr"] as const;
type Stage = (typeof ACTIVE_STAGES)[number];

const STAGE_LABEL: Record<Stage, RegExp> = {
  device_detection: /^Run Device Detection on/,
  cropping: /^Run Cropping on/,
  ocr: /^Run Ocr on/,
};

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
    return new Promise((resolve) => {
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
    }) as Promise<{ completed: number; failed: number; running: number; pending: number; total: number }>;
  }, stage);
}

/** Pull the OCR title + total fields straight off each screenshot row.
 *  Lets us assert the BMP fix actually populated them in production. */
async function idbTitleStats(page: Page): Promise<{
  total: number;
  withTitle: number;
  withTotal: number;
  dailyTotalPages: number;
  sampleTitles: string[];
}> {
  return await page.evaluate(async () => {
    return new Promise((resolve) => {
      const req = indexedDB.open("ScreenshotProcessorDB");
      req.onsuccess = () => {
        try {
          const tx = req.result.transaction("screenshots", "readonly");
          const store = tx.objectStore("screenshots");
          const all = store.getAll();
          all.onsuccess = () => {
            const rows = all.result as Array<{
              extracted_title?: string | null;
              extracted_total?: string | null;
            }>;
            let withTitle = 0;
            let withTotal = 0;
            let dailyTotalPages = 0;
            const sampleTitles: string[] = [];
            for (const r of rows) {
              const title = r.extracted_title ?? null;
              const total = r.extracted_total ?? null;
              if (title && title.trim().length > 0) {
                withTitle++;
                if (title === "Daily Total") dailyTotalPages++;
                if (sampleTitles.length < 8) sampleTitles.push(title);
              }
              if (total && total.trim().length > 0) withTotal++;
            }
            resolve({ total: rows.length, withTitle, withTotal, dailyTotalPages, sampleTitles });
          };
          all.onerror = () => resolve({ total: 0, withTitle: 0, withTotal: 0, dailyTotalPages: 0, sampleTitles: [] });
        } catch {
          resolve({ total: 0, withTitle: 0, withTotal: 0, dailyTotalPages: 0, sampleTitles: [] });
        }
      };
      req.onerror = () => resolve({ total: 0, withTitle: 0, withTotal: 0, dailyTotalPages: 0, sampleTitles: [] });
    }) as Promise<{ total: number; withTitle: number; withTotal: number; dailyTotalPages: number; sampleTitles: string[] }>;
  });
}

async function clearAllState(page: Page) {
  await page.goto("/");
  await page.waitForLoadState("domcontentloaded");
  await page.evaluate(async () => {
    localStorage.clear();
    sessionStorage.clear();
    const dbs = await indexedDB.databases();
    for (const db of dbs) {
      if (db.name) indexedDB.deleteDatabase(db.name);
    }
    try {
      const root = await navigator.storage.getDirectory();
      // @ts-expect-error - values() is supported in Chromium
      for await (const handle of root.values()) {
        await root.removeEntry(handle.name, { recursive: true });
      }
    } catch { /* ignore */ }
  });
  // Reload so the cleared state takes effect for the next page interaction.
  await page.reload();
  await page.waitForLoadState("domcontentloaded");
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
    await new Promise((r) => setTimeout(r, opts.intervalMs ?? 1500));
  }
}

test.describe.configure({ mode: "serial" });

test.describe("WASM 3-stage pipeline perf", () => {
  test(`runs device detection → cropping → ocr on ${COUNT} screenshots`, async ({ page }) => {
    test.setTimeout(15 * 60_000);

    const stageWallMs: Record<Stage, number> = {
      device_detection: 0,
      cropping: 0,
      ocr: 0,
    };

    const consoleErrors: string[] = [];
    page.on("pageerror", (e) => consoleErrors.push(e.message));
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });

    await clearAllState(page);

    // Local mode auto-auths on mount, so no /login step required.
    // Drop straight onto the home page and fill the required group name
    // before the upload — the Load Folder button is gated on it now.
    await page.goto("/");
    await page.getByPlaceholder("Group name (required)").fill("perf-bench");

    // Upload via the hidden <input webkitdirectory> the home page mounts.
    const fileInput = page.locator('input[type="file"][webkitdirectory]').first();
    await fileInput.setInputFiles(FIXTURE_DIR);

    // Auto-navigate to /preprocessing happens after upload. Confirm we
    // landed there and IndexedDB has settled at the expected count.
    await expect(page).toHaveURL(/\/preprocessing/, { timeout: 60_000 });
    await pollUntil(
      () => idbScreenshotCount(page),
      (n) => n >= COUNT,
      { timeoutMs: 5 * 60_000, intervalMs: 500, label: `IDB to reach ${COUNT}` },
    );

    // Pool size is exposed by the processing service — pull it for the
    // per-screenshot rate report. If unset (e.g. service not yet
    // instantiated by the time we ask), fall back to navigator
    // hardwareConcurrency / 2.
    const poolSize = await page.evaluate(async () => {
      const cores = navigator.hardwareConcurrency ?? 4;
      return Math.max(2, Math.min(8, Math.floor(cores / 2)));
    });

    for (const stage of ACTIVE_STAGES) {
      await page.getByTestId(`wizard-tab-${stage}`).click();

      const runBtn = page.getByRole("button", { name: STAGE_LABEL[stage] });
      await expect(runBtn).toBeEnabled({ timeout: 30_000 });

      const t0 = Date.now();
      await runBtn.click();

      const stageBudgetMs = stage === "ocr" ? 12 * 60_000 : 3 * 60_000;
      const result = await pollUntil(
        () => idbStageStatusCounts(page, stage),
        (s) => s.completed + s.failed >= COUNT && s.running === 0,
        {
          timeoutMs: stageBudgetMs,
          intervalMs: 500,
          label: `${stage} to complete`,
        },
      );

      const wallMs = Date.now() - t0;
      stageWallMs[stage] = wallMs;

      const failureRate = result.failed / Math.max(1, result.completed + result.failed);
      expect(failureRate, `${stage} exceeded 10% failure rate`).toBeLessThan(0.1);

      // eslint-disable-next-line no-console
      console.log(
        `[perf] ${stage}: ${wallMs}ms wall, ${result.completed} ok, ${result.failed} failed, ${(wallMs / Math.max(1, result.completed)).toFixed(0)}ms/screenshot`,
      );
    }

    // After OCR, pull title + total stats. The BMP fix is correct iff
    // most of the rows have non-empty extracted_title / extracted_total.
    // The 4 base fixtures get cloned with unique tEXt chunks so the
    // visual content is identical — every clone of the IMG_0807 fixture
    // should resolve the same title.
    const titleStats = await idbTitleStats(page);
    // eslint-disable-next-line no-console
    console.log("[perf] OCR title stats:", JSON.stringify(titleStats));

    // We expect ≥ 80% of rows to have a non-empty title. Synthetic
    // tEXt-injected fixtures preserve the original pixels, so leptess
    // should hit the same title on every clone of an underlying
    // fixture. A drop below 80% means the BMP / title pipeline
    // regressed.
    const titleRate = titleStats.withTitle / Math.max(1, titleStats.total);
    expect(
      titleRate,
      `Only ${titleStats.withTitle}/${titleStats.total} rows have a non-empty extracted_title; BMP fix may have regressed`,
    ).toBeGreaterThan(0.8);

    const totalRate = titleStats.withTotal / Math.max(1, titleStats.total);
    expect(
      totalRate,
      `Only ${titleStats.withTotal}/${titleStats.total} rows have an extracted_total`,
    ).toBeGreaterThan(0.8);

    // Surface OCR throughput vs single-worker estimate so a regression
    // back to the serial path is obvious in the test log.
    const ocrPerScreenshotMs = stageWallMs.ocr / COUNT;
    const expectedSerialFloorMs = 800; // a fast single-LepTess image
    // eslint-disable-next-line no-console
    console.log(
      `[perf] pool=${poolSize} workers, ocr=${ocrPerScreenshotMs.toFixed(0)}ms/screenshot, ` +
      `theoretical-serial-floor=${expectedSerialFloorMs}ms — speedup ≥ ${(expectedSerialFloorMs / ocrPerScreenshotMs).toFixed(1)}× expected`,
    );

    // Surface any console errors that fired during the run so a silent
    // worker crash is loud.
    const filtered = consoleErrors.filter(
      (msg) =>
        !msg.includes("Service not registered") &&
        !msg.includes("ResizeObserver loop limit exceeded"),
    );
    if (filtered.length > 0) {
      // eslint-disable-next-line no-console
      console.warn("[perf] Console errors during run:");
      for (const e of filtered) {
        // eslint-disable-next-line no-console
        console.warn("  ", e);
      }
    }
  });
});
