import { test, expect } from "@playwright/test";
import { HomePage } from "../pages/HomePage";
import { AnnotationPage } from "../pages/AnnotationPage";
import { LoginPage } from "../pages/LoginPage";

/**
 * Visual Regression Tests
 *
 * These tests capture screenshots for visual regression testing.
 * On first run, they will generate baseline images.
 *
 * To update baselines: npx playwright test --update-snapshots
 *
 * Note: Tests use maxDiffPixelRatio to allow minor rendering differences
 * across different environments.
 */

// Common options for screenshot comparison
const screenshotOptions = {
  maxDiffPixelRatio: 0.1, // Allow 10% pixel difference for cross-env compatibility
  threshold: 0.3, // Allow some color variation
};

test.describe("Visual Regression Tests", () => {
  test.describe("Homepage", () => {
    test("should match homepage layout", async ({ page }) => {
      const homePage = new HomePage(page);
      await homePage.goto();
      await page.waitForLoadState("networkidle");

      // Take screenshot
      await expect(page).toHaveScreenshot("homepage.png", {
        fullPage: true,
        ...screenshotOptions,
      });
    });

    test("should match homepage with groups", async ({ page }) => {
      const homePage = new HomePage(page);
      await homePage.goto();
      await homePage.waitForGroupsLoad();

      const groupCount = await homePage.getGroupCount();

      if (groupCount > 0) {
        await expect(page).toHaveScreenshot("homepage-with-groups.png", {
          fullPage: true,
          ...screenshotOptions,
        });
      } else {
        await expect(page).toHaveScreenshot("homepage-empty.png", {
          fullPage: true,
          ...screenshotOptions,
        });
      }
    });
  });

  test.describe("Annotation Page", () => {
    test("should match annotation workspace", async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.login("testuser");

      const annotationPage = new AnnotationPage(page);
      await annotationPage.goto();

      const hasScreenshot = await annotationPage.waitForScreenshotLoad();
      if (!hasScreenshot) {
        // Capture empty state instead
        await expect(page).toHaveScreenshot("annotation-empty.png", {
          fullPage: true,
          ...screenshotOptions,
        });
        return;
      }

      await expect(page).toHaveScreenshot("annotation-workspace.png", {
        fullPage: true,
        ...screenshotOptions,
      });
    });

    test("should match no screenshots state", async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.login("testuser");

      const annotationPage = new AnnotationPage(page);
      await annotationPage.goto();

      await annotationPage.waitForScreenshotLoad();

      // This will either show a screenshot or empty state
      await expect(page).toHaveScreenshot("annotation-page.png", {
        fullPage: true,
        ...screenshotOptions,
      });
    });
  });

  test.describe("Admin Page", () => {
    test("should match admin page for admin user", async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.login("admin");

      await page.goto("admin");
      await page.waitForLoadState("networkidle");

      await expect(page).toHaveScreenshot("admin-page.png", {
        fullPage: true,
        ...screenshotOptions,
      });
    });

    test("should match access denied state", async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.login("testuser");

      await page.goto("admin");
      await page.waitForLoadState("networkidle");

      await expect(page).toHaveScreenshot("admin-access-denied.png", {
        fullPage: true,
        ...screenshotOptions,
      });
    });
  });

  // Mobile/tablet tests removed - not needed for internal research tool

  test.describe("Login Page", () => {
    test("should match login page layout", async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();

      await expect(page).toHaveScreenshot("login-page.png", {
        fullPage: true,
      });
    });
  });

  test.describe("Print Layouts", () => {
    test("should match print layout for annotation", async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.login("testuser");

      const annotationPage = new AnnotationPage(page);
      await annotationPage.goto();
      await annotationPage.waitForScreenshotLoad();

      // Emulate print media
      await page.emulateMedia({ media: "print" });

      await expect(page).toHaveScreenshot("annotation-print.png", {
        fullPage: true,
        ...screenshotOptions,
      });
    });
  });
});
