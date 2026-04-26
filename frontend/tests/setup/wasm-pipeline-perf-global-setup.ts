import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Generate the perf-test fixtures: clones of the four real screenshots
 * with a unique tEXt chunk per clone so each PNG has a distinct
 * SHA-256 (the WASM upload path dedups by content hash).
 */
export default async function globalSetup(): Promise<void> {
  const script = path.resolve(
    __dirname,
    "..",
    "..",
    "scripts",
    "generate-stress-fixtures.ts",
  );
  const count = process.env.PERF_COUNT ?? "50";
  const outDir = process.env.PERF_OUT_DIR ?? "/tmp/test-screenshots-perf";
  execFileSync("bun", ["run", script, count, outDir], { stdio: "inherit" });
}
