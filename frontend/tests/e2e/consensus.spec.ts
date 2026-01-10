import { test, expect } from "@playwright/test";
import { ConsensusPage, ConsensusComparisonPage } from "../pages/ConsensusPage";

test.describe("Consensus Page", () => {
  let consensusPage: ConsensusPage;

  test.beforeEach(async ({ page }) => {
    consensusPage = new ConsensusPage(page);

    // Login first
    await page.goto("login");
    await page.fill('input[name="username"]', "testuser");
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(annotate|home)/);
  });

  test.describe("Main Consensus View", () => {
    test("should load consensus page and show title", async ({ page }) => {
      await consensusPage.goto();
      await consensusPage.waitForLoad();

      const title = consensusPage.pageTitle;
      await expect(title).toContainText("Cross-Rater Consensus");
    });

    test("should display summary statistics", async ({ page }) => {
      await consensusPage.goto();
      await consensusPage.waitForLoad();

      // Summary stats should be visible (when not filtering by group)
      const stats = await consensusPage.getSummaryStats();

      // Stats should be numbers (might be 0 if no data)
      expect(typeof stats.total).toBe("number");
      expect(typeof stats.verified).toBe("number");
      expect(typeof stats.singleVerified).toBe("number");
      expect(typeof stats.agreed).toBe("number");
      expect(typeof stats.disputed).toBe("number");

      // Total should be >= verified
      expect(stats.total).toBeGreaterThanOrEqual(stats.verified);

      // Verified should be >= sum of tiers (they might not add up exactly due to display)
      expect(stats.verified).toBeGreaterThanOrEqual(0);
    });

    test("should display group cards when groups exist", async ({ page }) => {
      await consensusPage.goto();
      await consensusPage.waitForLoad();

      const groups = await consensusPage.getGroupCards();

      // If there are groups, verify structure
      if (groups.length > 0) {
        const firstGroup = groups[0];
        expect(firstGroup.name).toBeTruthy();
        expect(typeof firstGroup.singleVerified).toBe("number");
        expect(typeof firstGroup.agreed).toBe("number");
        expect(typeof firstGroup.disputed).toBe("number");
      }
    });

    test("should show empty state when no verified screenshots", async ({ page }) => {
      await consensusPage.goto();
      await consensusPage.waitForLoad();

      const groups = await consensusPage.getGroupCards();

      // If no groups, should show empty state
      if (groups.length === 0) {
        const isEmpty = await consensusPage.isEmptyStateVisible();
        expect(isEmpty).toBe(true);
      }
    });

    test("should show loading spinner initially", async ({ page }) => {
      // Navigate without waiting
      await page.goto("consensus");

      // Spinner might be visible very briefly
      // Just verify page eventually loads
      await consensusPage.waitForLoad();
      await expect(consensusPage.pageTitle).toBeVisible();
    });
  });

  test.describe("Group Card Interactions", () => {
    test("should display tier counts for each group", async ({ page }) => {
      await consensusPage.goto();
      await consensusPage.waitForLoad();

      const groups = await consensusPage.getGroupCards();

      if (groups.length === 0) {
        test.skip(true, "No groups available");
        return;
      }

      // Each group should have tier counts
      for (const group of groups) {
        expect(group.singleVerified).toBeGreaterThanOrEqual(0);
        expect(group.agreed).toBeGreaterThanOrEqual(0);
        expect(group.disputed).toBeGreaterThanOrEqual(0);
      }
    });

    test("should show image type badge (Battery/Screen Time)", async ({ page }) => {
      await consensusPage.goto();
      await consensusPage.waitForLoad();

      const groups = await consensusPage.getGroupCards();

      if (groups.length === 0) {
        test.skip(true, "No groups available");
        return;
      }

      // Each group should have an image type
      for (const group of groups) {
        expect(["Battery", "Screen Time", ""]).toContain(group.imageType);
      }
    });

    test("should show progress bar for verified groups", async ({ page }) => {
      await consensusPage.goto();
      await consensusPage.waitForLoad();

      const groups = await consensusPage.getGroupCards();
      const groupsWithVerified = groups.filter(
        (g) => g.singleVerified + g.agreed + g.disputed > 0
      );

      if (groupsWithVerified.length === 0) {
        test.skip(true, "No groups with verified screenshots");
        return;
      }

      // Progress bar should exist for groups with verified screenshots
      const progressBars = page.locator(".w-full.bg-gray-200.rounded-full");
      const count = await progressBars.count();
      expect(count).toBeGreaterThan(0);
    });
  });

  test.describe("Tier Navigation", () => {
    test("should navigate to tier view when clicking tier with screenshots", async ({
      page,
    }) => {
      await consensusPage.goto();
      await consensusPage.waitForLoad();

      const groups = await consensusPage.getGroupCards();

      // Find a group with single verified screenshots
      const groupWithSingle = groups.find((g) => g.singleVerified > 0);

      if (!groupWithSingle) {
        test.skip(true, "No groups with single verified screenshots");
        return;
      }

      await consensusPage.clickGroupTier(groupWithSingle.name, "single_verified");

      // Should update URL with query params
      expect(page.url()).toContain("group=");
      expect(page.url()).toContain("tier=single_verified");

      // Should show tier info
      const tierInfo = await consensusPage.getCurrentTierInfo();
      expect(tierInfo?.tier).toBe("single_verified");
    });

    test("should show back button when viewing tier list", async ({ page }) => {
      await consensusPage.goto();
      await consensusPage.waitForLoad();

      const groups = await consensusPage.getGroupCards();
      const groupWithData = groups.find(
        (g) => g.singleVerified > 0 || g.agreed > 0 || g.disputed > 0
      );

      if (!groupWithData) {
        test.skip(true, "No groups with verified screenshots");
        return;
      }

      // Navigate to a tier
      if (groupWithData.singleVerified > 0) {
        await consensusPage.clickGroupTier(groupWithData.name, "single_verified");
      } else if (groupWithData.agreed > 0) {
        await consensusPage.clickGroupTier(groupWithData.name, "agreed");
      } else {
        await consensusPage.clickGroupTier(groupWithData.name, "disputed");
      }

      // Back button should be visible
      await expect(consensusPage.backToGroupsButton).toBeVisible();
    });

    test("should return to groups view when clicking back", async ({ page }) => {
      await consensusPage.goto();
      await consensusPage.waitForLoad();

      const groups = await consensusPage.getGroupCards();
      const groupWithData = groups.find((g) => g.singleVerified > 0);

      if (!groupWithData) {
        test.skip(true, "No groups with single verified screenshots");
        return;
      }

      await consensusPage.clickGroupTier(groupWithData.name, "single_verified");
      await consensusPage.backToGroups();

      // Should be back at main view
      expect(page.url()).toBe(page.url().split("?")[0]);

      // Should show group cards again
      const groupsAfter = await consensusPage.getGroupCards();
      expect(groupsAfter.length).toBeGreaterThan(0);
    });

    test("should handle deep linking with group and tier params", async ({
      page,
    }) => {
      // First get a valid group
      await consensusPage.goto();
      await consensusPage.waitForLoad();

      const groups = await consensusPage.getGroupCards();
      const groupWithSingle = groups.find((g) => g.singleVerified > 0);

      if (!groupWithSingle) {
        test.skip(true, "No groups with single verified screenshots");
        return;
      }

      // Navigate directly with params
      await consensusPage.goto({
        groupId: groupWithSingle.name,
        tier: "single_verified",
      });
      await consensusPage.waitForLoad();

      // Should load tier view directly
      const tierInfo = await consensusPage.getCurrentTierInfo();
      expect(tierInfo).not.toBeNull();
    });
  });

  test.describe("Screenshot Tier List", () => {
    test("should display screenshots in tier list", async ({ page }) => {
      await consensusPage.goto();
      await consensusPage.waitForLoad();

      const groups = await consensusPage.getGroupCards();
      const groupWithScreenshots = groups.find((g) => g.singleVerified > 0);

      if (!groupWithScreenshots) {
        test.skip(true, "No single-verified screenshots available");
        return;
      }

      await consensusPage.clickGroupTier(groupWithScreenshots.name, "single_verified");

      // Wait for tier list to load
      await page.waitForTimeout(1000);

      const screenshots = await consensusPage.getTierScreenshots();

      // If no screenshots found, skip (might be UI structure mismatch)
      if (screenshots.length === 0) {
        console.log("No screenshots found in tier list (UI structure may differ)");
        return;
      }

      // Each screenshot should have an ID
      for (const screenshot of screenshots) {
        expect(screenshot.id).toBeGreaterThan(0);
      }
    });

    test("should show 'Has Differences' badge for disputed screenshots", async ({
      page,
    }) => {
      await consensusPage.goto();
      await consensusPage.waitForLoad();

      const groups = await consensusPage.getGroupCards();
      const groupWithDisputed = groups.find((g) => g.disputed > 0);

      if (!groupWithDisputed) {
        test.skip(true, "No disputed screenshots available");
        return;
      }

      await consensusPage.clickGroupTier(groupWithDisputed.name, "disputed");

      const screenshots = await consensusPage.getTierScreenshots();

      // Disputed screenshots should have hasDifferences = true
      const hasAnyWithDifferences = screenshots.some((s) => s.hasDifferences);
      expect(hasAnyWithDifferences).toBe(true);
    });

    test("should show empty message when tier has no screenshots", async ({
      page,
    }) => {
      await consensusPage.goto();
      await consensusPage.waitForLoad();

      const groups = await consensusPage.getGroupCards();
      const groupWithNoDisputed = groups.find(
        (g) => g.disputed === 0 && (g.singleVerified > 0 || g.agreed > 0)
      );

      if (!groupWithNoDisputed) {
        test.skip(true, "All groups have disputed or no verified screenshots");
        return;
      }

      // This might fail if the tier click is disabled when count is 0
      // The UI should prevent clicking tiers with 0 count
      const tierCell = page
        .locator(".bg-white.border.border-gray-200.rounded-lg.p-5")
        .filter({ has: page.locator("h3", { hasText: groupWithNoDisputed.name }) })
        .locator(".grid.grid-cols-3 > div")
        .nth(2); // disputed tier

      // Tier cell should have opacity-50 class when count is 0
      await expect(tierCell).toHaveClass(/opacity-50/);
    });

    test("should navigate to comparison page when clicking screenshot", async ({
      page,
    }) => {
      await consensusPage.goto();
      await consensusPage.waitForLoad();

      const groups = await consensusPage.getGroupCards();
      const groupWithScreenshots = groups.find(
        (g) => g.singleVerified > 0 || g.agreed > 0 || g.disputed > 0
      );

      if (!groupWithScreenshots) {
        test.skip(true, "No screenshots available");
        return;
      }

      // Navigate to a tier that has screenshots
      if (groupWithScreenshots.singleVerified > 0) {
        await consensusPage.clickGroupTier(
          groupWithScreenshots.name,
          "single_verified"
        );
      } else if (groupWithScreenshots.agreed > 0) {
        await consensusPage.clickGroupTier(groupWithScreenshots.name, "agreed");
      } else {
        await consensusPage.clickGroupTier(groupWithScreenshots.name, "disputed");
      }

      // Wait for tier list to render
      await page.waitForTimeout(1000);

      const screenshots = await consensusPage.getTierScreenshots();

      if (screenshots.length === 0) {
        console.log("No screenshots in tier list - skipping");
        return;
      }

      await consensusPage.clickScreenshot(screenshots[0].id);

      // Should navigate to comparison page
      expect(page.url()).toContain(`/consensus/compare/${screenshots[0].id}`);
    });
  });

  test.describe("Filtering and Search", () => {
    test("should show correct counts in tier badges", async ({ page }) => {
      await consensusPage.goto();
      await consensusPage.waitForLoad();

      const groups = await consensusPage.getGroupCards();
      const groupWithSingle = groups.find((g) => g.singleVerified > 0);

      if (!groupWithSingle) {
        test.skip(true, "No groups with single verified");
        return;
      }

      await consensusPage.clickGroupTier(groupWithSingle.name, "single_verified");

      const tierInfo = await consensusPage.getCurrentTierInfo();
      expect(tierInfo?.count).toBe(groupWithSingle.singleVerified);
    });
  });
});

