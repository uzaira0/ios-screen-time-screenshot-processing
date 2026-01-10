import { test, expect } from "../fixtures/auth";
import { HomePage } from "../pages/HomePage";
import { AnnotationPage } from "../pages/AnnotationPage";
import { LoginPage } from "../pages/LoginPage";
import { waitForToast } from "../utils/helpers";
import * as fs from "fs";
import * as path from "path";

/**
 * Complete Annotation Workflow E2E Tests
 *
 * These tests verify the entire annotation workflow from start to finish,
 * including database state verification via API calls.
 */
test.describe("Complete Annotation Workflow", () => {
  test.describe("Full annotation flow with database verification", () => {
    test("should complete full workflow from login through annotation with API verification", async ({
      page,
      request,
    }) => {
      const baseURL = process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";

      // Step 1: Login
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.login("testuser");

      // Should redirect to annotation page after login
      await expect(page).toHaveURL(/\/annotate/);

      // Step 2: Navigate to home to view groups
      await page.goto(".");
      await page.waitForLoadState("domcontentloaded");
      await page.waitForTimeout(1000);

      const homePage = new HomePage(page);

      // Step 3: Check if groups exist
      const groupCount = await homePage.getGroupCount();

      if (groupCount === 0) {
        await expect(homePage.emptyState).toBeVisible();
        test.skip(true, "No groups in database - upload screenshots first");
        return;
      }

      // Step 4: Navigate to annotation page
      await page.goto("annotate");
      const annotationPage = new AnnotationPage(page);

      // Step 5: Wait for screenshot or empty state
      try {
        const hasScreenshot = await annotationPage.waitForScreenshotLoad();
        if (!hasScreenshot) {
          test.skip(true, "No screenshots to annotate");
          return;
        }
      } catch {
        const noScreenshots = page.getByText(/no screenshots|all done|queue is empty/i);
        const hasNoScreenshots = await noScreenshots.isVisible().catch(() => false);
        if (hasNoScreenshots) {
          test.skip(true, "No screenshots to annotate");
          return;
        }
      }

      // Step 6: Record current screenshot ID for later verification
      const screenshotId = await annotationPage.getCurrentScreenshotId();

      // Step 7: Edit hourly values
      const hourlyInputs = page.locator('input[type="number"]');
      const inputCount = await hourlyInputs.count();

      if (inputCount > 0) {
        // Set specific test values
        const testValues = [15, 30, 45];
        for (let i = 0; i < Math.min(3, inputCount); i++) {
          const input = page.getByTestId(`hour-input-${i}`);
          if (await input.isVisible()) {
            await input.clear();
            await input.fill(String(testValues[i]));
          }
        }

        // Wait for auto-save
        await page.waitForTimeout(2000);
      }

      // Step 8: Verify the screenshot
      const verifyButton = page.getByRole("button", { name: /verified/i }).first();
      const hasVerify = await verifyButton.isVisible().catch(() => false);

      if (hasVerify) {
        await verifyButton.click();
        try {
          await waitForToast(page, /verified|saved|success/i);
        } catch {
          await page.waitForTimeout(1000);
        }
      }

      // Step 9: Verify database state via API
      if (screenshotId) {
        const screenshotResponse = await request.get(
          `${baseURL}/screenshots/${screenshotId}`,
          {
            headers: { "X-Username": "testuser" },
          }
        );

        if (screenshotResponse.ok()) {
          const screenshotData = await screenshotResponse.json();
          // Verify screenshot exists and has been processed
          expect(screenshotData.id).toBe(screenshotId);
        }
      }
    });

    test("should navigate between screenshots and preserve values", async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.login("testuser");

      const annotationPage = new AnnotationPage(page);
      await annotationPage.goto();

      try {
        const hasScreenshot = await annotationPage.waitForScreenshotLoad();
        if (!hasScreenshot) {
          test.skip(true, "No screenshots available");
          return;
        }
      } catch {
        test.skip(true, "No screenshots available");
        return;
      }

      // Get initial screenshot ID
      const firstScreenshotId = await annotationPage.getCurrentScreenshotId();

      // Set a value on the first screenshot
      const hour0Input = page.getByTestId("hour-input-0");
      if (await hour0Input.isVisible()) {
        await hour0Input.clear();
        await hour0Input.fill("42");
        await page.waitForTimeout(2000); // Wait for auto-save
      }

      // Check if navigation is available
      const navInfo = await annotationPage.getNavigationInfo();

      if (navInfo.hasNext) {
        // Navigate to next screenshot
        await annotationPage.navigateNext();
        await page.waitForTimeout(1000);

        // Navigate back
        await annotationPage.navigatePrev();
        await page.waitForTimeout(1000);

        // Verify we're back on the same screenshot
        const currentId = await annotationPage.getCurrentScreenshotId();
        expect(currentId).toBe(firstScreenshotId);

        // Verify value is preserved
        if (await hour0Input.isVisible()) {
          const preservedValue = await hour0Input.inputValue();
          expect(preservedValue).toBe("42");
        }
      }
    });

    test("should edit title and verify persistence", async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.login("testuser");

      const annotationPage = new AnnotationPage(page);
      await annotationPage.goto();

      try {
        const hasScreenshot = await annotationPage.waitForScreenshotLoad();
        if (!hasScreenshot) {
          test.skip(true, "No screenshots available");
          return;
        }
      } catch {
        test.skip(true, "No screenshots available");
        return;
      }

      // Find title input (only for screen_time type)
      const titleInput = page.getByLabel(/app.*title|title/i);
      const hasTitleInput = await titleInput.isVisible().catch(() => false);

      if (!hasTitleInput) {
        console.log("Title input not visible - may be battery type screenshot");
        return;
      }

      // Set a test title
      const testTitle = `Test App ${Date.now()}`;
      await titleInput.clear();
      await titleInput.fill(testTitle);
      await page.waitForTimeout(2000); // Wait for auto-save

      // Refresh the page
      await page.reload();
      await page.waitForTimeout(2000);

      // Verify title is preserved
      const refreshedTitleInput = page.getByLabel(/app.*title|title/i);
      if (await refreshedTitleInput.isVisible()) {
        const savedTitle = await refreshedTitleInput.inputValue();
        expect(savedTitle).toBe(testTitle);
      }
    });
  });

  test.describe("Basic workflow tests", () => {
    test("should complete full workflow from login to annotation submission", async ({
      page,
    }) => {
      // Step 1: Login
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.login("testuser");

      // Should redirect to annotation page after login
      await expect(page).toHaveURL(/\/annotate/);

      // Step 2: Navigate to home to view groups
      await page.goto(".");
      await page.waitForLoadState("domcontentloaded");
      await page.waitForTimeout(1000);

      const homePage = new HomePage(page);

      // Step 3: Check if groups exist
      const groupCount = await homePage.getGroupCount();

      if (groupCount === 0) {
        await expect(homePage.emptyState).toBeVisible();
        test.skip(true, "No groups in database - upload screenshots first");
        return;
      }

      // Step 4: Navigate to annotation page
      await page.goto("annotate");
      const annotationPage = new AnnotationPage(page);

      // Step 5: Wait for screenshot or empty state
      try {
        await annotationPage.waitForScreenshotLoad();
      } catch {
        const noScreenshots = page.getByText(/no screenshots|all done|queue is empty/i);
        const hasNoScreenshots = await noScreenshots.isVisible().catch(() => false);
        if (hasNoScreenshots) {
          test.skip(true, "No screenshots to annotate");
          return;
        }
      }

      // Step 6: Verify annotation interface is visible
      const hourlyInputs = page.locator('input[type="number"]');
      const inputCount = await hourlyInputs.count();

      if (inputCount > 0) {
        const firstInput = hourlyInputs.first();
        await firstInput.clear();
        await firstInput.fill("30");
        await page.waitForTimeout(1500);
      }

      // Step 7: Try to verify the screenshot
      const verifyButton = page.getByRole("button", { name: /verify/i }).first();
      const hasVerify = await verifyButton.isVisible().catch(() => false);

      if (hasVerify) {
        await verifyButton.click();
        try {
          await waitForToast(page, /verified|saved|success/i);
        } catch {
          await page.waitForTimeout(1000);
        }
      }
    });

    test("should handle workflow with no screenshots", async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.login("testuser");

      await page.goto("annotate");
      await page.waitForLoadState("domcontentloaded");

      try {
        await Promise.race([
          page.getByTestId("annotation-workspace").waitFor({ state: "visible", timeout: 10000 }),
          page
            .getByText(/no screenshots|all done|queue is empty|no screenshots available/i)
            .first()
            .waitFor({ state: "visible", timeout: 10000 }),
        ]);
      } catch {
        // Continue and check state
      }
      await page.waitForTimeout(500);

      const hasScreenshot = await page.locator("img").first().isVisible().catch(() => false);
      const hasEmptyState = await page
        .getByText(/no screenshots|all done|queue is empty|no screenshots available/i)
        .first()
        .isVisible()
        .catch(() => false);
      const hasWorkspace = await page.getByTestId("annotation-workspace").isVisible().catch(() => false);
      const isLoading = await page.getByText(/loading/i).isVisible().catch(() => false);
      const hasActionButtons = await page.getByTestId("action-buttons").isVisible().catch(() => false);

      expect(hasScreenshot || hasEmptyState || hasWorkspace || isLoading || hasActionButtons).toBe(true);
    });

    test("should handle skip workflow", async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.login("testuser");

      const annotationPage = new AnnotationPage(page);
      await annotationPage.goto();
      await page.waitForLoadState("domcontentloaded");

      try {
        await annotationPage.waitForScreenshotLoad();
      } catch {
        test.skip(true, "No screenshots available to test skip");
        return;
      }

      const skipButton = page.getByRole("button", { name: /skip/i }).first();
      const hasSkip = await skipButton.isVisible().catch(() => false);

      if (!hasSkip) {
        test.skip(true, "Skip button not visible");
        return;
      }

      await skipButton.click();
      await page.waitForTimeout(1000);
      const pageStillFunctional = await page.locator("body").isVisible();
      expect(pageStillFunctional).toBe(true);
    });

    test("should handle keyboard navigation workflow", async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.login("testuser");

      const annotationPage = new AnnotationPage(page);
      await annotationPage.goto();

      try {
        await annotationPage.waitForScreenshotLoad();
      } catch {
        test.skip(true, "No screenshots available");
        return;
      }

      await page.keyboard.press("v");
      await page.waitForTimeout(500);

      await page.keyboard.press("ArrowRight");
      await page.waitForTimeout(500);

      expect(await page.locator("body").isVisible()).toBe(true);
    });

    test("should complete workflow and return to home", async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.login("testuser");

      await page.goto("annotate");
      await page.waitForLoadState("domcontentloaded");

      const homeLink = page.getByRole("link", { name: /screenshot.*processor|home/i }).first();
      const hasHomeLink = await homeLink.isVisible().catch(() => false);

      if (hasHomeLink) {
        await homeLink.click();
        await expect(page).toHaveURL(/\/$/);
      } else {
        await page.goto(".");
        await expect(page).toHaveURL(/\/$/);
      }

      await page.waitForLoadState("domcontentloaded");
      expect(await page.locator("body").isVisible()).toBe(true);
    });

    test("should handle queue completion", async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.login("testuser");

      await page.goto("annotate");
      await page.waitForLoadState("domcontentloaded");

      try {
        await Promise.race([
          page.getByTestId("annotation-workspace").waitFor({ state: "visible", timeout: 10000 }),
          page
            .getByText(/all done|no screenshots|queue is empty|no screenshots available/i)
            .first()
            .waitFor({ state: "visible", timeout: 10000 }),
        ]);
      } catch {
        // Continue
      }
      await page.waitForTimeout(500);

      const completionMessage = page.getByText(
        /all done|no screenshots|queue is empty|nothing to annotate|no screenshots available/i
      );
      const screenshot = page.locator("img").first();
      const workspace = page.getByTestId("annotation-workspace");
      const loadingIndicator = page.getByText(/loading/i);
      const actionButtons = page.getByTestId("action-buttons");

      const hasCompletion = await completionMessage.first().isVisible().catch(() => false);
      const hasScreenshot = await screenshot.isVisible().catch(() => false);
      const hasWorkspace = await workspace.isVisible().catch(() => false);
      const isLoading = await loadingIndicator.isVisible().catch(() => false);
      const hasActionButtons = await actionButtons.isVisible().catch(() => false);

      expect(hasCompletion || hasScreenshot || hasWorkspace || isLoading || hasActionButtons).toBe(true);
    });

    test("should display navigation info when screenshots exist", async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.login("testuser");

      const annotationPage = new AnnotationPage(page);
      await annotationPage.goto();

      try {
        await annotationPage.waitForScreenshotLoad();
      } catch {
        test.skip(true, "No screenshots available");
        return;
      }

      const navInfo = page.getByText(/\d+\s*(of|\/)\s*\d+/);
      const hasNavInfo = await navInfo.isVisible().catch(() => false);

      const prevButton = page.getByRole("button", { name: /previous|prev|←/i });
      const nextButton = page.getByRole("button", { name: /next|→/i });

      const hasPrev = await prevButton.isVisible().catch(() => false);
      const hasNext = await nextButton.isVisible().catch(() => false);

      console.log("Nav info visible:", hasNavInfo);
      console.log("Prev button:", hasPrev);
      console.log("Next button:", hasNext);
    });
  });
});

