import { create } from "zustand";

/**
 * Authentication store using the global auth pattern.
 *
 * Auth model:
 * - SITE_PASSWORD: Optional shared password for all users (if configured)
 * - Username: Honor-system identification for audit logging
 *
 * Storage:
 * - sitePassword: Stored in localStorage, sent via X-Site-Password header
 * - username: Stored in localStorage, sent via X-Username header
 * - userId/role: From backend user record (auto-created on first login)
 */
interface AuthState {
  userId: number | null;
  username: string | null;
  role: string | null;
  sitePassword: string | null;
  isAuthenticated: boolean;
  login: (
    userId: number,
    username: string,
    sitePassword?: string,
    role?: string
  ) => void;
  logout: () => void;
  setUserId: (userId: number) => void;
  setRole: (role: string) => void;
  setSitePassword: (password: string) => void;
}

function safeGetItem(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}

export const useAuthStore = create<AuthState>((set) => ({
  userId: (() => { const v = safeGetItem("userId"); return v ? parseInt(v, 10) : null; })(),
  username: safeGetItem("username"),
  role: safeGetItem("userRole"),
  sitePassword: safeGetItem("sitePassword"),
  isAuthenticated: !!safeGetItem("username"),

  login: (
    userId: number,
    username: string,
    sitePassword?: string,
    role?: string
  ) => {
    try {
      localStorage.setItem("userId", String(userId));
      localStorage.setItem("username", username);
      if (sitePassword) localStorage.setItem("sitePassword", sitePassword);
      if (role) localStorage.setItem("userRole", role);
    } catch { /* localStorage unavailable — session won't persist across refresh */ }
    set({
      userId,
      username,
      sitePassword: sitePassword || null,
      role: role || null,
      isAuthenticated: true,
    });
  },

  logout: () => {
    try {
      localStorage.removeItem("userId");
      localStorage.removeItem("username");
      localStorage.removeItem("userRole");
      localStorage.removeItem("sitePassword");
    } catch { /* localStorage unavailable */ }
    set({
      userId: null,
      username: null,
      role: null,
      sitePassword: null,
      isAuthenticated: false,
    });
  },

  setUserId: (userId: number) => {
    localStorage.setItem("userId", String(userId));
    set({ userId });
  },

  setRole: (role: string) => {
    localStorage.setItem("userRole", role);
    set({ role });
  },

  setSitePassword: (password: string) => {
    localStorage.setItem("sitePassword", password);
    set({ sitePassword: password });
  },
}));
