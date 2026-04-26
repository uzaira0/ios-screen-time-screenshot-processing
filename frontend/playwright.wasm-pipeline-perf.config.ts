import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Perf-focused 3-stage WASM pipeline run. Generates a small set of
 * synthetic fixtures (default 50 — set PERF_COUNT for more / fewer)
 * and times each preprocessing stage end-to-end so a regression to
 * single-worker OCR or to broken Tesseract decoding is loud.
 *
 * Run on demand:
 *   PERF_COUNT=50 bun run test:e2e:perf
 */
export default defineConfig({
  testDir: "./tests",
  testMatch: /wasm-pipeline-perf\.spec\.ts$/,
  fullyParallel: false,
  workers: 1,
  // 15 min total — fits a 200-screenshot run on a slow runner with the
  // pool. Default 50 finishes in well under 2 min.
  timeout: 15 * 60_000,
  expect: { timeout: 60_000 },
  globalSetup: path.resolve(__dirname, "tests/setup/wasm-pipeline-perf-global-setup.ts"),
  use: {
    baseURL: "http://127.0.0.1:9094",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 30_000,
    navigationTimeout: 60_000,
  },
  webServer: {
    command: "python3 tests/spa-server.py 9094 dist",
    url: "http://127.0.0.1:9094/",
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
