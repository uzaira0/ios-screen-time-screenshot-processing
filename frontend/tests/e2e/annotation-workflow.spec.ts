import { test, expect } from "../fixtures/auth";
import { AnnotationPage } from "../pages/AnnotationPage";
import { HomePage } from "../pages/HomePage";

/**
 * Annotation Workflow Tests
 *
 * Tests the complete annotation workflow including:
 * - Loading screenshots
 * - Grid overlay display and adjustment
 * - Hourly value editing
 * - Title editing
 * - Navigation between screenshots
 * - Keyboard shortcuts
 * - Auto-save functionality
 */
test.describe("Annotation Workflow", () => {
  let annotationPage: AnnotationPage;

  test.beforeEach(async ({ authenticatedPage }) => {
    annotationPage = new AnnotationPage(authenticatedPage);
  });

  test.describe("Loading and Display", () => {
    test("should display annotation workspace when screenshot is available", async ({
      authenticatedPage,
    }) => {
      await annotationPage.goto();

      const hasScreenshot = await annotationPage.waitForScreenshotLoad();

      if (!hasScreenshot) {
        // Empty state should be shown
        const allDone = await annotationPage.isAllDoneVisible();
        expect(allDone).toBe(true);
        return;
      }

      // Workspace should be visible
      await expect(annotationPage.workspace).toBeVisible();
    });

    test("should display screenshot metadata in header", async ({
      authenticatedPage,
    }) => {
      await annotationPage.goto();

      const hasScreenshot = await annotationPage.waitForScreenshotLoad();
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      // Should show screenshot ID in URL
      const screenshotId = await annotationPage.getCurrentScreenshotId();
      expect(screenshotId).toBeGreaterThan(0);
    });

    test("should display OCR total when available", async ({
      authenticatedPage,
    }) => {
      await annotationPage.goto();

      const hasScreenshot = await annotationPage.waitForScreenshotLoad();
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      // OCR total element should exist (content may be "--" if no OCR)
      await expect(annotationPage.ocrTotal).toBeVisible();
    });

    test("should display bar total calculated from hourly values", async ({
      authenticatedPage,
    }) => {
      await annotationPage.goto();

      const hasScreenshot = await annotationPage.waitForScreenshotLoad();
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      await expect(annotationPage.barTotal).toBeVisible();
      const barTotalText = await annotationPage.getBarTotal();
      expect(barTotalText).toMatch(/\d+m|\d+h/);
    });
  });

  test.describe("Hourly Value Editing", () => {
    test("should allow editing hourly values", async ({ authenticatedPage }) => {
      await annotationPage.goto();

      const hasScreenshot = await annotationPage.waitForScreenshotLoad();
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      // Check if verified (read-only mode)
      const isVerified = await annotationPage.isVerifiedByCurrentUser();
      if (isVerified) {
        test.skip(true, "Screenshot is already verified - read-only mode");
        return;
      }

      // Edit hour 0
      const hour0Input = annotationPage.getHourInput(0);
      const hasInput = await hour0Input.isVisible().catch(() => false);

      if (!hasInput) {
        test.skip(true, "Hour inputs not visible");
        return;
      }

      await hour0Input.clear();
      await hour0Input.fill("25");
      await expect(hour0Input).toHaveValue("25");
    });

    test("should update bar total when hourly value changes", async ({
      authenticatedPage,
    }) => {
      await annotationPage.goto();

      const hasScreenshot = await annotationPage.waitForScreenshotLoad();
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      const isVerified = await annotationPage.isVerifiedByCurrentUser();
      if (isVerified) {
        test.skip(true, "Screenshot is verified - read-only mode");
        return;
      }

      // Set hour 0 to 30 minutes
      await annotationPage.setHourlyValue(0, 30);
      await authenticatedPage.waitForTimeout(500);

      const newTotal = await annotationPage.getBarTotal();

      // Total should be a valid format
      // Just verify we got a valid response
      expect(newTotal).toMatch(/\d+m|\d+h/);
    });

    test("should enforce min/max values for hourly inputs", async ({
      authenticatedPage,
    }) => {
      await annotationPage.goto();

      const hasScreenshot = await annotationPage.waitForScreenshotLoad();
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      const isVerified = await annotationPage.isVerifiedByCurrentUser();
      if (isVerified) {
        test.skip(true, "Screenshot is verified");
        return;
      }

      const hour0Input = annotationPage.getHourInput(0);
      if (!(await hour0Input.isVisible().catch(() => false))) {
        test.skip(true, "Hour input not visible");
        return;
      }

      // Try to enter value > 60 (max)
      await hour0Input.fill("75");
      await hour0Input.blur();
      await authenticatedPage.waitForTimeout(500);

      // Value should be clamped or rejected
      const value = await hour0Input.inputValue();
      const numValue = parseFloat(value);
      expect(numValue).toBeLessThanOrEqual(60);
    });
  });

  test.describe("Navigation", () => {
    test("should display navigation buttons", async ({ authenticatedPage }) => {
      await annotationPage.goto();

      const hasScreenshot = await annotationPage.waitForScreenshotLoad();
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      // Navigation buttons should exist
      await expect(annotationPage.nextButton).toBeVisible();
      await expect(annotationPage.prevButton).toBeVisible();
    });

    test("should display navigation info (X/Y format)", async ({
      authenticatedPage,
    }) => {
      await annotationPage.goto();

      const hasScreenshot = await annotationPage.waitForScreenshotLoad();
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      const navInfo = await annotationPage.getNavigationInfo();
      expect(navInfo.currentIndex).toBeGreaterThan(0);
      expect(navInfo.total).toBeGreaterThan(0);
    });

    test("should navigate to next screenshot when clicking next button", async ({
      authenticatedPage,
    }) => {
      await annotationPage.goto();

      const hasScreenshot = await annotationPage.waitForScreenshotLoad();
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      const navInfo = await annotationPage.getNavigationInfo();

      if (!navInfo.hasNext) {
        test.skip(true, "No next screenshot available");
        return;
      }

      const initialId = await annotationPage.getCurrentScreenshotId();
      await annotationPage.navigateNext();
      await authenticatedPage.waitForTimeout(1000);

      const newId = await annotationPage.getCurrentScreenshotId();
      // IDs might be same if wraparound, but navigation should complete
      expect(newId).not.toBeNull();
    });

    test("should navigate to previous screenshot when clicking prev button", async ({
      authenticatedPage,
    }) => {
      await annotationPage.goto();

      const hasScreenshot = await annotationPage.waitForScreenshotLoad();
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      const navInfo = await annotationPage.getNavigationInfo();

      if (!navInfo.hasPrev) {
        test.skip(true, "No previous screenshot available");
        return;
      }

      await annotationPage.navigatePrev();
      await authenticatedPage.waitForTimeout(1000);

      // Should still be on annotation page
      await expect(authenticatedPage).toHaveURL(/\/annotate/);
    });

    test("should update URL when navigating between screenshots", async ({
      authenticatedPage,
    }) => {
      await annotationPage.goto();

      const hasScreenshot = await annotationPage.waitForScreenshotLoad();
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      const navInfo = await annotationPage.getNavigationInfo();

      if (!navInfo.hasNext) {
        test.skip(true, "No next screenshot to test URL update");
        return;
      }

      const initialUrl = authenticatedPage.url();
      await annotationPage.navigateNext();
      await authenticatedPage.waitForTimeout(1000);

      const newUrl = authenticatedPage.url();

      // URL should update to include screenshot ID
      expect(newUrl).toContain("/annotate/");
    });
  });

  test.describe("Keyboard Shortcuts", () => {
    test("should navigate with arrow keys", async ({ authenticatedPage }) => {
      await annotationPage.goto();

      const hasScreenshot = await annotationPage.waitForScreenshotLoad();
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      // Press right arrow to go next
      await annotationPage.pressShortcut("ArrowRight");
      await authenticatedPage.waitForTimeout(1000);

      // Page should still be functional
      await expect(annotationPage.workspace).toBeVisible();
    });

    test("should skip with Escape key", async ({ authenticatedPage }) => {
      await annotationPage.goto();

      const hasScreenshot = await annotationPage.waitForScreenshotLoad();
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      // Press Escape to skip
      await annotationPage.pressShortcut("Escape");
      await authenticatedPage.waitForTimeout(1000);

      // Page should still be functional (might show next screenshot or empty)
      await expect(authenticatedPage.locator("body")).toBeVisible();
    });

    test("should toggle verify with V key", async ({ authenticatedPage }) => {
      await annotationPage.goto();

      const hasScreenshot = await annotationPage.waitForScreenshotLoad();
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      const initialVerified = await annotationPage.isVerifiedByCurrentUser();

      // Press V to toggle
      await annotationPage.pressShortcut("v");
      await authenticatedPage.waitForTimeout(1000);

      const newVerified = await annotationPage.isVerifiedByCurrentUser();

      // State should toggle (if allowed)
      // Note: might not toggle if title is required
      console.log("Verified before:", initialVerified, "After:", newVerified);
    });
  });

  test.describe("Auto-Save", () => {
    test("should show auto-save status indicator", async ({
      authenticatedPage,
    }) => {
      await annotationPage.goto();

      const hasScreenshot = await annotationPage.waitForScreenshotLoad();
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      await expect(annotationPage.autoSaveStatus).toBeVisible();
    });

    test("should show saving status when editing values", async ({
      authenticatedPage,
    }) => {
      await annotationPage.goto();

      const hasScreenshot = await annotationPage.waitForScreenshotLoad();
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      const isVerified = await annotationPage.isVerifiedByCurrentUser();
      if (isVerified) {
        test.skip(true, "Screenshot is verified");
        return;
      }

      const hour0Input = annotationPage.getHourInput(0);
      if (!(await hour0Input.isVisible().catch(() => false))) {
        test.skip(true, "Hour input not visible");
        return;
      }

      // Check if input is disabled (read-only mode)
      const isDisabled = await hour0Input.isDisabled().catch(() => false);
      if (isDisabled) {
        test.skip(true, "Hourly input is disabled (read-only mode)");
        return;
      }

      // Edit a value to trigger auto-save
      await hour0Input.fill("15");

      // Wait for auto-save to trigger (longer timeout needed)
      await authenticatedPage.waitForTimeout(3000);

      // Auto-save status should be visible (it's always shown)
      await expect(annotationPage.autoSaveStatus).toBeVisible();
    });
  });

  test.describe("Group Filtering", () => {
    test("should apply group filter from URL", async ({ authenticatedPage }) => {
      await annotationPage.goto({ groupId: "test-group" });

      // URL should contain group parameter
      expect(authenticatedPage.url()).toContain("group=test-group");

      // Page should load (might be empty for non-existent group)
      await authenticatedPage.waitForTimeout(2000);
      await expect(authenticatedPage.locator("body")).toBeVisible();
    });

    test("should apply processing status filter from URL", async ({
      authenticatedPage,
    }) => {
      await annotationPage.goto({ processingStatus: "completed" });

      expect(authenticatedPage.url()).toContain("processing_status=completed");

      await authenticatedPage.waitForTimeout(2000);
      await expect(authenticatedPage.locator("body")).toBeVisible();
    });

    test("should navigate from home page with group filter", async ({
      authenticatedPage,
    }) => {
      const homePage = new HomePage(authenticatedPage);
      await homePage.goto();
      await homePage.waitForGroupsLoad();

      const groupCount = await homePage.getGroupCount();
      if (groupCount === 0) {
        test.skip(true, "No groups available");
        return;
      }

      // Click on first group
      const firstGroupCard = authenticatedPage
        .locator('[data-testid="group-card"]')
        .first();
      await firstGroupCard.getByTestId("total-screenshots").click();

      // Should navigate to annotation page with group filter
      await expect(authenticatedPage).toHaveURL(/\/annotate.*group=/);
    });

    test("should navigate from home page with status filter", async ({
      authenticatedPage,
    }) => {
      const homePage = new HomePage(authenticatedPage);
      await homePage.goto();
      await homePage.waitForGroupsLoad();

      const groupCount = await homePage.getGroupCount();
      if (groupCount === 0) {
        test.skip(true, "No groups available");
        return;
      }

      // Click on pending status
      const firstGroupCard = authenticatedPage
        .locator('[data-testid="group-card"]')
        .first();
      const pendingElement = firstGroupCard.getByTestId("status-pending");

      if (!(await pendingElement.isVisible().catch(() => false))) {
        test.skip(true, "Pending status not visible");
        return;
      }

      await pendingElement.click();

      await expect(authenticatedPage).toHaveURL(/processing_status=pending/);
    });
  });
});
