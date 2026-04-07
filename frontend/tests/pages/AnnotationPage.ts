import type { Page, Locator } from "@playwright/test";

/**
 * Page Object Model for the Annotation Page
 *
 * Encapsulates interactions with the annotation workspace including:
 * - Grid selection
 * - Hourly value editing
 * - Annotation submission
 * - Screenshot navigation
 * - Verification workflow
 * - Skip workflow
 */
export class AnnotationPage {
  readonly page: Page;
  readonly workspace: Locator;
  readonly gridSelector: Locator;
  readonly hourlyEditor: Locator;
  readonly submitButton: Locator;
  readonly skipButton: Locator;
  readonly verifyButton: Locator;
  readonly notesTextarea: Locator;
  readonly titleInput: Locator;
  readonly ocrTotal: Locator;
  readonly barTotal: Locator;
  readonly processingIndicator: Locator;
  readonly autoSaveStatus: Locator;
  readonly nextButton: Locator;
  readonly prevButton: Locator;
  readonly screenshotSelector: Locator;
  readonly navigationInfo: Locator;
  readonly verifierInfo: Locator;

  constructor(page: Page) {
    this.page = page;
    this.workspace = page.getByTestId("annotation-workspace");
    this.gridSelector = page.getByTestId("grid-selector");
    this.hourlyEditor = page.getByTestId("hourly-editor");
    this.submitButton = page.getByRole("button", { name: /submit/i });
    this.skipButton = page.getByRole("button", { name: /skip/i });
    this.verifyButton = page.getByRole("button", { name: /verified/i });
    this.notesTextarea = page.getByLabel("Notes");
    this.titleInput = page.getByLabel(/app.*title/i);
    this.ocrTotal = page.getByTestId("ocr-total");
    this.barTotal = page.getByTestId("bar-total");
    this.processingIndicator = page.getByTestId("processing-indicator");
    this.autoSaveStatus = page.getByTestId("auto-save-status");
    this.nextButton = page.getByTestId("navigate-next");
    this.prevButton = page.getByTestId("navigate-prev");
    this.screenshotSelector = page.getByTestId("screenshot-selector");
    this.navigationInfo = page.getByTestId("navigation-info");
    this.verifierInfo = page.locator('text="Verified by:"');
  }

  /**
   * Navigate to annotation page
   * @param waitForLoad - if true, waits for screenshot to load (may timeout if no screenshots)
   */
  async goto(
    options: {
      groupId?: string;
      processingStatus?: string;
      participantId?: string;
      waitForLoad?: boolean;
    } = {},
  ) {
    const params = new URLSearchParams();
    if (options.groupId) params.set("group", options.groupId);
    if (options.processingStatus)
      params.set("processing_status", options.processingStatus);
    if (options.participantId)
      params.set("participant_id", options.participantId);

    const url = params.toString()
      ? `/annotate?${params.toString()}`
      : "/annotate";
    await this.page.goto(url);
    // Don't use networkidle - WebSocket/polling keeps network active
    await this.page.waitForLoadState("domcontentloaded");

    // Only wait for screenshot load if explicitly requested
    if (options.waitForLoad !== false) {
      await this.waitForPageReady();
    }
  }

  /**
   * Wait for page to be ready (either shows screenshot or no screenshots message)
   */
  async waitForPageReady() {
    // Wait for either workspace OR "no screenshots" message
    await Promise.race([
      this.workspace.waitFor({ state: "visible", timeout: 10000 }),
      this.page
        .getByText(/no screenshots|queue is empty|all done/i)
        .waitFor({ state: "visible", timeout: 10000 }),
    ]).catch(() => {
      // If neither appears, the page might still be loading or have an error
    });
  }

  /**
   * Wait for screenshot to load
   * Returns true if screenshot loaded, false if no screenshots available
   */
  async waitForScreenshotLoad(): Promise<boolean> {
    // Wait for page to stabilize
    await this.page.waitForTimeout(1000);

    // Wait for either workspace with content OR "no screenshots" message
    await Promise.race([
      this.workspace.waitFor({ state: "visible", timeout: 15000 }),
      this.page
        .getByText(/no screenshots|queue is empty|all done/i)
        .first()
        .waitFor({ state: "visible", timeout: 15000 }),
    ]).catch(() => {});

    // Check if we have content or empty state
    const hasWorkspace = await this.workspace.isVisible().catch(() => false);
    const hasBarTotal = await this.barTotal.isVisible().catch(() => false);
    const hasSkipButton = await this.skipButton.isVisible().catch(() => false);
    const hasNoScreenshots = await this.page
      .getByText(/no screenshots|queue is empty|all done/i)
      .first()
      .isVisible()
      .catch(() => false);

    if (hasNoScreenshots) {
      return false;
    }

    if (hasWorkspace && (hasBarTotal || hasSkipButton)) {
      return true;
    }

    // If neither, throw to indicate timeout
    throw new Error("Screenshot load timed out - no content or empty state");
  }

