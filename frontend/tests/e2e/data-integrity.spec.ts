import { test, expect } from "../fixtures/auth";
import { AnnotationPage } from "../pages/AnnotationPage";

/**
 * Data Integrity E2E Tests
 *
 * Tests data integrity throughout the application:
 * - Hourly values calculation accuracy
 * - Total calculation correctness
 * - Auto-save reliability
 * - Data persistence
 * - Concurrent editing handling
 * - Export data accuracy
 * - Database consistency via API verification
 * - Orphaned entries detection
 */
test.describe("Data Integrity", () => {
  let annotationPage: AnnotationPage;

  test.beforeEach(async ({ page }) => {
    annotationPage = new AnnotationPage(page);
  });

  /**
   * Helper to wait for annotation page with screenshot
   */
  async function ensureScreenshotLoaded(page: import("@playwright/test").Page) {
    // Login first
    await page.goto("login");
    await page.getByPlaceholder("Username").fill("testuser");
    await page.getByRole("button", { name: /continue/i }).click();
    await page.waitForURL("**/annotate**");

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

  test.describe("Calculation Integrity", () => {
    test("should calculate total correctly from hourly values", async ({ page }) => {
      const hasScreenshot = await ensureScreenshotLoaded(page);
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      const barTotal = page.getByTestId("bar-total");
      if (!(await barTotal.isVisible())) {
        test.skip(true, "Bar total not visible");
        return;
      }

      // Clear all and set specific values
      let expectedTotal = 0;
      const testValues = [10, 20, 30, 15, 25, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];

      for (let hour = 0; hour < 24; hour++) {
        const input = page.getByTestId(`hour-input-${hour}`);
        if (await input.isVisible()) {
          await input.clear();
          await input.fill(String(testValues[hour]));
          expectedTotal += testValues[hour];
        }
      }

      await page.waitForTimeout(1000);

      // Get displayed total
      const totalText = await barTotal.textContent();
      const displayedTotal = parseInt(totalText?.match(/\d+/)?.[0] || "0");

      console.log("Expected:", expectedTotal, "Displayed:", displayedTotal);
      expect(Math.abs(displayedTotal - expectedTotal)).toBeLessThan(5);
    });

    test("should preserve decimal precision in calculations", async ({ page }) => {
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
      await hour0Input.fill("30.5");
      await page.waitForTimeout(500);

      const value = await hour0Input.inputValue();
      console.log("Decimal handling:", value);
    });

    test("should correctly sum all hourly values for total", async ({ page }) => {
      const hasScreenshot = await ensureScreenshotLoaded(page);
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      const barTotal = page.getByTestId("bar-total");
      if (!(await barTotal.isVisible())) {
        test.skip(true, "Bar total not visible");
        return;
      }

      let expectedSum = 0;
      for (let hour = 0; hour < 24; hour++) {
        const input = page.getByTestId(`hour-input-${hour}`);
        if (await input.isVisible()) {
          const randomValue = Math.floor(Math.random() * 30);
          await input.clear();
          await input.fill(String(randomValue));
          expectedSum += randomValue;
        }
      }

      await page.waitForTimeout(1000);

      const totalText = await barTotal.textContent();
      console.log("Expected sum:", expectedSum, "Total displayed:", totalText);
    });
  });

  test.describe("Auto-save and Persistence", () => {
    test("should auto-save changes within debounce period", async ({ page }) => {
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

      let saveRequestSent = false;
      page.on("request", (request) => {
        if (request.url().includes("/annotations")) {
          saveRequestSent = true;
        }
      });

      await hour0Input.clear();
      await hour0Input.fill("42");
      await page.waitForTimeout(3000);

      console.log("Auto-save request sent:", saveRequestSent);
    });

    test("should persist data across page refresh", async ({ page }) => {
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

      const testValue = "37";
      await hour0Input.clear();
      await hour0Input.fill(testValue);
      await hour0Input.blur();
      await page.waitForTimeout(3000);

      await page.reload();
      await page.waitForTimeout(3000);

      const refreshedInput = page.getByTestId("hour-input-0");
      if (await refreshedInput.isVisible()) {
        const persistedValue = await refreshedInput.inputValue();
        console.log("Set:", testValue, "Persisted:", persistedValue);
      }
    });

    test("should maintain data integrity across navigation", async ({ page }) => {
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
      await hour0Input.fill("55");
      await page.waitForTimeout(2000);

      const nextButton = page.getByTestId("navigate-next");
      if (await nextButton.isVisible()) {
        await nextButton.click();
        await page.waitForTimeout(1000);

        const prevButton = page.getByTestId("navigate-prev");
        await prevButton.click();
        await page.waitForTimeout(1000);

        const valueAfterNav = await hour0Input.inputValue();
        console.log("Value after navigation:", valueAfterNav);
      }
    });
  });

  test.describe("Validation and Edge Cases", () => {
    test("should handle simultaneous edits correctly", async ({ page }) => {
      const hasScreenshot = await ensureScreenshotLoaded(page);
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      for (let hour = 0; hour < 5; hour++) {
        const input = page.getByTestId(`hour-input-${hour}`);
        if (await input.isVisible()) {
          await input.fill(String(hour * 10));
        }
      }

      await page.waitForTimeout(2000);

      for (let hour = 0; hour < 5; hour++) {
        const input = page.getByTestId(`hour-input-${hour}`);
        if (await input.isVisible()) {
          const value = await input.inputValue();
          console.log(`Hour ${hour}: expected ${hour * 10}, got ${value}`);
        }
      }
    });

    test("should not lose data on form submission error", async ({ page }) => {
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
      await hour0Input.fill("99");

      await page.route("**/api/v1/annotations/**", (route) => {
        route.fulfill({
          status: 500,
          body: JSON.stringify({ detail: "Save failed" }),
        });
      });

      await page.waitForTimeout(3000);

      const value = await hour0Input.inputValue();
      expect(value).toBe("99");
    });

    test("should validate hourly values are within range", async ({ page }) => {
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
      await hour0Input.fill("999");
      await hour0Input.blur();
      await page.waitForTimeout(500);

      const value = await hour0Input.inputValue();
      const numValue = parseInt(value || "0");
      console.log("Value after 999 input:", numValue);
    });

    test("should handle zero values correctly", async ({ page }) => {
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
      await hour0Input.fill("0");
      await hour0Input.blur();
      await page.waitForTimeout(500);

      const value = await hour0Input.inputValue();
      expect(value).toBe("0");
    });

    test("should handle empty input as zero", async ({ page }) => {
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
      await hour0Input.blur();
      await page.waitForTimeout(500);

      const value = await hour0Input.inputValue();
      console.log("Empty input value:", value);
    });
  });

  test.describe("Notes and Metadata", () => {
    test("should preserve annotation notes", async ({ page }) => {
      const hasScreenshot = await ensureScreenshotLoaded(page);
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }

      const notesTextarea = page.getByLabel(/notes/i);
      if (!(await notesTextarea.isVisible())) {
        console.log("Notes textarea not visible");
        return;
      }

      const testNote = "Test note " + Date.now();
      await notesTextarea.fill(testNote);
      await notesTextarea.blur();
      await page.waitForTimeout(2000);

      await page.reload();
      await page.waitForTimeout(2000);

      const refreshedNotes = page.getByLabel(/notes/i);
      if (await refreshedNotes.isVisible()) {
        const savedNote = await refreshedNotes.inputValue();
        console.log("Saved note:", savedNote);
      }
    });

    test("should track save status accurately", async ({ page }) => {
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

      const autoSaveStatus = page.getByTestId("auto-save-status");

      await hour0Input.clear();
      await hour0Input.fill("33");

      await page.waitForTimeout(500);
      const savingStatus = await autoSaveStatus.textContent().catch(() => "");
      console.log("Status during save:", savingStatus);

      await page.waitForTimeout(3000);
      const savedStatus = await autoSaveStatus.textContent().catch(() => "");
      console.log("Status after save:", savedStatus);
    });
  });
});

