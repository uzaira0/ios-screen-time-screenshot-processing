import type { Page, Locator } from '@playwright/test';

/**
 * Page Object Model for the Admin Page
 *
 * Encapsulates interactions with the admin dashboard including:
 * - User management
 * - User role updates
 * - User activation/deactivation
 */
export class AdminPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly userTable: Locator;
  readonly accessDeniedMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: /user management/i });
    this.userTable = page.getByTestId('user-table');
    this.accessDeniedMessage = page.getByText(/access denied/i);
  }

  /**
   * Navigate to admin page
   */
  async goto() {
    await this.page.goto('/admin');
  }

  /**
   * Check if access denied message is visible
   */
  async isAccessDenied(): Promise<boolean> {
    return this.accessDeniedMessage.isVisible();
  }

  /**
   * Get user row by username
   */
  getUserRow(username: string): Locator {
    return this.userTable.getByRole('row').filter({ hasText: username });
  }

  /**
   * Get total number of users
   */
  async getUserCount(): Promise<number> {
    const rows = this.userTable.getByRole('row');
    const count = await rows.count();
    // Subtract 1 for header row
    return count > 0 ? count - 1 : 0;
  }

  /**
   * Get user info by username
   */
  async getUserInfo(username: string): Promise<{
    username: string;
    email: string;
    role: string;
    isActive: boolean;
    annotationsCount: number;
  }> {
    const row = this.getUserRow(username);

    const usernameCell = row.getByTestId('user-username');
    const emailCell = row.getByTestId('user-email');
    const roleCell = row.getByTestId('user-role');
    const activeCell = row.getByTestId('user-active');
    const annotationsCell = row.getByTestId('user-annotations');

    return {
      username: (await usernameCell.textContent()) || '',
      email: (await emailCell.textContent()) || '',
      role: (await roleCell.textContent()) || '',
      isActive: (await activeCell.textContent())?.toLowerCase() === 'active',
      annotationsCount: parseInt((await annotationsCell.textContent()) || '0'),
    };
  }

  /**
   * Update user role
   */
  async updateUserRole(username: string, newRole: 'admin' | 'annotator') {
    const row = this.getUserRow(username);
    const roleSelect = row.getByTestId('role-select');

    const responsePromise = this.page.waitForResponse(/\/api\/admin\/users\/\d+/);
    await roleSelect.selectOption(newRole);
    await responsePromise;
  }

  /**
   * Toggle user active status
   */
  async toggleUserActive(username: string) {
    const row = this.getUserRow(username);
    const activeToggle = row.getByTestId('active-toggle');

    const responsePromise = this.page.waitForResponse(/\/api\/admin\/users\/\d+/);
    await activeToggle.click();
    await responsePromise;
  }

  /**
   * Deactivate user
   */
  async deactivateUser(username: string) {
    const row = this.getUserRow(username);
    const deactivateButton = row.getByRole('button', { name: /deactivate/i });

    const responsePromise = this.page.waitForResponse(/\/api\/admin\/users\/\d+/);
    await deactivateButton.click();
    await responsePromise;
  }

  /**
   * Activate user
   */
  async activateUser(username: string) {
    const row = this.getUserRow(username);
    const activateButton = row.getByRole('button', { name: /activate/i });

    const responsePromise = this.page.waitForResponse(/\/api\/admin\/users\/\d+/);
    await activateButton.click();
    await responsePromise;
  }

  /**
   * Wait for user table to load
   */
  async waitForTableLoad() {
    await this.userTable.waitFor({ state: 'visible' });
  }

  /**
   * Search for user (if search is implemented)
   */
  async searchUser(searchTerm: string) {
    const searchInput = this.page.getByPlaceholder(/search/i);
    await searchInput.fill(searchTerm);
    await this.page.waitForTimeout(300); // Debounce
  }
}
