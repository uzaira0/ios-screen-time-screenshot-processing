import { test as setup, expect } from "@playwright/test";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const authFile = path.join(__dirname, "../playwright/.auth/user.json");
const adminAuthFile = path.join(__dirname, "../playwright/.auth/admin.json");

/**
 * Helper function to login with retry logic for flaky React hydration
 */
async function performLogin(
  page: import("@playwright/test").Page,
  username: string,
) {
  // Navigate to login page (relative path so baseURL path is preserved)
  await page.goto("login");

  // Wait for the form to be fully loaded and stable
  await page.waitForLoadState("networkidle");

  // Fill username - use fill which is more reliable
  const usernameInput = page.getByPlaceholder("Username");
  await usernameInput.waitFor({ state: "visible" });
  await usernameInput.fill(username);

  // Verify the value was entered
  await expect(usernameInput).toHaveValue(username);

  // Wait for button to be enabled
  const continueButton = page.getByRole("button", { name: /continue/i });
  await expect(continueButton).toBeEnabled({ timeout: 5000 });

  // Click continue button
  await continueButton.click();

  // Wait for redirect away from login page
  await page.waitForURL(/(?!.*\/login)/);
  await page.waitForLoadState("networkidle");
}

/**
 * Setup authentication for regular user
 */
setup("authenticate as user", async ({ page }) => {
  await performLogin(page, "testuser");

  // Save signed-in state
  await page.context().storageState({ path: authFile });
});

/**
 * Setup authentication for admin user
 */
setup("authenticate as admin", async ({ page }) => {
  await performLogin(page, "admin");

  // Save signed-in state
  await page.context().storageState({ path: adminAuthFile });
});
