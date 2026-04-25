import { config } from "@/config";
import { useCapabilityCheck } from "@/hooks/useCapabilityCheck";

/**
 * Privacy + diagnostics footer. Shown on every page in WASM/local mode.
 *
 * - Affirms "fully local" so first-time visitors know nothing leaves their device.
 * - Surfaces version + commit SHA so bug reports include the exact build.
 * - Surfaces a single-thread / capability hint when the browser is missing
 *   something the pipeline relies on.
 */
export const Footer = () => {
  const caps = useCapabilityCheck();
  if (!config.isLocalMode) return null;

  const missing: string[] = [];
  if (!caps.loading) {
    if (!caps.opfs) missing.push("OPFS");
    if (!caps.indexedDb) missing.push("IndexedDB");
    if (!caps.offscreenCanvas) missing.push("OffscreenCanvas");
    if (!caps.webAssembly) missing.push("WebAssembly");
  }

  return (
    <footer className="shrink-0 border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 px-4 py-2 text-xs text-slate-500 dark:text-slate-400 flex flex-wrap items-center justify-between gap-2">
      <div className="flex items-center gap-2">
        <span aria-hidden="true">🔒</span>
        <span>
          Fully local — no uploads, no telemetry. All processing runs in your browser.
        </span>
      </div>
      <div className="flex items-center gap-3">
        {!caps.loading && !caps.crossOriginIsolated && (
          <span
            className="text-amber-600 dark:text-amber-400"
            title="Single-threaded WASM. Self-host the Docker image for multi-threaded OCR."
          >
            single-threaded
          </span>
        )}
        {missing.length > 0 && (
          <span
            className="text-red-600 dark:text-red-400"
            title="This browser is missing features required by the WASM pipeline."
          >
            missing: {missing.join(", ")}
          </span>
        )}
        <span
          className="font-mono"
          title="App version and short commit SHA. Include these in bug reports."
        >
          v{config.appVersion} · {config.commitSha}
        </span>
      </div>
    </footer>
  );
};
