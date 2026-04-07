import { createContext, useContext, useMemo, useEffect, useRef, useState, createElement, type ReactNode } from "react";
import { usePreprocessingPipelineService } from "@/core";
import { createPreprocessingStore, type PreprocessingState } from "@/store/preprocessingStore";
import type { IPreprocessingService } from "@/core/interfaces/IPreprocessingService";
import { config } from "@/config";

type PreprocessingStore = ReturnType<typeof createPreprocessingStore>;

// Store instances cached by service identity, with reference counting
interface StoreEntry {
  store: PreprocessingStore;
  refCount: number;
}
const storeInstances = new Map<string, StoreEntry>();

const CLEANUP_DELAY_MS = 5000;

const PreprocessingStoreContext = createContext<PreprocessingStore | null>(null);

/**
 * Provider that creates a preprocessing store backed by the DI-resolved service.
 * Wrap PreprocessingPage (or any subtree that needs preprocessing state) with this.
 */
export function PreprocessingProvider({ children }: { children: ReactNode }) {
  const service = usePreprocessingPipelineService();
  const cacheKeyRef = useRef<string | null>(null);

  const store = useMemo(() => {
    // Use a stable key — in practice there's one preprocessing service per mode
    const cacheKey = "preprocessing";
    cacheKeyRef.current = cacheKey;

    const existing = storeInstances.get(cacheKey);
    if (existing) {
      existing.refCount++;
      return existing.store;
    }

    const newStore = createPreprocessingStore(service);
    storeInstances.set(cacheKey, { store: newStore, refCount: 1 });
    return newStore;
  }, [service]);

  // Cleanup on unmount: stop polling immediately, then clean up store after delay
  useEffect(() => {
    const currentKey = cacheKeyRef.current;
    const currentStore = store;
    return () => {
      // Stop polling immediately to prevent stale interval timers
      currentStore.getState().stopPolling();

      if (!currentKey) return;
      setTimeout(() => {
        const entry = storeInstances.get(currentKey);
        if (entry) {
          entry.refCount--;
          if (entry.refCount <= 0) {
            storeInstances.delete(currentKey);
            if (config.isDev) {
              console.log(`[PreprocessingProvider] Cleaned up store for key: ${currentKey}`);
            }
          }
        }
      }, CLEANUP_DELAY_MS);
    };
  }, [store]);

  return createElement(
    serviceContext.Provider,
    { value: service },
    createElement(PreprocessingStoreContext.Provider, { value: store }, children),
  );
}

/**
 * Drop-in replacement for the old `usePreprocessingStore` import.
 * Supports the same selector pattern: `usePreprocessingStore((s) => s.field)`
 */
export function usePreprocessingStore(): PreprocessingStore;
export function usePreprocessingStore<T>(selector: (state: PreprocessingState) => T): T;
export function usePreprocessingStore<T>(selector?: (state: PreprocessingState) => T) {
  const store = useContext(PreprocessingStoreContext);
  if (!store) {
    throw new Error("usePreprocessingStore must be used within a <PreprocessingProvider>");
  }
  if (selector) {
    return store(selector);
  }
  return store;
}

// ---------------------------------------------------------------------------
// Image URL hooks — async blob URL loading with cleanup for WASM mode
// ---------------------------------------------------------------------------

const serviceContext = createContext<IPreprocessingService | null>(null);

/**
 * Load an image URL for a screenshot via the preprocessing service.
 * In server mode this returns a static API URL; in WASM mode it creates
 * an object URL from the blob store and revokes it on cleanup.
 */
export function useScreenshotImageUrl(
  screenshotId: number | undefined,
  method: "getImageUrl" | "getStageImageUrl" | "getOriginalImageUrl" = "getImageUrl",
  stage?: string,
  refreshKey?: number,
): string | null {
  const service = useContext(serviceContext);
  const [url, setUrl] = useState<string | null>(null);
  const prevIdRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!service || screenshotId == null) {
      setUrl(null);
      return;
    }

    // Only clear URL when screenshot ID changes
    if (prevIdRef.current !== screenshotId) {
      setUrl(null);
      prevIdRef.current = screenshotId;
    }

    let revoked = false;
    let objectUrl: string | null = null;

    (async () => {
      try {
        let result: string;
        if (method === "getStageImageUrl" && stage) {
          result = await service.getStageImageUrl(screenshotId, stage);
        } else if (method === "getOriginalImageUrl") {
          result = await service.getOriginalImageUrl(screenshotId);
        } else {
          result = await service.getImageUrl(screenshotId);
        }
        if (!revoked) {
          // Append cache-buster so browser doesn't serve stale image after redaction
          objectUrl = result.startsWith("blob:") ? result :
            result + (result.includes("?") ? "&" : "?") + `_t=${refreshKey ?? 0}`;
          setUrl(objectUrl);
        } else if (result.startsWith("blob:") && method !== "getImageUrl") {
          URL.revokeObjectURL(result);
        }
      } catch (err) {
        console.error(`[useScreenshotImageUrl] Failed to load image for screenshot ${screenshotId}:`, err);
        if (!revoked) setUrl(null);
      }
    })();

    return () => {
      revoked = true;
      // Revoke blob URLs from getOriginalImageUrl (always uncached) and
      // getStageImageUrl (uncached per-call URLs). Only getImageUrl uses
      // the shared LRU cache and should NOT be revoked here.
      if (objectUrl?.startsWith("blob:") && method !== "getImageUrl") {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [service, screenshotId, method, stage, refreshKey]);

  return url;
}
