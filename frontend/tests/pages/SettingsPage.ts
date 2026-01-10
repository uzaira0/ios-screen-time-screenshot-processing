import type { Page, Locator } from "@playwright/test";

/**
 * Page Object Model for the Settings Page
 *
 * Encapsulates interactions with settings including:
 * - Mode information display
 * - Mode switching (WASM/Server)
 * - Settings toggles
 * - About section
 */
export class SettingsPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly currentModeSection: Locator;
  readonly modeSwitchSection: Locator;
  readonly localModeSettings: Locator;
  readonly serverModeSettings: Locator;
  readonly aboutSection: Locator;
  readonly backLink: Locator;

  constructor(page: Page) {
    this.page = page;
    // Use exact: true to avoid matching "Server Mode Settings"
    this.heading = page.getByRole("heading", { name: "Settings", exact: true });
    this.currentModeSection = page.locator("text=Current Mode").first();
    this.modeSwitchSection = page.locator("text=Switch Processing Mode").first();
    this.localModeSettings = page.locator("text=Local Mode Settings").first();
    this.serverModeSettings = page.locator("text=Server Mode Settings").first();
    this.aboutSection = page.getByRole("heading", { name: "About" });
    this.backLink = page.getByRole("link", { name: /back to/i });
  }

  /**
   * Navigate to settings page
   */
  async goto() {
    await this.page.goto("settings");
    await this.page.waitForLoadState("domcontentloaded");
  }

  /**
   * Get current mode (WASM or Server)
   */
  async getCurrentMode(): Promise<"wasm" | "server"> {
    const modeText = await this.page
      .locator("text=Current Mode:")
      .first()
      .textContent();
    return modeText?.includes("Local") ? "wasm" : "server";
  }

  /**
   * Check if mode switching is available
   */
  async canSwitchMode(): Promise<boolean> {
    return this.modeSwitchSection.isVisible();
  }

  /**
   * Toggle a setting by its label
   */
  async toggleSetting(settingName: string) {
    const settingRow = this.page.locator(`text=${settingName}`).first();
    const checkbox = settingRow.locator("xpath=..").locator('input[type="checkbox"]');
    await checkbox.click();
  }

  /**
   * Check if a setting is enabled
   */
  async isSettingEnabled(settingName: string): Promise<boolean> {
    const settingRow = this.page.locator(`text=${settingName}`).first();
    const checkbox = settingRow.locator("xpath=..").locator('input[type="checkbox"]');
    return checkbox.isChecked();
  }

  /**
   * Get version info from About section
   */
  async getVersion(): Promise<string> {
    // The version is in format: <strong>Version:</strong> 1.0.0
    // We need to get the parent element that contains both the label and value
    const versionElement = this.page.locator("strong:has-text('Version:')").locator("xpath=..");
    const fullText = await versionElement.textContent();
    // Extract version number from "Version: 1.0.0"
    const match = fullText?.match(/Version:\s*(\d+\.\d+\.\d+)/);
    return match?.[1] || "";
  }

  /**
   * Get build info from About section
   */
  async getBuildInfo(): Promise<string> {
    const buildText = await this.page
      .locator("text=Build:")
      .first()
      .textContent();
    return buildText?.replace("Build:", "").trim() || "";
  }

  /**
   * Navigate back to home
   */
  async navigateBack() {
    await this.backLink.click();
    // Wait for navigation to complete - handle both absolute and relative URLs
    await this.page.waitForLoadState("domcontentloaded");
    // The URL will be like "http://127.0.0.1:5175/" - check pathname
    await this.page.waitForFunction(() => {
      const path = window.location.pathname;
      return path.endsWith("/") || path.endsWith("/home");
    }, { timeout: 10000 });
  }

  /**
   * Get data storage info
   */
  async getDataStorageInfo(): Promise<string> {
    const storageElement = this.page.locator("text=Data Storage").first();
    const parentCard = storageElement.locator("xpath=..");
    const valueElement = parentCard.locator(".text-gray-600");
    return (await valueElement.textContent()) || "";
  }

  /**
   * Get processing info
   */
  async getProcessingInfo(): Promise<string> {
    const processingElement = this.page.locator("text=Processing").first();
    const parentCard = processingElement.locator("xpath=..");
    const valueElement = parentCard.locator(".text-gray-600");
    return (await valueElement.textContent()) || "";
  }

  /**
   * Get network requirement info
   */
  async getNetworkInfo(): Promise<string> {
    const networkElement = this.page.locator("text=Network Required").first();
    const parentCard = networkElement.locator("xpath=..");
    const valueElement = parentCard.locator(".text-gray-600");
    return (await valueElement.textContent()) || "";
  }
}