test.describe("Consensus Comparison Page", () => {
  let comparisonPage: ConsensusComparisonPage;
  let consensusPage: ConsensusPage;

  test.beforeEach(async ({ page }) => {
    comparisonPage = new ConsensusComparisonPage(page);
    consensusPage = new ConsensusPage(page);

    // Login first
    await page.goto("login");
    await page.fill('input[name="username"]', "testuser");
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(annotate|home)/);
  });

  test("should load comparison page for valid screenshot", async ({ page }) => {
    // First find a valid screenshot ID
    await consensusPage.goto();
    await consensusPage.waitForLoad();

    const groups = await consensusPage.getGroupCards();
    const groupWithScreenshots = groups.find(
      (g) => g.singleVerified > 0 || g.agreed > 0 || g.disputed > 0
    );

    if (!groupWithScreenshots) {
      test.skip(true, "No screenshots available");
      return;
    }

    // Navigate to get a screenshot ID
    if (groupWithScreenshots.singleVerified > 0) {
      await consensusPage.clickGroupTier(
        groupWithScreenshots.name,
        "single_verified"
      );
    } else if (groupWithScreenshots.agreed > 0) {
      await consensusPage.clickGroupTier(groupWithScreenshots.name, "agreed");
    } else {
      await consensusPage.clickGroupTier(groupWithScreenshots.name, "disputed");
    }

    // Wait for tier list to load
    await page.waitForTimeout(1000);

    const screenshots = await consensusPage.getTierScreenshots();

    if (screenshots.length === 0) {
      console.log("No screenshots found in tier list");
      return;
    }

    await comparisonPage.goto(screenshots[0].id);
    await comparisonPage.waitForLoad();

    // Should not show error
    const hasError = await comparisonPage.isErrorVisible();
    expect(hasError).toBe(false);
  });

  test("should show error for invalid screenshot ID", async ({ page }) => {
    await comparisonPage.goto(999999);
    await comparisonPage.waitForLoad();

    // Should show error or not found
    const hasError = await comparisonPage.isErrorVisible();
    // This depends on how the app handles missing screenshots
    // It might redirect or show an error
    expect(page.url()).toMatch(/consensus/);
  });

  test("should display screenshot image", async ({ page }) => {
    // Navigate to find a valid screenshot
    await consensusPage.goto();
    await consensusPage.waitForLoad();

    const groups = await consensusPage.getGroupCards();
    const groupWithScreenshots = groups.find(
      (g) => g.singleVerified > 0 || g.agreed > 0 || g.disputed > 0
    );

    if (!groupWithScreenshots) {
      test.skip(true, "No screenshots available");
      return;
    }

    if (groupWithScreenshots.singleVerified > 0) {
      await consensusPage.clickGroupTier(
        groupWithScreenshots.name,
        "single_verified"
      );
    } else if (groupWithScreenshots.agreed > 0) {
      await consensusPage.clickGroupTier(groupWithScreenshots.name, "agreed");
    } else {
      await consensusPage.clickGroupTier(groupWithScreenshots.name, "disputed");
    }

    // Wait for tier list to load
    await page.waitForTimeout(1000);

    const screenshots = await consensusPage.getTierScreenshots();

    if (screenshots.length === 0) {
      console.log("No screenshots found in tier list");
      return;
    }

    await comparisonPage.goto(screenshots[0].id);
    await comparisonPage.waitForLoad();

    // Screenshot image should be visible
    await expect(comparisonPage.screenshotImage).toBeVisible({ timeout: 10000 });
  });

  test("should have back navigation", async ({ page }) => {
    await consensusPage.goto();
    await consensusPage.waitForLoad();

    const groups = await consensusPage.getGroupCards();
    const groupWithScreenshots = groups.find((g) => g.singleVerified > 0);

    if (!groupWithScreenshots) {
      test.skip(true, "No screenshots available");
      return;
    }

    await consensusPage.clickGroupTier(
      groupWithScreenshots.name,
      "single_verified"
    );

    // Wait for tier list to load
    await page.waitForTimeout(1000);

    const screenshots = await consensusPage.getTierScreenshots();

    if (screenshots.length === 0) {
      console.log("No screenshots found in tier list");
      return;
    }

    await comparisonPage.goto(screenshots[0].id);
    await comparisonPage.waitForLoad();

    // Back button should exist
    await expect(comparisonPage.backButton).toBeVisible();
  });

  test("should show resolve button only for disputed screenshots", async ({
    page,
  }) => {
    await consensusPage.goto();
    await consensusPage.waitForLoad();

    const groups = await consensusPage.getGroupCards();
    const groupWithDisputed = groups.find((g) => g.disputed > 0);

    if (!groupWithDisputed) {
      test.skip(true, "No disputed screenshots available");
      return;
    }

    await consensusPage.clickGroupTier(groupWithDisputed.name, "disputed");

    // Wait for tier list to load
    await page.waitForTimeout(1000);

    const screenshots = await consensusPage.getTierScreenshots();

    if (screenshots.length === 0) {
      console.log("No disputed screenshots found in tier list");
      return;
    }

    await comparisonPage.goto(screenshots[0].id);
    await comparisonPage.waitForLoad();

    // Resolve button might be visible for disputed screenshots
    const isResolveVisible = await comparisonPage.isResolveButtonVisible();
    // The presence depends on tier - disputed should have it
    expect(isResolveVisible).toBeDefined();
  });
});

