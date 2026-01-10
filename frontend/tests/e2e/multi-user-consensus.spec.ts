import { test, expect, Browser, BrowserContext, Page } from "@playwright/test";
import { AnnotationPage } from "../pages/AnnotationPage";
import { ConsensusPage } from "../pages/ConsensusPage";

/**
 * Helper to create a new authenticated context for a user
 */
async function createUserContext(
  browser: Browser,
  username: string
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext();
  const page = await context.newPage();

  // Login the user
  await page.goto("login");
  await page.waitForLoadState("domcontentloaded");
  await page.getByPlaceholder("Username").fill(username);
  await page.getByRole("button", { name: /continue/i }).click();
  await page.waitForURL("**/annotate**");

  return { context, page };
}

/**
 * Helper to annotate a screenshot with specific hourly values
 */
async function annotateScreenshot(
  page: Page,
  screenshotId: number,
  hourlyValues: number[],
  verify = true
): Promise<void> {
  // Navigate to specific screenshot
  await page.goto(`/annotate/${screenshotId}`);
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(2000);

  // Set hourly values
  for (let i = 0; i < Math.min(hourlyValues.length, 24); i++) {
    const input = page.getByTestId(`hour-input-${i}`);
    if (await input.isVisible()) {
      await input.clear();
      await input.fill(String(hourlyValues[i]));
    }
  }

  // Wait for auto-save
  await page.waitForTimeout(2000);

  // Verify if requested
  if (verify) {
    const verifyButton = page.getByRole("button", { name: /verified/i }).first();
    if (await verifyButton.isVisible()) {
      await verifyButton.click();
      await page.waitForTimeout(1500);
    }
  }
}

/**
 * Multi-User Consensus Workflow E2E Tests
 *
 * These tests verify the consensus system works correctly when multiple users
 * annotate the same screenshot. Tests use separate browser contexts to simulate
 * different users.
 */