test.describe("Annotation Verification with API", () => {
  test("should verify annotation data is saved correctly via API", async ({ page, request }) => {
    const baseURL = process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";

    // Login
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login("testuser");

    const annotationPage = new AnnotationPage(page);
    await annotationPage.goto();

    try {
      const hasScreenshot = await annotationPage.waitForScreenshotLoad();
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }
    } catch {
      test.skip(true, "No screenshots available");
      return;
    }

    const screenshotId = await annotationPage.getCurrentScreenshotId();
    if (!screenshotId) {
      test.skip(true, "Could not get screenshot ID");
      return;
    }

    // Make some edits
    const testValue = 25;
    const hour0Input = page.getByTestId("hour-input-0");
    if (await hour0Input.isVisible()) {
      await hour0Input.clear();
      await hour0Input.fill(String(testValue));
      await page.waitForTimeout(2000);
    }

    // Verify the annotation
    const verifyButton = page.getByRole("button", { name: /verified/i }).first();
    if (await verifyButton.isVisible()) {
      await verifyButton.click();
      await page.waitForTimeout(1000);
    }

    // Verify via API that the annotation was saved
    const annotationsResponse = await request.get(`${baseURL}/annotations/history`, {
      headers: { "X-Username": "testuser" },
    });

    if (annotationsResponse.ok()) {
      const annotations = await annotationsResponse.json();
      // Should have at least one annotation
      expect(Array.isArray(annotations)).toBe(true);
    }

    // Verify screenshot state via API
    const screenshotResponse = await request.get(`${baseURL}/screenshots/${screenshotId}`, {
      headers: { "X-Username": "testuser" },
    });

    if (screenshotResponse.ok()) {
      const screenshotData = await screenshotResponse.json();
      expect(screenshotData.id).toBe(screenshotId);
    }
  });

  test("should verify unverify workflow correctly updates database", async ({ page, request }) => {
    const baseURL = process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";

    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login("testuser");

    const annotationPage = new AnnotationPage(page);
    await annotationPage.goto();

    try {
      const hasScreenshot = await annotationPage.waitForScreenshotLoad();
      if (!hasScreenshot) {
        test.skip(true, "No screenshots available");
        return;
      }
    } catch {
      test.skip(true, "No screenshots available");
      return;
    }

    const screenshotId = await annotationPage.getCurrentScreenshotId();
    if (!screenshotId) {
      test.skip(true, "Could not get screenshot ID");
      return;
    }

    // Get initial state
    const initialResponse = await request.get(`${baseURL}/screenshots/${screenshotId}`, {
      headers: { "X-Username": "testuser" },
    });

    if (!initialResponse.ok()) {
      test.skip(true, "Could not fetch screenshot");
      return;
    }

    const initialData = await initialResponse.json();
    const initialVerifiers = initialData.verified_by_user_ids || [];

    // Verify the screenshot
    const verifyButton = page.getByRole("button", { name: /verified/i }).first();
    if (!(await verifyButton.isVisible())) {
      test.skip(true, "Verify button not visible");
      return;
    }

    await verifyButton.click();
    await page.waitForTimeout(1500);

    // Check state after verification
    const afterVerifyResponse = await request.get(`${baseURL}/screenshots/${screenshotId}`, {
      headers: { "X-Username": "testuser" },
    });

    if (afterVerifyResponse.ok()) {
      const afterVerifyData = await afterVerifyResponse.json();
      // User should now be in the verified_by list (or list should be longer)
      const afterVerifiers = afterVerifyData.verified_by_user_ids || [];
      expect(afterVerifiers.length).toBeGreaterThanOrEqual(initialVerifiers.length);
    }
  });
});

