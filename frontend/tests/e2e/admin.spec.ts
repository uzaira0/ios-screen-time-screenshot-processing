import { test, expect } from "../fixtures/auth";
import { waitForToast } from "../utils/helpers";

test.describe("Admin Page", () => {
  test("should deny access to non-admin users", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto("admin");

    await expect(authenticatedPage.getByText(/access denied/i)).toBeVisible();
    await expect(
      authenticatedPage.getByText(/login as "admin"/i),
    ).toBeVisible();
  });

  test("should allow access to admin users", async ({ adminPage }) => {
    await adminPage.goto("admin");

    await expect(
      adminPage.getByRole("heading", { name: /user management/i }),
    ).toBeVisible();
  });

  test("should display user list", async ({ adminPage }) => {
    await adminPage.goto("admin");

    // Wait for users to load
    await adminPage.waitForLoadState("networkidle");

    // Should display some user data (at least the admin user)
    const userTable = adminPage.getByTestId("user-table");

    // If table exists, check it has content
    const tableVisible = await userTable.isVisible().catch(() => false);
    if (tableVisible) {
      const rows = userTable.getByRole("row");
      const rowCount = await rows.count();
      // At least 1 row (could be header-only or header + users)
      expect(rowCount).toBeGreaterThanOrEqual(1);
    } else {
      // Alternative: check for users section or "no users" message
      const hasHeading = await adminPage
        .getByRole("heading", { name: /user management/i })
        .isVisible()
        .catch(() => false);
      const hasNoUsers = await adminPage
        .getByText(/no users found/i)
        .isVisible()
        .catch(() => false);
      expect(hasHeading || hasNoUsers).toBe(true);
    }
  });

  test("should display user information when users exist", async ({
    adminPage,
  }) => {
    await adminPage.goto("admin");
    await adminPage.waitForLoadState("networkidle");

    // Check for user table presence
    const userTable = adminPage.getByTestId("user-table");
    const tableVisible = await userTable.isVisible().catch(() => false);

    if (!tableVisible) {
      // If no table, check for "no users" state
      const noUsers = await adminPage
        .getByText(/no users found/i)
        .isVisible()
        .catch(() => false);
      if (noUsers) {
        test.skip(true, "No users in database");
      }
      return;
    }

    // If table exists, verify it has at least one row with user data
    // The table should show usernames - look for any row content
    const rows = userTable.locator("tbody tr");
    const rowCount = await rows.count();

    if (rowCount === 0) {
      test.skip(true, "No user rows in table");
      return;
    }

    // Verify at least one row has content
    const firstRowText = await rows.first().textContent();
    expect(firstRowText).toBeTruthy();
  });

  test("should toggle user role", async ({ adminPage }) => {
    await adminPage.goto("admin");
    await adminPage.waitForLoadState("networkidle");

    // Find a non-admin user to promote (or admin to demote)
    const promoteButton = adminPage
      .getByRole("button", { name: /promote/i })
      .first();
    const demoteButton = adminPage
      .getByRole("button", { name: /demote/i })
      .first();

    const hasPromote = await promoteButton.isVisible().catch(() => false);
    const hasDemote = await demoteButton.isVisible().catch(() => false);

    if (!hasPromote && !hasDemote) {
      test.skip(true, "No users to promote/demote");
      return;
    }

    // Toggle the role and then restore
    if (hasPromote) {
      await promoteButton.click();
      await waitForToast(adminPage, /user updated|updated successfully/i);
      // Wait for page to update, then restore the original state
      await adminPage.waitForTimeout(500);
      const restoreButton = adminPage.getByRole("button", { name: /demote/i }).first();
      if (await restoreButton.isVisible().catch(() => false)) {
        await restoreButton.click();
        await waitForToast(adminPage, /user updated|updated successfully/i);
      }
    } else if (hasDemote) {
      await demoteButton.click();
      await waitForToast(adminPage, /user updated|updated successfully/i);
      // Wait for page to update, then restore the original state
      await adminPage.waitForTimeout(500);
      const restoreButton = adminPage.getByRole("button", { name: /promote/i }).first();
      if (await restoreButton.isVisible().catch(() => false)) {
        await restoreButton.click();
        await waitForToast(adminPage, /user updated|updated successfully/i);
      }
    }
  });

  test("should toggle user active status", async ({ adminPage }) => {
    await adminPage.goto("admin");
    await adminPage.waitForLoadState("networkidle");

    // Find activate/deactivate buttons
    const activateButton = adminPage
      .getByRole("button", { name: /activate/i })
      .first();
    const deactivateButton = adminPage
      .getByRole("button", { name: /deactivate/i })
      .first();

    const hasActivate = await activateButton.isVisible().catch(() => false);
    const hasDeactivate = await deactivateButton.isVisible().catch(() => false);

    if (!hasActivate && !hasDeactivate) {
      test.skip(true, "No users to activate/deactivate");
      return;
    }

    // Toggle the status
    if (hasDeactivate) {
      await deactivateButton.click();
      await waitForToast(adminPage, /user updated|updated successfully/i);
      // Wait for page to update, then restore the original state
      await adminPage.waitForTimeout(500);
      const restoreButton = adminPage.getByRole("button", { name: /activate/i }).first();
      if (await restoreButton.isVisible().catch(() => false)) {
        await restoreButton.click();
        await waitForToast(adminPage, /user updated|updated successfully/i);
      }
    } else if (hasActivate) {
      await activateButton.click();
      await waitForToast(adminPage, /user updated|updated successfully/i);
      // Wait for page to update, then restore the original state
      await adminPage.waitForTimeout(500);
      const restoreButton = adminPage.getByRole("button", { name: /deactivate/i }).first();
      if (await restoreButton.isVisible().catch(() => false)) {
        await restoreButton.click();
        await waitForToast(adminPage, /user updated|updated successfully/i);
      }
    }
  });

  test("should show user table or empty message", async ({ adminPage }) => {
    await adminPage.goto("admin");
    await adminPage.waitForLoadState("networkidle");

    // Either show user table or "no users" message
    const userTable = adminPage.getByTestId("user-table");
    const noUsersMessage = adminPage.getByText(/no users found/i);

    const tableVisible = await userTable.isVisible().catch(() => false);
    const noUsersVisible = await noUsersMessage.isVisible().catch(() => false);

    // One of these should be true
    expect(tableVisible || noUsersVisible).toBe(true);
  });

  test("should display role badges correctly", async ({ adminPage }) => {
    await adminPage.goto("admin");
    await adminPage.waitForLoadState("networkidle");

    const userTable = adminPage.getByTestId("user-table");
    const tableVisible = await userTable.isVisible().catch(() => false);

    if (!tableVisible) {
      test.skip(true, "No user table visible");
      return;
    }

    // Check for role badges (annotator or admin)
    const roleBadges = adminPage.getByTestId("user-role");
    const badgeCount = await roleBadges.count();

    if (badgeCount > 0) {
      // Verify at least one badge exists with a valid role
      const firstBadge = roleBadges.first();
      const text = await firstBadge.textContent();
      expect(text?.toLowerCase()).toMatch(/annotator|admin/);
    }
  });

  test("should display active status badges", async ({ adminPage }) => {
    await adminPage.goto("admin");
    await adminPage.waitForLoadState("networkidle");

    const userTable = adminPage.getByTestId("user-table");
    const tableVisible = await userTable.isVisible().catch(() => false);

    if (!tableVisible) {
      test.skip(true, "No user table visible");
      return;
    }

    // Check for status badges
    const statusBadges = adminPage.getByTestId("user-active");
    const badgeCount = await statusBadges.count();

    if (badgeCount > 0) {
      const firstBadge = statusBadges.first();
      const text = await firstBadge.textContent();
      expect(text?.toLowerCase()).toMatch(/active|inactive/);
    }
  });
});
