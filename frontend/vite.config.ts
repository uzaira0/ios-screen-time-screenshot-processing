import { defineConfig, type PluginOption } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "path";
import { readFileSync } from "fs";
import { execSync } from "child_process";

// Tauri expects a fixed port for dev, and sets TAURI_DEV_HOST for mobile
const host = process.env.TAURI_DEV_HOST;

// Read version from package.json for injection into app
const pkg = JSON.parse(readFileSync(resolve(__dirname, "package.json"), "utf-8"));

// Commit SHA: prefer the env var that GitHub Actions/CI sets (VITE_COMMIT_SHA
// or GITHUB_SHA), else shell out to git for local dev. "dev" if neither.
function resolveCommitSha(): string {
  const envSha = process.env.VITE_COMMIT_SHA || process.env.GITHUB_SHA;
  if (envSha) return envSha.slice(0, 7);
  try {
    return execSync("git rev-parse --short HEAD", { stdio: ["ignore", "pipe", "ignore"] })
      .toString()
      .trim();
  } catch {
    return "dev";
  }
}
const commitSha = resolveCommitSha();

export default defineConfig(async () => {
  const plugins: PluginOption[] = [tailwindcss(), react()];

  // Bundle analysis: ANALYZE=1 bun run build
  if (process.env.ANALYZE) {
    const { visualizer } = await import("rollup-plugin-visualizer");
    plugins.push(
      visualizer({
        open: true,
        gzipSize: true,
        brotliSize: true,
        filename: "dist/stats.html",
      })
    );
  }

  return {
    plugins,
    define: {
      __APP_VERSION__: JSON.stringify(pkg.version),
      __COMMIT_SHA__: JSON.stringify(commitSha),
    },
    resolve: {
      alias: {
        "@": resolve(__dirname, "./src"),
      },
    },
    base: "./",
    server: {
      host: host || false,
      port: 5173,
      strictPort: true,
    },
    worker: {
      format: "es" as const,
    },
    build: {
      outDir: "dist",
      target: "esnext" as const,
    },
  };
});
