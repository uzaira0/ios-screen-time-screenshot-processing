import { test as base, type Page } from "@playwright/test";
import * as path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Custom fixtures for authenticated pages with different user roles
 */
type AuthFixtures = {
  authenticatedPage: Page;
  adminPage: Page;
};

export const test = base.extend<AuthFixtures>({
  /**
   * Authenticated page fixture - creates a new page with user auth state
   */
  authenticatedPage: async ({ browser }, use) => {
    const context = await browser.newContext({
      storageState: path.join(__dirname, "../../playwright/.auth/user.json"),
    });
    const page = await context.newPage();
    await use(page);
    await context.close();
  },

  /**
   * Admin page fixture - creates a new page with admin auth state
   */
  adminPage: async ({ browser }, use) => {
    const context = await browser.newContext({
      storageState: path.join(__dirname, "../../playwright/.auth/admin.json"),
    });
    const page = await context.newPage();
    await use(page);
    await context.close();
  },
});

export { expect } from "@playwright/test";
