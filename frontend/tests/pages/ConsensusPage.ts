import type { Page, Locator } from "@playwright/test";

/**
 * Page Object Model for the Consensus Page
 *
 * Encapsulates interactions with the consensus verification view including:
 * - Summary statistics
 * - Group cards with verification tiers
 * - Screenshot tier lists
 * - Screenshot comparison view
 * - Dispute resolution
 */
export class ConsensusPage {
  readonly page: Page;

  // Summary stats
  readonly totalScreenshotsCard: Locator;
  readonly verifiedCard: Locator;
  readonly singleVerifiedCard: Locator;
  readonly agreedCard: Locator;
  readonly disputedCard: Locator;

  // Navigation
  readonly backToGroupsButton: Locator;
  readonly pageTitle: Locator;

  // Loading states
  readonly loadingSpinner: Locator;

  constructor(page: Page) {
    this.page = page;

    // Summary stat cards (by their position and text content)
    this.totalScreenshotsCard = page.locator('text="Total Screenshots"').locator("..");
    this.verifiedCard = page.locator('text="Verified"').locator("..");
    this.singleVerifiedCard = page.locator('text="Single Verified"').locator("..");
    this.agreedCard = page.locator('text="Agreed"').locator("..");
    this.disputedCard = page.locator('text="Disputed"').locator("..");

    // Navigation
    this.backToGroupsButton = page.getByRole("button", { name: /back to groups/i });
    this.pageTitle = page.locator("h1").first();

    // Loading
    this.loadingSpinner = page.locator(".animate-spin");
  }

  /**
   * Navigate to consensus page
   */
  async goto(options: { groupId?: string; tier?: string } = {}) {
    const params = new URLSearchParams();
    if (options.groupId) params.set("group", options.groupId);
    if (options.tier) params.set("tier", options.tier);

    const url = params.toString() ? `/consensus?${params.toString()}` : "/consensus";
    await this.page.goto(url);
    await this.page.waitForLoadState("domcontentloaded");
  }

  /**
   * Wait for page to fully load (spinner disappears and content appears)
   */
  async waitForLoad() {
    await this.loadingSpinner.waitFor({ state: "hidden", timeout: 15000 }).catch(() => {});
    // Wait a bit for content to render
    await this.page.waitForTimeout(500);
  }

  /**
   * Get summary statistics from the cards
   */
  async getSummaryStats(): Promise<{
    total: number;
    verified: number;
    singleVerified: number;
    agreed: number;
    disputed: number;
  }> {
    // Extract numbers from the stat cards
    const extractNumber = async (card: Locator): Promise<number> => {
      try {
        const text = await card.locator(".text-2xl, .text-lg").first().textContent();
        return parseInt(text?.trim() || "0", 10);
      } catch {
        return 0;
      }
    };

    return {
      total: await extractNumber(this.totalScreenshotsCard),
      verified: await extractNumber(this.verifiedCard),
      singleVerified: await extractNumber(this.singleVerifiedCard),
      agreed: await extractNumber(this.agreedCard),
      disputed: await extractNumber(this.disputedCard),
    };
  }

  /**
   * Get all group cards on the page
   */
  async getGroupCards(): Promise<
    Array<{
      name: string;
      imageType: string;
      totalVerified: string;
      singleVerified: number;
      agreed: number;
      disputed: number;
    }>
  > {
    const cards = this.page.locator(".bg-white.border.border-gray-200.rounded-lg.p-5");
    const count = await cards.count();
    const groups: Array<{
      name: string;
      imageType: string;
      totalVerified: string;
      singleVerified: number;
      agreed: number;
      disputed: number;
    }> = [];

    for (let i = 0; i < count; i++) {
      const card = cards.nth(i);

      // Get group name
      const name = (await card.locator("h3").textContent())?.trim() || "";

      // Get image type badge
      const typeBadge = card.locator("span.text-xs.rounded-full");
      const imageType = (await typeBadge.textContent())?.trim() || "";

      // Get total verified (e.g., "15 / 100")
      const verifiedText = (await card.locator(".text-blue-600").textContent())?.trim() || "0 / 0";

      // Get tier counts from the grid (3 columns: single, agreed, disputed)
      const tierCounts = card.locator(".grid.grid-cols-3 .text-lg");
      const singleVerified = parseInt((await tierCounts.nth(0).textContent())?.trim() || "0", 10);
      const agreed = parseInt((await tierCounts.nth(1).textContent())?.trim() || "0", 10);
      const disputed = parseInt((await tierCounts.nth(2).textContent())?.trim() || "0", 10);

      groups.push({
        name,
        imageType,
        totalVerified: verifiedText,
        singleVerified,
        agreed,
        disputed,
      });
    }

    return groups;
  }

