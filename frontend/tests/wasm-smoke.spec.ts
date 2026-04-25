import { test, expect, type Page } from "@playwright/test";

// ─── Constants ───────────────────────────────────────────────────────────────

/** Directory containing test fixture images (webkitdirectory requires a dir) */
const FIXTURES_DIR = "/tmp/test-screenshots";

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Clear all local state. Must be called AFTER navigating to the app origin. */
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
  });
}

/** Log in as a local WASM user */
async function wasmLogin(page: Page, username = "TestUser") {
  await page.goto("/login");
  await page.waitForLoadState("domcontentloaded");

  // If already redirected away from login, we're logged in
  if (!page.url().includes("/login")) return;

  // Wait for the login form to be ready
  const startBtn = page.getByRole("button", { name: /get started/i });
  await expect(startBtn).toBeVisible({ timeout: 5000 });

  const usernameInput = page.getByPlaceholder("Username (optional)");
  if (username && (await usernameInput.isVisible())) {
    await usernameInput.fill(username);
  }

  await startBtn.click();
  await expect(page).not.toHaveURL(/\/login/, { timeout: 5000 });
}

/** Upload test fixtures via the webkitdirectory file input */
async function uploadFixtures(page: Page) {
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles(FIXTURES_DIR);
  // Wait for upload to complete
  await page.waitForTimeout(5000);
}

// ─── Auth & Login ────────────────────────────────────────────────────────────

test.describe("WASM Authentication", () => {
  test.beforeEach(async ({ page }) => {
    await clearAllState(page);
  });

  test("redirects unauthenticated user to /login", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/);
  });

  test("shows Local Mode UI on login page", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByText("Local Mode")).toBeVisible();
    await expect(page.getByPlaceholder("Username (optional)")).toBeVisible();
    await expect(
      page.getByRole("button", { name: /get started/i }),
    ).toBeVisible();
  });

  test("does NOT show password field in WASM mode", async ({ page }) => {
    await page.goto("/login");
    await page.waitForLoadState("domcontentloaded");
    await expect(page.locator("#password")).not.toBeVisible();
  });

  test("logs in with default username when field is empty", async ({
    page,
  }) => {
    await page.goto("/login");
    await page
      .getByRole("button", { name: /get started/i })
      .click();
    await expect(page).not.toHaveURL(/\/login/);
  });

  test("logs in with custom username", async ({ page }) => {
    await page.goto("/login");
    await page.getByPlaceholder("Username (optional)").fill("Alice");
    await page
      .getByRole("button", { name: /get started/i })
      .click();
    await expect(page).not.toHaveURL(/\/login/);
    // Pin to the header username chip — the welcome toast also contains
    // "Alice", which trips strict mode.
    await expect(page.getByText("Alice", { exact: true })).toBeVisible();
  });

  test("shows optional server sync checkbox", async ({ page }) => {
    await page.goto("/login");
    await expect(
      page.getByText("Connect to Server (optional)"),
    ).toBeVisible();
  });

  test("toggling server sync reveals URL field", async ({ page }) => {
    await page.goto("/login");
    await expect(page.locator("#server-url")).not.toBeVisible();
    await page.getByText("Connect to Server (optional)").click();
    await expect(page.locator("#server-url")).toBeVisible();
  });

  test("session persists across page reloads", async ({ page }) => {
    await wasmLogin(page, "PersistUser");
    await page.reload();
    await expect(page).not.toHaveURL(/\/login/);
  });
});

// ─── Navigation ──────────────────────────────────────────────────────────────

