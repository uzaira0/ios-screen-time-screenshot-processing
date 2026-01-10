import { defineConfig, type PluginOption } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "path";
import { readFileSync } from "fs";

// Tauri expects a fixed port for dev, and sets TAURI_DEV_HOST for mobile
const host = process.env.TAURI_DEV_HOST;

// Read version from package.json for injection into app
const pkg = JSON.parse(readFileSync(resolve(__dirname, "package.json"), "utf-8"));

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
