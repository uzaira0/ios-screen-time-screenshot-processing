import { test, expect } from "@playwright/test";
import { LoginPage } from "../pages/LoginPage";

test.describe("Authentication", () => {
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    // Go to a page to be able to clear localStorage, then clear it
    await page.goto(".");
    await page.evaluate(() => {
      localStorage.removeItem("username");
      // Keep app-mode as "server" if it was set
    });
  });

  test("should display login page", async ({ page }) => {
    await page.goto("login");

    await expect(loginPage.heading).toBeVisible();
    await expect(loginPage.usernameInput).toBeVisible();
    await expect(loginPage.loginButton).toBeVisible();
  });

  test("should login with valid username", async ({ page }) => {
    await page.goto("login");
    await loginPage.login("testuser");

    // Should redirect to annotation page (not home)
    await expect(page).toHaveURL(/(?!.*\/login)/);

    // Wait for header to be present
    await page.waitForSelector("header");

    // Should show username in header - check for the username text anywhere
    // The header shows "Welcome, <span>username</span>"
    await expect(page.locator("header").getByText("testuser")).toBeVisible();
  });

  test("should login as admin", async ({ page }) => {
    await page.goto("login");
    await loginPage.login("admin");

    await expect(page).toHaveURL(/(?!.*\/login)/);

    // Wait for header
    await page.waitForSelector("header");

    // Should show admin username in header (use exact match to avoid matching Admin link)
    await expect(
      page.locator("header").getByText("admin", { exact: true }),
    ).toBeVisible();

    // Navigate to home to check admin link
    await page.goto(".");
    // Should show admin link in navigation
    await expect(page.getByRole("link", { name: /admin/i })).toBeVisible();
  });

  test("should persist login state after page refresh", async ({ page }) => {
    await page.goto("login");
    await loginPage.login("testuser");

    // Reload the page
    await page.reload();

    // Wait for header
    await page.waitForSelector("header");

    // Should still be logged in - check for username in header
    await expect(page.locator("header").getByText("testuser")).toBeVisible();
  });

  test("should logout successfully", async ({ page }) => {
    await page.goto("login");
    await loginPage.login("testuser");

    // Wait for toast to disappear completely
    await page.waitForTimeout(3000);

    // Dismiss any remaining toasts by clicking elsewhere first
    await page.locator("header").click();
    await page.waitForTimeout(500);

    // Click logout button
    await page.getByRole("button", { name: /logout/i }).click();

    // Should redirect to login page
    await expect(page).toHaveURL(/\/login/, { timeout: 10000 });

    // Header should not show username
    await expect(
      page.locator("header").getByText("testuser"),
    ).not.toBeVisible();
  });

  test("should clear login state after logout", async ({ page }) => {
    await page.goto("login");
    await loginPage.login("testuser");

    // Wait for toast to disappear completely
    await page.waitForTimeout(3000);

    // Dismiss any remaining toasts by clicking elsewhere first
    await page.locator("header").click();
    await page.waitForTimeout(500);

    await page.getByRole("button", { name: /logout/i }).click();

    // Wait for logout to complete
    await expect(page).toHaveURL(/\/login/, { timeout: 10000 });

    // Try to access protected page
    await page.goto("annotate");

    // Should redirect to login
    await expect(page).toHaveURL(/\/login/);
  });

  test("should redirect to login when accessing protected route while unauthenticated", async ({
    page,
  }) => {
    // Try to access annotation page without logging in
    await page.goto("annotate");

    // Should redirect to login
    await expect(page).toHaveURL(/\/login/);
  });

  test("should redirect to login when accessing admin page while unauthenticated", async ({
    page,
  }) => {
    await page.goto("admin");

    await expect(page).toHaveURL(/\/login/);
  });

  test("should not allow empty username", async ({ page }) => {
    await page.goto("login");

    // Button should be disabled when username is empty
    await expect(loginPage.loginButton).toBeDisabled();

    // Verify we're still on login page
    await expect(page).toHaveURL(/\/login/);
  });

  test("should store username in localStorage", async ({ page }) => {
    await page.goto("login");
    await loginPage.login("testuser");

    // Check localStorage
    const username = await page.evaluate(() =>
      localStorage.getItem("username"),
    );
    expect(username).toBe("testuser");
  });

  test("should clear localStorage on logout", async ({ page }) => {
    await page.goto("login");
    await loginPage.login("testuser");

    await page.getByRole("button", { name: /logout/i }).click();

    // Check localStorage is cleared
    const username = await page.evaluate(() =>
      localStorage.getItem("username"),
    );
    expect(username).toBeNull();
  });

  test("should handle special characters in username", async ({ page }) => {
    await page.goto("login");

    const specialUsername = "user-123_test";
    await loginPage.login(specialUsername);

    await expect(page).toHaveURL(/(?!.*\/login)/);

    // Wait for header
    await page.waitForSelector("header");

    // Check for username in header
    await expect(
      page.locator("header").getByText(specialUsername),
    ).toBeVisible();
  });

  test("should show correct navigation for authenticated users", async ({
    page,
  }) => {
    await page.goto("login");
    await loginPage.login("testuser");

    // Navigate to home page to see nav links
    await page.goto(".");

    // Should show Annotate link in nav
    await expect(
      page.locator("nav").getByRole("link", { name: /annotate/i }),
    ).toBeVisible();

    // Should show Logout button
    await expect(page.getByRole("button", { name: /logout/i })).toBeVisible();

    // Should not show Login link in header (since user is authenticated)
    await expect(
      page.getByRole("banner").getByRole("link", { name: /^login$/i }),
    ).not.toBeVisible();
  });

  test("should show correct navigation for unauthenticated users", async ({
    page,
  }) => {
    // Home page is accessible without auth
    await page.goto(".");

    // Should show Login link in header (be specific to avoid matching multiple)
    await expect(
      page.getByRole("banner").getByRole("link", { name: /login/i }),
    ).toBeVisible();

    // Should not show Logout button
    await expect(
      page.getByRole("button", { name: /logout/i }),
    ).not.toBeVisible();

    // Should not show Annotate navigation link in nav (hidden for unauthenticated)
    await expect(
      page.locator("nav").getByRole("link", { name: /annotate/i }),
    ).not.toBeVisible();
  });

  test("should redirect back to annotation page after login from protected route", async ({
    page,
  }) => {
    // Try to access annotation page - should redirect to login
    await page.goto("annotate");
    await expect(page).toHaveURL(/\/login/);

    // Login
    await loginPage.login("testuser");

    // Should redirect to annotation page (the login always goes to /annotate)
    await expect(page).toHaveURL(/(?!.*\/login)/);
  });
});
