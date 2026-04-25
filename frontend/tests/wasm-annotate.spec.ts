/**
 * WASM annotate-and-export — 50 screenshots through five distinct user paths.
 *
 * Splits the 50 screenshots into 5 cohorts of 10 and exercises a different
 * annotation flow on each:
 *   [0..9]   verify as-is (V key, no edits)
 *   [10..19] edit hour-12 to 30, then verify
 *   [20..29] edit title to "TestApp_<idx>", then verify
 *   [30..39] skip with rotating reasons (duplicate / bad_quality / wrong_type
 *            / daily_total / other)
 *   [40..49] left pending (visited but no action)
 *
 * Then exports CSV from the home page and asserts every cohort's expected
 * fields landed correctly in the file.
 *
 * Each annotation uses the real UI controls — same input the user touches
 * (data-testid="hour-input-12", aria-label="App or title name", V key,
 * Skip dropdown).  No service-layer back-doors.
 *
 * Run on demand:
 *   bun run test:e2e:annotate
 */
import { test, expect, type Page } from "@playwright/test";

const COUNT = Number(process.env.ANNOTATE_COUNT ?? 50);
const FIXTURE_DIR = process.env.ANNOTATE_OUT_DIR ?? "/tmp/test-screenshots-50";

const ACTIVE_STAGES = ["device_detection", "cropping", "ocr"] as const;
type Stage = (typeof ACTIVE_STAGES)[number];
const STAGE_RUN_LABEL: Record<Stage, RegExp> = {
  device_detection: /^Run Device Detection on/,
  cropping: /^Run Cropping on/,
  ocr: /^Run Ocr on/,
};

// Reason key → exact menu label rendered in the AnnotationWorkspace skip
// dropdown (AnnotationWorkspace.tsx:924). Sentence case, not title case.
const SKIP_REASONS: ReadonlyArray<{ key: string; label: string }> = [
  { key: "duplicate", label: "Duplicate" },
  { key: "bad_quality", label: "Bad quality" },
  { key: "wrong_type", label: "Wrong type" },
  { key: "daily_total", label: "Daily total" },
  { key: "other", label: "Other" },
];

// ─── IDB helpers ──────────────────────────────────────────────────────────

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
        } catch { resolve(-1); }
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
        } catch { resolve({ completed: 0, failed: 0, running: 0, pending: 0, total: 0 }); }
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
    for (const db of dbs) if (db.name) indexedDB.deleteDatabase(db.name);
    try {
      const root = await navigator.storage.getDirectory();
      // @ts-expect-error - values() is supported in Chromium
      for await (const handle of root.values()) {
        await root.removeEntry(handle.name, { recursive: true });
      }
    } catch { /* ignore */ }
  });
}

async function login(page: Page, username = "AnnotateUser") {
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
        `Timed out waiting for ${opts.label} after ${opts.timeoutMs}ms (last: ${JSON.stringify(last)})`,
      );
    }
    await new Promise((r) => setTimeout(r, opts.intervalMs ?? 1500));
  }
}

// ─── CSV parsing (handles quoted cells with embedded commas/quotes) ────────

function parseCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i]!;
    if (inQuotes) {
      if (c === '"') {
        if (line[i + 1] === '"') { cur += '"'; i++; }
        else { inQuotes = false; }
      } else { cur += c; }
    } else {
      if (c === '"') inQuotes = true;
      else if (c === ",") { out.push(cur); cur = ""; }
      else { cur += c; }
    }
  }
  out.push(cur);
  return out;
}

function parseCsv(text: string): { headers: string[]; rows: Record<string, string>[] } {
  // Strip UTF-8 BOM
  const stripped = text.charCodeAt(0) === 0xFEFF ? text.slice(1) : text;
  const lines = stripped.split(/\r?\n/).filter((l) => l.length > 0);
  const headers = parseCsvLine(lines[0]!);
  const rows = lines.slice(1).map((line) => {
    const cells = parseCsvLine(line);
    const row: Record<string, string> = {};
    headers.forEach((h, i) => { row[h] = cells[i] ?? ""; });
    return row;
  });
  return { headers, rows };
}

// ─── The spec ───────────────────────────────────────────────────────────────

test.describe.configure({ mode: "serial" });