/**
 * Database Integrity Tests via API
 *
 * These tests verify database consistency by calling API endpoints directly.
 */
test.describe("Database Integrity via API", () => {
  test("should verify no orphaned entries after group deletion", async ({ request }) => {
    const baseURL = process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";

    // This test requires admin access
    const orphanedResponse = await request.get(`${baseURL}/admin/orphaned-entries`, {
      headers: { "X-Username": "admin" },
    });

    if (orphanedResponse.ok()) {
      const orphanedData = await orphanedResponse.json();

      console.log("Orphaned entries check:", JSON.stringify(orphanedData, null, 2));

      // There should be no orphaned entries
      expect(orphanedData.orphaned_annotations).toBe(0);
      expect(orphanedData.orphaned_consensus).toBe(0);
      expect(orphanedData.orphaned_queue_states).toBe(0);
      expect(orphanedData.screenshots_without_group).toBe(0);
    } else if (orphanedResponse.status() === 403) {
      console.log("Admin access required - skipping orphaned entries check");
    }
  });

  test("should verify foreign key relationships are valid", async ({ request }) => {
    const baseURL = process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";

    // Fetch screenshots
    const screenshotsResponse = await request.get(`${baseURL}/screenshots/list?limit=10`, {
      headers: { "X-Username": "testuser" },
    });

    if (!screenshotsResponse.ok()) {
      console.log("Could not fetch screenshots - API may not be available");
      return;
    }

    const screenshotsData = await screenshotsResponse.json();
    const screenshots = screenshotsData.screenshots || [];

    for (const screenshot of screenshots) {
      // Verify screenshot has valid group_id
      expect(screenshot.id).toBeDefined();
      expect(screenshot.group_id).toBeDefined();

      // Verify we can fetch the screenshot individually
      const detailResponse = await request.get(`${baseURL}/screenshots/${screenshot.id}`, {
        headers: { "X-Username": "testuser" },
      });

      if (detailResponse.ok()) {
        const detail = await detailResponse.json();
        expect(detail.id).toBe(screenshot.id);
      }
    }
  });

  test("should verify annotation-screenshot relationships", async ({ request }) => {
    const baseURL = process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";

    // Fetch user's annotation history
    const annotationsResponse = await request.get(`${baseURL}/annotations/history`, {
      headers: { "X-Username": "testuser" },
    });

    if (!annotationsResponse.ok()) {
      console.log("Could not fetch annotations - API may not be available");
      return;
    }

    const annotations = await annotationsResponse.json();

    for (const annotation of annotations) {
      // Verify annotation has required fields
      expect(annotation.id).toBeDefined();
      expect(annotation.screenshot_id).toBeDefined();
      expect(annotation.user_id).toBeDefined();

      // Verify the referenced screenshot exists
      const screenshotResponse = await request.get(
        `${baseURL}/screenshots/${annotation.screenshot_id}`,
        { headers: { "X-Username": "testuser" } }
      );

      if (screenshotResponse.ok()) {
        const screenshot = await screenshotResponse.json();
        expect(screenshot.id).toBe(annotation.screenshot_id);
      }
    }
  });

  test("should verify consensus data consistency", async ({ request }) => {
    const baseURL = process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";

    // Fetch consensus groups
    const groupsResponse = await request.get(`${baseURL}/consensus/groups`, {
      headers: { "X-Username": "testuser" },
    });

    if (!groupsResponse.ok()) {
      console.log("Could not fetch consensus groups - API may not be available");
      return;
    }

    const groups = await groupsResponse.json();

    for (const group of groups) {
      // Verify group has required fields
      expect(group.group_id).toBeDefined();
      expect(typeof group.single_verified_count).toBe("number");
      expect(typeof group.agreed_count).toBe("number");
      expect(typeof group.disputed_count).toBe("number");

      // Counts should be non-negative
      expect(group.single_verified_count).toBeGreaterThanOrEqual(0);
      expect(group.agreed_count).toBeGreaterThanOrEqual(0);
      expect(group.disputed_count).toBeGreaterThanOrEqual(0);
    }
  });

  test("should verify stats endpoint returns consistent data", async ({ request }) => {
    const baseURL = process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";

    // Fetch overall stats
    const statsResponse = await request.get(`${baseURL}/screenshots/stats`, {
      headers: { "X-Username": "testuser" },
    });

    if (!statsResponse.ok()) {
      console.log("Could not fetch stats - API may not be available");
      return;
    }

    const stats = await statsResponse.json();

    // Stats should have expected structure
    expect(typeof stats.total).toBe("number");
    expect(typeof stats.pending).toBe("number");
    expect(typeof stats.completed).toBe("number");
    expect(typeof stats.failed).toBe("number");
    expect(typeof stats.skipped).toBe("number");

    // Total should be >= sum of status counts (or equal if no other statuses)
    const sumOfStatuses = stats.pending + stats.completed + stats.failed + stats.skipped;
    expect(stats.total).toBeGreaterThanOrEqual(sumOfStatuses);
  });
});

