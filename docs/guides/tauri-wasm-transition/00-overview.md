# Chapter 00: Overview

## Who This Guide Is For

This guide targets senior developers who have built and shipped React/TypeScript web applications and now need to extend one into a desktop application using Tauri v2. It assumes familiarity with:

- TypeScript's strict mode and advanced type features
- React state management (Zustand, Context)
- Service-oriented frontend architecture (dependency injection, interface segregation)
- WASM basics (what it is, when it helps, build tooling)
- CI/CD pipelines (GitHub Actions)

It does **not** assume prior experience with Tauri, Rust, Electron, or desktop application distribution. If you have shipped Electron apps before, you will find Tauri's model simpler in some ways (no Node.js runtime, no Chromium bundle) and more constrained in others (Rust FFI boundary, platform-specific webview quirks).

This guide is written against a real codebase -- an iOS Screen Time screenshot processing platform -- and every code example is drawn from production source files. Where a pattern is project-specific, it is called out explicitly.

---

## Architecture Vision

The system supports three entry points that converge on a single React frontend with pluggable service implementations:

```
                    Starting Points
                    ===============

  Web Application        PyQt6 Desktop GUI        Static SPA (WASM)
  (FastAPI + React)      (Python + Qt)             (No backend)
        |                      |                        |
        |   Port algorithms    |                        |
        +------+   to TS/WASM  |    Already client-     |
               |       +-------+    side processing     |
               |       |                   |            |
               v       v                   v            v
        +----------------------------------------------+
        |         Shared React Frontend                |
        |                                              |
        |   +----------------+  +------------------+   |
        |   | DI Container   |  | Zustand Stores   |   |
        |   | (mode-aware    |  | (UI state,       |   |
        |   |  service       |  |  screenshot      |   |
        |   |  resolution)   |  |  cache)          |   |
        |   +-------+--------+  +------------------+   |
        |           |                                   |
        |   +-------v----------------------------------+|
        |   |  Service Interfaces (IScreenshotService, ||
        |   |  IAnnotationService, IProcessingService, ||
        |   |  IStorageService, IPreprocessingService)  |
        |   +-------+----------------+---------+-------+|
        |           |                |         |        |
        |   +-------v------+ +------v---+ +---v------+ |
        |   | Server Impls | |WASM Impls| |Tauri Impl| |
        |   | (axios/fetch)| |(IndexedDB| |(reuses   | |
        |   |              | | Workers  | | WASM now,| |
        |   |              | | Tess.js) | | SQLite   | |
        |   |              | |          | | later)   | |
        |   +--------------+ +----------+ +----------+ |
        +----------------------------------------------+
                          |
               +----------+-----------+
               |                      |
        +------v------+      +-------v--------+
        | Browser      |      | Tauri Shell    |
        | (nginx/SPA)  |      | (system webview|
        |              |      |  + Rust backend|
        |              |      |  + auto-update)|
        +--------------+      +----------------+
```

**Key invariant**: No React component ever checks which mode it is running in. Components call service interfaces; the DI container resolves the correct implementation at bootstrap time.

---

## When to Use (and When Not To)

Use this decision tree before committing to a Tauri migration:

```
Does your app need to work offline (no network at all)?
  |
  +-- No --> Does it need desktop distribution (IT-managed installs)?
  |            |
  |            +-- No --> Does it need native OS APIs (filesystem, notifications, tray)?
  |            |            |
  |            |            +-- No --> STOP. A PWA with a service worker is simpler.
  |            |            |
  |            |            +-- Yes --> Tauri is a good fit. Proceed.
  |            |
  |            +-- Yes --> Tauri is a good fit. Proceed.
  |
  +-- Yes --> Can it run entirely in the browser (IndexedDB + WASM)?
               |
               +-- Yes --> Build WASM mode first. Add Tauri shell later
               |           for distribution convenience. This is the
               |           lowest-risk path (chapters 01-05 first).
               |
               +-- No (needs filesystem, large storage, native perf) -->
                   Tauri is required. Plan for Rust-side storage
                   (SQLite via tauri-plugin-sql) from the start.
```

**PWA is almost always the right first step.** If your offline needs are met by IndexedDB + Cache API + a service worker, Tauri adds complexity without proportional benefit. Tauri becomes compelling when you need:

- Signed installers for IT deployment (MSI, DMG, DEB)
- Auto-updates without app store review
- Native filesystem access beyond the browser sandbox
- System tray integration or global shortcuts
- Guaranteed local-only data processing (regulatory/compliance)

---

## Decision Log