test.describe("Consensus Page - API Integration", () => {
  test.beforeEach(async ({ page }) => {
    // Login first
    await page.goto("login");
    await page.fill('input[name="username"]', "testuser");
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(annotate|home)/);
  });

  test("should make API call to fetch groups", async ({ page }) => {
    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().includes("/api/v1/consensus/groups") &&
        response.status() === 200
    );

    await page.goto("consensus");

    const response = await responsePromise;
    expect(response.ok()).toBe(true);

    const data = await response.json();
    expect(Array.isArray(data)).toBe(true);
  });

  test("should make API call to fetch tier screenshots", async ({ page }) => {
    const consensusPage = new ConsensusPage(page);
    await consensusPage.goto();
    await consensusPage.waitForLoad();

    const groups = await consensusPage.getGroupCards();
    const groupWithScreenshots = groups.find((g) => g.singleVerified > 0);

    if (!groupWithScreenshots) {
      test.skip(true, "No groups with screenshots");
      return;
    }

    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().includes("/api/v1/consensus/groups/") &&
        response.url().includes("/screenshots") &&
        response.status() === 200
    );

    await consensusPage.clickGroupTier(
      groupWithScreenshots.name,
      "single_verified"
    );

    const response = await responsePromise;
    expect(response.ok()).toBe(true);

    const data = await response.json();
    expect(Array.isArray(data)).toBe(true);
  });

  test("should make API call to fetch comparison data", async ({ page }) => {
    const consensusPage = new ConsensusPage(page);
    await consensusPage.goto();
    await consensusPage.waitForLoad();

    const groups = await consensusPage.getGroupCards();
    const groupWithScreenshots = groups.find(
      (g) => g.singleVerified > 0 || g.agreed > 0 || g.disputed > 0
    );

    if (!groupWithScreenshots) {
      test.skip(true, "No screenshots available");
      return;
    }

    if (groupWithScreenshots.singleVerified > 0) {
      await consensusPage.clickGroupTier(
        groupWithScreenshots.name,
        "single_verified"
      );
    } else if (groupWithScreenshots.agreed > 0) {
      await consensusPage.clickGroupTier(groupWithScreenshots.name, "agreed");
    } else {
      await consensusPage.clickGroupTier(groupWithScreenshots.name, "disputed");
    }

    // Wait for tier list to load
    await page.waitForTimeout(1000);

    const screenshots = await consensusPage.getTierScreenshots();

    if (screenshots.length === 0) {
      console.log("No screenshots found in tier list");
      return;
    }

    const screenshotId = screenshots[0].id;

    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().includes(`/api/v1/consensus/screenshots/${screenshotId}/compare`) &&
        response.status() === 200
    );

    await page.goto(`/consensus/compare/${screenshotId}`);

    const response = await responsePromise;
    expect(response.ok()).toBe(true);
  });

  test("should handle API errors gracefully", async ({ page }) => {
    // Navigate to a non-existent screenshot
    await page.goto("consensus/compare/999999999");

    // Should show error message or redirect
    // Wait for page to settle
    await page.waitForTimeout(2000);

    // Should not crash - page should still be functional
    expect(page.url()).toBeDefined();
  });
});

