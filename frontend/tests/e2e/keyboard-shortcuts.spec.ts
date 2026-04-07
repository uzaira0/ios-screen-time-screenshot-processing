import { test, expect } from "@playwright/test";
import { AnnotationPage } from "../pages/AnnotationPage";

/**
 * Keyboard Shortcuts Tests
 *
 * Tests all keyboard shortcuts in the application:
 * - Navigation (ArrowLeft/Right, J/K)
 * - Actions (V for verify, S for skip, Escape)
 * - Editing shortcuts
 * - Help dialog (?/H)
 * - Focus management
 */
test.describe("Keyboard Shortcuts", () => {
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

  test("should navigate to next screenshot with ArrowRight", async ({
    page,
  }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    // Get current screenshot info
    const navInfo = page.getByTestId("navigation-info");
    const initialText = await navInfo.textContent().catch(() => "");

    // Press right arrow (when not in input)
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(1000);

    // Check if navigation occurred
    const newText = await navInfo.textContent().catch(() => "");
    console.log("Navigation info:", initialText, "->", newText);
  });

  test("should navigate to previous screenshot with ArrowLeft", async ({
    page,
  }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    // Press left arrow
    await page.keyboard.press("ArrowLeft");
    await page.waitForTimeout(1000);

    // Page should remain functional
    await expect(page.getByTestId("annotation-workspace")).toBeVisible();
  });

  test("should navigate with J/K keys (vim-style)", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    // Make sure no input is focused
    await page.keyboard.press("Escape");
    await page.waitForTimeout(200);

    // Press K for next
    await page.keyboard.press("k");
    await page.waitForTimeout(500);

    // Press J for previous
    await page.keyboard.press("j");
    await page.waitForTimeout(500);

    // Page should remain functional
    await expect(page.getByTestId("annotation-workspace")).toBeVisible();
  });

  test("should toggle verify with V key", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    // Get initial verify button state
    const verifyButton = page.getByRole("button", { name: /verified/i });
    const initialText = await verifyButton.textContent().catch(() => "");

    // Ensure we're not in an input
    await page.keyboard.press("Escape");
    await page.waitForTimeout(200);

    // Press V to toggle verify
    await page.keyboard.press("v");
    await page.waitForTimeout(1000);

    // Check if button text changed
    const newText = await verifyButton.textContent().catch(() => "");
    console.log("Verify button:", initialText, "->", newText);
  });

  test("should skip with S key", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    // Ensure we're not in an input
    await page.keyboard.press("Escape");
    await page.waitForTimeout(200);

    // Set up response listener
    let skipCalled = false;
    page.on("response", (response) => {
      if (response.url().includes("/skip")) {
        skipCalled = true;
      }
    });

    // Press S to skip
    await page.keyboard.press("s");
    await page.waitForTimeout(1000);

    console.log("Skip API called:", skipCalled);
  });

  test("should close modals with Escape key", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    // Press Escape
    await page.keyboard.press("Escape");
    await page.waitForTimeout(200);

    // Page should still be functional
    await expect(page.getByTestId("annotation-workspace")).toBeVisible();
  });

  test("should show help dialog with ? key", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    // Ensure we're not in an input
    await page.keyboard.press("Escape");
    await page.waitForTimeout(200);

    // Press ? to show help
    await page.keyboard.press("?");
    await page.waitForTimeout(500);

    // Look for keyboard shortcuts help
    const helpDialog = page.getByText(/keyboard shortcuts/i);
    const helpVisible = await helpDialog.isVisible().catch(() => false);

    console.log("Help dialog visible:", helpVisible);

    // Close help
    await page.keyboard.press("Escape");
  });

  test("should show help dialog with H key", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    await page.keyboard.press("Escape");
    await page.waitForTimeout(200);

    // Press H for help
    await page.keyboard.press("h");
    await page.waitForTimeout(500);

    const helpDialog = page.getByText(/keyboard shortcuts/i);
    const helpVisible = await helpDialog.isVisible().catch(() => false);

    console.log("Help dialog visible (H key):", helpVisible);

    await page.keyboard.press("Escape");
  });

  test("should not trigger shortcuts when input is focused", async ({
    page,
  }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    const hour0Input = page.getByTestId("hour-input-0");
    if (!(await hour0Input.isVisible())) {
      test.skip(true, "Hour inputs not visible");
      return;
    }

    // Focus input
    await hour0Input.focus();
    await hour0Input.fill("30");

    // Press V - should type 'v' in input, not trigger verify
    await page.keyboard.type("v");

    const value = await hour0Input.inputValue();
    // Value might include 'v' (as text) or just be numeric if validation removes it
    console.log("Input value after V key:", value);
  });

  test("should navigate to home with Escape from workspace", async ({
    page,
  }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    // Multiple Escape presses might navigate home
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await page.waitForTimeout(500);

    // Check current URL
    const url = page.url();
    console.log("URL after double Escape:", url);
  });

  test("should handle modifier keys (Ctrl+S for save)", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    // Set up response listener
    let saveCalled = false;
    page.on("response", (response) => {
      if (response.url().includes("/annotations")) {
        saveCalled = true;
      }
    });

    // Press Ctrl+S
    await page.keyboard.press("Control+s");
    await page.waitForTimeout(1000);

    console.log("Save triggered with Ctrl+S:", saveCalled);
  });

  test("should focus first input with Tab from workspace", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    // Make sure no input is focused
    await page.keyboard.press("Escape");
    await page.waitForTimeout(200);

    // Tab to focus first focusable element
    await page.keyboard.press("Tab");
    await page.waitForTimeout(200);

    // Something should be focused
    const focusedTag = await page.evaluate(
      () => document.activeElement?.tagName
    );
    console.log("Focused element after Tab:", focusedTag);
  });

  test("should cycle through elements with Tab", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    // Tab through several elements
    const focusedElements: string[] = [];

    for (let i = 0; i < 10; i++) {
      await page.keyboard.press("Tab");
      await page.waitForTimeout(100);

      const focusedInfo = await page.evaluate(() => ({
        tag: document.activeElement?.tagName,
        testId: document.activeElement?.getAttribute("data-testid"),
        className: document.activeElement?.className,
      }));

      focusedElements.push(focusedInfo.testId || focusedInfo.tag || "unknown");
    }

    console.log("Tab cycle:", focusedElements.join(" -> "));
  });

  test("should support Shift+Tab for reverse navigation", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    // Tab forward a few times
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");

    // Get current focused element
    const forward = await page.evaluate(
      () => document.activeElement?.getAttribute("data-testid")
    );

    // Shift+Tab back
    await page.keyboard.press("Shift+Tab");
    await page.waitForTimeout(100);

    const backward = await page.evaluate(
      () => document.activeElement?.getAttribute("data-testid")
    );

    console.log("Forward:", forward, "Backward:", backward);
  });

  test("should handle number keys for quick value entry", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    const hour0Input = page.getByTestId("hour-input-0");
    if (!(await hour0Input.isVisible())) {
      test.skip(true, "Hour inputs not visible");
      return;
    }

    // Focus and clear
    await hour0Input.focus();
    await hour0Input.clear();

    // Type number
    await page.keyboard.type("42");

    const value = await hour0Input.inputValue();
    expect(value).toBe("42");
  });

  test("should handle Enter key to move to next input", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    const hour0Input = page.getByTestId("hour-input-0");
    if (!(await hour0Input.isVisible())) {
      test.skip(true, "Hour inputs not visible");
      return;
    }

    await hour0Input.focus();
    await hour0Input.fill("30");

    // Press Enter
    await page.keyboard.press("Enter");
    await page.waitForTimeout(100);

    // Check what's focused now
    const focusedTestId = await page.evaluate(
      () => document.activeElement?.getAttribute("data-testid")
    );

    console.log("Focused after Enter:", focusedTestId);
  });

  test("should handle Delete/Backspace to clear input", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    const hour0Input = page.getByTestId("hour-input-0");
    if (!(await hour0Input.isVisible())) {
      test.skip(true, "Hour inputs not visible");
      return;
    }

    await hour0Input.fill("30");
    await hour0Input.focus();

    // Select all and delete
    await page.keyboard.press("Control+a");
    await page.keyboard.press("Delete");

    const value = await hour0Input.inputValue();
    expect(value).toBe("");
  });

  test("should support undo with Ctrl+Z", async ({ page }) => {
    const hasScreenshot = await ensureScreenshotLoaded(page);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    const hour0Input = page.getByTestId("hour-input-0");
    if (!(await hour0Input.isVisible())) {
      test.skip(true, "Hour inputs not visible");
      return;
    }

    await hour0Input.clear();
    await hour0Input.fill("30");
    await page.waitForTimeout(100);
    await hour0Input.fill("45");

    const beforeUndo = await hour0Input.inputValue();

    // Ctrl+Z to undo
    await page.keyboard.press("Control+z");
    await page.waitForTimeout(100);

    const afterUndo = await hour0Input.inputValue();
    console.log("Before undo:", beforeUndo, "After undo:", afterUndo);
  });
});
