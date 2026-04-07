// App version injected by Vite define at build time (from package.json)
declare const __APP_VERSION__: string;

// Runtime configuration injected by docker-entrypoint.sh via config.js
declare global {
  interface Window {
    __CONFIG__?: { basePath?: string; apiBaseUrl?: string };
    __TAURI_INTERNALS__?: unknown;
  }
}

// Check if we're in development mode.
// Bun's bundler replaces import.meta.env.MODE at build time.
// Falls back to checking process.env for SSR/test environments.
const isDev =
  import.meta.env?.MODE === "development" ||
  (typeof process !== "undefined" &&
    process.env?.NODE_ENV === "development");

export const config = {
  get basePath(): string {
    return window.__CONFIG__?.basePath || "";
  },
  /** Whether an API backend is available (server mode vs WASM mode) */
  get hasApi(): boolean {
    return !!window.__CONFIG__?.apiBaseUrl;
  },
  get apiBaseUrl(): string {
    // In server mode, apiBaseUrl is explicitly set in window.__CONFIG__
    // In WASM mode, falls back to basePath-derived URL (used by server-mode components only)
    return window.__CONFIG__?.apiBaseUrl ?? `${this.basePath}/api/v1`;
  },
  get wsUrl(): string {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    return `${protocol}//${host}${this.basePath}/api/ws`;
  },
  get isDev(): boolean {
    return isDev;
  },
  get isProd(): boolean {
    return !isDev;
  },
  /** Whether running inside a Tauri desktop shell */
  get isTauri(): boolean {
    return !!window.__TAURI_INTERNALS__;
  },
  /** Whether running in a local-only mode (no backend server) */
  get isLocalMode(): boolean {
    return this.isTauri || !this.hasApi;
  },
  get appVersion(): string {
    return typeof __APP_VERSION__ !== "undefined" ? __APP_VERSION__ : "dev";
  },
};
