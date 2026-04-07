import type { Page, Locator } from "@playwright/test";

/**
 * Page Object Model for the Home Page
 *
 * Encapsulates interactions with the homepage including:
 * - Group listing
 * - Statistics display
 * - Navigation to annotation page
 * - Admin features (delete group)
 */
export class HomePage {
  readonly page: Page;
  readonly heading: Locator;
  readonly groupsSection: Locator;
  readonly annotateAllButton: Locator;
  readonly loginButton: Locator;
  readonly emptyState: Locator;
  readonly exportCsvButton: Locator;
  readonly deleteConfirmModal: Locator;

  constructor(page: Page) {
    this.page = page;
    // Match "Study Groups" heading on the home page
    this.heading = page.getByRole("heading", {
      name: /study groups/i,
    });
    this.groupsSection = page.getByTestId("groups-section");
    this.annotateAllButton = page.getByRole("link", { name: /annotate all/i });
    this.loginButton = page.getByRole("link", { name: /login/i });
    this.emptyState = page.getByTestId("empty-groups-state");
    this.exportCsvButton = page.getByRole("button", { name: /export csv/i });
    this.deleteConfirmModal = page.locator('[role="dialog"], .fixed.inset-0');
  }

  /**
   * Navigate to home page
   */
  async goto() {
    await this.page.goto(".");
    await this.heading.waitFor({ state: "visible" });
  }

  /**
   * Get number of groups displayed
   */
  async getGroupCount(): Promise<number> {
    const groups = this.page.getByTestId("group-card");
    return groups.count();
  }

  /**
   * Get group card by name
   */
  getGroupCard(groupName: string): Locator {
    return this.page.getByTestId("group-card").filter({ hasText: groupName });
  }

  /**
   * Click on a group to navigate to annotation page
   */
  async selectGroup(groupName: string) {
    // Click on the total screenshots area which triggers navigation
    await this.getGroupCard(groupName).getByTestId("total-screenshots").click();
  }

  /**
   * Click on a specific processing status within a group
   */
  async selectGroupByStatus(
    groupName: string,
    status: "pending" | "completed" | "failed" | "skipped",
  ) {
    const groupCard = this.getGroupCard(groupName);
    await groupCard.getByTestId(`status-${status}`).click();
  }

  /**
   * Get stats value for a group
   */
  async getGroupStats(groupName: string): Promise<{
    total: number;
    pending: number;
    completed: number;
    failed: number;
    skipped: number;
  }> {
    const groupCard = this.getGroupCard(groupName);

    // Extract just the number from text - the bold element contains only the number
    const extractNumber = (text: string | null): number => {
      if (!text) return 0;
      const match = text.match(/\d+/);
      return match ? parseInt(match[0]) : 0;
    };

    // Get the bold number from each stat element
    const total = await groupCard
      .getByTestId("total-screenshots")
      .locator(".font-bold")
      .textContent();
    const pending = await groupCard
      .getByTestId("status-pending")
      .locator(".font-bold")
      .textContent();
    const completed = await groupCard
      .getByTestId("status-completed")
      .locator(".font-bold")
      .textContent();
    const failed = await groupCard
      .getByTestId("status-failed")
      .locator(".font-bold")
      .textContent();
    const skipped = await groupCard
      .getByTestId("status-skipped")
      .locator(".font-bold")
      .textContent();

    return {
      total: extractNumber(total),
      pending: extractNumber(pending),
      completed: extractNumber(completed),
      failed: extractNumber(failed),
      skipped: extractNumber(skipped),
    };
  }

  /**
   * Check if empty state is visible
   */
  async isEmptyStateVisible(): Promise<boolean> {
    return this.emptyState.isVisible();
  }

  /**
   * Click "Annotate All" button
   */
  async clickAnnotateAll() {
    await this.annotateAllButton.click();
  }

  /**
   * Click "Login" button
   */
  async clickLogin() {
    await this.loginButton.click();
  }

  /**
   * Wait for groups to load
   */
  async waitForGroupsLoad() {
    // Wait for network to settle first
    await this.page.waitForLoadState("networkidle");

    // Give React time to render after API response
    await this.page.waitForTimeout(500);

    // Wait for either groups or empty state
    await Promise.race([
      this.page
        .getByTestId("group-card")
        .first()
        .waitFor({ state: "visible", timeout: 10000 }),
      this.emptyState.waitFor({ state: "visible", timeout: 10000 }),
    ]).catch(() => {
      // If neither appears, that's okay - might still be loading
    });
  }

  /**
   * Check if admin delete button is visible for a group
   */
  async isDeleteButtonVisible(groupName: string): Promise<boolean> {
    const groupCard = this.getGroupCard(groupName);
    const deleteButton = groupCard.getByRole("button", { name: /delete/i });
    return deleteButton.isVisible().catch(() => false);
  }

  /**
   * Click delete button for a group (admin only)
   */
  async clickDeleteGroup(groupName: string) {
    const groupCard = this.getGroupCard(groupName);
    const deleteButton = groupCard.getByRole("button", { name: /delete/i });
    await deleteButton.click();
  }

  /**
   * Confirm delete in the modal
   */
  async confirmDelete() {
    const confirmButton = this.deleteConfirmModal.getByRole("button", {
      name: /delete group/i,
    });
    await confirmButton.click();
  }

  /**
   * Cancel delete in the modal
   */
  async cancelDelete() {
    const cancelButton = this.deleteConfirmModal.getByRole("button", {
      name: /cancel/i,
    });
    await cancelButton.click();
  }

  /**
   * Check if delete confirmation modal is visible
   */
  async isDeleteModalVisible(): Promise<boolean> {
    return this.deleteConfirmModal.isVisible().catch(() => false);
  }

  /**
   * Get stats for deleted screenshots in a group
   */
  async getDeletedCount(groupName: string): Promise<number> {
    const groupCard = this.getGroupCard(groupName);
    const deletedElement = groupCard.getByTestId("status-deleted");
    if (!(await deletedElement.isVisible().catch(() => false))) {
      return 0;
    }
    const text = await deletedElement.locator(".font-bold").textContent();
    return text ? parseInt(text.match(/\d+/)?.[0] || "0") : 0;
  }
}
