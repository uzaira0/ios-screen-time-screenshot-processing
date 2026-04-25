import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Annotate-and-export config for the WASM build. Uploads 50 unique
 * screenshots, runs the active stages, then drives 50 annotations
 * through five distinct user paths (verify-as-is, edit hourly + verify,
 * edit title + verify, skip with reason, leave pending) and asserts
 * the exported CSV reflects each variant.
 *
 * Run on demand:
 *   bun run test:e2e:annotate
 */
export default defineConfig({
  testDir: "./tests",
  testMatch: /wasm-annotate\.spec\.ts$/,
  fullyParallel: false,
  workers: 1,
  // 10 minutes — upload+preprocess for 50 screenshots projects to ~10s,
  // annotation walk to ~75s, export + assertions to ~5s. 10 min covers
  // worst-case CI hardware with comfortable margin.
  timeout: 10 * 60_000,
  expect: { timeout: 30_000 },
  globalSetup: path.resolve(__dirname, "tests/setup/wasm-annotate-global-setup.ts"),
  use: {
    baseURL: "http://127.0.0.1:9091",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 15_000,
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
});
