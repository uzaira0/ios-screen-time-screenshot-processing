import { useEffect, useState } from "react";

export interface BrowserCapabilities {
  /** SharedArrayBuffer (cross-origin isolation). False on GitHub Pages. */
  crossOriginIsolated: boolean;
  /** OPFS — required for blob storage. */
  opfs: boolean;
  /** IndexedDB — required for the local DB. */
  indexedDb: boolean;
  /** OffscreenCanvas — required for worker-side image decode. */
  offscreenCanvas: boolean;
  /** WebAssembly — required for the Rust pipeline. */
  webAssembly: boolean;
  /** Service Worker — required for offline mode. */
  serviceWorker: boolean;
  /** True when nothing critical is missing. */
  ready: boolean;
  /** True when probing is still in progress. */
  loading: boolean;
}

/**
 * Probe the browser for the features the WASM build relies on. Used to drive
 * the capability banner — surfaces clearly which feature is missing instead
 * of letting some unrelated downstream call blow up.
 */
export function useCapabilityCheck(): BrowserCapabilities {
  const [caps, setCaps] = useState<BrowserCapabilities>({
    crossOriginIsolated: false,
    opfs: false,
    indexedDb: false,
    offscreenCanvas: false,
    webAssembly: false,
    serviceWorker: false,
    ready: false,
    loading: true,
  });

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const crossOriginIsolated =
        typeof window !== "undefined" && window.crossOriginIsolated === true;

      let opfs = false;
      try {
        if (typeof navigator !== "undefined" && "storage" in navigator) {
          // OPFS root accessor is async and may throw on Safari < 17.
          const dir = await (
            navigator.storage as { getDirectory?: () => Promise<unknown> }
          ).getDirectory?.();
          opfs = !!dir;
        }
      } catch {
        opfs = false;
      }

      const indexedDb =
        typeof indexedDB !== "undefined" && typeof indexedDB.open === "function";

      const offscreenCanvas = typeof OffscreenCanvas !== "undefined";
      const webAssembly = typeof WebAssembly !== "undefined";
      const serviceWorker =
        typeof navigator !== "undefined" && "serviceWorker" in navigator;

      // Critical = anything that breaks the core WASM flow. SW + COI are nice
      // to have. The app degrades on those rather than failing.
      const ready = opfs && indexedDb && offscreenCanvas && webAssembly;

      if (!cancelled) {
        setCaps({
          crossOriginIsolated,
          opfs,
          indexedDb,
          offscreenCanvas,
          webAssembly,
          serviceWorker,
          ready,
          loading: false,
        });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return caps;
}
