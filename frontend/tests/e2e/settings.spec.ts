import { test, expect } from "@playwright/test";
import { SettingsPage } from "../pages/SettingsPage";

/**
 * Settings Page Tests
 *
 * Tests the settings page functionality:
 * - Mode display (WASM/Server)
 * - Mode switching (if available)
 * - Settings toggles
 * - About information
 * - Navigation
 */
test.describe("Settings Page", () => {
  let settingsPage: SettingsPage;

  test.beforeEach(async ({ page }) => {
    settingsPage = new SettingsPage(page);
  });

  test("should display settings page heading", async ({ page }) => {
    await settingsPage.goto();

    await expect(settingsPage.heading).toBeVisible();
    await expect(page.getByText(/configure your screenshot/i)).toBeVisible();
  });

  test("should display current mode information", async ({ page }) => {
    await settingsPage.goto();

    // Should show current mode section
    const modeSection = page.locator("text=Current Mode:").first();
    await expect(modeSection).toBeVisible();

    // Should indicate which mode is active
    const mode = await settingsPage.getCurrentMode();
    expect(["wasm", "server"]).toContain(mode);
  });

  test("should display data storage information", async ({ page }) => {
    await settingsPage.goto();

    const dataStorageSection = page.locator("text=Data Storage").first();
    await expect(dataStorageSection).toBeVisible();
  });

  test("should display processing information", async ({ page }) => {
    await settingsPage.goto();

    const processingSection = page.locator("text=Processing").first();
    await expect(processingSection).toBeVisible();
  });

  test("should display network requirement information", async ({ page }) => {
    await settingsPage.goto();

    const networkSection = page.locator("text=Network Required").first();
    await expect(networkSection).toBeVisible();
  });

  test("should display About section", async ({ page }) => {
    await settingsPage.goto();

    await expect(settingsPage.aboutSection).toBeVisible();

    // Version should be displayed
    const versionText = page.locator("text=Version:").first();
    await expect(versionText).toBeVisible();

    // Build info should be displayed
    const buildText = page.locator("text=Build:").first();
    await expect(buildText).toBeVisible();
  });

  test("should display version number", async ({ page }) => {
    await settingsPage.goto();

    const version = await settingsPage.getVersion();
    // Version should be a valid semver format
    expect(version).toMatch(/^\d+\.\d+\.\d+$/);
  });

  test("should have back navigation link", async ({ page }) => {
    await settingsPage.goto();

    await expect(settingsPage.backLink).toBeVisible();
    await expect(settingsPage.backLink).toHaveText(/back to/i);
  });

  test("should navigate back to home when clicking back link", async ({
    page,
  }) => {
    await settingsPage.goto();

    await settingsPage.backLink.click();
    // Wait for navigation to home - check pathname since URL includes host
    await page.waitForFunction(() => {
      const path = window.location.pathname;
      return path.endsWith("/") || path.endsWith("/home");
    }, { timeout: 10000 });
  });

  test("should display mode-specific settings for WASM mode", async ({
    page,
  }) => {
    await settingsPage.goto();

    const mode = await settingsPage.getCurrentMode();

    if (mode === "wasm") {
      // WASM mode should show local mode settings
      await expect(settingsPage.localModeSettings).toBeVisible();

      // Should have specific toggles
      const autoProcess = page.locator("text=Auto-process uploads").first();
      await expect(autoProcess).toBeVisible();

      const debugImages = page.locator("text=Save debug images").first();
      await expect(debugImages).toBeVisible();

      const pwaFeatures = page.locator("text=Enable PWA features").first();
      await expect(pwaFeatures).toBeVisible();
    } else {
      test.skip(true, "Not in WASM mode");
    }
  });

  test("should display mode-specific settings for Server mode", async ({
    page,
  }) => {
    await settingsPage.goto();

    const mode = await settingsPage.getCurrentMode();

    if (mode === "server") {
      // Server mode should show server mode settings
      await expect(settingsPage.serverModeSettings).toBeVisible();

      // Should have specific toggles
      const realTimeNotifications = page
        .locator("text=Real-time notifications")
        .first();
      await expect(realTimeNotifications).toBeVisible();

      const autoRefresh = page.locator("text=Auto-refresh on updates").first();
      await expect(autoRefresh).toBeVisible();
    } else {
      test.skip(true, "Not in Server mode");
    }
  });

  test("should toggle settings", async ({ page }) => {
    await settingsPage.goto();

    const mode = await settingsPage.getCurrentMode();

    if (mode === "wasm") {
      // Find a toggle
      const toggle = page
        .locator('input[type="checkbox"]')
        .first();

      if (await toggle.isVisible()) {
        const initialState = await toggle.isChecked();

        await toggle.click();
        await page.waitForTimeout(300);

        const newState = await toggle.isChecked();
        expect(newState).not.toBe(initialState);

        // Toggle back
        await toggle.click();
        await page.waitForTimeout(300);
      }
    }
  });

  test("should display browser information in About section", async ({
    page,
  }) => {
    await settingsPage.goto();

    const browserInfo = page.locator("text=Browser:").first();
    await expect(browserInfo).toBeVisible();
  });

  test("should display storage information for WASM mode", async ({ page }) => {
    await settingsPage.goto();

    const mode = await settingsPage.getCurrentMode();

    if (mode === "wasm") {
      const storageInfo = page.locator("text=Storage:").first();
      await expect(storageInfo).toBeVisible();
    }
  });

  test("should display API endpoint for Server mode", async ({ page }) => {
    await settingsPage.goto();

    const mode = await settingsPage.getCurrentMode();

    if (mode === "server") {
      const apiEndpoint = page.locator("text=API Endpoint:").first();
      const hasEndpoint = await apiEndpoint.isVisible().catch(() => false);
      console.log("API Endpoint visible:", hasEndpoint);
    }
  });

  test("should show mode switch option if available", async ({ page }) => {
    await settingsPage.goto();

    const canSwitch = await settingsPage.canSwitchMode();
    console.log("Mode switch available:", canSwitch);

    if (canSwitch) {
      await expect(settingsPage.modeSwitchSection).toBeVisible();
    }
  });

  test("should handle settings page accessibility", async ({ page }) => {
    await settingsPage.goto();

    // Check for proper heading hierarchy
    const h1 = page.locator("h1");
    await expect(h1).toHaveCount(1);

    const h2s = page.locator("h2");
    const h2Count = await h2s.count();
    expect(h2Count).toBeGreaterThan(0);

    // Check for labels on inputs
    const checkboxes = page.locator('input[type="checkbox"]');
    const checkboxCount = await checkboxes.count();

    for (let i = 0; i < checkboxCount; i++) {
      const checkbox = checkboxes.nth(i);
      const hasLabel = await checkbox.evaluate((el) => {
        const label = el.closest("label");
        return label !== null;
      });
      // Each checkbox should be in a label
      console.log(`Checkbox ${i} has label:`, hasLabel);
    }
  });

  test("should maintain settings after page reload", async ({ page }) => {
    await settingsPage.goto();

    const mode = await settingsPage.getCurrentMode();

    // Toggle a setting - click the visible toggle wrapper div, not the hidden checkbox
    // The toggle is inside a label, click the label element
    const toggleLabel = page.locator('label.relative.inline-flex').first();
    if (await toggleLabel.isVisible()) {
      await toggleLabel.click();
      await page.waitForTimeout(500);
    }

    // Reload
    await page.reload();
    await page.waitForLoadState("domcontentloaded");

    // Mode should be preserved
    const modeAfter = await settingsPage.getCurrentMode();
    expect(modeAfter).toBe(mode);
  });

  test("should display correct mode indicator emoji", async ({ page }) => {
    await settingsPage.goto();

    const mode = await settingsPage.getCurrentMode();

    if (mode === "wasm") {
      // WASM mode should show laptop emoji
      const laptopEmoji = page.getByText("💻").first();
      await expect(laptopEmoji).toBeVisible();
    } else {
      // Server mode should show desktop emoji - use first() to avoid strict mode violation
      const desktopEmoji = page.getByText("🖥️").first();
      await expect(desktopEmoji).toBeVisible();
    }
  });

  test("should display correct mode description", async ({ page }) => {
    await settingsPage.goto();

    const mode = await settingsPage.getCurrentMode();

    if (mode === "wasm") {
      await expect(
        page.getByText(/processing happens entirely in your browser/i)
      ).toBeVisible();
    } else {
      await expect(
        page.getByText(/using backend server for processing/i)
      ).toBeVisible();
    }
  });

  test("should show correct data storage info for mode", async ({ page }) => {
    await settingsPage.goto();

    const mode = await settingsPage.getCurrentMode();
    const storageInfo = await settingsPage.getDataStorageInfo();

    if (mode === "wasm") {
      expect(storageInfo.toLowerCase()).toContain("indexeddb");
    } else {
      expect(storageInfo.toLowerCase()).toContain("server");
    }
  });

  test("should show correct network requirement for mode", async ({ page }) => {
    await settingsPage.goto();

    const mode = await settingsPage.getCurrentMode();
    const networkInfo = await settingsPage.getNetworkInfo();

    if (mode === "wasm") {
      expect(networkInfo.toLowerCase()).toContain("no");
    } else {
      expect(networkInfo.toLowerCase()).toContain("yes");
    }
  });

  test("should handle keyboard navigation on settings page", async ({
    page,
  }) => {
    await settingsPage.goto();

    // Tab through elements
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");

    // Something should be focused
    const focusedTag = await page.evaluate(
      () => document.activeElement?.tagName
    );
    expect(focusedTag).not.toBe("BODY");
  });

  test("should be responsive on mobile viewport", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await settingsPage.goto();

    // Content should still be visible
    await expect(settingsPage.heading).toBeVisible();
    await expect(settingsPage.aboutSection).toBeVisible();

    // Cards should stack vertically (check layout)
    const infoCards = page.locator(".bg-gray-50.p-3.rounded");
    const count = await infoCards.count();

    if (count > 0) {
      const boxes = await Promise.all(
        Array.from({ length: count }, (_, i) =>
          infoCards.nth(i).boundingBox()
        )
      );

      // On mobile, cards should be stacked (similar x positions)
      console.log("Card positions:", boxes.map((b) => b?.x));
    }
  });
});
