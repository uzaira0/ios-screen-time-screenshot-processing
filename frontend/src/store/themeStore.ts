import { create } from "zustand";
import { Sun, Moon, Monitor } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type ThemeMode = "light" | "dark" | "system";

interface ThemeState {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
}

/** Shared theme metadata — used by Header (cycle) and SettingsPage (selector) */
export const THEME_OPTIONS: { value: ThemeMode; label: string; icon: LucideIcon }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];

/** Cycle order for the Header toggle button */
export const THEME_CYCLE: Record<ThemeMode, ThemeMode> = {
  light: "dark",
  dark: "system",
  system: "light",
};

function applyTheme(mode: ThemeMode) {
  const isDark =
    mode === "dark" ||
    (mode === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", isDark);
}

const raw = typeof localStorage !== "undefined" ? localStorage.getItem("theme") : null;
const initial: ThemeMode = raw && (["light", "dark", "system"] as string[]).includes(raw)
  ? (raw as ThemeMode)
  : "system";

// Apply synchronously before React mounts to prevent theme flash
applyTheme(initial);

// Listen for OS preference changes when in "system" mode
if (typeof window !== "undefined") {
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    const current = useThemeStore.getState().mode;
    if (current === "system") applyTheme("system");
  });
}

export const useThemeStore = create<ThemeState>((set) => ({
  mode: initial,
  setMode: (mode) => {
    localStorage.setItem("theme", mode);
    applyTheme(mode);
    set({ mode });
  },
}));
