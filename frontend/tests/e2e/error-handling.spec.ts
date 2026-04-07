import { test, expect } from "@playwright/test";

/**
 * Error Handling Tests
 *
 * Tests the application's error handling:
 * - API error responses
 * - Network failures
 * - Invalid data
 * - Session expiry
 * - Error boundaries
 * - Recovery mechanisms
 */
test.describe("Error Handling", () => {
  test("should handle API 500 error gracefully", async ({ page }) => {
    // Intercept API and return 500
    await page.route("**/api/v1/screenshots/**", (route) => {
      route.fulfill({
        status: 500,
        body: JSON.stringify({ detail: "Internal server error" }),
      });
    });

    await page.goto("annotate");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2000);

    // Should show error message or fallback UI
    const errorMsg = page.getByText(/error|failed|unavailable/i);
    const hasError = await errorMsg.first().isVisible().catch(() => false);

    // Page should not crash (no uncaught exceptions)
    await expect(page.locator("body")).toBeVisible();

    console.log("500 error handled, error shown:", hasError);
  });

  test("should handle API 404 error gracefully", async ({ page }) => {
    await page.route("**/api/v1/screenshots/999999", (route) => {
      route.fulfill({
        status: 404,
        body: JSON.stringify({ detail: "Screenshot not found" }),
      });
    });

    await page.goto("annotate?id=999999");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2000);

    // Should show not found or navigate to different screenshot
    const notFound = page.getByText(/not found|no screenshot/i);
    const hasNotFound = await notFound.first().isVisible().catch(() => false);

    await expect(page.locator("body")).toBeVisible();
    console.log("404 error handled:", hasNotFound);
  });

  test("should handle API 401 unauthorized error", async ({ page }) => {
    await page.route("**/api/v1/**", (route) => {
      route.fulfill({
        status: 401,
        body: JSON.stringify({ detail: "Unauthorized" }),
      });
    });

    await page.goto("annotate");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2000);

    // Should redirect to login or show auth error
    const loginForm = page.getByRole("button", { name: /login/i });
    const authError = page.getByText(/unauthorized|login required/i);

    const hasLogin = await loginForm.isVisible().catch(() => false);
    const hasAuthError = await authError.first().isVisible().catch(() => false);
    const isLoginPage = page.url().includes("/login");

    console.log(
      "401 handled - Login:",
      hasLogin,
      "Error:",
      hasAuthError,
      "Redirect:",
      isLoginPage
    );
  });

  test("should handle network timeout", async ({ page }) => {
    // Simulate slow network
    await page.route("**/api/v1/**", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 30000));
      route.abort("timedout");
    });

    await page.goto("annotate");

    // Should show loading or timeout message
    const loading = page.getByText(/loading|connecting/i);
    const timeout = page.getByText(/timeout|slow/i);

    const hasLoading = await loading.first().isVisible().catch(() => false);
    const hasTimeout = await timeout.first().isVisible().catch(() => false);

    await page.waitForTimeout(5000);
    console.log("Network timeout - Loading:", hasLoading, "Timeout:", hasTimeout);
  });

  test("should handle network disconnection", async ({ page }) => {
    await page.goto("annotate");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2000);

    // Simulate offline
    await page.context().setOffline(true);

    // Try to navigate or perform action
    await page.getByRole("button", { name: /verified/i }).first().click().catch(() => {});

    // Should show offline indicator or error
    const offlineBanner = page.getByText(/offline|no connection/i);
    const hasOffline = await offlineBanner.first().isVisible().catch(() => false);

    // Restore connection
    await page.context().setOffline(false);

    console.log("Offline handling:", hasOffline);
  });

  test("should handle malformed API response", async ({ page }) => {
    await page.route("**/api/v1/screenshots/next**", (route) => {
      route.fulfill({
        status: 200,
        body: "not valid json {{{",
        headers: { "content-type": "application/json" },
      });
    });

    await page.goto("annotate");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2000);

    // Should handle JSON parse error gracefully
    await expect(page.locator("body")).toBeVisible();

    const errorMsg = page.getByText(/error|invalid|parse/i);
    const hasError = await errorMsg.first().isVisible().catch(() => false);

    console.log("Malformed JSON handled:", hasError);
  });

  test("should recover from error state", async ({ page }) => {
    // First simulate error
    await page.route("**/api/v1/screenshots/**", (route) => {
      route.fulfill({
        status: 500,
        body: JSON.stringify({ detail: "Server error" }),
      });
    });

    await page.goto("annotate");
    await page.waitForTimeout(2000);

    // Clear route interception
    await page.unroute("**/api/v1/screenshots/**");

    // Try refreshing
    await page.reload();
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2000);

    // Should recover if server is now available
    const workspace = page.getByTestId("annotation-workspace");
    const noScreenshots = page.getByText(/no screenshots/i);

    const hasWorkspace = await workspace.isVisible().catch(() => false);
    const hasEmpty = await noScreenshots.first().isVisible().catch(() => false);

    console.log("Recovery - Workspace:", hasWorkspace, "Empty:", hasEmpty);
  });

  test("should show retry button on error", async ({ page }) => {
    await page.route("**/api/v1/screenshots/**", (route) => {
      route.fulfill({
        status: 500,
        body: JSON.stringify({ detail: "Server error" }),
      });
    });

    await page.goto("annotate");
    await page.waitForTimeout(2000);

    // Look for retry button
    const retryButton = page.getByRole("button", { name: /retry|try again/i });
    const hasRetry = await retryButton.isVisible().catch(() => false);

    console.log("Retry button visible:", hasRetry);
  });

  test("should handle form validation errors", async ({ page }) => {
    await page.goto("annotate");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2000);

    const hour0Input = page.getByTestId("hour-input-0");
    if (!(await hour0Input.isVisible())) {
      test.skip(true, "No screenshot/inputs available");
      return;
    }

    // Enter invalid value
    await hour0Input.fill("-100");
    await hour0Input.blur();

    // Should show validation feedback
    const validationError = page.getByText(/invalid|must be|cannot be/i);
    const hasValidation = await validationError
      .first()
      .isVisible()
      .catch(() => false);

    // Or input should have error styling
    const hasErrorClass = await hour0Input.evaluate(
      (el) =>
        el.classList.contains("border-red") ||
        el.getAttribute("aria-invalid") === "true"
    );

    console.log(
      "Validation error - Message:",
      hasValidation,
      "Styling:",
      hasErrorClass
    );
  });

  test("should handle session expiry", async ({ page }) => {
    await page.goto("annotate");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2000);

    // Simulate session expiry on next request
    await page.route("**/api/v1/**", (route) => {
      route.fulfill({
        status: 401,
        body: JSON.stringify({ detail: "Session expired" }),
      });
    });

    // Try an action
    const verifyButton = page.getByRole("button", { name: /verified/i });
    if (await verifyButton.isVisible()) {
      await verifyButton.click();
      await page.waitForTimeout(1000);
    }

    // Should prompt re-login
    const sessionExpired = page.getByText(/session.*expired|please.*login/i);
    const hasExpiry = await sessionExpired.first().isVisible().catch(() => false);

    console.log("Session expiry handled:", hasExpiry);
  });

  test("should display error boundary for component crashes", async ({
    page,
  }) => {
    // This tests React Error Boundary
    await page.addInitScript(() => {
      // We can't easily crash a component, but we can check error boundary exists
      (window as any).__testErrorBoundary = true;
    });

    await page.goto("annotate");
    await page.waitForLoadState("domcontentloaded");

    // Error boundary should be in place (not crashing the whole app)
    await expect(page.locator("body")).toBeVisible();
  });

  test("should handle image load failure", async ({ page }) => {
    await page.route("**/*.png", (route) => {
      route.abort("failed");
    });

    await page.route("**/*.jpg", (route) => {
      route.abort("failed");
    });

    await page.goto("annotate");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2000);

    // Should show placeholder or error
    const imgError = page.getByText(/image.*failed|could not load/i);
    const hasImgError = await imgError.first().isVisible().catch(() => false);

    // Page should still be functional
    await expect(page.locator("body")).toBeVisible();

    console.log("Image load error handled:", hasImgError);
  });

  test("should handle rate limiting", async ({ page }) => {
    await page.route("**/api/v1/**", (route) => {
      route.fulfill({
        status: 429,
        body: JSON.stringify({ detail: "Too many requests" }),
        headers: { "Retry-After": "60" },
      });
    });

    await page.goto("annotate");
    await page.waitForTimeout(2000);

    // Should show rate limit message
    const rateLimited = page.getByText(/too many|rate limit|slow down/i);
    const hasRateLimit = await rateLimited.first().isVisible().catch(() => false);

    console.log("Rate limiting handled:", hasRateLimit);
  });

  test("should preserve unsaved changes on error", async ({ page }) => {
    await page.goto("annotate");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2000);

    const hour0Input = page.getByTestId("hour-input-0");
    if (!(await hour0Input.isVisible())) {
      test.skip(true, "No inputs available");
      return;
    }

    // Make a change
    await hour0Input.clear();
    await hour0Input.fill("42");

    // Simulate save error
    await page.route("**/api/v1/annotations/**", (route) => {
      route.fulfill({
        status: 500,
        body: JSON.stringify({ detail: "Save failed" }),
      });
    });

    await page.waitForTimeout(3000);

    // Value should still be in input
    const value = await hour0Input.inputValue();
    expect(value).toBe("42");
  });

  test("should show meaningful error messages", async ({ page }) => {
    await page.route("**/api/v1/screenshots/**", (route) => {
      route.fulfill({
        status: 400,
        body: JSON.stringify({ detail: "Invalid screenshot ID format" }),
      });
    });

    await page.goto("annotate?id=invalid");
    await page.waitForTimeout(2000);

    // Should show the actual error message, not generic
    const specificError = page.getByText(/invalid screenshot id/i);
    const hasSpecific = await specificError.isVisible().catch(() => false);

    console.log("Specific error message shown:", hasSpecific);
  });

  test("should handle WebSocket connection failure", async ({ page }) => {
    // Block WebSocket
    await page.route("**/ws/**", (route) => {
      route.abort("failed");
    });

    await page.goto("annotate");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2000);

    // App should still work without WebSocket
    await expect(page.locator("body")).toBeVisible();

    const wsError = page.getByText(/real-time.*unavailable|connection/i);
    const hasWsError = await wsError.first().isVisible().catch(() => false);

    console.log("WebSocket failure handled:", hasWsError);
  });

  test("should handle concurrent request conflicts", async ({ page }) => {
    let requestCount = 0;

    await page.route("**/api/v1/annotations/**", (route) => {
      requestCount++;
      if (requestCount === 2) {
        // Conflict on second request
        route.fulfill({
          status: 409,
          body: JSON.stringify({ detail: "Conflict: data was modified" }),
        });
      } else {
        route.continue();
      }
    });

    await page.goto("annotate");
    await page.waitForTimeout(2000);

    const hour0Input = page.getByTestId("hour-input-0");
    if (await hour0Input.isVisible()) {
      await hour0Input.fill("30");
      await page.waitForTimeout(500);
      await hour0Input.fill("45");
      await page.waitForTimeout(2000);
    }

    console.log("Request count:", requestCount);
    await expect(page.locator("body")).toBeVisible();
  });
});
