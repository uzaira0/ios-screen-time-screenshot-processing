/**
 * Bun production build script
 *
 * Builds the app bundle, CSS, service worker, and generates index.html + manifest.
 */

import { rm, mkdir, copyFile } from "fs/promises";
import { join, resolve } from "path";

const ROOT_DIR = resolve(import.meta.dir, "..");
const SRC_DIR = join(ROOT_DIR, "src");
const DIST_DIR = join(ROOT_DIR, "dist");
const PUBLIC_DIR = join(ROOT_DIR, "public");

// Path alias plugin for @/ -> src/
const pathAliasPlugin: import("bun").BunPlugin = {
  name: "path-alias",
  setup(build) {
    build.onResolve({ filter: /^@\// }, async (args) => {
      const relativePath = args.path.replace(/^@\//, "");
      const basePath = join(SRC_DIR, relativePath);

      // Try different extensions
      const extensions = [".tsx", ".ts", ".js", ".jsx", ""];
      for (const ext of extensions) {
        const fullPath = basePath + ext;
        const file = Bun.file(fullPath);
        if (await file.exists()) {
          return { path: fullPath };
        }
      }

      // Try as directory with index file
      const indexExtensions = [".tsx", ".ts", ".js", ".jsx"];
      for (const ext of indexExtensions) {
        const indexPath = join(basePath, "index" + ext);
        const file = Bun.file(indexPath);
        if (await file.exists()) {
          return { path: indexPath };
        }
      }

      // Fallback to original behavior
      return { path: basePath };
    });
  },
};

async function build() {
  console.log("\x1b[34m[build]\x1b[0m Starting production build...\n");
  const startTime = performance.now();

  // Clean dist directory
  await rm(DIST_DIR, { recursive: true, force: true });
  await mkdir(DIST_DIR, { recursive: true });
  await mkdir(join(DIST_DIR, "assets"), { recursive: true });

  // Bundle JavaScript
  console.log("\x1b[33m[build]\x1b[0m Bundling JavaScript...");

  const result = await Bun.build({
    entrypoints: [join(SRC_DIR, "main.tsx")],
    outdir: join(DIST_DIR, "assets"),
    target: "browser",
    format: "esm",
    splitting: true,
    sourcemap: "external",
    minify: true,
    naming: "[name]-[hash].[ext]",
    plugins: [pathAliasPlugin],
    external: [
      "@tauri-apps/api",
      "@tauri-apps/api/core",
      "@tauri-apps/plugin-process",
      "@tauri-apps/plugin-updater",
    ],
    define: {
      "process.env.NODE_ENV": JSON.stringify("production"),
    },
  });

  if (!result.success) {
    console.error("\x1b[31m[build]\x1b[0m Build failed:");
    for (const log of result.logs) {
      console.error(log);
    }
    process.exit(1);
  }

  // Get the main bundle filename
  let mainBundle = "";
  for (const output of result.outputs) {
    // Use path.basename for cross-platform compatibility (Windows uses \ not /)
    const name = output.path.split(/[/\\]/).pop() || "";
    if (name.startsWith("main-") && name.endsWith(".js") && !name.endsWith(".map")) {
      mainBundle = name;
    }
    console.log("  \x1b[32m✓\x1b[0m " + name + " (" + (output.size / 1024).toFixed(1) + " KB)");
  }

  // Build service worker
  console.log("\n\x1b[33m[build]\x1b[0m Building service worker...");
  const swResult = await Bun.build({
    entrypoints: [join(SRC_DIR, "service-worker.ts")],
    outdir: DIST_DIR,
    target: "browser",
    format: "esm",
    minify: true,
    naming: "sw.js",
  });

  if (!swResult.success) {
    console.error("\x1b[31m[build]\x1b[0m Service worker build failed:");
    for (const log of swResult.logs) {
      console.error(log);
    }
  } else {
    console.log("  \x1b[32m✓\x1b[0m sw.js");
  }

  // Build Tailwind CSS (v4)
  console.log("\n\x1b[33m[build]\x1b[0m Building CSS...");
  const cssProc = Bun.spawn(
    [
      "bunx",
      "@tailwindcss/cli",
      "-i",
      join(SRC_DIR, "index.css"),
      "-o",
      join(DIST_DIR, "assets", "index.css"),
      "--minify",
    ],
    {
      cwd: ROOT_DIR,
      stdout: "inherit",
      stderr: "inherit",
    }
  );
  await cssProc.exited;

  // Copy public files
  console.log("\n\x1b[33m[build]\x1b[0m Copying public files...");
  try {
    const publicGlob = new Bun.Glob("**/*");
    for await (const file of publicGlob.scan(PUBLIC_DIR)) {
      const src = join(PUBLIC_DIR, file);
      const dest = join(DIST_DIR, file);
      await mkdir(join(DIST_DIR, file, ".."), { recursive: true });
      await copyFile(src, dest);
      console.log("  \x1b[32m✓\x1b[0m " + file);
    }
  } catch {
    console.log("  (no public files)");
  }

  // Subpath awareness: BASE_PATH (e.g. "/ios-screen-time-screenshot-processing")
  // is set by the GitHub Pages workflow before invoking the build. Empty by
  // default for root-served deploys (Docker, local). The leading slash is
  // mandatory; trailing slash is stripped.
  const rawBase = (process.env.BASE_PATH || "").trim();
  const BASE_PATH = rawBase === "" || rawBase === "/" ? "" : rawBase.replace(/\/+$/, "");
  if (BASE_PATH) {
    console.log(`\x1b[33m[build]\x1b[0m BASE_PATH = ${BASE_PATH}`);
  }
  const baseHrefTag = BASE_PATH ? `\n    <base href="${BASE_PATH}/" />` : "";
  const prefix = (p: string) => `${BASE_PATH}${p.startsWith("/") ? p : "/" + p}`;

  // Generate index.html
  // Use relative paths (./assets/) so it works with any base path prefix
  console.log("\n\x1b[33m[build]\x1b[0m Generating index.html...");
  const html = `<!DOCTYPE html>
<html lang="en">
  <head>${baseHrefTag}
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>iOS Screen Time Screenshot Processing</title>
    <link rel="stylesheet" href="./assets/index.css" />
    <link rel="manifest" href="./manifest.json" />
    <meta name="theme-color" content="#0F766E" />
  </head>
  <body>
    <div id="root"></div>
    <script src="./config.js"></script>
    <script type="module" src="./assets/${mainBundle}"></script>
    <script>
      if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('./sw.js').catch(() => {});
      }
    </script>
  </body>
</html>`;

  await Bun.write(join(DIST_DIR, "index.html"), html);

  // Emit a default config.js so static hosts (GitHub Pages, plain nginx) don't
  // 404 the <script src="./config.js"> in index.html. The Docker entrypoint
  // overwrites this file with the runtime-injected API_BASE_URL when the
  // backend variant of the image is built.
  console.log("\n\x1b[33m[build]\x1b[0m Generating config.js (no-API default)...");
  await Bun.write(
    join(DIST_DIR, "config.js"),
    `// Generated by frontend/server/build.ts. Static-host default: WASM mode\n` +
      `// (no API). Docker entrypoint overwrites this when API_BASE_URL is set.\n` +
      `window.__CONFIG__ = ${JSON.stringify({ basePath: BASE_PATH })};\n`,
  );

  // Generate PWA manifest. Single source of truth for both deployments — the
  // older frontend/public/manifest.webmanifest is no longer copied into dist.
  // start_url / scope / shortcut/share/file URLs are all BASE_PATH-aware.
  console.log("\n\x1b[33m[build]\x1b[0m Generating manifest.json...");
  const manifest = {
    name: "iOS Screen Time Screenshot Processing",
    short_name: "iOS Screen Time",
    description:
      "Extract and analyze battery and screen time usage data from iOS screenshots — fully local OCR, no uploads.",
    start_url: prefix("/"),
    scope: prefix("/"),
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#0F766E",
    orientation: "any",
    icons: [
      {
        src: prefix("/icons/icon.svg"),
        sizes: "any",
        type: "image/svg+xml",
        purpose: "any maskable",
      },
    ],
    screenshots: [
      {
        src: prefix("/screenshots/desktop-1280x720.png"),
        sizes: "1280x720",
        type: "image/png",
        form_factor: "wide",
        label: "iOS Screen Time — Desktop View",
      },
      {
        src: prefix("/screenshots/mobile-750x1334.png"),
        sizes: "750x1334",
        type: "image/png",
        form_factor: "narrow",
        label: "iOS Screen Time — Mobile View",
      },
    ],
    categories: ["productivity", "utilities", "tools"],
    shortcuts: [
      {
        name: "Upload Screenshots",
        short_name: "Upload",
        description: "Upload new screenshots for processing",
        url: prefix("/?action=upload"),
        icons: [
          {
            src: prefix("/icons/icon.svg"),
            sizes: "any",
            type: "image/svg+xml",
          },
        ],
      },
      {
        name: "View Gallery",
        short_name: "Gallery",
        description: "View all processed screenshots",
        url: prefix("/?action=gallery"),
        icons: [
          {
            src: prefix("/icons/icon.svg"),
            sizes: "any",
            type: "image/svg+xml",
          },
        ],
      },
    ],
    share_target: {
      action: prefix("/share"),
      method: "POST",
      enctype: "multipart/form-data",
      params: {
        files: [
          {
            name: "screenshots",
            accept: ["image/png", "image/jpeg", "image/jpg"],
          },
        ],
      },
    },
    file_handlers: [
      {
        action: prefix("/open"),
        accept: {
          "image/png": [".png"],
          "image/jpeg": [".jpg", ".jpeg"],
        },
      },
    ],
    launch_handler: { client_mode: "focus-existing" },
    edge_side_panel: { preferred_width: 480 },
    prefer_related_applications: false,
  };
  await Bun.write(join(DIST_DIR, "manifest.json"), JSON.stringify(manifest, null, 2));

  const elapsed = ((performance.now() - startTime) / 1000).toFixed(2);
  console.log("\n\x1b[32m[build]\x1b[0m Build completed in " + elapsed + "s");
  console.log("\x1b[32m[build]\x1b[0m Output: " + DIST_DIR);
  console.log("\n\x1b[32m[build]\x1b[0m Service worker included at sw.js");
}

build();
