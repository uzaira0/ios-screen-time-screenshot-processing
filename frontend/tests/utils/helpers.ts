import type { Page, APIRequestContext } from "@playwright/test";

/**
 * Login helper function
 */
export async function login(page: Page, username: string) {
  await page.goto("login");
  await page.getByLabel("Username").fill(username);
  await page.getByRole("button", { name: /login/i }).click();
  await page.waitForURL("**/");
}

/**
 * Logout helper function
 */
export async function logout(page: Page) {
  await page.getByRole("button", { name: /logout/i }).click();
  await page.waitForURL("**/login");
}

/**
 * Wait for API response helper
 */
export async function waitForAPIResponse<T>(
  page: Page,
  urlPattern: string | RegExp,
  action: () => Promise<void>,
): Promise<T> {
  const responsePromise = page.waitForResponse(urlPattern);
  await action();
  const response = await responsePromise;
  return response.json();
}

/**
 * Mock API endpoint helper
 */
export async function mockAPIEndpoint(
  page: Page,
  method: "GET" | "POST" | "PUT" | "DELETE",
  urlPattern: string | RegExp,
  responseData: any,
  statusCode: number = 200,
) {
  await page.route(urlPattern, async (route) => {
    if (route.request().method() === method) {
      await route.fulfill({
        status: statusCode,
        contentType: "application/json",
        body: JSON.stringify(responseData),
      });
    } else {
      await route.continue();
    }
  });
}

/**
 * Upload screenshot helper (via API)
 *
 * Uses the base64-encoded JSON upload endpoint.
 * Requires UPLOAD_API_KEY to be set (defaults to dev key).
 */
export async function uploadScreenshot(
  request: APIRequestContext,
  baseURL: string,
  file: Buffer,
  filename: string,
  imageType: "battery" | "screen_time" = "screen_time",
  options: {
    apiKey?: string;
    groupId?: string;
    participantId?: string;
  } = {},
) {
  const {
    apiKey = "dev-upload-key-change-in-production",
    groupId = "test-group",
    participantId = "test-participant",
  } = options;

  // Convert buffer to base64
  const base64Image = file.toString("base64");

  const response = await request.post(`${baseURL}/api/v1/screenshots/upload`, {
    headers: {
      "X-API-Key": apiKey,
    },
    data: {
      screenshot: base64Image,
      participant_id: participantId,
      group_id: groupId,
      image_type: imageType,
      filename: filename,
    },
  });

  return response.json();
}

/**
 * Wait for element to be visible with custom timeout
 */
export async function waitForVisible(
  page: Page,
  selector: string,
  timeout: number = 5000,
) {
  await page.waitForSelector(selector, { state: "visible", timeout });
}

/**
 * Fill hourly data inputs
 */
export async function fillHourlyData(
  page: Page,
  hourlyData: Record<number, number>,
) {
  for (const [hour, value] of Object.entries(hourlyData)) {
    await page.getByTestId(`hour-input-${hour}`).fill(value.toString());
  }
}

/**
 * Get screenshot from test fixtures
 */
export function getTestImagePath(filename: string): string {
  return `./tests/fixtures/images/${filename}`;
}

/**
 * Wait for toast notification
 */
export async function waitForToast(page: Page, message: string | RegExp) {
  await page
    .getByRole("status")
    .filter({ hasText: message })
    .waitFor({ state: "visible" });
}

/**
 * Dismiss toast notification
 */
export async function dismissToast(page: Page) {
  const toast = page.getByRole("status").first();
  if (await toast.isVisible()) {
    await toast.getByRole("button", { name: /close/i }).click();
  }
}

/**
 * Navigate to annotation page with filters
 */
export async function navigateToAnnotation(
  page: Page,
  options: {
    groupId?: string;
    processingStatus?: string;
    participantId?: string;
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
  await page.goto(url);
}

/**
 * Wait for screenshot to load in annotation workspace
 */
export async function waitForScreenshotLoad(page: Page) {
  await page.getByTestId("annotation-workspace").waitFor({ state: "visible" });
  await page.getByTestId("grid-selector").waitFor({ state: "visible" });
}

/**
 * Submit annotation helper
 */
export async function submitAnnotation(page: Page, notes?: string) {
  if (notes) {
    await page.getByLabel("Notes").fill(notes);
  }

  const responsePromise = page.waitForResponse("/api/annotations/");
  await page.getByRole("button", { name: /submit/i }).click();
  await responsePromise;
}

/**
 * Skip screenshot helper
 */
export async function skipScreenshot(page: Page) {
  const responsePromise = page.waitForResponse(/\/api\/screenshots\/\d+\/skip/);
  await page.getByRole("button", { name: /skip/i }).click();
  await responsePromise;
}

/**
 * Check if element has text content
 */
export async function hasText(
  page: Page,
  selector: string,
  text: string | RegExp,
): Promise<boolean> {
  const element = page.locator(selector);
  const content = await element.textContent();
  if (typeof text === "string") {
    return content?.includes(text) || false;
  }
  return text.test(content || "");
}