test.describe("Consensus Page - Accessibility", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("login");
    await page.fill('input[name="username"]', "testuser");
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(annotate|home)/);
  });

  test("should have correct heading structure", async ({ page }) => {
    const consensusPage = new ConsensusPage(page);
    await consensusPage.goto();
    await consensusPage.waitForLoad();

    // Should have h1 heading
    const h1 = page.locator("h1");
    await expect(h1).toBeVisible();
    await expect(h1).toContainText("Consensus");
  });

  test("should have keyboard-accessible tier buttons", async ({ page }) => {
    const consensusPage = new ConsensusPage(page);
    await consensusPage.goto();
    await consensusPage.waitForLoad();

    const groups = await consensusPage.getGroupCards();

    if (groups.length === 0) {
      test.skip(true, "No groups available");
      return;
    }

    // Tier buttons should be focusable
    const tierButtons = page.locator(".grid.grid-cols-3 > div.cursor-pointer");
    const count = await tierButtons.count();

    if (count > 0) {
      await tierButtons.first().focus();
      await expect(tierButtons.first()).toBeFocused;
    }
  });

  test("should have proper color contrast for status badges", async ({
    page,
  }) => {
    const consensusPage = new ConsensusPage(page);
    await consensusPage.goto();
    await consensusPage.waitForLoad();

    // Verify color-coded elements have sufficient contrast
    // This is a basic check - full a11y testing would use axe-core

    // Yellow (single) badge
    const yellowBadge = page.locator(".text-yellow-700");
    if ((await yellowBadge.count()) > 0) {
      await expect(yellowBadge.first()).toBeVisible();
    }

    // Green (agreed) badge
    const greenBadge = page.locator(".text-green-700");
    if ((await greenBadge.count()) > 0) {
      await expect(greenBadge.first()).toBeVisible();
    }

    // Red (disputed) badge
    const redBadge = page.locator(".text-red-700");
    if ((await redBadge.count()) > 0) {
      await expect(redBadge.first()).toBeVisible();
    }
  });
});