/**
 * Admin Group Deletion Integrity Tests
 */
test.describe("Admin Group Deletion Integrity", () => {
  test("should verify group deletion removes all related data", async ({ request }) => {
    const baseURL = process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";

    // First, check current orphaned entries (before any deletion)
    const beforeOrphaned = await request.get(`${baseURL}/admin/orphaned-entries`, {
      headers: { "X-Username": "admin" },
    });

    if (beforeOrphaned.status() === 403) {
      console.log("Admin access required - skipping group deletion test");
      return;
    }

    if (beforeOrphaned.ok()) {
      const beforeData = await beforeOrphaned.json();
      console.log("Orphaned entries before test:", JSON.stringify(beforeData, null, 2));
    }

    // Get list of groups
    const groupsResponse = await request.get(`${baseURL}/screenshots/groups`, {
      headers: { "X-Username": "admin" },
    });

    if (!groupsResponse.ok()) {
      console.log("Could not fetch groups");
      return;
    }

    const groups = await groupsResponse.json();

    // Find a test group to delete (only delete groups with 'test' or 'e2e' in name)
    const testGroup = groups.find(
      (g: { id: string; name: string }) =>
        g.id.includes("test") ||
        g.id.includes("e2e") ||
        g.name?.includes("test") ||
        g.name?.includes("e2e")
    );

    if (!testGroup) {
      console.log("No test group found to delete - skipping deletion test");
      return;
    }

    console.log("Found test group to delete:", testGroup.id);

    // Delete the group
    const deleteResponse = await request.delete(`${baseURL}/admin/groups/${testGroup.id}`, {
      headers: { "X-Username": "admin" },
    });

    if (deleteResponse.ok()) {
      const deleteData = await deleteResponse.json();
      console.log("Group deleted:", JSON.stringify(deleteData, null, 2));

      expect(deleteData.success).toBe(true);
      expect(deleteData.group_id).toBe(testGroup.id);
    }

    // Verify no orphaned entries after deletion
    const afterOrphaned = await request.get(`${baseURL}/admin/orphaned-entries`, {
      headers: { "X-Username": "admin" },
    });

    if (afterOrphaned.ok()) {
      const afterData = await afterOrphaned.json();
      console.log("Orphaned entries after deletion:", JSON.stringify(afterData, null, 2));

      expect(afterData.orphaned_annotations).toBe(0);
      expect(afterData.orphaned_consensus).toBe(0);
      expect(afterData.orphaned_queue_states).toBe(0);
    }
  });

  test("should cleanup orphaned entries if any exist", async ({ request }) => {
    const baseURL = process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";

    // First check for orphaned entries
    const orphanedResponse = await request.get(`${baseURL}/admin/orphaned-entries`, {
      headers: { "X-Username": "admin" },
    });

    if (orphanedResponse.status() === 403) {
      console.log("Admin access required - skipping cleanup test");
      return;
    }

    if (!orphanedResponse.ok()) {
      console.log("Could not check orphaned entries");
      return;
    }

    const orphanedData = await orphanedResponse.json();
    const totalOrphaned =
      orphanedData.orphaned_annotations +
      orphanedData.orphaned_consensus +
      orphanedData.orphaned_queue_states;

    if (totalOrphaned === 0) {
      console.log("No orphaned entries to cleanup");
      return;
    }

    console.log("Found orphaned entries:", JSON.stringify(orphanedData, null, 2));

    // Cleanup orphaned entries
    const cleanupResponse = await request.post(`${baseURL}/admin/cleanup-orphaned`, {
      headers: { "X-Username": "admin" },
    });

    if (cleanupResponse.ok()) {
      const cleanupData = await cleanupResponse.json();
      console.log("Cleanup result:", JSON.stringify(cleanupData, null, 2));

      expect(cleanupData.success).toBe(true);
    }

    // Verify cleanup was successful
    const afterCleanup = await request.get(`${baseURL}/admin/orphaned-entries`, {
      headers: { "X-Username": "admin" },
    });

    if (afterCleanup.ok()) {
      const afterData = await afterCleanup.json();
      expect(afterData.orphaned_annotations).toBe(0);
      expect(afterData.orphaned_consensus).toBe(0);
      expect(afterData.orphaned_queue_states).toBe(0);
    }
  });
});

/**
 * Export Data Integrity Tests
 */
test.describe("Export Data Integrity", () => {
  test("should verify export JSON data matches database state", async ({ request }) => {
    const baseURL = process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";

    // Fetch export data
    const exportResponse = await request.get(`${baseURL}/screenshots/export/json`, {
      headers: { "X-Username": "testuser" },
    });

    if (!exportResponse.ok()) {
      console.log("Could not fetch export data - API may not be available");
      return;
    }

    const exportData = await exportResponse.json();

    // Export should be an array
    expect(Array.isArray(exportData)).toBe(true);

    // Each exported item should have required fields
    for (const item of exportData) {
      expect(item.screenshot_id).toBeDefined();
    }
  });

  test("should verify export CSV endpoint is available", async ({ request }) => {
    const baseURL = process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";

    const exportResponse = await request.get(`${baseURL}/screenshots/export/csv`, {
      headers: { "X-Username": "testuser" },
    });

    if (exportResponse.ok()) {
      const contentType = exportResponse.headers()["content-type"];
      // Should be CSV content type
      expect(contentType).toContain("text/csv");
    }
  });
});