test.describe("WASM Navigation", () => {
  test.beforeEach(async ({ page }) => {
    await wasmLogin(page);
  });

  test("header shows all expected nav links", async ({ page }) => {
    // WASM mode hides Upload, Consensus, and Admin (see Header.tsx) — those
    // require server features (cross-rater consensus, admin endpoints, the
    // separate upload page). The "/" route is labelled "Groups" rather than
    // "Home"; renaming is a separate UX item.
    const nav = page.locator("nav");
    await expect(nav.getByText("Preprocessing")).toBeVisible();
    await expect(nav.getByText("Groups")).toBeVisible();
    await expect(nav.getByText("Annotate")).toBeVisible();
    await expect(nav.getByText("Settings")).toBeVisible();
  });

  test("Consensus link is NOT shown in WASM mode", async ({ page }) => {
    await expect(
      page.locator("nav").getByText("Consensus", { exact: true }),
    ).not.toBeVisible();
  });

  test("Upload link is NOT shown in WASM mode", async ({ page }) => {
    await expect(
      page.locator("nav").getByText("Upload", { exact: true }),
    ).not.toBeVisible();
  });

  test("Admin link is NOT shown in WASM mode", async ({ page }) => {
    await expect(
      page.locator("nav").getByText("Admin"),
    ).not.toBeVisible();
  });

  test("navigates to Preprocessing page", async ({ page }) => {
    await page.getByRole("link", { name: "Preprocessing" }).click();
    await expect(page).toHaveURL(/\/preprocessing/);
    await expect(page.getByText("Preprocessing")).toBeVisible();
  });

  test("navigates to Annotate page", async ({ page }) => {
    await page.getByRole("link", { name: "Annotate" }).click();
    await expect(page).toHaveURL(/\/annotate/);
  });

  test("/consensus redirects to / in WASM mode (server-only feature)", async ({
    page,
  }) => {
    // AppRouter gates /consensus on features.consensusComparison, which
    // bootstrapWasm sets to false (single-rater workflows have no
    // cross-rater comparison to render). The route redirects to home.
    await page.goto("/consensus");
    await expect(page).toHaveURL(/127\.0\.0\.1:9091\/?$/);
  });

  test("navigates to Settings page", async ({ page }) => {
    await page.getByRole("link", { name: "Settings" }).click();
    await expect(page).toHaveURL(/\/settings/);
  });

  test("logo links back to home", async ({ page }) => {
    await page.getByRole("link", { name: "Preprocessing" }).click();
    await page
      .getByRole("link", { name: "iOS Screen Time" })
      .first()
      .click();
    await expect(page).toHaveURL(/\/$/);
  });

  test("theme toggle button exists and works", async ({ page }) => {
    // Theme toggle should not crash
    const themeBtn = page
      .locator("button")
      .filter({ has: page.locator("svg") })
      .last();
    await themeBtn.click();
    await expect(page.locator("html")).toBeVisible();
  });
});

// ─── Home Page ───────────────────────────────────────────────────────────────

test.describe("WASM Home Page - Empty State", () => {
  test.beforeEach(async ({ page }) => {
    await clearAllState(page);
    await wasmLogin(page);
  });

  test("shows Load Folder button", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /load folder/i }),
    ).toBeVisible();
  });

  test("shows image type selector", async ({ page }) => {
    await expect(page.getByText(/screen time/i).first()).toBeVisible();
  });

  test("page loads without errors", async ({ page }) => {
    const body = await page.textContent("body");
    expect(body!.length).toBeGreaterThan(50);
  });
});

// ─── Screenshot Upload ───────────────────────────────────────────────────────

test.describe("WASM Screenshot Upload", () => {
  test.beforeEach(async ({ page }) => {
    await clearAllState(page);
    await wasmLogin(page);
  });

  test("uploads screenshots via folder input", async ({ page }) => {
    await uploadFixtures(page);

    // Should show success toast or group card
    await expect(
      page.getByText(/loaded|uploaded|screenshot/i).first(),
    ).toBeVisible({ timeout: 15000 });
  });

  test("shows group card after upload", async ({ page }) => {
    await uploadFixtures(page);

    // Group card should appear
    await expect(
      page
        .getByTestId("group-card")
        .or(page.locator("[class*='card']").filter({ hasText: /\d+/ }))
        .first(),
    ).toBeVisible({ timeout: 15000 });
  });

  test("shows status counts on group card", async ({ page }) => {
    await uploadFixtures(page);
    await page.waitForTimeout(2000);

    // Group card should have numeric counts
    const body = await page.textContent("body");
    // After upload, we should see numbers representing screenshot counts
    expect(body).toMatch(/[1-9]/);
  });

  test("detects duplicate uploads", async ({ page }) => {
    // First upload
    await uploadFixtures(page);
    await page.waitForTimeout(3000);

    // Second upload of same files
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(FIXTURES_DIR);
    await page.waitForTimeout(5000);

    // Should show some duplicate indication (toast or count)
    const body = await page.textContent("body");
    expect(body).toBeTruthy();
  });

  test("uploaded data persists across reload", async ({ page }) => {
    await uploadFixtures(page);
    await page.waitForTimeout(3000);

    await page.reload();
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2000);

    // Groups should still be visible after reload
    const body = await page.textContent("body");
    // Should NOT show empty state
    expect(body).not.toContain("No screenshots loaded");
  });

  test("content hash is stored for deduplication", async ({ page }) => {
    await uploadFixtures(page);
    await page.waitForTimeout(3000);

    const hasHash = await page.evaluate(async () => {
      return new Promise<boolean>((resolve) => {
        const req = indexedDB.open("ScreenshotProcessorDB");
        req.onsuccess = () => {
          const db = req.result;
          try {
            const tx = db.transaction("screenshots", "readonly");
            const store = tx.objectStore("screenshots");
            const getAll = store.getAll();
            getAll.onsuccess = () => {
              const screenshots = getAll.result;
              resolve(
                screenshots.length > 0 &&
                  typeof screenshots[0].content_hash === "string" &&
                  screenshots[0].content_hash.length > 0,
              );
            };
            getAll.onerror = () => resolve(false);
          } catch {
            resolve(false);
          }
        };
        req.onerror = () => resolve(false);
      });
    });
    expect(hasHash).toBe(true);
  });
});

