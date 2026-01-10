/**
 * Application Configuration
 *
 * Supports three-mode operation:
 * - Server mode: when apiBaseUrl is present in window.__CONFIG__
 * - WASM mode: when apiBaseUrl is absent (local-first, offline in browser)
 * - Tauri mode: when running inside a Tauri desktop shell
 */

import { config } from "@/config";

export type AppMode = "server" | "wasm" | "tauri";

export interface AppConfig {
  mode: AppMode;
  apiBaseUrl?: string;
  features: {
    offlineMode: boolean;
    autoProcessing: boolean;
    exportToFile: boolean;
  };
}

/**
 * Detect application mode based on configuration.
 * Tauri → tauri mode, apiBaseUrl present → server mode, otherwise → wasm mode.
 */
export function detectMode(): AppMode {
  if (config.isTauri) return "tauri";
  return config.hasApi ? "server" : "wasm";
}

/**
 * Creates application configuration based on detected mode.
 */
export function createConfig(): AppConfig {
  const mode = detectMode();

  if (mode === "tauri" || mode === "wasm") {
    return {
      mode,
      features: {
        offlineMode: true,
        autoProcessing: true,
        exportToFile: true,
      },
    };
  }

  return {
    mode: "server",
    apiBaseUrl: config.apiBaseUrl,
    features: {
      offlineMode: false,
      autoProcessing: true,
      exportToFile: false,
    },
  };
}
