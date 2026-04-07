import { useEffect, useCallback, useState, useRef } from "react";
import { useSearchParams, Link } from "react-router";
import { Layout } from "@/components/layout/Layout";
import { usePreprocessingStore } from "@/hooks/usePreprocessingWithDI";
import type { Stage } from "@/store/preprocessingStore";
import { PreprocessingWizard } from "@/components/preprocessing/PreprocessingWizard";
import { StageSummaryBar } from "@/components/preprocessing/StageSummaryBar";
import { DeviceDetectionTab } from "@/components/preprocessing/DeviceDetectionTab";
import { CroppingTab } from "@/components/preprocessing/CroppingTab";
import { PHIDetectionTab } from "@/components/preprocessing/PHIDetectionTab";
import { PHIRedactionTab } from "@/components/preprocessing/PHIRedactionTab";
import { OCRTab } from "@/components/preprocessing/OCRTab";
import { EventLogPanel } from "@/components/preprocessing/EventLogPanel";
import { PreprocessingQueueView } from "@/components/preprocessing/PreprocessingQueueView";
import { usePreprocessingPipelineService } from "@/core";
import { PREPROCESSING_STAGES } from "@/core/generated/constants";
import { KeyboardShortcutsModal, useKeyboardShortcutsModal } from "@/components/preprocessing/KeyboardShortcutsModal";

// ---------------------------------------------------------------------------
// LLM Controls — endpoint, model dropdown + manual entry, API key, status
// ---------------------------------------------------------------------------

type ConnectionStatus = "idle" | "checking" | "connected" | "error";

interface LLMModel {
  id: string;
  owned_by?: string;
}

function LLMControls({
  endpoint,
  setEndpoint,
  model,
  setModel,
  apiKey,
  setApiKey,
}: {
  endpoint: string;
  setEndpoint: (v: string) => void;
  model: string;
  setModel: (v: string) => void;
  apiKey: string;
  setApiKey: (v: string) => void;
}) {
  const [status, setStatus] = useState<ConnectionStatus>("idle");
  const [models, setModels] = useState<LLMModel[]>([]);
  const [manualEntry, setManualEntry] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Fetch models when endpoint or apiKey changes
  const fetchModels = useCallback(async () => {
    if (!endpoint.trim()) {
      setStatus("idle");
      setModels([]);
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setStatus("checking");

    try {
      const base = endpoint.replace(/\/+$/, "");
      const headers: Record<string, string> = {};
      if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

      const res = await fetch(`${base}/models`, {
        headers,
        signal: controller.signal,
      });

      if (!res.ok) {
        setStatus("error");
        setModels([]);
        return;
      }

      const data = await res.json();
      const fetched: LLMModel[] = (data?.data ?? []).map(
        (m: { id: string; owned_by?: string }) => ({
          id: m.id,
          owned_by: m.owned_by,
        }),
      );

      setModels(fetched);
      setStatus("connected");

      // Auto-select first model if current model is empty or not in list
      if (fetched.length > 0 && !fetched.some((m) => m.id === model)) {
        setModel(fetched[0]!.id);
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      setStatus("error");
      setModels([]);
    }
  }, [endpoint, apiKey, model, setModel]);

  // Debounce endpoint/apiKey changes
  useEffect(() => {
    const timer = setTimeout(fetchModels, 600);
    return () => {
      clearTimeout(timer);
      abortRef.current?.abort();
    };
  }, [fetchModels]);

  const statusDot =
    status === "connected"
      ? "bg-green-500"
      : status === "error"
        ? "bg-red-500"
        : status === "checking"
          ? "bg-yellow-400 animate-pulse"
          : "bg-slate-400";

  return (
    <>
      <div className="flex items-center gap-2">
        <label className="text-sm text-slate-600 dark:text-slate-300">Endpoint:</label>
        <div className="relative">
          <input
            type="text"
            value={endpoint}
            onChange={(e) => setEndpoint(e.target.value)}
            placeholder="http://localhost:1234/v1"
            className="text-sm border border-slate-300 dark:border-slate-600 rounded-md px-2 py-1 w-56 pr-7 dark:bg-slate-700 dark:text-slate-100"
          />
          <span
            className={`absolute right-2 top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full ${statusDot}`}
            title={status === "connected" ? `Connected (${models.length} model${models.length !== 1 ? "s" : ""})` : status === "error" ? "Connection failed" : status === "checking" ? "Checking..." : "Not connected"}
          />
        </div>
      </div>
      <div className="flex items-center gap-2">
        <label className="text-sm text-slate-600 dark:text-slate-300">API Key:</label>
        <input
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="Optional"
          className="text-sm border border-slate-300 dark:border-slate-600 rounded-md px-2 py-1 w-36 dark:bg-slate-700 dark:text-slate-100"
        />
      </div>
      <div className="flex items-center gap-2">
        <label className="text-sm text-slate-600 dark:text-slate-300">Model:</label>
        {!manualEntry && models.length > 0 ? (
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="text-sm border border-slate-300 dark:border-slate-600 rounded-md px-2 py-1 w-48 dark:bg-slate-700 dark:text-slate-100"
          >
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.id}
              </option>
            ))}
          </select>
        ) : (
          <input
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="e.g. openai/gpt-4o"
            className="text-sm border border-slate-300 dark:border-slate-600 rounded-md px-2 py-1 w-48 dark:bg-slate-700 dark:text-slate-100"
          />
        )}
        <button
          type="button"
          onClick={() => setManualEntry(!manualEntry)}
          className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 underline"
          title={manualEntry ? "Switch to dropdown" : "Enter model manually"}
        >
          {manualEntry ? "dropdown" : "manual"}
        </button>
      </div>
    </>
  );
}

