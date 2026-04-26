import React from "react";
import { Layout } from "@/components/layout/Layout";
import { Link } from "react-router";
import { config } from "@/config";
import { PHI_REDACTION_METHODS, GRID_DETECTION_METHODS } from "@/core/generated/constants";
import {
  Wifi,
  WifiOff,
  RefreshCw,
  Server,
  AlertTriangle,
  ArrowLeft,
  HardDrive,
  Globe,
  Loader2,
  X,
  Monitor,
  Unplug,
  CheckCircle2,
  Sliders,
  RotateCcw,
  Trash2,
  Database,
} from "lucide-react";
import { useSyncStore } from "@/core/implementations/wasm/sync";
import { useThemeStore, THEME_OPTIONS } from "@/store/themeStore";
import { useSettingsStore } from "@/store/settingsStore";
import { Card } from "@/components/ui/Card";
import { Toggle } from "@/components/ui/Toggle";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/** One failing section shouldn't wipe the entire settings page. Wrap each
 *  card so a thrown error renders a small inline message and the rest of
 *  the page still works. */
function Section({ children }: { children: React.ReactNode }) {
  return (
    <ErrorBoundary
      fallback={
        <Card padding="lg">
          <p className="text-sm text-red-600 dark:text-red-400">
            This section failed to load. Other settings still work; reload to retry.
          </p>
        </Card>
      }
    >
      {children}
    </ErrorBoundary>
  );
}