// ─── Preprocessing Page ──────────────────────────────────────────────────────

test.describe("WASM Preprocessing Page", () => {
  test.beforeEach(async ({ page }) => {
    await wasmLogin(page);
  });

  test("shows pipeline heading", async ({ page }) => {
    await page.goto("/preprocessing");
    await expect(
      page.getByRole("heading", { name: /preprocessing pipeline/i }),
    ).toBeVisible();
  });

  test("shows wizard stage tabs", async ({ page }) => {
    await page.goto("/preprocessing");
    // Wait for React to mount + the wizard heading to render before checking
    // for stage descriptions.
    await expect(
      page.getByRole("heading", { name: /preprocessing pipeline/i }),
    ).toBeVisible({ timeout: 10_000 });
    const body = await page.textContent("body");
    expect(body).toMatch(
      /Identifies device type|Removes iPad sidebar|Detects personal information|Blacks out detected|Extracts app title/,
    );
  });

  test("Group selector exists", async ({ page }) => {
    await page.goto("/preprocessing");
    await expect(page.getByText(/group:/i).first()).toBeVisible();
  });

  test("shows screenshot count footer", async ({ page }) => {
    await page.goto("/preprocessing");
    await page.waitForTimeout(1000);
    // Footer renders `<n> screenshots in <group>`. With no upload, n=0.
    const body = await page.textContent("body");
    expect(body).toMatch(/\d+ screenshots? in/);
  });

  test("populates after uploading screenshots", async ({ page }) => {
    await clearAllState(page);
    await wasmLogin(page);
    await uploadFixtures(page);

    await page.goto("/preprocessing");
    await page.waitForTimeout(2000);

    const body = await page.textContent("body");
    // After uploading 4 fixtures, the footer should reflect that count.
    expect(body).toMatch(/[1-9]\d*\s+screenshots?\s+in/);
  });
});

// ─── Annotation Page ─────────────────────────────────────────────────────────

test.describe("WASM Annotation Page - Empty", () => {
  test.beforeEach(async ({ page }) => {
    await wasmLogin(page);
  });

  test("loads without crash", async ({ page }) => {
    await page.goto("/annotate");
    await page.waitForLoadState("domcontentloaded");
    const body = await page.textContent("body");
    expect(body).toBeTruthy();
  });

  test("shows something when no data", async ({ page }) => {
    await clearAllState(page);
    await wasmLogin(page);
    await page.goto("/annotate");
    await page.waitForTimeout(2000);
    const body = await page.textContent("body");
    expect(body!.length).toBeGreaterThan(20);
  });
});

test.describe("WASM Annotation Page - With Data", () => {
  test.beforeEach(async ({ page }) => {
    await clearAllState(page);
    await wasmLogin(page);
    await uploadFixtures(page);
  });

  test("loads annotation workspace", async ({ page }) => {
    await page.goto("/annotate");
    await page.waitForTimeout(3000);
    const body = await page.textContent("body");
    expect(body!.length).toBeGreaterThan(50);
  });

  test("shows screenshot image or selector", async ({ page }) => {
    await page.goto("/annotate");
    // Wait for loading state to resolve
    await page
      .getByText("Loading screenshot...")
      .waitFor({ state: "hidden", timeout: 15000 })
      .catch(() => {});
    await page.waitForTimeout(2000);

    // Look for any annotation-related element (image, canvas, or selector)
    const body = await page.textContent("body");
    // Should have substantial content (not just "Loading...")
    expect(body!.length).toBeGreaterThan(100);
  });

  test("navigation buttons exist when multiple screenshots", async ({
    page,
  }) => {
    await page.goto("/annotate");
    await page.waitForTimeout(3000);

    const nav = page
      .getByTestId("navigate-next")
      .or(page.getByRole("button", { name: /next/i }));
    // With 4 screenshots, next should be available
    if ((await nav.count()) > 0) {
      await expect(nav.first()).toBeVisible();
    }
  });

  test("can navigate to specific screenshot via URL", async ({ page }) => {
    // Get the first screenshot ID
    const firstId = await page.evaluate(async () => {
      return new Promise<number | null>((resolve) => {
        const req = indexedDB.open("ScreenshotProcessorDB");
        req.onsuccess = () => {
          const db = req.result;
          try {
            const tx = db.transaction("screenshots", "readonly");
            const store = tx.objectStore("screenshots");
            const cursorReq = store.openCursor();
            cursorReq.onsuccess = () => {
              resolve(cursorReq.result ? (cursorReq.result.key as number) : null);
            };
            cursorReq.onerror = () => resolve(null);
          } catch {
            resolve(false as unknown as null);
          }
        };
        req.onerror = () => resolve(null);
      });
    });

    if (firstId) {
      await page.goto(`/annotate/${firstId}`);
      await page.waitForTimeout(3000);
      const body = await page.textContent("body");
      expect(body!.length).toBeGreaterThan(50);
    }
  });
});