test.describe("WASM annotate + export: 50 screenshots, 5 user paths", () => {
  test(`annotates ${COUNT} screenshots in 5 ways and exports a CSV`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));

    // 1. Fresh state, login, upload 50 screenshots.
    await clearAllState(page);
    await login(page);
    await page.locator('input[type="file"]').setInputFiles(FIXTURE_DIR);
    await pollUntil(
      () => idbScreenshotCount(page),
      (n) => n >= COUNT,
      { timeoutMs: 5 * 60_000, intervalMs: 1500, label: `IDB to reach ${COUNT}` },
    );

    // 2. Run all active preprocessing stages so each row has OCR data.
    await page.goto("/preprocessing");
    await expect(
      page.getByRole("heading", { name: /preprocessing pipeline/i }),
    ).toBeVisible({ timeout: 30_000 });

    for (const stage of ACTIVE_STAGES) {
      await page.getByTestId(`wizard-tab-${stage}`).click();
      const runBtn = page.getByRole("button", { name: STAGE_RUN_LABEL[stage] });
      await expect(runBtn).toBeEnabled({ timeout: 30_000 });
      await runBtn.click();
      await pollUntil(
        () => idbStageStatusCounts(page, stage),
        (s) => s.completed + s.failed >= COUNT && s.running === 0,
        { timeoutMs: 5 * 60_000, intervalMs: 2000, label: `${stage} to finish` },
      );
    }

    // 3. Sanity-check the upload count.
    const totalUploaded = await idbScreenshotCount(page);
    expect(totalUploaded).toBe(COUNT);

    // 4. Click into the group via the home page — same path a user takes
    //    after their preprocessing run lights up the group card. Total
    //    Screenshots is the broadest entry; it lands on /annotate?group=…
    //    with no processing_status filter so all 50 are reachable.
    await page.goto("/");
    const groupCard = page.getByTestId("group-card").first();
    await expect(groupCard).toBeVisible({ timeout: 30_000 });
    await groupCard.getByTestId("total-screenshots").click();
    await expect(page).toHaveURL(/\/annotate\?/);

    const waitForWorkspace = async () => {
      await page
        .getByText("Loading screenshot...")
        .waitFor({ state: "hidden", timeout: 30_000 })
        .catch(() => { /* may never appear for a hot cache */ });
      await expect(page.getByTestId("annotation-workspace")).toBeVisible({ timeout: 30_000 });
    };
    await waitForWorkspace();

    // Helper — read the current screenshot id from the URL the workspace
    // syncs (/annotate/<id>?group=…) so cohort assertions can map back to
    // exactly the rows the test edited.
    const currentScreenshotId = async (): Promise<number> => {
      const m = page.url().match(/\/annotate\/(\d+)/);
      if (!m) throw new Error(`URL has no screenshot id: ${page.url()}`);
      return Number(m[1]);
    };

    const visitedIds = {
      verifyOnly: [] as number[],
      editHourly: [] as number[],
      editTitle: [] as number[],
      skip: [] as { id: number; reason: string }[],
      pending: [] as number[],
    };

    // 5. Walk 50 positions. V (verify) and the Skip dropdown both
    //    auto-advance the queue; the Pending cohort needs an explicit
    //    navigate-next click. After each action, wait for the URL to
    //    flip to a new screenshot id before the next iteration so the
    //    walk is deterministic regardless of action timing.
    const nextBtn = page.getByTestId("navigate-next");
    const waitForIdChange = async (prevId: number) => {
      await page.waitForFunction(
        (prev) => {
          const m = window.location.pathname.match(/\/annotate\/(\d+)/);
          return m ? Number(m[1]) !== prev : false;
        },
        prevId,
        { timeout: 15_000 },
      );
    };

    for (let walkPos = 0; walkPos < COUNT; walkPos++) {
      await waitForWorkspace();
      const id = await currentScreenshotId();

      if (walkPos < 10) {
        // The Verify guard requires a non-empty App/Title (OCR sometimes
        // doesn't fill this on synthetic fixtures). Set a baseline title
        // so V actually completes the verification — the cohort still
        // represents "verify with no edits to OCR-extracted hourly data".
        visitedIds.verifyOnly.push(id);
        const title = page.getByLabel("App or title name");
        const existing = await title.inputValue().catch(() => "");
        if (!existing || existing.trim().length === 0) {
          await title.fill("VerifyOnly");
          await title.blur();
          await page.waitForTimeout(250);
        }
        await page.keyboard.press("v");
      } else if (walkPos < 20) {
        visitedIds.editHourly.push(id);
        // Same title guard as verify-only — set a baseline if OCR left it empty.
        const titleInput = page.getByLabel("App or title name");
        const existingTitle = await titleInput.inputValue().catch(() => "");
        if (!existingTitle || existingTitle.trim().length === 0) {
          await titleInput.fill("EditHourly");
          await titleInput.blur();
          await page.waitForTimeout(150);
        }
        const hour = page.getByTestId("hour-input-12");
        await expect(hour).toBeVisible();
        await hour.fill("");
        await hour.fill("30");
        await hour.blur();
        await page.waitForTimeout(250);
        await page.keyboard.press("v");
      } else if (walkPos < 30) {
        const idx = walkPos - 20;
        visitedIds.editTitle.push(id);
        const title = page.getByLabel("App or title name");
        await expect(title).toBeVisible();
        await title.fill(`TestApp_${idx}`);
        await title.blur();
        await page.waitForTimeout(250);
        await page.keyboard.press("v");
      } else if (walkPos < 40) {
        const reason = SKIP_REASONS[(walkPos - 30) % SKIP_REASONS.length]!;
        visitedIds.skip.push({ id, reason: reason.key });
        await page.getByRole("button", { name: /skip with reason/i }).click();
        await page.getByRole("button", { name: reason.label, exact: true }).click();
      } else {
        // Pending — no action; the explicit click below moves to next id.
        visitedIds.pending.push(id);
      }

      if (walkPos === COUNT - 1) break; // last iteration

      // Some actions auto-advance (skip always, V conditionally); others
      // don't. Probe the URL — if it already changed, the action advanced.
      // Otherwise click navigate-next ourselves.
      await page.waitForTimeout(400);
      const afterAction = await currentScreenshotId().catch(() => id);
      if (afterAction === id) {
        await expect(nextBtn).toBeEnabled({ timeout: 10_000 });
        await nextBtn.click();
      }
      await waitForIdChange(id);
    }

    expect(visitedIds.verifyOnly.length).toBe(10);
    expect(visitedIds.editHourly.length).toBe(10);
    expect(visitedIds.editTitle.length).toBe(10);
    expect(visitedIds.skip.length).toBe(10);
    expect(visitedIds.pending.length).toBe(10);

    // 5. Export CSV from the home page and pull the file.
    await page.goto("/");
    await expect(page.getByTestId("group-card").first()).toBeVisible({ timeout: 15_000 });
    const downloadPromise = page.waitForEvent("download", { timeout: 60_000 });
    await page.getByRole("button", { name: /export csv/i }).first().click();
    const download = await downloadPromise;
    const csvPath = await download.path();
    expect(csvPath).toBeTruthy();
    const fs = await import("node:fs/promises");
    const csvText = await fs.readFile(csvPath!, "utf8");

    // 6. Sanity-check the file shape: BOM, header, COUNT data rows.
    expect(csvText.charCodeAt(0)).toBe(0xFEFF);
    const { headers, rows } = parseCsv(csvText);
    expect(rows.length).toBe(COUNT);
    expect(headers).toContain("Screenshot ID");
    expect(headers).toContain("Is Verified");
    expect(headers).toContain("Title");
    expect(headers).toContain("Processing Status");
    expect(headers).toContain("Hour 12");
    // The expected hourly columns should all be present.
    for (let h = 0; h < 24; h++) {
      expect(headers).toContain(`Hour ${h}`);
    }

    // 7. Per-cohort assertions on the CSV — uses the ids the test actually
    //    visited, captured at walk time, so they line up regardless of
    //    Dexie key ordering or queue filter quirks.
    const byId = new Map(rows.map((r) => [Number(r["Screenshot ID"]), r]));

    for (const id of visitedIds.verifyOnly) {
      const row = byId.get(id)!;
      expect(row, `missing row for verify-only id ${id}`).toBeDefined();
      expect(row["Is Verified"]).toBe("Yes");
      expect(Number(row["Verified By Count"])).toBeGreaterThanOrEqual(1);
    }

    for (const id of visitedIds.editHourly) {
      const row = byId.get(id)!;
      expect(row["Is Verified"]).toBe("Yes");
      expect(row["Hour 12"]).toBe("30");
    }

    for (let i = 0; i < visitedIds.editTitle.length; i++) {
      const id = visitedIds.editTitle[i]!;
      const row = byId.get(id)!;
      expect(row["Is Verified"]).toBe("Yes");
      expect(row["Title"]).toBe(`TestApp_${i}`);
    }

    for (const { id } of visitedIds.skip) {
      const row = byId.get(id)!;
      expect(row["Processing Status"]).toBe("skipped");
      expect(row["Is Verified"]).toBe("No");
    }

    for (const id of visitedIds.pending) {
      const row = byId.get(id)!;
      expect(row["Is Verified"]).toBe("No");
      expect(row["Processing Status"]).not.toBe("skipped");
    }

    // 8. No uncaught JS errors during the whole journey.
    const critical = errors.filter((e) => !e.includes("Service not registered"));
    expect(critical, `uncaught JS errors:\n${critical.join("\n")}`).toEqual([]);
  });
});
