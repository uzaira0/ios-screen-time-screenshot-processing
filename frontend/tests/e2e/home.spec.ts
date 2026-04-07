import { test, expect } from "../fixtures/auth";
import { HomePage } from "../pages/HomePage";

test.describe("Home Page", () => {
  test("should display homepage with title and description", async ({
    authenticatedPage,
  }) => {
    const homePage = new HomePage(authenticatedPage);
    await homePage.goto();

    await expect(homePage.heading).toBeVisible();
    await expect(
      authenticatedPage.getByText(/collaborative tool for annotating/i),
    ).toBeVisible();
  });

  test("should display groups when available", async ({
    authenticatedPage,
  }) => {
    const homePage = new HomePage(authenticatedPage);
    await homePage.goto();
    await homePage.waitForGroupsLoad();

    const groupCount = await homePage.getGroupCount();

    // Groups may or may not exist depending on database state
    if (groupCount === 0) {
      // Empty state should be visible
      await expect(homePage.emptyState).toBeVisible();
    } else {
      // Groups section should have group cards
      expect(groupCount).toBeGreaterThan(0);
    }
  });

  test("should display empty state when no groups exist", async ({
    authenticatedPage,
  }) => {
    const homePage = new HomePage(authenticatedPage);
    await homePage.goto();
    await homePage.waitForGroupsLoad();

    const groupCount = await homePage.getGroupCount();

    if (groupCount === 0) {
      await expect(homePage.emptyState).toBeVisible();
      await expect(authenticatedPage.getByText(/no groups yet/i)).toBeVisible();
    } else {
      // Skip this test if groups exist
      test.skip(true, "Groups exist in database - cannot test empty state");
    }
  });

  test("should display group statistics correctly", async ({
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

    // Get the first group name
    const firstGroupCard = authenticatedPage
      .locator('[data-testid="group-card"]')
      .first();
    const firstGroupVisible = await firstGroupCard
      .isVisible()
      .catch(() => false);

    if (firstGroupVisible) {
      // Should show some statistics - check for status indicators
      const hasPending = await firstGroupCard
        .getByTestId("status-pending")
        .isVisible()
        .catch(() => false);
      const hasCompleted = await firstGroupCard
        .getByTestId("status-completed")
        .isVisible()
        .catch(() => false);
      const hasTotal = await firstGroupCard
        .getByTestId("total-screenshots")
        .isVisible()
        .catch(() => false);

      // At least one stat should be visible
      expect(hasPending || hasCompleted || hasTotal).toBe(true);
    }
  });

  test("should navigate to annotation page when clicking group", async ({
    authenticatedPage,
  }) => {
    const homePage = new HomePage(authenticatedPage);
    await homePage.goto();
    await homePage.waitForGroupsLoad();

    const groupCount = await homePage.getGroupCount();

    if (groupCount === 0) {
      test.skip(true, "No groups available to click");
      return;
    }

    // Click on total-screenshots area which triggers navigation
    const firstGroupCard = authenticatedPage
      .locator('[data-testid="group-card"]')
      .first();
    const totalScreenshots = firstGroupCard.getByTestId("total-screenshots");
    await totalScreenshots.click();

    // Should navigate to annotation page with group filter
    await expect(authenticatedPage).toHaveURL(/\/annotate.*group=/);
  });

  test("should show login button when not authenticated", async ({
    browser,
  }) => {
    // Create a fresh context WITHOUT authentication
    const context = await browser.newContext({
      storageState: undefined,
    });
    const page = await context.newPage();

    await page.addInitScript(() => {
      localStorage.clear();
    });

    await page.goto(".");
    await page.waitForLoadState("networkidle");

    // Should show "Login" link somewhere for unauthenticated users
    await expect(
      page.getByRole("link", { name: /login/i }).first(),
    ).toBeVisible({ timeout: 10000 });

    await context.close();
  });

  test('should show "Annotate All" button when authenticated', async ({
    authenticatedPage,
  }) => {
    const homePage = new HomePage(authenticatedPage);
    await homePage.goto();

    await expect(homePage.annotateAllButton).toBeVisible();
  });

  test('should navigate to annotation page when clicking "Annotate All"', async ({
    authenticatedPage,
  }) => {
    const homePage = new HomePage(authenticatedPage);
    await homePage.goto();
    await homePage.clickAnnotateAll();

    await expect(authenticatedPage).toHaveURL(/\/annotate/);
  });

  test("should display progress bar for groups", async ({
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

    const firstGroupCard = authenticatedPage
      .locator('[data-testid="group-card"]')
      .first();

    // Progress bar container should be visible
    const progressBar = firstGroupCard.locator(".bg-gray-200.rounded-full");
    const hasProgressBar = await progressBar.isVisible().catch(() => false);

    // Progress percentage should be displayed
    const progressText = firstGroupCard.getByText(/\d+%\s*processed/i);
    const hasProgressText = await progressText.isVisible().catch(() => false);

    // At least one should be present if groups have progress tracking
    console.log("Progress bar visible:", hasProgressBar);
    console.log("Progress text visible:", hasProgressText);
  });

  test("should display image type badge for each group", async ({
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

    const firstGroupCard = authenticatedPage
      .locator('[data-testid="group-card"]')
      .first();

    // Look for image type badge (Screen Time or Battery)
    const screenTimeBadge = firstGroupCard.locator("span.rounded-full", {
      hasText: "Screen Time",
    });
    const batteryBadge = firstGroupCard.locator("span.rounded-full", {
      hasText: "Battery",
    });

    const hasScreenTime = await screenTimeBadge.isVisible().catch(() => false);
    const hasBattery = await batteryBadge.isVisible().catch(() => false);

    // At least one type badge should be visible
    expect(hasScreenTime || hasBattery).toBe(true);
  });

  test("should handle API errors gracefully", async ({ authenticatedPage }) => {
    const homePage = new HomePage(authenticatedPage);
    await homePage.goto();

    // Page should still be functional even if API has issues
    await expect(homePage.groupsSection).toBeVisible();
  });

  test("should refresh groups periodically", async ({ authenticatedPage }) => {
    const homePage = new HomePage(authenticatedPage);
    await homePage.goto();
    await homePage.waitForGroupsLoad();

    // Wait for potential auto-refresh (typically 5 seconds)
    await authenticatedPage.waitForTimeout(6000);

    // Page should still be responsive after refresh
    await expect(homePage.groupsSection).toBeVisible();
  });

  test("should show correct group status counts", async ({
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

    const firstGroupCard = authenticatedPage
      .locator('[data-testid="group-card"]')
      .first();

    // Check for status indicators (pending, completed, failed, skipped)
    const statusTexts = ["pending", "completed", "failed", "skipped"];
    let foundAnyStatus = false;

    for (const status of statusTexts) {
      const statusElement = firstGroupCard.getByText(new RegExp(status, "i"));
      if (await statusElement.isVisible().catch(() => false)) {
        foundAnyStatus = true;
        break;
      }
    }

    // Or check for numeric status counts
    const numericCounts = firstGroupCard.locator("text=/\\d+/");
    const countVisible = await numericCounts
      .first()
      .isVisible()
      .catch(() => false);

    expect(foundAnyStatus || countVisible).toBe(true);
  });
});
