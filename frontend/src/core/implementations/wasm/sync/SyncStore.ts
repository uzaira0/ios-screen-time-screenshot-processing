import { create } from "zustand";
import { syncService } from "./SyncService";
import type { SyncConfig, HealthCheckResult } from "./SyncService";

export interface SyncError {
  message: string;
  timestamp: string;
}

export interface SyncResult {
  screenshots: number;
  annotations: number;
  pulled: number;
}

interface SyncState {
  isOnline: boolean;
  isSyncing: boolean;
  lastSyncAt: string | null;
  pendingUploads: number;
  pendingDownloads: number;
  serverUrl: string;
  username: string;
  sitePassword: string;
  configLoaded: boolean;
  lastSyncResult: SyncResult | null;
  errors: SyncError[];

  // Actions
  setServerUrl: (url: string) => void;
  setUsername: (username: string) => void;
  setSitePassword: (password: string) => void;
  initConfig: () => Promise<void>;
  configureNow: () => Promise<void>;
  checkHealth: () => Promise<HealthCheckResult>;
  disconnect: () => Promise<void>;
  syncNow: () => Promise<void>;
  refreshPendingCounts: () => Promise<void>;
  clearErrors: () => void;
}

export const useSyncStore = create<SyncState>((set, get) => {
  // Listen for online/offline events
  if (typeof window !== "undefined") {
    const updateOnline = () => set({ isOnline: navigator.onLine });
    window.addEventListener("online", updateOnline);
    window.addEventListener("offline", updateOnline);
  }

  let persistTimer: ReturnType<typeof setTimeout> | null = null;

  const buildConfig = (): SyncConfig | null => {
    const { serverUrl, username, sitePassword } = get();
    if (!serverUrl || !username) return null;
    return { serverUrl, username, sitePassword: sitePassword || undefined };
  };

  const flushPersistTimer = () => {
    if (persistTimer) {
      clearTimeout(persistTimer);
      persistTimer = null;
    }
  };

  const debouncedPersist = () => {
    flushPersistTimer();
    persistTimer = setTimeout(() => {
      const config = buildConfig();
      if (config) {
        syncService.configure(config);
        syncService.saveConfig(config);
      }
    }, 500);
  };

  const setField = (patch: Partial<SyncState>) => {
    set(patch);
    debouncedPersist();
  };

  return {
    isOnline: typeof navigator !== "undefined" ? navigator.onLine : true,
    isSyncing: false,
    lastSyncAt: null,
    pendingUploads: 0,
    pendingDownloads: 0,
    serverUrl: "",
    username: "",
    sitePassword: "",
    configLoaded: false,
    lastSyncResult: null,
    errors: [],

    setServerUrl: (url: string) => setField({ serverUrl: url }),
    setUsername: (username: string) => setField({ username }),
    setSitePassword: (password: string) => setField({ sitePassword: password }),

    initConfig: async () => {
      try {
        const config = await syncService.loadConfig();
        if (config) {
          set({
            serverUrl: config.serverUrl,
            username: config.username,
            sitePassword: config.sitePassword || "",
            configLoaded: true,
          });
        } else {
          set({ configLoaded: true });
        }
      } catch (error) {
        console.error("[SyncStore] Failed to load sync config:", error);
        set({ configLoaded: true });
      }
    },

    configureNow: async () => {
      flushPersistTimer();
      const config = buildConfig();
      if (config) {
        syncService.configure(config);
        await syncService.saveConfig(config);
      }
    },

    checkHealth: async (): Promise<HealthCheckResult> => {
      const config = buildConfig();
      if (!config) {
        return { ok: false, error: "Server URL and username are required" };
      }
      syncService.configure(config);
      return syncService.checkServerHealth();
    },

    disconnect: async () => {
      flushPersistTimer();
      await syncService.clearConfig();
      set({
        serverUrl: "",
        username: "",
        sitePassword: "",
        lastSyncAt: null,
        lastSyncResult: null,
        pendingUploads: 0,
        pendingDownloads: 0,
        errors: [],
      });
    },

    syncNow: async () => {
      flushPersistTimer();

      const config = buildConfig();
      if (!config) {
        set({
          errors: [
            ...get().errors,
            {
              message: "Server URL and username are required",
              timestamp: new Date().toISOString(),
            },
          ],
        });
        return;
      }

      syncService.configure(config);
      set({ isSyncing: true, errors: [], lastSyncResult: null });

      try {
        const health = await syncService.checkServerHealth();
        if (!health.ok) {
          set({
            isSyncing: false,
            errors: [
              {
                message: health.error || "Cannot reach server",
                timestamp: new Date().toISOString(),
              },
            ],
          });
          return;
        }

        const result = await syncService.sync((progress) => {
          set({
            pendingUploads:
              progress.phase === "push"
                ? progress.total - progress.current
                : get().pendingUploads,
          });
        });

        const syncErrors: SyncError[] = result.errors.map((msg) => ({
          message: msg,
          timestamp: new Date().toISOString(),
        }));

        set({
          isSyncing: false,
          lastSyncAt: new Date().toISOString(),
          lastSyncResult: {
            screenshots: result.pushed.screenshots,
            annotations: result.pushed.annotations,
            pulled: result.pulled.annotations,
          },
          errors: syncErrors,
        });

        // Refresh counts after sync
        await get().refreshPendingCounts();
      } catch (err) {
        set({
          isSyncing: false,
          errors: [
            {
              message:
                err instanceof Error ? err.message : "Sync failed",
              timestamp: new Date().toISOString(),
            },
          ],
        });
      }
    },

    refreshPendingCounts: async () => {
      try {
        const counts = await syncService.getPendingCounts();
        set({
          pendingUploads: counts.pendingUploads,
          pendingDownloads: counts.pendingDownloads,
        });
      } catch (error) {
        console.warn("[SyncStore] Failed to refresh pending counts:", error);
      }
    },

    clearErrors: () => set({ errors: [] }),
  };
});