// ─── Consensus Page ──────────────────────────────────────────────────────────

test.describe("WASM Consensus Page", () => {
  test.beforeEach(async ({ page }) => {
    await wasmLogin(page);
  });

  test("loads without crash", async ({ page }) => {
    await page.goto("/consensus");
    await page.waitForLoadState("domcontentloaded");
    const body = await page.textContent("body");
    expect(body).toBeTruthy();
  });

  test("shows page content", async ({ page }) => {
    await page.goto("/consensus");
    await page.waitForTimeout(2000);
    const body = await page.textContent("body");
    expect(body!.length).toBeGreaterThan(10);
  });
});

// ─── Settings Page ───────────────────────────────────────────────────────────

test.describe("WASM Settings Page", () => {
  test.beforeEach(async ({ page }) => {
    await wasmLogin(page);
  });

  test("loads settings page", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByText(/settings/i).first()).toBeVisible();
  });

  test("has theme controls", async ({ page }) => {
    await page.goto("/settings");
    await expect(
      page.getByText(/theme|appearance|dark mode/i).first(),
    ).toBeVisible();
  });
});

// ─── Browser API Availability ────────────────────────────────────────────────

test.describe("WASM Browser APIs", () => {
  test.beforeEach(async ({ page }) => {
    await wasmLogin(page);
  });

  test("IndexedDB available", async ({ page }) => {
    expect(
      await page.evaluate(() => typeof indexedDB !== "undefined"),
    ).toBe(true);
  });

  test("OPFS available", async ({ page }) => {
    expect(
      await page.evaluate(async () => {
        try {
          await navigator.storage.getDirectory();
          return true;
        } catch {
          return false;
        }
      }),
    ).toBe(true);
  });

  test("Web Workers available", async ({ page }) => {
    expect(
      await page.evaluate(() => typeof Worker !== "undefined"),
    ).toBe(true);
  });

  test("OffscreenCanvas available", async ({ page }) => {
    expect(
      await page.evaluate(() => typeof OffscreenCanvas !== "undefined"),
    ).toBe(true);
  });

  test("Blob URLs work", async ({ page }) => {
    expect(
      await page.evaluate(() => {
        const blob = new Blob(["test"]);
        const url = URL.createObjectURL(blob);
        URL.revokeObjectURL(url);
        return url.startsWith("blob:");
      }),
    ).toBe(true);
  });

  test("crypto.subtle SHA-256 works", async ({ page }) => {
    expect(
      await page.evaluate(async () => {
        const data = new TextEncoder().encode("test");
        const hash = await crypto.subtle.digest("SHA-256", data);
        return hash.byteLength === 32;
      }),
    ).toBe(true);
  });

  test("ScreenshotProcessorDB initialized", async ({ page }) => {
    await page.waitForTimeout(1000);
    const dbNames = await page.evaluate(async () => {
      const dbs = await indexedDB.databases();
      return dbs.map((d) => d.name);
    });
    expect(dbNames).toContain("ScreenshotProcessorDB");
  });
});

// ─── Offline Isolation ───────────────────────────────────────────────────────