function SyncSection() {
  const {
    isOnline,
    isSyncing,
    lastSyncAt,
    pendingUploads,
    serverUrl,
    username,
    sitePassword,
    lastSyncResult,
    errors,
    setServerUrl,
    setUsername,
    setSitePassword,
    syncNow,
    disconnect,
    initConfig,
    clearErrors,
    refreshPendingCounts,
  } = useSyncStore();

  const [showDisconnectConfirm, setShowDisconnectConfirm] = React.useState(false);

  React.useEffect(() => {
    initConfig().then(() => refreshPendingCounts());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDisconnect = async () => {
    await disconnect();
    setShowDisconnectConfirm(false);
  };

  return (
    <Card padding="lg">
      <div className="flex items-center gap-3 mb-4">
        <Server className="w-6 h-6 text-primary-700 dark:text-primary-400" />
        <div>
          <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
            Sync to Server
          </h2>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Push local data to a server for multi-user consensus
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {isOnline ? (
            <span className="flex items-center gap-1 text-sm text-green-700 dark:text-green-400">
              <Wifi className="w-4 h-4" /> Online
            </span>
          ) : (
            <span className="flex items-center gap-1 text-sm text-slate-500 dark:text-slate-400">
              <WifiOff className="w-4 h-4" /> Offline
            </span>
          )}
        </div>
      </div>

      <div className="space-y-4">
        <div>
          <label
            htmlFor="sync-server-url"
            className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1"
          >
            Server API URL
          </label>
          <input
            id="sync-server-url"
            type="url"
            placeholder="http://localhost:8002/api/v1"
            value={serverUrl}
            onChange={(e) => setServerUrl(e.target.value)}
            className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-md text-sm bg-white dark:bg-slate-700 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>

        <div>
          <label
            htmlFor="sync-username"
            className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1"
          >
            Username
          </label>
          <input
            id="sync-username"
            type="text"
            placeholder="your-username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-md text-sm bg-white dark:bg-slate-700 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>

        <div>
          <label
            htmlFor="sync-site-password"
            className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1"
          >
            Site Password (optional)
          </label>
          <input
            id="sync-site-password"
            type="password"
            placeholder="Leave blank if not required"
            value={sitePassword}
            onChange={(e) => setSitePassword(e.target.value)}
            className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-md text-sm bg-white dark:bg-slate-700 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <button
            onClick={syncNow}
            disabled={isSyncing || !serverUrl || !username}
            className="flex items-center gap-2 px-4 py-2 bg-primary-700 text-white rounded-md text-sm font-medium hover:bg-primary-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus-ring"
          >
            {isSyncing ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            {isSyncing ? "Syncing..." : "Sync Now"}
          </button>

          {serverUrl && (
            <>
              {showDisconnectConfirm ? (
                <div className="flex items-center gap-2">
                  <span className="text-sm text-slate-600 dark:text-slate-400">
                    Clear sync config?
                  </span>
                  <button
                    onClick={handleDisconnect}
                    className="px-3 py-1.5 text-sm font-medium text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors focus-ring"
                  >
                    Yes, disconnect
                  </button>
                  <button
                    onClick={() => setShowDisconnectConfirm(false)}
                    className="px-3 py-1.5 text-sm text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 transition-colors focus-ring"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setShowDisconnectConfirm(true)}
                  disabled={isSyncing}
                  className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-red-700 dark:text-red-400 bg-white dark:bg-slate-800 border border-red-200 dark:border-red-800 rounded-md hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus-ring"
                >
                  <Unplug className="w-4 h-4" />
                  Disconnect
                </button>
              )}
            </>
          )}

          <div className="text-sm text-slate-600 dark:text-slate-400 space-x-4">
            {pendingUploads > 0 && (
              <span>{pendingUploads} screenshot{pendingUploads !== 1 ? "s" : ""} to sync</span>
            )}
            {lastSyncAt && (
              <span>
                Last sync: {new Date(lastSyncAt).toLocaleTimeString()}
              </span>
            )}
          </div>
        </div>

        {/* Sync results */}
        {lastSyncResult && (
          <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-md p-3">
            <span className="flex items-center gap-1 text-sm font-medium text-green-800 dark:text-green-300 mb-1">
              <CheckCircle2 className="w-4 h-4" /> Sync Complete
            </span>
            <p className="text-sm text-green-700 dark:text-green-300">
              Pushed {lastSyncResult.screenshots} screenshot{lastSyncResult.screenshots !== 1 ? "s" : ""}
              {", "}
              {lastSyncResult.annotations} annotation{lastSyncResult.annotations !== 1 ? "s" : ""}
              {lastSyncResult.pulled > 0 && (
                <>{". "}Pulled {lastSyncResult.pulled} remote annotation{lastSyncResult.pulled !== 1 ? "s" : ""}</>
              )}
            </p>
          </div>
        )}

        {errors.length > 0 && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md p-3">
            <div className="flex items-center justify-between mb-1">
              <span className="flex items-center gap-1 text-sm font-medium text-red-800 dark:text-red-300">
                <AlertTriangle className="w-4 h-4" /> Sync Errors
              </span>
              <button
                onClick={clearErrors}
                className="text-red-600 hover:text-red-800 focus-ring"
                aria-label="Clear errors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <ul className="text-sm text-red-700 dark:text-red-300 space-y-1">
              {errors.map((err, i) => (
                <li key={i}>{err.message}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}

const PHI_NER_DETECTOR_OPTIONS = [
  { value: "presidio" as const, label: "Presidio (Microsoft)", desc: "Fast — 6ms per image, good for common PHI patterns" },
  { value: "gliner" as const, label: "GLiNER (zero-shot)", desc: "More accurate — F1=0.98, catches edge cases, 112ms per image" },
];

const PHI_REDACTION_LABELS: Record<string, string> = { redbox: "Red Box", blackbox: "Black Box", pixelate: "Pixelate" };
const PHI_REDACTION_OPTIONS = PHI_REDACTION_METHODS.map((m) => ({ value: m, label: PHI_REDACTION_LABELS[m] ?? m }));

const GRID_METHOD_LABELS: Record<string, string> = { line_based: "Line-Based", ocr_anchored: "OCR-Anchored" };
const GRID_METHOD_OPTIONS = GRID_DETECTION_METHODS.map((m) => ({ value: m, label: GRID_METHOD_LABELS[m] ?? m }));

function ProcessingSection() {
  const { skipDailyTotals, gridDetectionMethod, maxShift, autoProcessOnUpload, autoAdvanceAfterVerify, set: setSetting, reset } = useSettingsStore();

  return (
    <Card padding="lg">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <Sliders className="w-6 h-6 text-primary-700 dark:text-primary-400" />
          <div>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
              Processing
            </h2>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              Configure how screenshots are processed
            </p>
          </div>
        </div>
        <button
          onClick={reset}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-700 rounded-md hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors focus-ring"
        >
          <RotateCcw className="w-3 h-3" />
          Reset Defaults
        </button>
      </div>

      <div className="space-y-5">
        {/* Skip Daily Totals */}
        <div className="flex items-center justify-between py-3 border-b border-slate-200 dark:border-slate-700">
          <div>
            <div className="font-medium text-slate-900 dark:text-slate-100">
              Skip Daily Total Images
            </div>
            <div className="text-sm text-slate-600 dark:text-slate-400">
              Automatically skip daily total screenshots during preprocessing
            </div>
          </div>
          <Toggle
            checked={skipDailyTotals}
            onChange={(checked) => setSetting("skipDailyTotals", checked)}
            label="Skip daily totals"
          />
        </div>

        {/* Grid Detection Method */}
        <div className="py-3 border-b border-slate-200 dark:border-slate-700">
          <div className="font-medium text-slate-900 dark:text-slate-100 mb-1">
            Grid Detection Method
          </div>
          <div className="text-sm text-slate-600 dark:text-slate-400 mb-3">
            Method used to detect the graph grid boundaries
          </div>
          <div className="flex gap-2">
            {GRID_METHOD_OPTIONS.map(({ value, label }) => (
              <button
                key={value}
                onClick={() => setSetting("gridDetectionMethod", value)}
                className={`px-4 py-2 rounded-lg border text-sm font-medium transition-colors focus-ring ${
                  gridDetectionMethod === value
                    ? "bg-primary-50 dark:bg-primary-900/30 border-primary-300 dark:border-primary-700 text-primary-700 dark:text-primary-400"
                    : "bg-white dark:bg-slate-700 border-slate-200 dark:border-slate-600 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-600"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Boundary Optimizer */}
        <div className="py-3 border-b border-slate-200 dark:border-slate-700">
          <div className="font-medium text-slate-900 dark:text-slate-100 mb-1">
            Boundary Optimizer (Max Shift)
          </div>
          <div className="text-sm text-slate-600 dark:text-slate-400 mb-3">
            Maximum pixels to shift grid boundaries for alignment (0 = off)
          </div>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min={0}
              max={10}
              step={1}
              value={maxShift}
              onChange={(e) => setSetting("maxShift", Number(e.target.value))}
              className="w-48 accent-primary-600"
            />
            <span className="text-sm font-mono font-medium text-slate-700 dark:text-slate-300 w-6 text-center">
              {maxShift}
            </span>
          </div>
        </div>

        {/* Auto-Process on Upload */}
        <div className="flex items-center justify-between py-3 border-b border-slate-200 dark:border-slate-700">
          <div>
            <div className="font-medium text-slate-900 dark:text-slate-100">
              Auto-Process on Upload
            </div>
            <div className="text-sm text-slate-600 dark:text-slate-400">
              Automatically run OCR processing when screenshots are uploaded
            </div>
          </div>
          <Toggle
            checked={autoProcessOnUpload}
            onChange={(checked) => setSetting("autoProcessOnUpload", checked)}
            label="Auto-process on upload"
          />
        </div>

        {/* Auto-Advance After Verify */}
        <div className="flex items-center justify-between py-3">
          <div>
            <div className="font-medium text-slate-900 dark:text-slate-100">
              Auto-Advance After Verify
            </div>
            <div className="text-sm text-slate-600 dark:text-slate-400">
              Automatically move to the next screenshot after clicking Verify
            </div>
          </div>
          <Toggle
            checked={autoAdvanceAfterVerify}
            onChange={(checked) => setSetting("autoAdvanceAfterVerify", checked)}
            label="Auto-advance after verify"
          />
        </div>
      </div>
    </Card>
  );
}

function PHISection() {
  const {
    phiNerDetector, phiRedactionMethod,
    set: setSetting,
  } = useSettingsStore();

  return (
    <Card padding="lg">
      <div className="flex items-center gap-3 mb-4">
        <AlertTriangle className="w-6 h-6 text-amber-600 dark:text-amber-400" />
        <div>
          <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
            PHI Detection
          </h2>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Configure how personal health information is detected and redacted
          </p>
        </div>
      </div>

      <div className="space-y-5">
        {/* NER Detector */}
        <div className="py-3 border-b border-slate-200 dark:border-slate-700">
          <div className="font-medium text-slate-900 dark:text-slate-100 mb-1">
            Detection Model
          </div>
          <div className="text-sm text-slate-600 dark:text-slate-400 mb-3">
            Which model identifies names, emails, and other PHI in the screenshot text
          </div>
          <div className="flex gap-2">
            {PHI_NER_DETECTOR_OPTIONS.map(({ value, label, desc }) => (
              <button
                key={value}
                onClick={() => setSetting("phiNerDetector", value)}
                className={`px-4 py-2 rounded-lg border text-sm font-medium transition-colors focus-ring ${
                  phiNerDetector === value
                    ? "bg-primary-50 dark:bg-primary-900/30 border-primary-300 dark:border-primary-700 text-primary-700 dark:text-primary-400"
                    : "bg-white dark:bg-slate-700 border-slate-200 dark:border-slate-600 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-600"
                }`}
              >
                <div>{label}</div>
                <div className="text-xs opacity-70 mt-0.5">{desc}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Redaction Method */}
        <div className="py-3">
          <div className="font-medium text-slate-900 dark:text-slate-100 mb-1">
            Redaction Style
          </div>
          <div className="text-sm text-slate-600 dark:text-slate-400 mb-3">
            How detected PHI regions are obscured in the image
          </div>
          <div className="flex gap-2">
            {PHI_REDACTION_OPTIONS.map(({ value, label }) => (
              <button
                key={value}
                onClick={() => setSetting("phiRedactionMethod", value)}
                className={`px-4 py-2 rounded-lg border text-sm font-medium transition-colors focus-ring ${
                  phiRedactionMethod === value
                    ? "bg-primary-50 dark:bg-primary-900/30 border-primary-300 dark:border-primary-700 text-primary-700 dark:text-primary-400"
                    : "bg-white dark:bg-slate-700 border-slate-200 dark:border-slate-600 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-600"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const v = bytes / Math.pow(1024, i);
  return `${v >= 10 || i === 0 ? v.toFixed(0) : v.toFixed(1)} ${units[i]}`;
}

function StorageSection() {
  const [usage, setUsage] = React.useState<number | null>(null);
  const [quota, setQuota] = React.useState<number | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [confirming, setConfirming] = React.useState(false);

  const refresh = React.useCallback(async () => {
    try {
      const est = await navigator.storage.estimate();
      setUsage(est.usage ?? null);
      setQuota(est.quota ?? null);
    } catch {
      setUsage(null);
      setQuota(null);
    }
  }, []);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  async function deleteAll() {
    setBusy(true);
    try {
      // 1) IndexedDB databases (skip system DBs that throw on delete).
      try {
        const dbs = await indexedDB.databases?.();
        if (dbs) {
          await Promise.all(
            dbs
              .filter((db) => db.name)
              .map(
                (db) =>
                  new Promise<void>((resolve) => {
                    const req = indexedDB.deleteDatabase(db.name as string);
                    req.onsuccess = () => resolve();
                    req.onerror = () => resolve();
                    req.onblocked = () => resolve();
                  }),
              ),
          );
        }
      } catch {
        // ignore — falls through to SW + reload, which usually clears state
      }

      // 2) OPFS root: recursively wipe everything the app stored.
      try {
        const root = await navigator.storage.getDirectory();
        // @ts-expect-error — TS lib lacks the iterator typing for now.
        for await (const [name] of root.entries()) {
          await root.removeEntry(name, { recursive: true }).catch(() => {});
        }
      } catch {
        // OPFS may not be available — ok
      }

      // 3) Caches (service worker precache + runtime).
      try {
        const keys = await caches.keys();
        await Promise.all(keys.map((k) => caches.delete(k)));
      } catch {
        // ignore
      }

      // 4) Local + session storage.
      try {
        localStorage.clear();
        sessionStorage.clear();
      } catch {
        // ignore
      }

      // 5) Unregister the service worker so the next visit starts clean.
      try {
        const regs = await navigator.serviceWorker?.getRegistrations?.();
        if (regs) await Promise.all(regs.map((r) => r.unregister()));
      } catch {
        // ignore
      }

      window.location.reload();
    } finally {
      setBusy(false);
    }
  }

  const pct = usage !== null && quota ? Math.min(100, (usage / quota) * 100) : null;

  return (
    <Card padding="lg">
      <div className="flex items-center gap-3 mb-4">
        <Database className="w-6 h-6 text-primary-700 dark:text-primary-400" />
        <div>
          <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
            Local Storage
          </h2>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            All screenshots, annotations, and OCR caches stay on this device.
          </p>
        </div>
      </div>

      <div className="space-y-3 text-sm">
        <div className="flex justify-between text-slate-700 dark:text-slate-300">
          <span>Used</span>
          <span className="font-mono">
            {usage === null ? "—" : formatBytes(usage)}
            {quota ? ` / ${formatBytes(quota)}` : ""}
            {pct !== null ? ` (${pct.toFixed(1)}%)` : ""}
          </span>
        </div>
        {pct !== null && (
          <div className="h-2 w-full bg-slate-200 dark:bg-slate-700 rounded">
            <div
              className="h-2 bg-primary-500 rounded"
              style={{ width: `${pct}%` }}
              aria-label={`Storage used: ${pct.toFixed(1)}%`}
            />
          </div>
        )}
      </div>

      <div className="mt-6 flex flex-col sm:flex-row gap-3">
        <button
          onClick={refresh}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-md border border-slate-300 dark:border-slate-600 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 focus-ring"
        >
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
        {!confirming ? (
          <button
            onClick={() => setConfirming(true)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-md border border-red-300 dark:border-red-700 text-sm text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 focus-ring"
          >
            <Trash2 className="w-4 h-4" /> Delete all local data
          </button>
        ) : (
          <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-md p-3">
            <span className="text-sm text-red-700 dark:text-red-300">
              This wipes IndexedDB, OPFS, caches, localStorage, and unregisters the service worker. There is no undo.
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setConfirming(false)}
                disabled={busy}
                className="px-3 py-1.5 rounded-md border border-slate-300 dark:border-slate-600 text-sm text-slate-700 dark:text-slate-300 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={deleteAll}
                disabled={busy}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-red-600 text-white text-sm hover:bg-red-700 disabled:opacity-50"
              >
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                Yes, wipe everything
              </button>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

export const SettingsPage: React.FC = () => {
  const isLocalMode = config.isLocalMode;
  const modeLabel = config.isTauri ? "Desktop" : "Local (WASM)";
  const { mode: themeMode, setMode: setThemeMode } = useThemeStore();

  return (
    <Layout>
      <div className="max-w-4xl mx-auto space-y-8">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-100">Settings</h1>
          <p className="text-slate-600 dark:text-slate-400 mt-1">
            Configure your screenshot processing preferences
          </p>
        </div>

        {/* Theme */}
        <Card padding="lg">
          <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100 mb-4">
            Theme
          </h2>
          <div className="flex gap-3">
            {THEME_OPTIONS.map(({ value, label, icon: Icon }) => (
              <button
                key={value}
                onClick={() => setThemeMode(value)}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-lg border text-sm font-medium transition-colors focus-ring ${
                  themeMode === value
                    ? "bg-primary-50 dark:bg-primary-900/30 border-primary-300 dark:border-primary-700 text-primary-700 dark:text-primary-400"
                    : "bg-white dark:bg-slate-700 border-slate-200 dark:border-slate-600 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-600"
                }`}
              >
                <Icon className="w-4 h-4" />
                {label}
              </button>
            ))}
          </div>
        </Card>

        {/* Current Mode Info */}
        <Card padding="lg">
          <div className="flex items-center gap-3 mb-4">
            {isLocalMode ? (
              <HardDrive className="w-8 h-8 text-primary-700 dark:text-primary-400" />
            ) : (
              <Monitor className="w-8 h-8 text-primary-700 dark:text-primary-400" />
            )}
            <div>
              <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
                {isLocalMode ? `${modeLabel} Mode` : "Server Mode"}
              </h2>
              <p className="text-sm text-slate-600 dark:text-slate-400">
                {isLocalMode
                  ? "Processing locally in the browser"
                  : "Using backend server for processing"}
              </p>
            </div>
          </div>

          <div className="grid md:grid-cols-3 gap-4 text-sm">
            <div className="bg-slate-50 dark:bg-slate-700/50 p-3 rounded">
              <div className="font-medium text-slate-700 dark:text-slate-300">Data Storage</div>
              <div className="text-slate-600 dark:text-slate-400 mt-1">
                {isLocalMode ? "IndexedDB + OPFS" : "Server Database"}
              </div>
            </div>
            <div className="bg-slate-50 dark:bg-slate-700/50 p-3 rounded">
              <div className="font-medium text-slate-700 dark:text-slate-300">Processing</div>
              <div className="text-slate-600 dark:text-slate-400 mt-1">
                {isLocalMode
                  ? "Rust + leptess (WASM)"
                  : "Backend (Rust + Python OCR)"}
              </div>
            </div>
            <div className="bg-slate-50 dark:bg-slate-700/50 p-3 rounded">
              <div className="font-medium text-slate-700 dark:text-slate-300">Network Required</div>
              <div className="text-slate-600 dark:text-slate-400 mt-1">
                {isLocalMode ? (
                  <span className="flex items-center gap-1">
                    <Globe className="w-3.5 h-3.5" /> No (Offline Capable)
                  </span>
                ) : (
                  "Yes (Server Connection)"
                )}
              </div>
            </div>
          </div>
        </Card>

        {/* Processing settings */}
        <Section><ProcessingSection /></Section>

        {/* PHI Detection settings (server mode only) */}
        {!isLocalMode && <Section><PHISection /></Section>}

        {/* Sync section (WASM mode only) */}
        {isLocalMode && <Section><SyncSection /></Section>}

        {/* Local storage management (WASM mode only) */}
        {isLocalMode && <Section><StorageSection /></Section>}


        {/* About Section */}
        <Card padding="lg">
          <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100 mb-4">About</h2>
          <div className="space-y-2 text-sm text-slate-600 dark:text-slate-400">
            <p>
              <strong>Version:</strong> {config.appVersion}{" "}
              <span className="font-mono text-xs">({config.commitSha})</span>
            </p>
            <p>
              <strong>Build:</strong>{" "}
              {isLocalMode ? `${modeLabel} (Local-First)` : "Server (Collaborative)"}
            </p>
            <p>
              <strong>Browser:</strong> {navigator.userAgent.split(" ").pop()}
            </p>
            {config.hasApi && (
              <p>
                <strong>API Endpoint:</strong> {config.apiBaseUrl}
              </p>
            )}
          </div>
        </Card>

        <div className="flex justify-center">
          <Link
            to="/"
            className="flex items-center gap-2 px-6 py-3 text-primary-700 dark:text-primary-400 bg-primary-50 dark:bg-primary-900/20 rounded-lg hover:bg-primary-100 dark:hover:bg-primary-900/30 transition-colors font-medium focus-ring"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Home
          </Link>
        </div>
      </div>
    </Layout>
  );
};
