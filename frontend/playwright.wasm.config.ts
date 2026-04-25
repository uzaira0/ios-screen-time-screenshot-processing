import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Playwright config for the WASM smoke suite.
 *
 * Auto-runs `python3 tests/spa-server.py 9091 dist` against the production
 * build artifacts so the suite can run with one command:
 *   bunx playwright test --config playwright.wasm.config.ts
 *
 * Global setup (tests/setup/wasm-global-setup.ts) populates
 * /tmp/test-screenshots/ from tests/fixtures/images/ before the first test.
 *
 * Only runs files under tests/ that match wasm-* — the broader Playwright
 * suite (server/api/auth specs) lives in the same dir but is not relevant
 * for the WASM build.
 */
export default defineConfig({
  testDir: "./tests",
  testMatch: /wasm.*\.spec\.ts$/,
  fullyParallel: false,
  workers: 1,
  globalSetup: path.resolve(__dirname, "tests/setup/wasm-global-setup.ts"),
  use: {
    baseURL: "http://127.0.0.1:9091",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
  },
  webServer: {
    command: "python3 tests/spa-server.py 9091 dist",
    url: "http://127.0.0.1:9091/",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
    stdout: "pipe",
    stderr: "pipe",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  timeout: 30_000,
});
