import { execSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Global setup for the WASM Playwright suite (playwright.wasm.config.ts).
 *
 * The smoke spec at tests/wasm-smoke.spec.ts uploads a directory via the
 * webkitdirectory file input, so the fixtures must exist on disk at
 * /tmp/test-screenshots/. scripts/setup-e2e-fixtures.sh copies them there
 * idempotently.
 */
export default async function globalSetup(): Promise<void> {
  const script = path.resolve(__dirname, "..", "..", "scripts", "setup-e2e-fixtures.sh");
  execSync(`bash "${script}"`, { stdio: "inherit" });
}
