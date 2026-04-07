import { test, expect } from "@playwright/test";

/**
 * PHI Detection Settings E2E Tests
 *
 * Verifies the PHI Detection section on the Settings page:
 * - OCR Engine selection (pytesseract / leptess)
 * - NER Detector selection (presidio / gliner)
 * - Detection Preset selection
 * - Redaction Method selection
 * - Settings persist across page reloads (localStorage)
 */
test.describe("PHI Detection Settings", () => {
  test.beforeEach(async ({ page }) => {
    // Clear localStorage to start fresh
    await page.goto("/");
    await page.evaluate(() => localStorage.removeItem("processing-settings"));
    await page.goto("/settings");
    await page.waitForLoadState("domcontentloaded");
  });

  test("should display PHI Detection section in server mode", async ({
    page,
  }) => {
    // PHI section only shown in server mode (!isLocalMode)
    const phiHeading = page.getByText("PHI Detection");
    const isVisible = await phiHeading.isVisible().catch(() => false);

    if (isVisible) {
      await expect(phiHeading).toBeVisible();
      await expect(
        page.getByText(/personal health information/i),
      ).toBeVisible();
    } else {
      // In WASM/local mode, PHI section should not exist
      test.skip(true, "PHI settings only available in server mode");
    }
  });

  test("should display OCR Engine options", async ({ page }) => {
    await page.goto("/settings");
    const pytesseractBtn = page.getByRole("button", { name: /pytesseract/i });
    const leptessBtn = page.getByRole("button", { name: /leptess/i });

    if (await pytesseractBtn.isVisible().catch(() => false)) {
      await expect(pytesseractBtn).toBeVisible();
      await expect(leptessBtn).toBeVisible();
    } else {
      test.skip(true, "PHI settings not available in this mode");
    }
  });

  test("should display NER Detector options", async ({ page }) => {
    await page.goto("/settings");
    const presidioBtn = page.getByRole("button", { name: /presidio/i });
    const glinerBtn = page.getByRole("button", { name: /gliner/i });

    if (await presidioBtn.isVisible().catch(() => false)) {
      await expect(presidioBtn).toBeVisible();
      await expect(glinerBtn).toBeVisible();
    } else {
      test.skip(true, "PHI settings not available in this mode");
    }
  });

  test("should select OCR engine and persist", async ({ page }) => {
    await page.goto("/settings");
    const leptessBtn = page.getByRole("button", { name: /leptess/i });

    if (!(await leptessBtn.isVisible().catch(() => false))) {
      test.skip(true, "PHI settings not available");
      return;
    }

    // Click leptess
    await leptessBtn.click();
    await page.waitForTimeout(300);

    // Verify it's selected (has active styling)
    await expect(leptessBtn).toHaveClass(/bg-primary/);

    // Reload and verify persistence
    await page.reload();
    await page.waitForLoadState("domcontentloaded");

    const leptessBtnAfter = page.getByRole("button", { name: /leptess/i });
    await expect(leptessBtnAfter).toHaveClass(/bg-primary/);
  });

  test("should select NER detector and persist", async ({ page }) => {
    await page.goto("/settings");
    const glinerBtn = page.getByRole("button", { name: /gliner/i });

    if (!(await glinerBtn.isVisible().catch(() => false))) {
      test.skip(true, "PHI settings not available");
      return;
    }

    await glinerBtn.click();
    await page.waitForTimeout(300);

    await expect(glinerBtn).toHaveClass(/bg-primary/);

    // Reload and verify
    await page.reload();
    await page.waitForLoadState("domcontentloaded");

    const glinerBtnAfter = page.getByRole("button", { name: /gliner/i });
    await expect(glinerBtnAfter).toHaveClass(/bg-primary/);
  });

  test("should select detection preset", async ({ page }) => {
    await page.goto("/settings");
    const thoroughBtn = page.getByRole("button", { name: /thorough/i });

    if (!(await thoroughBtn.isVisible().catch(() => false))) {
      test.skip(true, "PHI settings not available");
      return;
    }

    await thoroughBtn.click();
    await page.waitForTimeout(300);

    await expect(thoroughBtn).toHaveClass(/bg-primary/);
  });

  test("should select redaction method", async ({ page }) => {
    await page.goto("/settings");
    const pixelateBtn = page.getByRole("button", { name: /pixelate/i });

    if (!(await pixelateBtn.isVisible().catch(() => false))) {
      test.skip(true, "PHI settings not available");
      return;
    }

    await pixelateBtn.click();
    await page.waitForTimeout(300);

    await expect(pixelateBtn).toHaveClass(/bg-primary/);
  });

  test("should store settings in localStorage", async ({ page }) => {
    await page.goto("/settings");
    const leptessBtn = page.getByRole("button", { name: /leptess/i });

    if (!(await leptessBtn.isVisible().catch(() => false))) {
      test.skip(true, "PHI settings not available");
      return;
    }

    // Change OCR engine to leptess
    await leptessBtn.click();
    await page.waitForTimeout(300);

    // Check localStorage
    const stored = await page.evaluate(() => {
      const raw = localStorage.getItem("processing-settings");
      return raw ? JSON.parse(raw) : null;
    });

    expect(stored).not.toBeNull();
    expect(stored.phiOcrEngine).toBe("leptess");
  });

  test("should default to pytesseract and presidio", async ({ page }) => {
    await page.goto("/settings");
    const pytesseractBtn = page.getByRole("button", { name: /pytesseract/i });

    if (!(await pytesseractBtn.isVisible().catch(() => false))) {
      test.skip(true, "PHI settings not available");
      return;
    }

    // Default: pytesseract should be selected
    await expect(pytesseractBtn).toHaveClass(/bg-primary/);

    // Default: presidio should be selected
    const presidioBtn = page.getByRole("button", { name: /presidio/i });
    await expect(presidioBtn).toHaveClass(/bg-primary/);
  });
});