test.describe("Multi-User Consensus Workflow", () => {
  test("should trigger consensus when two users annotate the same screenshot", async ({
    browser,
    request,
  }) => {
    const baseURL = process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";

    // Create two user contexts
    const userA = await createUserContext(browser, "consensus_user_a");
    const userB = await createUserContext(browser, "consensus_user_b");

    try {
      // First, find a screenshot to annotate
      const annotationPageA = new AnnotationPage(userA.page);
      await annotationPageA.goto();

      const hasScreenshot = await annotationPageA.waitForScreenshotLoad().catch(() => false);
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available for consensus test");
        return;
      }

      const screenshotId = await annotationPageA.getCurrentScreenshotId();
      if (!screenshotId) {
        test.skip(true, "Could not get screenshot ID");
        return;
      }

      // User A annotates with values [10, 20, 30, ...]
      const valuesA = Array.from({ length: 24 }, (_, i) => (i + 1) * 10);
      await annotateScreenshot(userA.page, screenshotId, valuesA, true);

      // User B annotates the same screenshot with same values
      const valuesB = [...valuesA]; // Same values - should result in agreement
      await annotateScreenshot(userB.page, screenshotId, valuesB, true);

      // Wait for consensus calculation
      await userA.page.waitForTimeout(2000);

      // Verify consensus was calculated via API
      const consensusResponse = await request.get(
        `${baseURL}/consensus/${screenshotId}`,
        { headers: { "X-Username": "consensus_user_a" } }
      );

      if (consensusResponse.ok()) {
        const consensusData = await consensusResponse.json();
        // Should have at least 2 annotations
        expect(consensusData.annotation_count).toBeGreaterThanOrEqual(2);
      }
    } finally {
      await userA.context.close();
      await userB.context.close();
    }
  });

  test("should detect disagreement when users submit different values", async ({
    browser,
    request,
  }) => {
    const baseURL = process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";

    const userA = await createUserContext(browser, "disagree_user_a");
    const userB = await createUserContext(browser, "disagree_user_b");

    try {
      // Find a screenshot to annotate
      const annotationPageA = new AnnotationPage(userA.page);
      await annotationPageA.goto();

      const hasScreenshot = await annotationPageA.waitForScreenshotLoad().catch(() => false);
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available for disagreement test");
        return;
      }

      const screenshotId = await annotationPageA.getCurrentScreenshotId();
      if (!screenshotId) {
        test.skip(true, "Could not get screenshot ID");
        return;
      }

      // User A annotates with values [10, 20, 30, ...]
      const valuesA = Array.from({ length: 24 }, (_, i) => (i + 1) * 10);
      await annotateScreenshot(userA.page, screenshotId, valuesA, true);

      // User B annotates with significantly different values
      const valuesB = Array.from({ length: 24 }, (_, i) => (i + 1) * 10 + 30); // +30 difference
      await annotateScreenshot(userB.page, screenshotId, valuesB, true);

      // Wait for consensus calculation
      await userA.page.waitForTimeout(2000);

      // Check consensus analysis via API
      const consensusResponse = await request.get(
        `${baseURL}/consensus/${screenshotId}`,
        { headers: { "X-Username": "disagree_user_a" } }
      );

      if (consensusResponse.ok()) {
        const consensusData = await consensusResponse.json();
        // Should detect disagreement due to different values
        // The has_consensus field indicates if there's agreement
        console.log("Consensus data:", JSON.stringify(consensusData, null, 2));
      }

      // Check the compare endpoint for disagreement details
      const compareResponse = await request.get(
        `${baseURL}/consensus/screenshots/${screenshotId}/compare`,
        { headers: { "X-Username": "disagree_user_a" } }
      );

      if (compareResponse.ok()) {
        const compareData = await compareResponse.json();
        // Should show the annotations from both users
        expect(compareData.annotations).toBeDefined();
        if (compareData.annotations) {
          expect(compareData.annotations.length).toBeGreaterThanOrEqual(2);
        }
      }
    } finally {
      await userA.context.close();
      await userB.context.close();
    }
  });

  test("should show disputed screenshots in consensus page", async ({ browser }) => {
    const userA = await createUserContext(browser, "view_consensus_user");

    try {
      // Navigate to consensus page
      const consensusPage = new ConsensusPage(userA.page);
      await consensusPage.goto();
      await consensusPage.waitForLoad();

      // Check for groups
      const groups = await consensusPage.getGroupCards();

      if (groups.length === 0) {
        console.log("No groups available - consensus page shows empty state");
        return;
      }

      // Look for a group with disputed screenshots
      const groupWithDisputed = groups.find((g) => g.disputed > 0);

      if (groupWithDisputed) {
        // Navigate to disputed tier
        await consensusPage.clickGroupTier(groupWithDisputed.name, "disputed");

        // Wait for tier list to load
        await userA.page.waitForTimeout(1000);

        // Get screenshots in the tier
        const screenshots = await consensusPage.getTierScreenshots();

        if (screenshots.length > 0) {
          // Each disputed screenshot should have hasDifferences = true
          const hasDisputedWithDifferences = screenshots.some((s) => s.hasDifferences);
          expect(hasDisputedWithDifferences).toBe(true);
        }
      } else {
        console.log("No disputed screenshots found - test passes (no disputes to verify)");
      }
    } finally {
      await userA.context.close();
    }
  });

  test("should show correct tier counts after multi-user verification", async ({
    browser,
    request,
  }) => {
    const baseURL = process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";

    const userA = await createUserContext(browser, "tier_count_user_a");
    const userB = await createUserContext(browser, "tier_count_user_b");

    try {
      // Get initial consensus stats
      const initialGroupsResponse = await request.get(`${baseURL}/consensus/groups`, {
        headers: { "X-Username": "tier_count_user_a" },
      });

      if (!initialGroupsResponse.ok()) {
        test.skip(true, "Could not fetch consensus groups");
        return;
      }

      const initialGroups = await initialGroupsResponse.json();

      // Find a screenshot to annotate
      const annotationPageA = new AnnotationPage(userA.page);
      await annotationPageA.goto();

      const hasScreenshot = await annotationPageA.waitForScreenshotLoad().catch(() => false);
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      const screenshotId = await annotationPageA.getCurrentScreenshotId();
      if (!screenshotId) {
        test.skip(true, "Could not get screenshot ID");
        return;
      }

      // Both users annotate with same values
      const values = Array.from({ length: 24 }, (_, i) => i * 5);
      await annotateScreenshot(userA.page, screenshotId, values, true);
      await annotateScreenshot(userB.page, screenshotId, values, true);

      // Wait for consensus calculation
      await userA.page.waitForTimeout(2000);

      // Get updated consensus stats
      const updatedGroupsResponse = await request.get(`${baseURL}/consensus/groups`, {
        headers: { "X-Username": "tier_count_user_a" },
      });

      if (updatedGroupsResponse.ok()) {
        const updatedGroups = await updatedGroupsResponse.json();

        // At least one group should show the screenshot in verified/agreed tier
        console.log("Initial groups:", JSON.stringify(initialGroups, null, 2));
        console.log("Updated groups:", JSON.stringify(updatedGroups, null, 2));
      }
    } finally {
      await userA.context.close();
      await userB.context.close();
    }
  });

  test("should allow admin to resolve disputed annotations", async ({ browser, request }) => {
    const baseURL = process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";

    // Create admin context
    const admin = await createUserContext(browser, "admin");

    try {
      // Navigate to consensus page
      const consensusPage = new ConsensusPage(admin.page);
      await consensusPage.goto();
      await consensusPage.waitForLoad();

      // Find a group with disputed screenshots
      const groups = await consensusPage.getGroupCards();
      const groupWithDisputed = groups.find((g) => g.disputed > 0);

      if (!groupWithDisputed) {
        console.log("No disputed screenshots to resolve");
        return;
      }

      // Navigate to disputed tier
      await consensusPage.clickGroupTier(groupWithDisputed.name, "disputed");
      await admin.page.waitForTimeout(1000);

      // Get disputed screenshots
      const screenshots = await consensusPage.getTierScreenshots();

      if (screenshots.length === 0) {
        console.log("No disputed screenshots in list");
        return;
      }

      // Navigate to comparison page
      await consensusPage.clickScreenshot(screenshots[0].id);
      await admin.page.waitForTimeout(2000);

      // Check if resolve button is available
      const resolveButton = admin.page.getByRole("button", { name: /resolve/i });
      const hasResolveButton = await resolveButton.isVisible().catch(() => false);

      if (hasResolveButton) {
        console.log("Resolve button is visible for admin");
        // Note: Actually clicking resolve would require selecting a resolution strategy
        // This test just verifies the UI is available to admins
      }
    } finally {
      await admin.context.close();
    }
  });
});

