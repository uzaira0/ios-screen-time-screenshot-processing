import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Global setup for the WASM stress suite (playwright.wasm-stress.config.ts).
 *
 * Generates 1000 unique PNGs into /tmp/test-screenshots-1000/ by cloning the
 * 4 real fixtures and injecting a unique tEXt chunk per clone. Idempotent:
 * the generator clears the output dir on each run.
 *
 * Override count via STRESS_COUNT env var, e.g. STRESS_COUNT=200 for a
 * shorter dry-run.
 */
export default async function globalSetup(): Promise<void> {
  const script = path.resolve(
    __dirname,
    "..",
    "..",
    "scripts",
    "generate-stress-fixtures.ts",
  );
  const count = process.env.STRESS_COUNT ?? "1000";
  const outDir = process.env.STRESS_OUT_DIR ?? "/tmp/test-screenshots-1000";
  execFileSync("bun", ["run", script, count, outDir], { stdio: "inherit" });
}