  /**
   * Click on a specific tier for a group
   */
  async clickGroupTier(groupName: string, tier: "single_verified" | "agreed" | "disputed") {
    // Find the group card
    const card = this.page.locator(".bg-white.border.border-gray-200.rounded-lg.p-5").filter({
      has: this.page.locator("h3", { hasText: groupName }),
    });

    // Map tier to column index
    const tierIndex = tier === "single_verified" ? 0 : tier === "agreed" ? 1 : 2;

    // Click the tier cell in the grid
    const tierCells = card.locator(".grid.grid-cols-3 > div");
    await tierCells.nth(tierIndex).click();

    await this.waitForLoad();
  }

  /**
   * Get screenshots in the current tier list view
   */
  async getTierScreenshots(): Promise<
    Array<{
      id: number;
      participantId: string | null;
      date: string | null;
      title: string | null;
      verifierCount: number;
      hasDifferences: boolean;
    }>
  > {
    // Wait for the list to load
    await this.page.waitForTimeout(500);

    // Try multiple possible selectors for list items
    let items = this.page.locator(".divide-y .p-4.hover\\:bg-gray-50");
    let count = await items.count();

    // If no items found with first selector, try alternative
    if (count === 0) {
      items = this.page.locator("[data-testid='screenshot-item'], .cursor-pointer.border-b");
      count = await items.count();
    }

    const screenshots: Array<{
      id: number;
      participantId: string | null;
      date: string | null;
      title: string | null;
      verifierCount: number;
      hasDifferences: boolean;
    }> = [];

    for (let i = 0; i < count; i++) {
      const item = items.nth(i);

      try {
        // Get screenshot ID (format: #123) - try multiple selectors
        let idText = "#0";
        const idElement = item.locator(".font-medium.text-gray-900, .font-semibold, [data-testid='screenshot-id']").first();
        if (await idElement.isVisible({ timeout: 1000 }).catch(() => false)) {
          idText = (await idElement.textContent())?.trim() || "#0";
        }
        const id = parseInt(idText.replace("#", ""), 10);

        // Get participant ID (purple text) - optional
        let participantId: string | null = null;
        const participantElement = item.locator(".text-purple-600, [data-testid='participant-id']").first();
        if (await participantElement.isVisible({ timeout: 500 }).catch(() => false)) {
          participantId = (await participantElement.textContent())?.trim() || null;
        }

        // Get date (gray text) - optional
        let dateText: string | null = null;
        const dateElement = item.locator(".text-gray-500, .text-sm.text-gray-600").first();
        if (await dateElement.isVisible({ timeout: 500 }).catch(() => false)) {
          dateText = (await dateElement.textContent())?.trim() || null;
        }

        // Get title - optional
        let title: string | null = null;
        const titleElement = item.locator(".text-gray-500.truncate, .truncate").first();
        if (await titleElement.isVisible({ timeout: 500 }).catch(() => false)) {
          title = (await titleElement.textContent())?.trim() || null;
        }

        // Get verifier count - optional
        let verifierCount = 0;
        const verifierElement = item.locator('text=/verifier/i').first();
        if (await verifierElement.isVisible({ timeout: 500 }).catch(() => false)) {
          const verifierText = (await verifierElement.textContent())?.trim() || "0";
          verifierCount = parseInt(verifierText.match(/\d+/)?.[0] || "0", 10);
        }

        // Check for differences badge - optional
        const hasDifferences = await item.locator('text="Has Differences"').isVisible().catch(() => false);

        screenshots.push({
          id,
          participantId,
          date: dateText,
          title,
          verifierCount,
          hasDifferences,
        });
      } catch {
        // Skip items that can't be parsed
        continue;
      }
    }

    return screenshots;
  }

  /**
   * Click on a screenshot in the tier list to open comparison view
   */
  async clickScreenshot(screenshotId: number) {
    const item = this.page.locator(`.p-4.hover\\:bg-gray-50`).filter({
      has: this.page.locator(`text="#${screenshotId}"`),
    });
    await item.click();

    // Wait for navigation to comparison page
    await this.page.waitForURL(/\/consensus\/compare\/\d+/);
  }

  /**
   * Go back to groups view
   */
  async backToGroups() {
    await this.backToGroupsButton.click();
    await this.waitForLoad();
  }

  /**
   * Check if the empty state is shown
   */
  async isEmptyStateVisible(): Promise<boolean> {
    const emptyText = this.page.locator('text="No Verified Screenshots"');
    return emptyText.isVisible();
  }

  /**
   * Check if no screenshots message is shown in tier list
   */
  async isNoScreenshotsInTierVisible(): Promise<boolean> {
    const emptyText = this.page.locator('text="No screenshots in this category"');
    return emptyText.isVisible();
  }

  /**
   * Get the current tier selection info
   */
  async getCurrentTierInfo(): Promise<{
    groupName: string;
    tier: string;
    count: number;
  } | null> {
    const tierBadge = this.page.locator(".px-3.py-1.rounded-full");
    if (!(await tierBadge.isVisible())) {
      return null;
    }

    const badgeText = (await tierBadge.textContent())?.trim() || "";
    // Parse "Single (10)" or "Agreed (5)" format
    const match = badgeText.match(/(\w+)\s*\((\d+)\)/);
    if (!match) return null;

    const groupHeader = this.page.locator("h2.text-lg.font-semibold");
    const groupName = (await groupHeader.textContent())?.trim() || "";

    const tierMap: Record<string, string> = {
      Single: "single_verified",
      Agreed: "agreed",
      Disputed: "disputed",
    };

    return {
      groupName,
      tier: tierMap[match[1]] || match[1].toLowerCase(),
      count: parseInt(match[2], 10),
    };
  }
}