  /**
   * Get hourly value input for a specific hour
   */
  getHourInput(hour: number): Locator {
    return this.page.getByTestId(`hour-input-${hour}`);
  }

  /**
   * Get value for a specific hour
   */
  async getHourlyValue(hour: number): Promise<number> {
    const input = this.getHourInput(hour);
    const value = await input.inputValue();
    return parseInt(value || "0");
  }

  /**
   * Set value for a specific hour
   * @param waitForSave - if true, waits for auto-save (default: false for faster tests)
   */
  async setHourlyValue(hour: number, value: number, waitForSave = false) {
    const input = this.getHourInput(hour);
    await input.fill(value.toString());
    // Wait for auto-save indicator if requested
    if (waitForSave) {
      await this.waitForAutoSave();
    }
  }

  /**
   * Set multiple hourly values
   */
  async setHourlyData(hourlyData: Record<number, number>) {
    for (const [hour, value] of Object.entries(hourlyData)) {
      await this.setHourlyValue(parseInt(hour), value);
    }
  }

  /**
   * Set notes
   */
  async setNotes(notes: string) {
    await this.notesTextarea.fill(notes);
  }

  /**
   * Set title (for screen_time screenshots)
   */
  async setTitle(title: string) {
    await this.titleInput.fill(title);
  }

  /**
   * Submit annotation
   */
  async submitAnnotation() {
    const responsePromise = this.page.waitForResponse("/api/annotations/");
    await this.submitButton.click();
    await responsePromise;
  }

  /**
   * Skip screenshot
   */
  async skipScreenshot() {
    const responsePromise = this.page.waitForResponse(
      /\/api\/screenshots\/\d+\/skip/,
    );
    await this.skipButton.click();
    await responsePromise;
  }

  /**
   * Verify screenshot
   */
  async verifyScreenshot() {
    await this.verifyButton.click();
    await this.page.waitForResponse(/\/api\/screenshots\/\d+\/verify/);
  }

  /**
   * Unverify screenshot
   */
  async unverifyScreenshot() {
    await this.verifyButton.click();
    await this.page.waitForResponse(/\/api\/screenshots\/\d+\/unverify/);
  }

  /**
   * Navigate to next screenshot
   */
  async navigateNext() {
    await this.nextButton.click();
    await this.waitForScreenshotLoad();
  }

  /**
   * Navigate to previous screenshot
   */
  async navigatePrev() {
    await this.prevButton.click();
    await this.waitForScreenshotLoad();
  }

  /**
   * Get current screenshot index info
   */
  async getNavigationInfo(): Promise<{
    currentIndex: number;
    total: number;
    hasNext: boolean;
    hasPrev: boolean;
  }> {
    const navInfo = this.page.getByTestId("navigation-info");
    const text = await navInfo.textContent();
    const match = text?.match(/(\d+)\s*\/\s*(\d+)/);

    return {
      currentIndex: match ? parseInt(match[1]) : 0,
      total: match ? parseInt(match[2]) : 0,
      hasNext: await this.nextButton.isEnabled(),
      hasPrev: await this.prevButton.isEnabled(),
    };
  }

  /**
   * Get OCR total
   */
  async getOCRTotal(): Promise<string> {
    return (await this.ocrTotal.textContent()) || "";
  }

  /**
   * Get bar total (calculated from hourly values)
   */
  async getBarTotal(): Promise<string> {
    return (await this.barTotal.textContent()) || "";
  }

  /**
   * Check if processing indicator is visible
   */
  async isProcessing(): Promise<boolean> {
    return this.processingIndicator.isVisible();
  }

  /**
   * Wait for auto-save to complete
   */
  async waitForAutoSave() {
    // Wait for "Saving..." indicator
    await this.page
      .getByText(/saving/i)
      .waitFor({ state: "visible", timeout: 1000 })
      .catch(() => {});
    // Wait for "Saved" indicator
    await this.page
      .getByText(/saved/i)
      .waitFor({ state: "visible", timeout: 5000 })
      .catch(() => {
        // Auto-save may not trigger if no changes were made
      });
  }

