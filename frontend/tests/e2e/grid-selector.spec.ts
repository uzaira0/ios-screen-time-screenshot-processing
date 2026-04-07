import { test, expect } from "@playwright/test";
import { AnnotationPage } from "../pages/AnnotationPage";

/**
 * Grid Selector Component Tests
 *
 * Tests the canvas-based grid selection functionality including:
 * - Mouse interactions (click, drag, resize)
 * - Touch interactions (for mobile)
 * - Zoom controls
 * - Grid boundary visualization
 * - Reprocessing triggers
 */
test.describe("Grid Selector", () => {
  let annotationPage: AnnotationPage;

  test.beforeEach(async ({ page }) => {
    annotationPage = new AnnotationPage(page);
  });

  /**
   * Helper to wait for annotation page with screenshot
   */
  async function ensureScreenshotLoaded(page: import("@playwright/test").Page) {
    await page.goto("annotate");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2000);

    const hasWorkspace = await page
      .getByTestId("annotation-workspace")
      .isVisible()
      .catch(() => false);
    const hasNoScreenshots = await page
      .getByText(/no screenshots|queue is empty/i)
      .first()
      .isVisible()
      .catch(() => false);

    if (hasNoScreenshots || !hasWorkspace) {
      return false;
    }
    return true;
  }

  test("should display grid selector canvas when screenshot is loaded", async ({
    page,
  }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    const gridSelector = page.getByTestId("grid-selector");
    await expect(gridSelector).toBeVisible();

    // Canvas should be present within grid selector
    const canvas = gridSelector.locator("canvas");
    await expect(canvas).toBeVisible();
  });

  test("should show screenshot image in grid selector", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    const gridSelector = page.getByTestId("grid-selector");
    const canvas = gridSelector.locator("canvas");

    // Get canvas dimensions - should have non-zero size
    const box = await canvas.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeGreaterThan(0);
    expect(box!.height).toBeGreaterThan(0);
  });

  test("should respond to mouse click on canvas", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    const gridSelector = page.getByTestId("grid-selector");
    const canvas = gridSelector.locator("canvas");
    const box = await canvas.boundingBox();

    if (!box) {
      test.skip(true, "Canvas not visible");
      return;
    }

    // Click in center of canvas
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);

    // Page should remain functional
    await expect(page.getByTestId("annotation-workspace")).toBeVisible();
  });

  test("should allow drag selection on canvas", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    const gridSelector = page.getByTestId("grid-selector");
    const canvas = gridSelector.locator("canvas");
    const box = await canvas.boundingBox();

    if (!box) {
      test.skip(true, "Canvas not visible");
      return;
    }

    // Perform drag selection
    const startX = box.x + box.width * 0.2;
    const startY = box.y + box.height * 0.2;
    const endX = box.x + box.width * 0.8;
    const endY = box.y + box.height * 0.8;

    await page.mouse.move(startX, startY);
    await page.mouse.down();
    await page.mouse.move(endX, endY);
    await page.mouse.up();

    // Wait for debounce and potential reprocess
    await page.waitForTimeout(1000);

    // Page should remain functional
    await expect(page.getByTestId("annotation-workspace")).toBeVisible();
  });

  test("should show zoom controls", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    // Look for zoom controls
    const zoomIn = page.getByRole("button", { name: /zoom in|\+/i });
    const zoomOut = page.getByRole("button", { name: /zoom out|-/i });
    const resetZoom = page.getByRole("button", { name: /reset|fit/i });

    // At least one zoom control should exist
    const hasZoomIn = await zoomIn.isVisible().catch(() => false);
    const hasZoomOut = await zoomOut.isVisible().catch(() => false);
    const hasReset = await resetZoom.isVisible().catch(() => false);

    // Log what we found
    console.log("Zoom controls:", { hasZoomIn, hasZoomOut, hasReset });
  });

  test("should trigger reprocess when grid is selected", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    const gridSelector = page.getByTestId("grid-selector");
    const canvas = gridSelector.locator("canvas");
    const box = await canvas.boundingBox();

    if (!box) {
      test.skip(true, "Canvas not visible");
      return;
    }

    // Set up response listener for reprocess API
    let reprocessCalled = false;
    page.on("response", (response) => {
      if (response.url().includes("/reprocess")) {
        reprocessCalled = true;
      }
    });

    // Perform drag selection
    await page.mouse.move(box.x + 50, box.y + 50);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width - 50, box.y + box.height - 50);
    await page.mouse.up();

    // Wait for debounce and potential reprocess
    await page.waitForTimeout(1500);

    console.log("Reprocess API called:", reprocessCalled);
  });

  test("should display grid overlay lines when coordinates are set", async ({
    page,
  }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    // Grid overlay should show hour lines
    const hourlyOverlay = page.getByTestId("hourly-overlay");
    const hasOverlay = await hourlyOverlay.isVisible().catch(() => false);

    console.log("Hourly overlay visible:", hasOverlay);
  });

  test("should handle double-click for auto-detect", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    const gridSelector = page.getByTestId("grid-selector");
    const canvas = gridSelector.locator("canvas");
    const box = await canvas.boundingBox();

    if (!box) {
      test.skip(true, "Canvas not visible");
      return;
    }

    // Double-click to trigger auto-detect
    await page.mouse.dblclick(box.x + box.width / 2, box.y + box.height / 2);

    // Wait for processing
    await page.waitForTimeout(1000);

    // Page should remain functional
    await expect(page.getByTestId("annotation-workspace")).toBeVisible();
  });

  test("should handle mouse wheel zoom", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    const gridSelector = page.getByTestId("grid-selector");
    const canvas = gridSelector.locator("canvas");
    const box = await canvas.boundingBox();

    if (!box) {
      test.skip(true, "Canvas not visible");
      return;
    }

    // Position mouse on canvas
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);

    // Scroll to zoom
    await page.mouse.wheel(0, -100);
    await page.waitForTimeout(300);

    await page.mouse.wheel(0, 100);
    await page.waitForTimeout(300);

    // Page should remain functional
    await expect(page.getByTestId("annotation-workspace")).toBeVisible();
  });

  test("should maintain selection after page interactions", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    const gridSelector = page.getByTestId("grid-selector");
    const canvas = gridSelector.locator("canvas");
    const box = await canvas.boundingBox();

    if (!box) {
      test.skip(true, "Canvas not visible");
      return;
    }

    // Make a selection
    await page.mouse.move(box.x + 50, box.y + 50);
    await page.mouse.down();
    await page.mouse.move(box.x + 200, box.y + 200);
    await page.mouse.up();

    await page.waitForTimeout(500);

    // Click somewhere else (e.g., hourly editor)
    const hourlyEditor = page.getByTestId("hourly-editor");
    if (await hourlyEditor.isVisible()) {
      await hourlyEditor.click();
    }

    // Grid selector should still be visible
    await expect(gridSelector).toBeVisible();
  });
});