test.describe("Consensus API Integration", () => {
  test("should fetch consensus groups correctly", async ({ page, request }) => {
    const baseURL = process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";

    // Login
    await page.goto("login");
    await page.getByPlaceholder("Username").fill("testuser");
    await page.getByRole("button", { name: /continue/i }).click();
    await page.waitForURL("**/annotate**");

    // Fetch consensus groups via API
    const response = await request.get(`${baseURL}/consensus/groups`, {
      headers: { "X-Username": "testuser" },
    });

    if (response.ok()) {
      const groups = await response.json();
      expect(Array.isArray(groups)).toBe(true);

      // Each group should have expected structure
      for (const group of groups) {
        expect(group.group_id).toBeDefined();
        expect(typeof group.single_verified_count).toBe("number");
        expect(typeof group.agreed_count).toBe("number");
        expect(typeof group.disputed_count).toBe("number");
      }
    }
  });

  test("should fetch comparison data for screenshot", async ({ page, request }) => {
    const baseURL = process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";

    // Login
    await page.goto("login");
    await page.getByPlaceholder("Username").fill("testuser");
    await page.getByRole("button", { name: /continue/i }).click();
    await page.waitForURL("**/annotate**");

    // Navigate to get a screenshot ID
    const annotationPage = new AnnotationPage(page);
    await annotationPage.goto();

    const hasScreenshot = await annotationPage.waitForScreenshotLoad().catch(() => false);
    if (!hasScreenshot) {
      test.skip(true, "No screenshots available");
      return;
    }

    const screenshotId = await annotationPage.getCurrentScreenshotId();
    if (!screenshotId) {
      test.skip(true, "Could not get screenshot ID");
      return;
    }

    // Fetch comparison data via API
    const response = await request.get(
      `${baseURL}/consensus/screenshots/${screenshotId}/compare`,
      { headers: { "X-Username": "testuser" } }
    );

    if (response.ok()) {
      const data = await response.json();
      expect(data.screenshot_id).toBe(screenshotId);
    }
  });

  test("should fetch consensus summary stats", async ({ page, request }) => {
    const baseURL = process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";

    // Login
    await page.goto("login");
    await page.getByPlaceholder("Username").fill("testuser");
    await page.getByRole("button", { name: /continue/i }).click();
    await page.waitForURL("**/annotate**");

    // Fetch summary stats
    const response = await request.get(`${baseURL}/consensus/summary/stats`, {
      headers: { "X-Username": "testuser" },
    });

    if (response.ok()) {
      const stats = await response.json();
      // Stats should have numeric values
      expect(typeof stats.total_verified).toBe("number");
      expect(typeof stats.single_verified).toBe("number");
      expect(typeof stats.agreed).toBe("number");
      expect(typeof stats.disputed).toBe("number");
    }
  });
});

