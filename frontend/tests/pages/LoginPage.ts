import type { Page, Locator } from "@playwright/test";
import { expect } from "@playwright/test";

/**
 * Page Object Model for the Login Page
 *
 * Encapsulates interactions with the login page
 */
export class LoginPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly usernameInput: Locator;
  readonly loginButton: Locator;
  readonly errorMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole("heading", { name: /ios screen time/i });
    // Use placeholder since label is sr-only
    this.usernameInput = page.getByPlaceholder("Username");
    // Button text is "Continue", not "Login"
    this.loginButton = page.getByRole("button", { name: /continue/i });
    this.errorMessage = page.getByTestId("login-error");
  }

  /**
   * Navigate to login page
   */
  async goto() {
    await this.page.goto("login");
    await this.heading.waitFor({ state: "visible" });
  }

  /**
   * Login with username
   * Waits for form to be stable before interacting
   */
  async login(username: string) {
    // Wait for page to be fully loaded
    await this.page.waitForLoadState("networkidle");

    // Wait for input to be visible and fill it
    await this.usernameInput.waitFor({ state: "visible" });
    await this.usernameInput.fill(username);

    // Verify the value was entered (helps with React controlled inputs)
    await expect(this.usernameInput).toHaveValue(username);

    // Wait for button to become enabled
    await expect(this.loginButton).toBeEnabled({ timeout: 5000 });

    // Click the button
    await this.loginButton.click();

    // Redirects to home page after login
    await this.page.waitForURL(/(?!.*\/login)/);
  }

  /**
   * Check if error message is visible
   */
  async isErrorVisible(): Promise<boolean> {
    return this.errorMessage.isVisible();
  }

  /**
   * Get error message text
   */
  async getErrorMessage(): Promise<string> {
    return (await this.errorMessage.textContent()) || "";
  }
}
