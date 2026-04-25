import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Stress config for the 1000-screenshot WASM E2E test.
 *
 * Separate from playwright.wasm.config.ts because:
 *   - The full pipeline (upload → device detect → crop → OCR) on 1000 images
 *     takes 15+ minutes on a typical laptop. Folding it into the smoke suite
 *     would gum up CI.
 *   - The fixture generation runs once (globalSetup) and writes 1000 PNGs to
 *     /tmp/test-screenshots-1000/.
 *
 * Run on demand:
 *   bun run test:e2e:stress
 *
 * Or directly:
 *   bunx playwright test --config playwright.wasm-stress.config.ts
 */
export default defineConfig({
  testDir: "./tests",
  testMatch: /wasm-stress\.spec\.ts$/,
  fullyParallel: false,
  workers: 1,
  // 45 minutes total. Dry-run at N=20 takes 18s; projecting to 1000 puts the
  // happy path near 15–18 min, with the rest of the budget covering OCR
  // worst-case (3s/screenshot on a slow runner) and the post-preprocessing
  // walk through annotation + export.
  timeout: 45 * 60_000,
  expect: { timeout: 60_000 },
  globalSetup: path.resolve(__dirname, "tests/setup/wasm-stress-global-setup.ts"),
  use: {
    baseURL: "http://127.0.0.1:9091",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 30_000,
    navigationTimeout: 60_000,
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
});
