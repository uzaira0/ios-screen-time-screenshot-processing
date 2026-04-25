import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Global setup for the WASM annotate-and-export suite. Reuses the stress
 * fixture generator (clones the 4 real fixtures with a unique tEXt chunk
 * per clone) but writes 50 PNGs to a separate tmp dir so it doesn't
 * collide with the stress harness output.
 */
export default async function globalSetup(): Promise<void> {
  const script = path.resolve(
    __dirname,
    "..",
    "..",
    "scripts",
    "generate-stress-fixtures.ts",
  );
  const count = process.env.ANNOTATE_COUNT ?? "50";
  const outDir = process.env.ANNOTATE_OUT_DIR ?? "/tmp/test-screenshots-50";
  execFileSync("bun", ["run", script, count, outDir], { stdio: "inherit" });
}