Every major architectural decision and why it was made:

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| **React + TypeScript** | Ecosystem maturity (component libraries, testing tools, hiring pool). DI pattern compatibility -- interfaces and generics work naturally. The existing codebase already uses React. | Svelte (smaller bundle but weaker DI story), Solid (faster but smaller ecosystem) |
| **DI container over scattered mode checks** | Without DI, every component that touches data needs `if (isOffline) { ... } else { ... }`. With 6 service interfaces and ~50 consuming components, that is 300+ conditional branches vs 6 factory registrations. The container also enables testing -- inject mocks by token. | Feature flags only (still requires conditionals), runtime proxy pattern (harder to debug) |
| **Strict types + OpenAPI generation** | Pydantic schemas are the single source of truth. `bun run generate:api-types` produces `api-schema.ts`. Frontend never defines interfaces that mirror backend models -- it imports generated types. Catches schema drift at build time, not in production. | Manual type definitions (drift), GraphQL codegen (different backend architecture) |
| **Progressive offline: switchable then coexisting** | Phase 1 runs in exactly one mode per session (server OR wasm OR tauri). Phase 2 adds coexistence -- local-first with background sync to server. Switchable mode is simpler to build and test; coexisting mode is added only after switchable mode is proven stable. | Full offline-first from day one (high risk, hard to debug sync conflicts) |
| **IndexedDB + OPFS over SQLite-in-WASM** | Browser-native, no additional WASM binary to load. IndexedDB handles structured data (screenshots, annotations); OPFS handles large blobs (image files). Dexie.js provides a clean query API over IndexedDB. SQLite-in-WASM (via wa-sqlite or sql.js) adds 500KB+ to the bundle and requires `SharedArrayBuffer` + COOP/COEP headers for OPFS-backed persistence. | SQLite-in-WASM (heavier, COOP/COEP complexity), localStorage (5MB limit) |
| **Tauri v2 over Electron** | 10x smaller binaries (system webview vs bundled Chromium). Rust security model (no Node.js in renderer, capability-based permissions). First-class auto-update plugin. Active v2 development with stable API. | Electron (proven but bloated), Neutralinojs (too immature), Wails (Go, different ecosystem) |
| **GitHub Actions for CI/CD** | First-class Tauri support via `tauri-apps/tauri-action`. Handles cross-compilation (macOS, Windows, Linux) with code signing. Battle-tested workflows in the Tauri ecosystem. Free for public repos, reasonable pricing for private. | GitLab CI (no first-class Tauri action), CircleCI (possible but requires custom config) |
| **Testing tiers: Essential, Recommended, Advanced** | Testing everything before shipping leads to analysis paralysis. Essential tier (type-check + unit + smoke E2E) catches 80% of regressions. Ship with Essential; add Recommended (integration, visual regression) in subsequent sprints. | Full test suite before launch (delays shipping), no tests (unacceptable risk) |
| **`exactOptionalPropertyTypes`** | Catches the difference between `{ key: undefined }` and `{ }` (missing key). Without it, `options?.timeout` silently accepts `undefined` as an explicit value, which can overwrite defaults in spread patterns. Common bug source in config objects. | Off by default in tsconfig; leaving it off means subtle bugs in option merging |
| **`noUncheckedIndexedAccess`** | Array access (`arr[i]`) and record access (`obj[key]`) return `T \| undefined` instead of `T`. Forces explicit null checks. Catches the #1 runtime error class in TypeScript: assuming an index access succeeded. | Off by default; leaving it off means every `arr[0].foo` is a potential `TypeError` |
| **`noImplicitOverride`** | Requires the `override` keyword when a subclass method overrides a parent method. Catches the bug where a parent class adds a new method that silently shadows a child method, or a child method name is refactored but the parent is not. | Off by default; without it, override relationships are invisible in code review |
| **basedpyright over mypy** | Stricter type checking out of the box (no gradual typing escape hatches). Faster execution (written in JS, not Python). Better Pydantic v2 support (understands `model_validator`, `field_validator` decorators). Language server integration for real-time feedback. | mypy (slower, weaker Pydantic support, more permissive defaults) |
| **context7 MCP for research** | LLM training data is stale -- Tauri v2 APIs changed significantly between beta and stable. context7 fetches current documentation from npm/PyPI/GitHub at query time. Eliminates hallucinated APIs. | Manual doc reading (slower), pinned doc snapshots (still stale) |

---

## Convergence Paths

Your starting point determines which chapters matter most:

### From a Web Application (FastAPI + React)

You already have a working server-mode frontend. Your primary task is adding client-side implementations of each service interface.

