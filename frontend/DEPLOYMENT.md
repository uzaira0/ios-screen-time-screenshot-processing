# Deployment

This frontend ships in two distinct shapes:

1. **WASM** — Rust pipeline (leptess + Leptonica + Tesseract) compiled to
   `wasm32-unknown-emscripten` runs the entire OCR/grid/extraction pipeline
   in the browser. No backend, no uploads. Public build target: GitHub Pages.
2. **Server-backed** — same UI but pointed at a running API. PHI detection,
   multi-user consensus, admin features come back online. Self-host via
   Docker.

Both shapes use the same `frontend/server/build.ts` entry. Deployment differs
only in which artifacts you ship and how `config.js` is generated.

## Build artifacts

A complete WASM build emits, in `frontend/dist/`:

```
dist/
├── index.html                  (with optional <base href> when BASE_PATH set)
├── manifest.json               (PWA — start_url/scope/icons all subpath-aware)
├── sw.js                       (service worker)
├── sw-precache.json            (read by sw.js on install)
├── config.js                   ({ basePath, apiBaseUrl? })
├── offline.html                (SW navigation fallback)
├── assets/
│   ├── main-<hash>.js          (~400 KB, app shell)
│   ├── main-<hash>.css
│   ├── nerWorker-<hash>.js     (~880 KB, PHI NER, lazy)
│   └── imageProcessor.worker.emscripten-<hash>.js
├── pipeline-em/
│   ├── IosScreenTimePipeline.js   (Emscripten JS glue, ~70 KB)
│   ├── IosScreenTimePipeline.wasm (Rust + Leptonica + Tesseract, ~3.5 MB)
│   └── eng.traineddata           (~5 MB)
├── icons/
│   ├── icon.svg
│   ├── icon-192.png
│   ├── icon-512.png
│   └── icon-maskable-512.png
└── docs/                        (markdown helpers shipped with the app)
```

## GitHub Pages (canonical public deploy)

`.github/workflows/deploy-gh-pages.yml` is the source of truth. On every push
to `main`:

1. Install Bun + Rust (channel pinned in `rust-toolchain.toml`) +
   Emscripten (4.0.0).
2. Cache the compiled Leptonica + Tesseract static libs by tag.
3. Run `scripts/build-wasm-emscripten.sh` (produces the `.wasm` + JS glue +
   stages `eng.traineddata` into `frontend/public/pipeline-em/`).
4. Run `bun run build` with `BASE_PATH=/<repo-name>` and
   `VITE_COMMIT_SHA=${{ github.sha }}` exported. Both feed the build
   script: `BASE_PATH` rewrites manifest URLs and injects `<base href>`,
   `VITE_COMMIT_SHA` ends up in the version footer.
5. Upload `frontend/dist/` as the Pages artifact, then `actions/deploy-pages`.

The workflow uses a `pages-${{ github.ref }}` concurrency group so an
in-flight deploy is superseded by newer commits on the same branch.

### Pages settings to verify (one-time, manual)

- Repo → **Settings → Pages → Source: GitHub Actions**.
- If running from a fork, also enable Pages on the fork.

### Limitations on Pages

- No COOP/COEP headers — `crossOriginIsolated` is `false`. Tesseract runs
  single-threaded. The footer in WASM mode surfaces this.
- No SharedArrayBuffer threading. Acceptable for the current dataset; the
  Docker variant lifts it.

## Docker (self-host)

`docker/docker-compose.wasm.yml` builds an nginx image that serves the same
`dist/` plus a runtime-injected `config.js` (so the UI can target an external
API endpoint if you set `API_BASE_URL`).

```bash
docker compose -f docker/docker-compose.wasm.yml up --build -d
```

The nginx config (`docker/nginx/nginx.wasm.conf`) sets:

- `Cross-Origin-Opener-Policy: same-origin`
- `Cross-Origin-Embedder-Policy: require-corp`

So `crossOriginIsolated === true` and Tesseract can use multiple threads.
CSP allows `'wasm-unsafe-eval'`.

## Self-hosting any static host (nginx, Cloudflare Pages, etc.)

Any static host works as long as it serves `dist/` with these caveats:

- Serve `*.wasm` with `Content-Type: application/wasm`.
- Allow long-immutable caching of `assets/*` and `pipeline-em/*` (filenames
  are hashed, so cache-bust is automatic).
- Set up SPA routing — every unknown path should fall back to `index.html`.
  The included `frontend/tests/spa-server.py` is a reference Python server
  that does this for local previews.
- If hosting under a subpath, set `BASE_PATH=/your-subpath` at build time
  and ensure the host serves `<repo>/sw.js` from the same scope.

## Local preview

```bash
cd frontend
bun install
bun run wasm:build           # only when WASM artifacts are stale
bun run build
python3 tests/spa-server.py 9091 dist
open http://localhost:9091/
```

To preview a subpath build locally:

```bash
BASE_PATH=/test-subpath bun run build
# spa-server.py needs to be run with the same prefix; see its --help
```

## Updating the WASM pipeline

`scripts/build-wasm-emscripten.sh` is the single source of truth. It:

1. Sources `emsdk` (installed system-wide via Homebrew on macOS or the
   `setup-emsdk` GitHub Action in CI).
2. Builds Leptonica (1.84.1) and Tesseract (5.4.1) as static libraries via
   `emcmake`/`emmake`. These outputs are deterministic given the toolchain
   versions and are cached by the GH Pages workflow.
3. Runs `cargo build --target wasm32-unknown-emscripten --bin pipeline_em`,
   linking against the static libs and exporting the C-ABI symbols listed in
   `crates/processing/src/bin/pipeline_em.rs`.
4. Stages the resulting `.wasm`, `.js` glue, and `eng.traineddata` into
   `frontend/public/pipeline-em/`. `bun run build` copies them into
   `frontend/dist/pipeline-em/`.

## What ships and what doesn't

The PWA manifest is generated at build time (not stored as a static file).
Edit `frontend/server/build.ts` to change manifest fields.

The tesseract.js fallback that previously coexisted with leptess has been
removed. There is one OCR engine (Rust + leptess), shipped via WASM.
