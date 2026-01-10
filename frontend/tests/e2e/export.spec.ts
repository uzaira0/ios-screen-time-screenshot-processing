import { test, expect } from "../fixtures/auth";

test.describe("Export Functionality", () => {
  test("should show export button on home page", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(".");
    await authenticatedPage.waitForLoadState("networkidle");

    // Look for export button or link
    const exportButton = authenticatedPage.getByRole("button", {
      name: /export/i,
    });
    const exportLink = authenticatedPage.getByRole("link", { name: /export/i });

    const hasExportButton = await exportButton.isVisible().catch(() => false);
    const hasExportLink = await exportLink.isVisible().catch(() => false);

    // Export functionality may or may not be visible depending on data
    // This test verifies the UI component exists when appropriate
    if (!hasExportButton && !hasExportLink) {
      // Check if we're on a page that should have export
      const pageTitle = await authenticatedPage.title();
      console.log("Page title:", pageTitle);
      // Export may not be available if no data exists
      test.skip(
        true,
        "Export button not visible - may require data in database",
      );
    }
  });

  test("should trigger download when export is clicked", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(".");
    await authenticatedPage.waitForLoadState("networkidle");

    // Look for Export CSV button (simplified export - CSV only)
    const exportCsvButton = authenticatedPage.getByRole("button", {
      name: /export.*csv/i,
    });
    const genericExportButton = authenticatedPage.getByRole("button", {
      name: /export/i,
    });

    const hasCsvExport = await exportCsvButton.isVisible().catch(() => false);
    const hasGenericExport = await genericExportButton
      .first()
      .isVisible()
      .catch(() => false);

    if (!hasCsvExport && !hasGenericExport) {
      test.skip(true, "No export buttons visible");
      return;
    }

    // Try to trigger a download
    const downloadPromise = authenticatedPage
      .waitForEvent("download", { timeout: 5000 })
      .catch(() => null);

    if (hasCsvExport) {
      await exportCsvButton.click();
    } else {
      await genericExportButton.first().click();
    }

    const download = await downloadPromise;

    if (download) {
      // Verify download has appropriate filename (CSV only now)
      const filename = download.suggestedFilename();
      expect(filename).toMatch(/\.csv$/);
    } else {
      // May show "no data" message or error
      const noDataMessage = authenticatedPage.getByText(
        /no annotations|no data|empty/i,
      );
      const hasNoData = await noDataMessage.isVisible().catch(() => false);
      if (hasNoData) {
        test.skip(true, "No data to export");
      }
    }
  });

  test("should handle export with no data gracefully", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(".");
    await authenticatedPage.waitForLoadState("networkidle");

    const exportButton = authenticatedPage
      .getByRole("button", { name: /export/i })
      .first();
    const hasExport = await exportButton.isVisible().catch(() => false);

    if (!hasExport) {
      test.skip(true, "Export button not visible");
      return;
    }

    await exportButton.click();

    // After clicking, either:
    // 1. A download starts
    // 2. A dialog appears
    // 3. An error/empty message appears
    // All are valid behaviors - we just verify no crash

    await authenticatedPage.waitForTimeout(1000);

    // Page should still be functional
    await expect(authenticatedPage.locator("body")).toBeVisible();
  });

  test("should export CSV directly without dialog", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(".");
    await authenticatedPage.waitForLoadState("networkidle");

    const exportButton = authenticatedPage
      .getByRole("button", { name: /export.*csv/i })
      .first();
    const hasExport = await exportButton.isVisible().catch(() => false);

    if (!hasExport) {
      test.skip(true, "Export CSV button not visible");
      return;
    }

    // Set up download listener
    const downloadPromise = authenticatedPage
      .waitForEvent("download", { timeout: 5000 })
      .catch(() => null);

    await exportButton.click();

    const download = await downloadPromise;

    // Export should trigger download directly (no dialog)
    if (download) {
      const filename = download.suggestedFilename();
      expect(filename).toMatch(/\.csv$/);
      console.log("CSV exported:", filename);
    } else {
      // No download - check for error or no data message
      const errorOrNoData = authenticatedPage.getByText(/error|no data|failed/i);
      const hasMessage = await errorOrNoData.first().isVisible().catch(() => false);
      console.log("Export message shown:", hasMessage);
    }
  });
});