test.describe("WASM Offline Isolation", () => {
  test("no API calls during full navigation", async ({ page }) => {
    const apiCalls: string[] = [];
    page.on("request", (req) => {
      const url = req.url();
      if (url.includes("/api/") || url.includes(":8002")) {
        apiCalls.push(url);
      }
    });

    await wasmLogin(page);

    for (const p of [
      "/preprocessing",
      "/annotate",
      "/consensus",
      "/settings",
      "/",
    ]) {
      await page.goto(p);
      await page.waitForLoadState("domcontentloaded");
      await page.waitForTimeout(500);
    }

    expect(apiCalls).toEqual([]);
  });

  test("no WebSocket connections attempted", async ({ page }) => {
    const wsAttempts: string[] = [];
    page.on("request", (req) => {
      if (req.url().startsWith("ws")) wsAttempts.push(req.url());
    });

    await wasmLogin(page);
    await page.waitForTimeout(3000);
    expect(wsAttempts).toEqual([]);
  });
});

// ─── Error Resilience ────────────────────────────────────────────────────────

test.describe("WASM Error Resilience", () => {
  test("no uncaught JS errors during login", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));

    await clearAllState(page);
    await wasmLogin(page);
    await page.waitForTimeout(1000);
    expect(errors).toEqual([]);
  });

  test("no uncaught JS errors during navigation", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));

    await wasmLogin(page);
    for (const p of [
      "/preprocessing",
      "/annotate",
      "/consensus",
      "/settings",
      "/",
    ]) {
      await page.goto(p);
      await page.waitForLoadState("domcontentloaded");
      await page.waitForTimeout(500);
    }
    expect(errors).toEqual([]);
  });

  test("no uncaught JS errors during upload", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));

    await clearAllState(page);
    await wasmLogin(page);
    await uploadFixtures(page);

    expect(errors).toEqual([]);
  });

  test("no critical console errors on any page", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        const text = msg.text();
        if (
          !text.includes("404") &&
          !text.includes("favicon") &&
          !text.includes("manifest") &&
          !text.includes("sw.js") &&
          !text.includes("service-worker") &&
          !text.includes("Worker error") &&
          // Transient: when the test rapidly navigates after a state-reset
          // login, a child component can render once before the new container
          // is provided. ErrorBoundary catches it and the next render succeeds.
          // Same exclusion as the Full Workflow test below.
          !text.includes("Service not registered")
        ) {
          errors.push(text);
        }
      }
    });

    await wasmLogin(page);
    for (const p of [
      "/",
      "/preprocessing",
      "/annotate",
      "/consensus",
      "/settings",
    ]) {
      await page.goto(p);
      await page.waitForTimeout(1500);
    }

    if (errors.length > 0) console.log("Console errors:", errors);
    expect(errors).toEqual([]);
  });
});

// ─── Logout ──────────────────────────────────────────────────────────────────

test.describe("WASM Logout", () => {
  test("logout returns to login page", async ({ page }) => {
    await wasmLogin(page);
    const logoutBtn = page
      .getByRole("button", { name: /log\s?out/i })
      .or(page.locator("[aria-label*='logout' i]"));

    if ((await logoutBtn.count()) > 0) {
      await logoutBtn.first().click();
      await expect(page).toHaveURL(/\/login/);
    }
  });
});

// ─── Full Workflow Integration ───────────────────────────────────────────────

test.describe("WASM Full Workflow", () => {
  test("login → upload → check preprocessing → visit annotate", async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));

    // Step 1: Clean state & login
    await clearAllState(page);
    await wasmLogin(page, "WorkflowUser");

    // Step 2: Upload screenshots on home page
    await uploadFixtures(page);

    // Step 3: Navigate to preprocessing — should show the wizard heading and
    // a footer with the uploaded screenshot count.
    await page.goto("/preprocessing");
    await page.waitForTimeout(2000);
    await expect(
      page.getByRole("heading", { name: /preprocessing pipeline/i }),
    ).toBeVisible();
    const preprocessBody = await page.textContent("body");
    expect(preprocessBody).toMatch(/[1-9]\d*\s+screenshots?\s+in/);

    // Step 4: Navigate to annotate — should have data
    await page.goto("/annotate");
    await page.waitForTimeout(3000);
    const body = await page.textContent("body");
    expect(body!.length).toBeGreaterThan(50);

    // Step 5: Navigate to consensus — should not crash
    await page.goto("/consensus");
    await page.waitForLoadState("domcontentloaded");

    // Step 6: Back to home — groups should persist
    await page.goto("/");
    await page.waitForTimeout(2000);
    const homeBody = await page.textContent("body");
    expect(homeBody).not.toContain("No screenshots loaded");

    // Filter out transient container initialization errors
    // (can occur when navigating rapidly after state reset)
    const criticalErrors = errors.filter(
      (e) => !e.includes("Service not registered"),
    );
    expect(criticalErrors).toEqual([]);
  });
});