/**
 * Page Object Model for the Consensus Comparison Page
 */
export class ConsensusComparisonPage {
  readonly page: Page;

  // Screenshot info
  readonly screenshotImage: Locator;
  readonly screenshotId: Locator;

  // Navigation
  readonly backButton: Locator;

  // Comparison table
  readonly comparisonTable: Locator;

  // Resolve dispute modal
  readonly resolveButton: Locator;
  readonly resolveModal: Locator;

  constructor(page: Page) {
    this.page = page;

    this.screenshotImage = page.locator("img[alt*='Screenshot']");
    this.screenshotId = page.locator('text=/Screenshot #\\d+/');
    this.backButton = page.getByRole("button", { name: /back/i });
    this.comparisonTable = page.locator("table");
    this.resolveButton = page.getByRole("button", { name: /resolve/i });
    this.resolveModal = page.locator('[role="dialog"]');
  }

  /**
   * Navigate to comparison page for a specific screenshot
   */
  async goto(screenshotId: number) {
    await this.page.goto(`/consensus/compare/${screenshotId}`);
    await this.page.waitForLoadState("domcontentloaded");
  }

  /**
   * Wait for page to load
   */
  async waitForLoad() {
    // Wait for screenshot image or error message
    await Promise.race([
      this.screenshotImage.waitFor({ state: "visible", timeout: 10000 }),
      this.page.locator('text=/not found|error/i').waitFor({ state: "visible", timeout: 10000 }),
    ]).catch(() => {});
  }

  /**
   * Get verifier annotations from the comparison table
   */
  async getVerifierAnnotations(): Promise<
    Array<{
      username: string;
      hourlyValues: Record<string, number | null>;
    }>
  > {
    // This depends on the actual table structure
    const rows = this.comparisonTable.locator("tbody tr");
    const count = await rows.count();
    const annotations: Array<{
      username: string;
      hourlyValues: Record<string, number | null>;
    }> = [];

    for (let i = 0; i < count; i++) {
      const row = rows.nth(i);
      const cells = row.locator("td");

      const username = (await cells.first().textContent())?.trim() || "";

      // Skip header rows or rows without username
      if (!username || username === "Hour") continue;

      const hourlyValues: Record<string, number | null> = {};
      // Hourly values would be in subsequent columns
      // This is simplified - real implementation depends on table structure

      annotations.push({ username, hourlyValues });
    }

    return annotations;
  }

  /**
   * Get highlighted differences
   */
  async getDifferences(): Promise<string[]> {
    const diffCells = this.page.locator(".text-red-700, .bg-red-100");
    const count = await diffCells.count();
    const differences: string[] = [];

    for (let i = 0; i < count; i++) {
      const text = await diffCells.nth(i).textContent();
      if (text) differences.push(text.trim());
    }

    return differences;
  }

  /**
   * Check if resolve button is visible (only for disputed screenshots)
   */
  async isResolveButtonVisible(): Promise<boolean> {
    return this.resolveButton.isVisible();
  }

  /**
   * Open resolve dispute modal
   */
  async openResolveModal() {
    await this.resolveButton.click();
    await this.resolveModal.waitFor({ state: "visible" });
  }

  /**
   * Submit resolution
   */
  async submitResolution(values: { hourlyValues?: Record<string, number>; notes?: string }) {
    // Fill in resolution form based on actual modal structure
    if (values.notes) {
      const notesInput = this.resolveModal.locator('textarea, input[name="notes"]');
      if (await notesInput.isVisible()) {
        await notesInput.fill(values.notes);
      }
    }

    const submitBtn = this.resolveModal.getByRole("button", { name: /confirm|submit|save/i });
    await submitBtn.click();

    // Wait for modal to close
    await this.resolveModal.waitFor({ state: "hidden" });
  }

  /**
   * Go back to consensus page
   */
  async goBack() {
    await this.backButton.click();
    await this.page.waitForURL(/\/consensus/);
  }

  /**
   * Check if error state is shown
   */
  async isErrorVisible(): Promise<boolean> {
    return this.page.locator('text=/not found|error/i').isVisible();
  }

  /**
   * Get screenshot info
   */
  async getScreenshotInfo(): Promise<{
    id: number;
    participantId: string | null;
    date: string | null;
  }> {
    const idText = (await this.screenshotId.textContent())?.trim() || "#0";
    const idMatch = idText.match(/#(\d+)/);

    return {
      id: idMatch ? parseInt(idMatch[1], 10) : 0,
      participantId: null, // Extract from page if displayed
      date: null, // Extract from page if displayed
    };
  }
}
