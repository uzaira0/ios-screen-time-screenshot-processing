import { test, expect } from "@playwright/test";

/**
 * Screenshot Capture Test
 *
 * Captures screenshots of all major pages to analyze the UI layout.
 * Uses the authenticated user from auth.setup.ts
 */
test.describe("Capture Screenshots for Analysis", () => {
  test("capture all major pages", async ({ page }) => {
    // 1. Home page - wait for groups to load
    await page.goto(".");
    await page.waitForLoadState("networkidle");
    // Wait for groups section and data to load
    await page.waitForSelector('[data-testid="groups-section"]', { timeout: 10000 });
    await page.waitForTimeout(2000); // Give time for API to return groups
    await page.screenshot({
      path: "test-results/screenshots/01-home-page.png",
      fullPage: true,
    });

    // 2. Annotation page - wait for workspace or empty state
    await page.goto("annotate");
    await page.waitForLoadState("domcontentloaded");
    // Wait for either workspace or empty state to appear
    await Promise.race([
      page.waitForSelector('[data-testid="annotation-workspace"]', { timeout: 15000 }),
      page.waitForSelector('text="No Screenshots Available"', { timeout: 15000 }),
      page.waitForSelector('text="All Done!"', { timeout: 15000 }),
    ]).catch(() => {});
    await page.waitForTimeout(3000); // Extra time for image to load
    await page.screenshot({
      path: "test-results/screenshots/02-annotation-page.png",
      fullPage: true,
    });

    // Check if we have a workspace with actual image
    const hasWorkspace = await page.getByTestId("annotation-workspace").isVisible().catch(() => false);
    if (hasWorkspace) {
      // Wait for image to load in the grid selector
      await page.waitForTimeout(2000);
      await page.screenshot({
        path: "test-results/screenshots/03-annotation-workspace-detail.png",
        fullPage: true,
      });
    }

    // 4. Settings page
    await page.goto("settings");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);
    await page.screenshot({
      path: "test-results/screenshots/04-settings-page.png",
      fullPage: true,
    });

    // 5. Consensus page
    await page.goto("consensus");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);
    await page.screenshot({
      path: "test-results/screenshots/05-consensus-page.png",
      fullPage: true,
    });

    // 6. Admin page (as testuser - shows access denied)
    await page.goto("admin");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(500);
    await page.screenshot({
      path: "test-results/screenshots/06-admin-access-denied.png",
      fullPage: true,
    });

    console.log("All screenshots captured to test-results/screenshots/");
  });
});
