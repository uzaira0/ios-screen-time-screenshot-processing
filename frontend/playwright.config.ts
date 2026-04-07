import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "url";
import path from "path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Test database URL - separate from development database
const TEST_DATABASE_URL =
  "postgresql+asyncpg://screenshot:screenshot@localhost:5435/screenshot_annotations_test";

/**
 * See https://playwright.dev/docs/test-configuration.
 */
export default defineConfig({
  testDir: "./tests",

  /* Global setup - resets test database before all tests */
  globalSetup: path.join(__dirname, "tests/setup/global-setup.ts"),

  /* Run tests in files in parallel */
  fullyParallel: true,

  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,

  /* Retry on CI only */
  retries: process.env.CI ? 2 : 0,

  /* Limit workers to avoid concurrency issues */
  workers: 1,

  /* Reporter to use. See https://playwright.dev/docs/test-reporters */
  reporter: [
    ["html", { outputFolder: "playwright-report" }],
    ["list"],
    ...(process.env.CI ? [["json", { outputFile: "test-results.json" }]] : []),
  ],

  /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
  use: {
    /* Base URL to use in actions like `await page.goto('/')`. */
    baseURL:
      process.env.PLAYWRIGHT_BASE_URL ||
      "http://127.0.0.1:5175/ios-screen-time-screenshot-processing/",

    /* Collect trace when retrying the failed test. See https://playwright.dev/docs/trace-viewer */
    trace: "on-first-retry",

    /* Screenshot on failure */
    screenshot: "only-on-failure",

    /* Video on failure */
    video: "retain-on-failure",

    /* Timeout for each action */
    actionTimeout: 10_000,

    /* Navigation timeout */
    navigationTimeout: 30_000,
  },

  /* Configure projects for major browsers */
  projects: [
    {
      name: "setup",
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: "upload-data",
      testMatch: /upload-screenshots\.setup\.ts/,
      dependencies: ["setup"],
    },

    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        // Use saved auth state from setup
        storageState: "playwright/.auth/user.json",
      },
      dependencies: ["setup", "upload-data"],
    },

    {
      name: "firefox",
      use: {
        ...devices["Desktop Firefox"],
        storageState: "playwright/.auth/user.json",
      },
      dependencies: ["setup"],
    },

    {
      name: "webkit",
      use: {
        ...devices["Desktop Safari"],
        storageState: "playwright/.auth/user.json",
      },
      dependencies: ["setup"],
    },

    /* Mobile viewports disabled - not a priority
    {
      name: "Mobile Chrome",
      use: {
        ...devices["Pixel 5"],
        storageState: "playwright/.auth/user.json",
      },
      dependencies: ["setup"],
    },
    {
      name: "Mobile Safari",
      use: {
        ...devices["iPhone 12"],
        storageState: "playwright/.auth/user.json",
      },
      dependencies: ["setup"],
    },
    */

    /* Test against branded browsers. */
    // {
    //   name: 'Microsoft Edge',
    //   use: { ...devices['Desktop Edge'], channel: 'msedge' },
    // },
    // {
    //   name: 'Google Chrome',
    //   use: { ...devices['Desktop Chrome'], channel: 'chrome' },
    // },
  ],

  /* Run your local dev servers before starting the tests */
  webServer: process.env.CI
    ? undefined
    : [
        {
          // Backend API server - uses TEST database (separate from dev)
          // Requires: docker-compose -f docker/docker-compose.dev.yml up -d
          command:
            "uvicorn src.screenshot_processor.web.api.main:app --host 127.0.0.1 --port 8002",
          url: "http://127.0.0.1:8002/health",
          cwd: "..",
          env: {
            ...process.env,
            DATABASE_URL: TEST_DATABASE_URL,
            SECRET_KEY:
              "test-secret-key-for-playwright-at-least-32-characters-long",
          },
          reuseExistingServer: true,
          timeout: 180_000, // 3 minutes for PostgreSQL startup
        },
        {
          // Frontend dev server
          command: "bun run dev -- --host 127.0.0.1 --port 5175",
          url: "http://127.0.0.1:5175",
          env: {
            ...process.env,
            VITE_PROXY_TARGET: "http://127.0.0.1:8002",
          },
          reuseExistingServer: true,
          timeout: 120_000,
        },
      ],

  /* Global timeout for each test */
  timeout: 30_000,

  /* Expect timeout */
  expect: {
    timeout: 5_000,
  },

  /* Output folder for test artifacts */
  outputDir: "test-results/",
});