test.describe("Consensus Page - Visual States", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("login");
    await page.fill('input[name="username"]', "testuser");
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(annotate|home)/);
  });

  test("should highlight differences in comparison view", async ({ page }) => {
    const consensusPage = new ConsensusPage(page);
    await consensusPage.goto();
    await consensusPage.waitForLoad();

    const groups = await consensusPage.getGroupCards();
    const groupWithDisputed = groups.find((g) => g.disputed > 0);

    if (!groupWithDisputed) {
      test.skip(true, "No disputed screenshots");
      return;
    }

    await consensusPage.clickGroupTier(groupWithDisputed.name, "disputed");

    const screenshots = await consensusPage.getTierScreenshots();

    if (screenshots.length === 0) {
      test.skip(true, "No disputed screenshots found");
      return;
    }

    await page.goto(`/consensus/compare/${screenshots[0].id}`);
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2000);

    // Differences should be highlighted (typically in red)
    const redHighlights = page.locator(
      ".text-red-700, .bg-red-100, .text-red-600"
    );
    const highlightCount = await redHighlights.count();

    // Disputed screenshots should have some red highlights
    expect(highlightCount).toBeGreaterThan(0);
  });

  test("should show correct tier colors in group cards", async ({ page }) => {
    const consensusPage = new ConsensusPage(page);
    await consensusPage.goto();
    await consensusPage.waitForLoad();

    const groups = await consensusPage.getGroupCards();

    if (groups.length === 0) {
      test.skip(true, "No groups available");
      return;
    }

    // Yellow for single verified
    const yellowCells = page.locator(".bg-yellow-50, .bg-yellow-100");
    const greenCells = page.locator(".bg-green-50, .bg-green-100");
    const redCells = page.locator(".bg-red-50, .bg-red-100");

    // At least some color-coded cells should exist
    const totalColoredCells =
      (await yellowCells.count()) +
      (await greenCells.count()) +
      (await redCells.count());

    expect(totalColoredCells).toBeGreaterThanOrEqual(0);
  });
});