export const PreprocessingPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const preprocessingService = usePreprocessingPipelineService();
  const groups = usePreprocessingStore((s) => s.groups);
  const selectedGroupId = usePreprocessingStore((s) => s.selectedGroupId);
  const setSelectedGroupId = usePreprocessingStore((s) => s.setSelectedGroupId);
  const loadGroups = usePreprocessingStore((s) => s.loadGroups);
  const screenshots = usePreprocessingStore((s) => s.screenshots);
  const isLoading = usePreprocessingStore((s) => s.isLoading);
  const activeStage = usePreprocessingStore((s) => s.activeStage);
  const setActiveStage = usePreprocessingStore((s) => s.setActiveStage);
  const eventLog = usePreprocessingStore((s) => s.eventLog);
  const redactionMethod = usePreprocessingStore((s) => s.redactionMethod);
  const setRedactionMethod = usePreprocessingStore((s) => s.setRedactionMethod);
  const llmEnabled = usePreprocessingStore((s) => s.llmEnabled);
  const setLlmEnabled = usePreprocessingStore((s) => s.setLlmEnabled);
  const llmEndpoint = usePreprocessingStore((s) => s.llmEndpoint);
  const setLlmEndpoint = usePreprocessingStore((s) => s.setLlmEndpoint);
  const llmModel = usePreprocessingStore((s) => s.llmModel);
  const setLlmModel = usePreprocessingStore((s) => s.setLlmModel);
  const llmApiKey = usePreprocessingStore((s) => s.llmApiKey);
  const setLlmApiKey = usePreprocessingStore((s) => s.setLlmApiKey);
  const stopPolling = usePreprocessingStore((s) => s.stopPolling);
  const setHighlightedScreenshotId = usePreprocessingStore((s) => s.setHighlightedScreenshotId);
  const setReturnUrl = usePreprocessingStore((s) => s.setReturnUrl);
  const returnUrl = usePreprocessingStore((s) => s.returnUrl);
  const queueMode = usePreprocessingStore((s) => s.queueMode);
  const shortcutsModal = useKeyboardShortcutsModal();
  const [shortcutsHintDismissed, setShortcutsHintDismissed] = useState(() => {
    try { return localStorage.getItem("shortcuts-hint-dismissed") === "1"; } catch { return false; }
  });

  // Load groups on mount, cleanup polling on unmount
  useEffect(() => {
    loadGroups();
    return () => stopPolling();
  }, [loadGroups, stopPolling]);

  const VALID_STAGES: readonly string[] = PREPROCESSING_STAGES;

  // Restore state from URL params on mount
  useEffect(() => {
    const stageParam = searchParams.get("stage");
    const groupParam = searchParams.get("group");
    const screenshotId = searchParams.get("screenshot_id");
    const returnUrlParam = searchParams.get("returnUrl");

    if (returnUrlParam) {
      setReturnUrl(returnUrlParam);
    }
    if (stageParam && VALID_STAGES.includes(stageParam)) {
      setActiveStage(stageParam as Stage);
    }
    if (groupParam) {
      setSelectedGroupId(groupParam);
    }

    if (screenshotId) {
      const id = parseInt(screenshotId, 10);
      if (!isNaN(id)) {
        preprocessingService.getScreenshot(id).then((screenshot) => {
          if (screenshot?.group_id) {
            setSelectedGroupId(screenshot.group_id);
          }
          setHighlightedScreenshotId(id);

          if (stageParam && VALID_STAGES.includes(stageParam)) {
            setActiveStage(stageParam as Stage);
          } else {
            const pp = (screenshot?.processing_metadata as Record<string, unknown>)?.preprocessing as Record<string, unknown> | undefined;
            const stageStatus = pp?.stage_status as Record<string, string> | undefined;
            if (stageStatus) {
              const stageOrder = ["device_detection", "cropping", "phi_detection", "phi_redaction"] as const;
              for (const s of stageOrder) {
                if (stageStatus[s] === "invalidated" || stageStatus[s] === "pending" || stageStatus[s] === "failed") {
                  setActiveStage(s);
                  break;
                }
              }
            }
          }
        }).catch((err) => {
          console.error(`[PreprocessingPage] Failed to load screenshot ${id} from deep-link:`, err);
        });
      }
    }
    // Only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Sync active stage and group to URL
  const syncToUrl = useCallback(() => {
    setSearchParams((prev: URLSearchParams) => {
      const next = new URLSearchParams(prev);
      next.set("stage", activeStage);
      if (selectedGroupId) {
        next.set("group", selectedGroupId);
      }
      return next;
    }, { replace: true });
  }, [activeStage, selectedGroupId, setSearchParams]);

  useEffect(() => {
    syncToUrl();
  }, [syncToUrl]);

  return (
    <Layout>
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          {returnUrl && (
            <Link
              to={returnUrl}
              className="px-3 py-1.5 text-sm text-slate-600 dark:text-slate-300 border border-slate-300 dark:border-slate-600 rounded-md hover:bg-slate-50 dark:hover:bg-slate-700"
            >
              &larr; Back to Annotation
            </Link>
          )}
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            Preprocessing Pipeline
          </h1>
          <button
            onClick={shortcutsModal.toggle}
            className="px-2 py-0.5 text-sm text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 border border-slate-300 dark:border-slate-600 rounded"
            title="Keyboard shortcuts (?)"
          >
            ?
          </button>
        </div>
        <div className="flex items-center gap-3">
          <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Group:</label>
          <select
            value={selectedGroupId}
            onChange={(e) => setSelectedGroupId(e.target.value)}
            className="text-sm border border-slate-300 dark:border-slate-600 rounded-md px-3 py-1.5 bg-white dark:bg-slate-700 dark:text-slate-100"
          >
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name} ({g.screenshot_count})
              </option>
            ))}
          </select>
        </div>
      </div>

      {queueMode ? (
        <PreprocessingQueueView />
      ) : (
        <>
          {/* Pipeline wizard steps */}
          <PreprocessingWizard />

          {/* Stage description */}
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400 ml-1">
            {{
              device_detection: "Identifies device type (iPad vs iPhone) from screenshot dimensions",
              cropping: "Removes iPad sidebar and non-graph regions",
              phi_detection: "Detects personal information (names, identifiers) for redaction",
              phi_redaction: "Blacks out detected personal information regions",
              ocr: "Extracts app title, usage total, and hourly values via OCR",
            }[activeStage]}
          </p>

          {/* Options - show preset/method controls for PHI stages */}
          {(activeStage === "phi_detection" || activeStage === "phi_redaction" || activeStage === "ocr") && (
            <div className="mt-3 flex flex-wrap items-center gap-4 p-3 bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
              {activeStage === "phi_detection" && (
                <>
                  <div className="flex items-center gap-2 border-l border-slate-300 dark:border-slate-600 pl-4">
                    <label className="flex items-center gap-1.5 text-sm font-medium text-slate-700 dark:text-slate-300 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={llmEnabled}
                        onChange={(e) => setLlmEnabled(e.target.checked)}
                        className="rounded border-slate-300 dark:border-slate-600"
                      />
                      LLM-Assisted
                    </label>
                  </div>
                  {llmEnabled && (
                    <LLMControls
                      endpoint={llmEndpoint}
                      setEndpoint={setLlmEndpoint}
                      model={llmModel}
                      setModel={setLlmModel}
                      apiKey={llmApiKey}
                      setApiKey={setLlmApiKey}
                    />
                  )}
                </>
              )}
              {activeStage === "phi_redaction" && (
                <div className="flex items-center gap-2">
                  <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
                    Method:
                  </label>
                  <select
                    value={redactionMethod}
                    onChange={(e) => setRedactionMethod(e.target.value)}
                    className="text-sm border border-slate-300 dark:border-slate-600 rounded-md px-2 py-1 dark:bg-slate-700 dark:text-slate-100"
                  >
                    <option value="redbox">Red Box</option>
                    <option value="blackbox">Black Box</option>
                    <option value="pixelate">Pixelate</option>
                  </select>
                </div>
              )}
              {activeStage === "ocr" && (
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-500 dark:text-slate-400">
                    Grid detection method and optimizer settings can be changed in{" "}
                    <a href="/settings" className="text-primary-600 dark:text-primary-400 hover:underline">Settings</a>
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Filter bar and run button */}
          <div className="mt-3">
            <StageSummaryBar />
          </div>

          {/* Stage content */}
          <div className="mt-4 bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <span className="inline-block w-6 h-6 border-2 border-slate-300 border-t-primary-600 rounded-full animate-spin" />
                <span className="ml-2 text-slate-500">Loading screenshots...</span>
              </div>
            ) : (
              <>
                {/* Keep tabs mounted but hidden to preserve scroll/sort state and avoid remount cost */}
                <div className={activeStage === "device_detection" ? "" : "hidden"}><DeviceDetectionTab /></div>
                <div className={activeStage === "cropping" ? "" : "hidden"}><CroppingTab /></div>
                <div className={activeStage === "phi_detection" ? "" : "hidden"}><PHIDetectionTab /></div>
                <div className={activeStage === "phi_redaction" ? "" : "hidden"}><PHIRedactionTab /></div>
                <div className={activeStage === "ocr" ? "" : "hidden"}><OCRTab /></div>
              </>
            )}
          </div>

          {/* Footer info */}
          <div className="mt-4 text-xs text-slate-400 dark:text-slate-500">
            {screenshots.length} screenshot{screenshots.length !== 1 ? "s" : ""} in
            group
            {selectedGroupId && ` "${selectedGroupId}"`}
          </div>

          {/* Event log side panel */}
          {eventLog && <EventLogPanel />}
        </>
      )}
      {/* Shortcuts hint */}
      {!shortcutsHintDismissed && (
        <button
          onClick={() => { shortcutsModal.toggle(); setShortcutsHintDismissed(true); try { localStorage.setItem("shortcuts-hint-dismissed", "1"); } catch { /* ignore */ } }}
          className="fixed bottom-4 right-4 text-xs text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
        >
          Press ? for shortcuts
        </button>
      )}
      <KeyboardShortcutsModal isOpen={shortcutsModal.isOpen} onClose={shortcutsModal.onClose} />
    </div>
    </Layout>
  );
};