  /**
   * Get auto-save status
   */
  async getAutoSaveStatus(): Promise<string> {
    return (await this.autoSaveStatus.textContent()) || "";
  }

  /**
   * Check if no screenshots message is visible
   */
  async isNoScreenshotsVisible(): Promise<boolean> {
    return this.page.getByText(/no screenshots/i).isVisible();
  }

  /**
   * Select grid coordinates (drag to select area)
   */
  async selectGridArea(coords: {
    startX: number;
    startY: number;
    endX: number;
    endY: number;
  }) {
    const canvas = this.gridSelector.locator("canvas");
    const box = await canvas.boundingBox();
    if (!box) throw new Error("Grid selector canvas not found");

    // Drag from start to end
    await this.page.mouse.move(box.x + coords.startX, box.y + coords.startY);
    await this.page.mouse.down();
    await this.page.mouse.move(box.x + coords.endX, box.y + coords.endY);
    await this.page.mouse.up();

    // Wait for processing to complete
    await this.page.waitForTimeout(500); // Debounce
    await this.page.waitForResponse(/\/api\/screenshots\/\d+\/reprocess/);
  }

  /**
   * Use keyboard shortcuts
   */
  async pressShortcut(shortcut: "Escape" | "ArrowLeft" | "ArrowRight" | "v") {
    await this.page.keyboard.press(shortcut);
  }

  /**
   * Check if screenshot is verified by current user
   */
  async isVerifiedByCurrentUser(): Promise<boolean> {
    // Check if verify button shows verified state (green background, checkmark)
    const button = this.verifyButton.first();
    if (!(await button.isVisible().catch(() => false))) {
      return false;
    }
    const buttonText = await button.textContent();
    return buttonText?.includes("Verified") && buttonText?.includes("undo") || false;
  }

  /**
   * Get current screenshot ID from URL
   */
  async getCurrentScreenshotId(): Promise<number | null> {
    const url = this.page.url();
    const match = url.match(/\/annotate\/(\d+)/);
    return match ? parseInt(match[1]) : null;
  }

  /**
   * Get verifier usernames if displayed
   */
  async getVerifierUsernames(): Promise<string[]> {
    const verifierElement = this.page.locator('text=/Verified by:/');
    if (!(await verifierElement.isVisible().catch(() => false))) {
      return [];
    }
    const text = await verifierElement.textContent();
    if (!text) return [];
    const match = text.match(/Verified by:\s*(.+)/);
    if (!match) return [];
    return match[1].split(",").map((s) => s.trim());
  }

  /**
   * Wait for verification state change
   */
  async waitForVerificationChange() {
    await this.page.waitForResponse(/\/api\/v1\/screenshots\/\d+\/(verify|unverify)/);
  }

  /**
   * Wait for skip response
   */
  async waitForSkipResponse() {
    await this.page.waitForResponse(/\/api\/v1\/screenshots\/\d+\/skip/);
  }

  /**
   * Check if "All Done" empty state is visible
   */
  async isAllDoneVisible(): Promise<boolean> {
    return this.page.getByText(/all done|no screenshots available|queue is empty/i).first().isVisible().catch(() => false);
  }

  /**
   * Get screenshot metadata from the header
   */
  async getScreenshotMetadata(): Promise<{
    id: number | null;
    groupId: string | null;
    participantId: string | null;
    date: string | null;
  }> {
    const id = await this.getCurrentScreenshotId();

    let groupId: string | null = null;
    const groupText = await this.page.locator('text=/Group:/')
      .first().textContent().catch(() => null);
    if (groupText) {
      const match = groupText.match(/Group:\s*(\S+)/);
      groupId = match ? match[1] : null;
    }

    let participantId: string | null = null;
    const pidText = await this.page.locator('text=/ID:/')
      .first().textContent().catch(() => null);
    if (pidText) {
      const match = pidText.match(/ID:\s*(\S+)/);
      participantId = match ? match[1] : null;
    }

    let date: string | null = null;
    const dateText = await this.page.locator('text=/Date:/')
      .first().textContent().catch(() => null);
    if (dateText) {
      const match = dateText.match(/Date:\s*(\S+)/);
      date = match ? match[1] : null;
    }

    return { id, groupId, participantId, date };
  }
}
