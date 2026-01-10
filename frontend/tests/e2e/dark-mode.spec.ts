import { test, expect } from "../fixtures/auth";

/**
 * Dark Mode / Theme Tests
 *
 * Tests the theme toggle functionality:
 * - Header toggle button cycles through light -> dark -> system -> light
 * - Theme persists across page reloads via localStorage
 * - System color scheme preference is respected in "system" mode
 * - Settings page theme selector buttons work
 */
test.describe("Dark Mode", () => {
  test.beforeEach(async ({ authenticatedPage }) => {
    // Clear any saved theme so each test starts from a known state
    await authenticatedPage.addInitScript(() => {
      localStorage.removeItem("theme");
    });
  });

  test("theme toggle cycles through light -> dark -> system -> light", async ({
    authenticatedPage,
  }) => {
    // Emulate light OS preference so "system" mode does not add "dark" class
    await authenticatedPage.emulateMedia({ colorScheme: "light" });

    // Start in light mode explicitly
    await authenticatedPage.addInitScript(() => {
      localStorage.setItem("theme", "light");
    });
    await authenticatedPage.goto(".");
    await authenticatedPage.waitForLoadState("domcontentloaded");

    const html = authenticatedPage.locator("html");

    // Verify starting state: light mode — no "dark" class
    await expect(html).not.toHaveClass(/dark/);

    // Find the theme toggle button in the header
    const themeToggle = authenticatedPage.getByRole("button", {
      name: /theme:/i,
    });
    await expect(themeToggle).toBeVisible();

    // 1st click: light -> dark
    await themeToggle.click();
    await expect(html).toHaveClass(/dark/);

    // 2nd click: dark -> system (with light OS preference, no "dark" class)
    await themeToggle.click();
    await expect(html).not.toHaveClass(/dark/);

    // Verify we are in system mode via the button aria-label
    await expect(themeToggle).toHaveAttribute(
      "aria-label",
      /theme: system/i,
    );

    // 3rd click: system -> light
    await themeToggle.click();
    await expect(html).not.toHaveClass(/dark/);
    await expect(themeToggle).toHaveAttribute(
      "aria-label",
      /theme: light/i,
    );
  });

  test("localStorage persistence across page reload", async ({
    authenticatedPage,
  }) => {
    // Start in light mode
    await authenticatedPage.addInitScript(() => {
      localStorage.setItem("theme", "light");
    });
    await authenticatedPage.goto(".");
    await authenticatedPage.waitForLoadState("domcontentloaded");

    const html = authenticatedPage.locator("html");
    const themeToggle = authenticatedPage.getByRole("button", {
      name: /theme:/i,
    });
    await expect(themeToggle).toBeVisible();

    // Click once to switch to dark mode
    await themeToggle.click();
    await expect(html).toHaveClass(/dark/);

    // Verify localStorage was updated
    const storedTheme = await authenticatedPage.evaluate(() =>
      localStorage.getItem("theme"),
    );
    expect(storedTheme).toBe("dark");

    // Reload the page
    await authenticatedPage.reload();
    await authenticatedPage.waitForLoadState("domcontentloaded");

    // Dark mode should persist after reload
    await expect(html).toHaveClass(/dark/);

    // localStorage should still have "dark"
    const storedThemeAfterReload = await authenticatedPage.evaluate(() =>
      localStorage.getItem("theme"),
    );
    expect(storedThemeAfterReload).toBe("dark");
  });

  test("system color scheme preference is respected", async ({
    authenticatedPage,
  }) => {
    // Set theme to "system" mode
    await authenticatedPage.addInitScript(() => {
      localStorage.setItem("theme", "system");
    });

    // Emulate dark OS preference
    await authenticatedPage.emulateMedia({ colorScheme: "dark" });
    await authenticatedPage.goto(".");
    await authenticatedPage.waitForLoadState("domcontentloaded");

    const html = authenticatedPage.locator("html");

    // System mode + dark OS preference = dark class should be present
    await expect(html).toHaveClass(/dark/);

    // Switch OS preference to light
    await authenticatedPage.emulateMedia({ colorScheme: "light" });

    // The media query change listener should remove the "dark" class
    // Give a brief moment for the event listener to fire
    await authenticatedPage.waitForTimeout(200);
    await expect(html).not.toHaveClass(/dark/);
  });

  test("settings page theme selector buttons work", async ({
    authenticatedPage,
  }) => {
    // Start in light mode
    await authenticatedPage.emulateMedia({ colorScheme: "light" });
    await authenticatedPage.addInitScript(() => {
      localStorage.setItem("theme", "light");
    });
    await authenticatedPage.goto("settings");
    await authenticatedPage.waitForLoadState("domcontentloaded");

    const html = authenticatedPage.locator("html");

    // Find the theme section
    const themeHeading = authenticatedPage.getByRole("heading", {
      name: "Theme",
    });
    await expect(themeHeading).toBeVisible();

    // Find the three theme buttons: Light, Dark, System
    const darkButton = authenticatedPage.getByRole("button", {
      name: /dark/i,
    });
    const lightButton = authenticatedPage.getByRole("button", {
      name: /light/i,
    });
    const systemButton = authenticatedPage.getByRole("button", {
      name: /system/i,
    });

    // Verify all three buttons are visible
    await expect(lightButton).toBeVisible();
    await expect(darkButton).toBeVisible();
    await expect(systemButton).toBeVisible();

    // Click Dark button
    await darkButton.click();
    await expect(html).toHaveClass(/dark/);

    // Verify localStorage updated
    let storedTheme = await authenticatedPage.evaluate(() =>
      localStorage.getItem("theme"),
    );
    expect(storedTheme).toBe("dark");

    // Click Light button
    await lightButton.click();
    await expect(html).not.toHaveClass(/dark/);

    storedTheme = await authenticatedPage.evaluate(() =>
      localStorage.getItem("theme"),
    );
    expect(storedTheme).toBe("light");

    // Click System button (with light OS preference, should stay light)
    await systemButton.click();
    await expect(html).not.toHaveClass(/dark/);

    storedTheme = await authenticatedPage.evaluate(() =>
      localStorage.getItem("theme"),
    );
    expect(storedTheme).toBe("system");
  });

  test("dark mode applies correct styles to header", async ({
    authenticatedPage,
  }) => {
    // Start in dark mode
    await authenticatedPage.addInitScript(() => {
      localStorage.setItem("theme", "dark");
    });
    await authenticatedPage.goto(".");
    await authenticatedPage.waitForLoadState("domcontentloaded");

    const html = authenticatedPage.locator("html");
    await expect(html).toHaveClass(/dark/);

    // Header should have dark background styling
    const header = authenticatedPage.locator("header").first();
    await expect(header).toBeVisible();

    // Verify the header has the dark mode class applied
    // The header uses "bg-white dark:bg-slate-800" — in dark mode,
    // computed background should be a dark color
    const bgColor = await header.evaluate((el) => {
      return window.getComputedStyle(el).backgroundColor;
    });

    // bg-slate-800 is roughly rgb(30, 41, 59) — verify it is dark
    // We just check it is not white (rgb(255, 255, 255))
    expect(bgColor).not.toBe("rgb(255, 255, 255)");
  });

  test("theme toggle button shows correct icon label", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.addInitScript(() => {
      localStorage.setItem("theme", "light");
    });
    await authenticatedPage.goto(".");
    await authenticatedPage.waitForLoadState("domcontentloaded");

    const themeToggle = authenticatedPage.getByRole("button", {
      name: /theme:/i,
    });
    await expect(themeToggle).toBeVisible();

    // Light mode: aria-label should say "Theme: light"
    await expect(themeToggle).toHaveAttribute(
      "aria-label",
      "Theme: light. Click to switch.",
    );

    // Click to dark
    await themeToggle.click();
    await expect(themeToggle).toHaveAttribute(
      "aria-label",
      "Theme: dark. Click to switch.",
    );

    // Click to system
    await themeToggle.click();
    await expect(themeToggle).toHaveAttribute(
      "aria-label",
      "Theme: system. Click to switch.",
    );
  });
});
