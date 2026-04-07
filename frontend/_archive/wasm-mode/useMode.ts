/**
 * Hook for accessing and managing application mode
 */

import { useState, useEffect } from "react";
import {
  environment,
  setAppMode,
  type AppMode,
  type EnvironmentConfig,
} from "@/config/environment";

export interface UseModeReturn {
  /** Current active mode */
  mode: AppMode;

  /** Full environment configuration */
  config: EnvironmentConfig;

  /** Switch to a different mode */
  switchMode: (newMode: AppMode) => void;

  /** Check if a specific mode is available */
  isAvailable: (mode: AppMode) => boolean;
}

export function useMode(): UseModeReturn {
  const [config] = useState<EnvironmentConfig>(environment);

  useEffect(() => {
    // Listen for mode changes (e.g., from other tabs)
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === "app-mode") {
        window.location.reload();
      }
    };

    window.addEventListener("storage", handleStorageChange);
    return () => window.removeEventListener("storage", handleStorageChange);
  }, []);

  const switchMode = (newMode: AppMode) => {
    setAppMode(newMode);
  };

  const isAvailable = (mode: AppMode): boolean => {
    return mode === "wasm" ? config.wasmAvailable : config.serverAvailable;
  };

  return {
    mode: config.mode,
    config,
    switchMode,
    isAvailable,
  };
}