**Primary chapters**: 01 (DI architecture), 02 (WASM processing), 03 (storage), 04 (Tauri shell), 05 (auto-updates)

**Key risk**: Assuming server-side processing can be replicated 1:1 in the browser. Some operations (multi-engine OCR fallback, GPU-accelerated inference) cannot run client-side. Design graceful degradation early.

### From a PyQt6 Desktop GUI

You have Python processing algorithms that need porting to TypeScript or Rust-to-WASM. The DI architecture is less relevant (you are building from scratch), but the algorithm porting is critical.

**Primary chapters**: 02 (WASM processing -- algorithm porting strategy), 01 (DI architecture for mode switching), 04 (Tauri shell)

**Key risk**: Pixel-level differences between Python (PIL/OpenCV) and browser (Canvas API) image processing. Port algorithms with numerical regression tests comparing Python output to TypeScript output on identical input images.

### From a Static SPA (No Backend)

You already run entirely client-side. Your task is wrapping the existing app in a Tauri shell and adding desktop-native features.

**Primary chapters**: 01 (DI architecture -- you may need to formalize ad-hoc service boundaries), 04 (Tauri shell integration), 05 (auto-updates)

**Key risk**: Assuming browser APIs work identically in Tauri's webview. System webviews lag behind Chrome/Firefox on API support. Test `OffscreenCanvas`, `Web Workers`, `IndexedDB`, and `OPFS` in each target platform's webview.

---

## Phase Map

The migration proceeds in two phases. Phase 1 is a prerequisite for Phase 2.

### Phase 1: Switchable Modes (Chapters 01-05)

The application runs in exactly one mode per session, determined at bootstrap:

```
detectMode()
    |
    +-- "server"  --> API-backed services (axios calls to FastAPI)
    |
    +-- "wasm"    --> Client-side services (IndexedDB + Tesseract.js)
    |
    +-- "tauri"   --> Desktop services (reuses WASM initially, later SQLite + Rust)
```

Mode detection uses a three-tier check:

```typescript
// frontend/src/core/config/config.ts
export function detectMode(): AppMode {
  if (config.isTauri) return "tauri";
  return config.hasApi ? "server" : "wasm";
}
```

Where the runtime config checks:

```typescript
// frontend/src/config.ts
export const config = {
  get isTauri(): boolean {
    return !!window.__TAURI_INTERNALS__;
  },
  get hasApi(): boolean {
    return !!window.__CONFIG__?.apiBaseUrl;
  },
  get isLocalMode(): boolean {
    return this.isTauri || !this.hasApi;
  },
};
```

**Phase 1 deliverables**:
- DI container with server, WASM, and Tauri bootstrap paths
- All 6 service interfaces implemented for each mode
- Tauri shell with auto-update support
- GitHub Actions CI/CD for cross-platform builds
- Essential-tier test coverage

### Phase 2: Coexisting Modes + Sync (Chapter 08)

The application runs local-first with optional background sync to a server:

```
Local-first operation
    |
    +-- All reads from IndexedDB (instant, offline-capable)
    |
    +-- All writes to IndexedDB first (optimistic)
    |
    +-- Background sync to server when online
    |       |
    |       +-- Conflict resolution (last-write-wins or manual merge)
    |       |
    |       +-- Sync status indicators in UI
    |
    +-- Falls back to local-only when offline (no degradation)
```

**Phase 2 deliverables**:
- `SyncService` with queue-based background sync
- Conflict resolution strategy
- Offline indicator and sync status UI
- Data migration from server-only to local-first

Phase 2 is documented in chapter 08 but should not be started until Phase 1 is stable and deployed.

---

## Chapter Index

| Chapter | Title | Focus |
|---------|-------|-------|
| 00 | Overview (this chapter) | Architecture vision, decision rationale, phase map |
| 01 | Dual-Mode Architecture | DI container, service interfaces, bootstrap, feature flags |
| 02 | WASM Processing | Web Workers, Tesseract.js, OffscreenCanvas, algorithm porting |
| 03 | Storage Layer | IndexedDB (Dexie), OPFS blob storage, migrations |
| 04 | Tauri Shell Integration | Tauri v2 setup, Rust commands, capability permissions |
| 05 | Auto-Updates | tauri-plugin-updater, GitHub Releases, code signing |
| 06 | CI/CD Pipeline | GitHub Actions, cross-compilation, artifact publishing |
| 07 | Testing Strategy | Essential/Recommended/Advanced tiers, platform-specific tests |
| 08 | Sync and Coexistence | Local-first with background sync, conflict resolution |