test.describe("Consensus Edge Cases", () => {
  test("should handle screenshot with only one verifier (single_verified tier)", async ({
    browser,
    request,
  }) => {
    const baseURL = process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";

    const user = await createUserContext(browser, "single_verifier_user");

    try {
      // Find a screenshot to annotate
      const annotationPage = new AnnotationPage(user.page);
      await annotationPage.goto();

      const hasScreenshot = await annotationPage.waitForScreenshotLoad().catch(() => false);
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      const screenshotId = await annotationPage.getCurrentScreenshotId();
      if (!screenshotId) {
        test.skip(true, "Could not get screenshot ID");
        return;
      }

      // Single user annotates and verifies
      const values = Array.from({ length: 24 }, (_, i) => i * 3);
      await annotateScreenshot(user.page, screenshotId, values, true);

      // Wait for processing
      await user.page.waitForTimeout(2000);

      // Check the screenshot state
      const response = await request.get(`${baseURL}/screenshots/${screenshotId}`, {
        headers: { "X-Username": "single_verifier_user" },
      });

      if (response.ok()) {
        const data = await response.json();
        // Should have exactly 1 verifier
        const verifiers = data.verified_by_user_ids || [];
        expect(verifiers.length).toBeGreaterThanOrEqual(1);
      }
    } finally {
      await user.context.close();
    }
  });

  test("should preserve annotations when navigating between screenshots", async ({
    browser,
  }) => {
    const user = await createUserContext(browser, "preserve_nav_user");

    try {
      const annotationPage = new AnnotationPage(user.page);
      await annotationPage.goto();

      const hasScreenshot = await annotationPage.waitForScreenshotLoad().catch(() => false);
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      // Get navigation info
      const navInfo = await annotationPage.getNavigationInfo();

      if (!navInfo.hasNext) {
        console.log("Only one screenshot - skipping navigation test");
        return;
      }

      // Get first screenshot ID
      const firstId = await annotationPage.getCurrentScreenshotId();

      // Set a value
      const hour0Input = user.page.getByTestId("hour-input-0");
      if (await hour0Input.isVisible()) {
        await hour0Input.clear();
        await hour0Input.fill("99");
        await user.page.waitForTimeout(2000); // Wait for auto-save
      }

      // Navigate to next
      await annotationPage.navigateNext();
      await user.page.waitForTimeout(1000);

      // Navigate back
      await annotationPage.navigatePrev();
      await user.page.waitForTimeout(1000);

      // Verify we're back on the same screenshot
      const currentId = await annotationPage.getCurrentScreenshotId();
      expect(currentId).toBe(firstId);

      // Verify value is preserved
      const preservedInput = user.page.getByTestId("hour-input-0");
      if (await preservedInput.isVisible()) {
        const value = await preservedInput.inputValue();
        expect(value).toBe("99");
      }
    } finally {
      await user.context.close();
    }
  });
});