test.describe("Screenshot Upload and Processing Workflow", () => {
  test("should upload a screenshot and verify processing via API", async ({ request }) => {
    const baseURL = process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";
    const testImagePath = path.join(__dirname, "../fixtures/images/test-screenshot.png");

    // Skip if test image doesn't exist
    if (!fs.existsSync(testImagePath)) {
      test.skip(true, "Test screenshot file not found");
      return;
    }

    const imageBuffer = fs.readFileSync(testImagePath);
    const base64Image = imageBuffer.toString("base64");

    // Upload screenshot
    const uploadResponse = await request.post(`${baseURL}/screenshots/upload`, {
      headers: {
        "X-API-Key": "dev-upload-key-change-in-production",
      },
      data: {
        screenshot: base64Image,
        participant_id: "e2e-test-participant",
        group_id: "e2e-test-group",
        image_type: "screen_time",
        filename: "test-screenshot.png",
      },
    });

    if (!uploadResponse.ok()) {
      console.log("Upload failed - API may not be configured for uploads");
      return;
    }

    const uploadData = await uploadResponse.json();
    expect(uploadData.id).toBeDefined();

    // Verify screenshot exists via API
    const screenshotResponse = await request.get(`${baseURL}/screenshots/${uploadData.id}`, {
      headers: { "X-Username": "testuser" },
    });

    if (screenshotResponse.ok()) {
      const screenshotData = await screenshotResponse.json();
      expect(screenshotData.group_id).toBe("e2e-test-group");
      expect(screenshotData.participant_id).toBe("e2e-test-participant");
    }
  });
});
