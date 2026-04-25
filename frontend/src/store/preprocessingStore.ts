import { create } from "zustand";
import type {
  Screenshot,
  Group,
  PreprocessingStageSummary,
  PreprocessingSummary,
  PreprocessingEvent,
  PreprocessingEventLog,
} from "@/types";
import type { IPreprocessingService, RunStageOptions } from "@/core/interfaces/IPreprocessingService";
import { api } from "@/services/apiClient";
import { config } from "@/config";
import { useSettingsStore } from "@/store/settingsStore";
import toast from "react-hot-toast";
import { PREPROCESSING_STAGES, StageStatus as SS, type PreprocessingStages, type StageStatuses } from "@/core/generated/constants";
import { parseOcrTotalMinutes, hasTotalsMismatchByThreshold } from "@/utils/formatters";

// Local types not in backend schema (UI-only concerns)
type Stage = PreprocessingStages;
type StageStatus = StageStatuses;
type FilterMode = "all" | "needs_review" | "invalidated" | "completed" | "skipped" | "pending";
type PageMode = "pipeline" | "upload";

interface UploadFileItem {
  file: File;
  participant_id: string;
  filename: string;
  original_filepath: string;
  screenshot_date: string;
  thumbnail?: string;
}

// Re-use generated types
type StageSummary = PreprocessingStageSummary;
type PreprocessingSummaryData = PreprocessingSummary;
type PreprocessingEventData = PreprocessingEvent;
type EventLogData = PreprocessingEventLog;

const STAGES: Stage[] = [...PREPROCESSING_STAGES];

interface PreprocessingState {
  // Data
  screenshots: Screenshot[];
  selectedGroupId: string;
  groups: Group[];
  summary: PreprocessingSummaryData | null;

  // Navigation
  activeStage: Stage;
  pageMode: PageMode;

  // Execution
  isRunningStage: boolean;
  stageProgress: { completed: number; total: number } | null;

  // Filtering
  filter: FilterMode;

  // Options
  phiPreset: string;
  redactionMethod: string;
  llmEnabled: boolean;
  llmEndpoint: string;
  llmModel: string;
  llmApiKey: string;


  // Event log detail
  selectedScreenshotId: number | null;
  eventLog: EventLogData | null;

  // Loading state
  isLoading: boolean;

  // Polling
  _pollInterval: ReturnType<typeof setInterval> | null;
  _pollCount: number;
  _queuedCount: number;
  _completedBaseline: number;
  _abortController: AbortController | null;
  _pollStage: Stage;
  _pendingTaskIds: string[];

  // Upload state (Phase 2)
  uploadFiles: UploadFileItem[];
  uploadImageType: "battery" | "screen_time";
  uploadGroupId: string;
  isUploading: boolean;
  uploadProgress: { completed: number; total: number } | null;
  uploadErrors: string[];

  // Per-stage table sort
  tableSortColumn: Record<string, string>;
  tableSortDirection: Record<string, "asc" | "desc">;

  // Deep-link state
  highlightedScreenshotId: number | null;
  returnUrl: string | null;

  // Image version counter — incremented on screenshot reload to bust stale blob URLs
  imageVersion: number;

  // Queue review mode
  queueMode: boolean;
  queueIndex: number;
  queueScreenshotIds: number[];

  // Actions
  setActiveStage: (stage: Stage) => void;
  setPageMode: (mode: PageMode) => void;
  setFilter: (filter: FilterMode) => void;
  setTableSort: (stage: Stage, column: string, direction: "asc" | "desc") => void;
  setSelectedGroupId: (groupId: string) => void;
  setPhiPreset: (preset: string) => void;
  setRedactionMethod: (method: string) => void;
  setLlmEnabled: (enabled: boolean) => void;
  setLlmEndpoint: (endpoint: string) => void;
  setLlmModel: (model: string) => void;
  setLlmApiKey: (key: string) => void;


  loadGroups: () => Promise<void>;
  loadScreenshots: () => Promise<void>;
  loadSummary: () => Promise<void>;
  runStage: (stage: Stage, screenshotIds?: number[]) => Promise<void>;
  stopStage: () => void;
  resetStage: (stage: Stage) => Promise<void>;
  skipStage: (stage: Stage, screenshotIds?: number[]) => Promise<void>;
  unskipStage: (stage: Stage, screenshotIds?: number[]) => Promise<void>;
  invalidateFromStage: (screenshotId: number, stage: string) => Promise<void>;
  loadEventLog: (screenshotId: number) => Promise<void>;
  clearEventLog: () => void;

  // Upload actions (Phase 2)
  setUploadFiles: (files: UploadFileItem[]) => void;
  setUploadImageType: (type: "battery" | "screen_time") => void;
  setUploadGroupId: (groupId: string) => void;
  startBrowserUpload: () => Promise<void>;
  cancelUpload: () => void;
  resetUploadResult: () => void;

  // Queue review actions
  enterQueue: (screenshotIds: number[], startIndex?: number) => void;
  exitQueue: () => void;
  queueNext: () => void;
  queuePrev: () => void;
  queueGoTo: (index: number) => void;

  // Deep-link actions
  setHighlightedScreenshotId: (id: number | null) => void;
  setReturnUrl: (url: string | null) => void;

  // Polling
  startPolling: () => void;
  stopPolling: () => void;

  // Derived helpers
  getStageStatus: (stage: Stage) => StageSummary;
  getScreenshotsForStage: (stage: Stage) => Screenshot[];
  getScreenshotStageStatus: (screenshot: Screenshot, stage: Stage) => StageStatus;
  isScreenshotException: (screenshot: Screenshot, stage: Stage) => boolean;
  getEligibleCount: (stage: Stage) => { eligible: number; blockedByPrereq: number };
}

/**
 * Factory function to create a preprocessing store with an injected service.
 * Server mode passes ServerPreprocessingService, WASM mode passes WASMPreprocessingService.
 *
 * `activeStages` controls which stages are eligible for prereq computation,
 * running-stage detection, and downstream invalidation. WASM mode passes the
 * 3-stage list (PHI removed); server/Tauri pass the full 5-stage list.
 */
export function createPreprocessingStore(
  service: IPreprocessingService,
  activeStages: readonly Stage[] = STAGES,
) {
  // Per-instance abort flag for upload cancellation (not module-level to avoid cross-store leaks)
  let _uploadCancelled = false;
  // One-shot guard: reconcile stuck stages on first loadSummary in WASM mode
  let _reconciled = false;

  return create<PreprocessingState>((set, get) => ({
  // Initial state
  screenshots: [],
  selectedGroupId: "",
  groups: [],
  summary: null,
  activeStage: activeStages[0] ?? "device_detection",
  pageMode: "pipeline",
  isRunningStage: false,
  stageProgress: null,
  filter: (() => { try { return (localStorage.getItem("pp-filter") as FilterMode) || "completed"; } catch { return "completed" as FilterMode; } })(),
  phiPreset: "screen_time",
  redactionMethod: "redbox",
  llmEnabled: false,
  llmEndpoint: "http://YOUR_LLM_HOST:1234/v1",
  llmModel: "openai/gpt-oss-20b",
  llmApiKey: "",
  selectedScreenshotId: null,
  eventLog: null,
  isLoading: false,
  _pollInterval: null,
  _pollCount: 0,
  _queuedCount: 0,
  _completedBaseline: 0,
  _abortController: null,
  _pollStage: activeStages[0] ?? "device_detection",
  _pendingTaskIds: [],

  // Upload state
  uploadFiles: [],
  uploadImageType: "screen_time",
  uploadGroupId: "",
  isUploading: false,
  uploadProgress: null,
  uploadErrors: [],

  // Per-stage table sort (restored from localStorage)
  tableSortColumn: (() => { try { const v = localStorage.getItem("pp-sort-col"); return v ? JSON.parse(v) : {}; } catch { return {}; } })(),
  tableSortDirection: (() => { try { const v = localStorage.getItem("pp-sort-dir"); return v ? JSON.parse(v) : {}; } catch { return {}; } })(),

  // Deep-link state
  highlightedScreenshotId: null,
  returnUrl: null,

  // Image version counter
  imageVersion: 0,

  // Queue review mode
  queueMode: false,
  queueIndex: 0,
  queueScreenshotIds: [],

  setActiveStage: (stage) => set({ activeStage: stage }),
  setPageMode: (mode) => set({ pageMode: mode }),
  setFilter: (filter) => { try { localStorage.setItem("pp-filter", filter); } catch { /* ignore */ } set({ filter }); },
  setTableSort: (stage, column, direction) => {
    const newCol = { ...get().tableSortColumn, [stage]: column };
    const newDir = { ...get().tableSortDirection, [stage]: direction };
    try { localStorage.setItem("pp-sort-col", JSON.stringify(newCol)); localStorage.setItem("pp-sort-dir", JSON.stringify(newDir)); } catch { /* ignore */ }
    set({ tableSortColumn: newCol, tableSortDirection: newDir });
  },
  setSelectedGroupId: (groupId) => {
    // If a stage is running for another group, stop polling first to prevent desync
    const { isRunningStage, selectedGroupId: currentGroup } = get();
    if (isRunningStage && currentGroup && currentGroup !== groupId) {
      get().stopPolling();
      set({ isRunningStage: false, stageProgress: null });
      // Show toast so user knows why the indicator disappeared
      import("react-hot-toast").then(({ default: toast }) => {
        toast("Switched groups — previous stage run continues in the background", { duration: 4000 });
      });
    }
    set({ selectedGroupId: groupId, screenshots: [], summary: null });
    // Auto-load when group changes — log errors instead of swallowing
    get().loadScreenshots().catch((e) => console.error("Failed to load screenshots for group:", e));
    get().loadSummary().catch((e) => console.error("Failed to load summary for group:", e));
  },
  setPhiPreset: (preset) => set({ phiPreset: preset }),
  setRedactionMethod: (method) => set({ redactionMethod: method }),
  setLlmEnabled: (enabled) => set({ llmEnabled: enabled }),
  setLlmEndpoint: (endpoint) => set({ llmEndpoint: endpoint }),
  setLlmModel: (model) => set({ llmModel: model }),
  setLlmApiKey: (key) => set({ llmApiKey: key }),

  loadGroups: async () => {
    try {
      const data = await service.getGroups();
      if (data && data.length > 0) {
        set({ groups: data });
        const { selectedGroupId } = get();
        const stillExists = data.some((g) => g.id === selectedGroupId);
        if (!selectedGroupId || !stillExists) {
          get().setSelectedGroupId(data[0]!.id);
        }
      } else {
        // All groups deleted — clear selection and data
        set({ groups: [], selectedGroupId: "", screenshots: [], summary: null });
      }
    } catch (err) {
      console.error("Failed to load groups:", err);
      toast.error("Failed to load groups");
    }
  },

  loadScreenshots: async () => {
    const { selectedGroupId } = get();
    if (!selectedGroupId) {
      set({ screenshots: [] });
      return;
    }

    // Only show loading spinner on initial load, not background refreshes
    const isInitialLoad = get().screenshots.length === 0;
    if (isInitialLoad) set({ isLoading: true });
    try {
      const data = await service.getScreenshots({
        group_id: selectedGroupId,
        page_size: 5000,
        sort_by: "id",
        sort_order: "asc",
      });
      if (data) {
        // Avoid replacing the array reference if data hasn't changed —
        // this prevents downstream useMemo/re-renders from triggering.
        const prev = get().screenshots;
        const next = data.items;
        const stageStatusJson = (s: Screenshot) => {
          const pp = (s.processing_metadata as Record<string, unknown> | undefined)?.preprocessing as Record<string, unknown> | undefined;
          return JSON.stringify(pp?.stage_status);
        };
        // Pre-cache prev stage_status strings to avoid 2N JSON.stringify calls during polling
        const prevCache = prev.map(stageStatusJson);
        const changed = prev.length !== next.length ||
          next.some((item, i) =>
            item.id !== prev[i]?.id ||
            item.processing_status !== prev[i]?.processing_status ||
            item.processed_at !== prev[i]?.processed_at ||
            stageStatusJson(item) !== prevCache[i]
          );
        if (changed) {
          // Don't increment imageVersion during polling — it causes every
          // row's image to re-fetch and flash. Only bump imageVersion for
          // explicit user actions (crop, redact) via bumpImageVersion().
          set({ screenshots: next });
        }
      }
    } catch (err) {
      console.error("Failed to load screenshots:", err);
      if (isInitialLoad) toast.error("Failed to load screenshots");
    } finally {
      if (isInitialLoad) set({ isLoading: false });
    }
  },

  loadSummary: async () => {
    const { selectedGroupId } = get();
    if (!selectedGroupId) return;

    // Reconcile stuck stages on first load in WASM mode (recovers from tab crash)
    if (!_reconciled && config.isLocalMode) {
      _reconciled = true;
      try {
        const count = await service.reconcileStuckStages?.();
        if (count && count > 0) {
          console.log(`[Preprocessing] Reconciled ${count} stuck screenshot(s)`);
          toast(`Recovered ${count} screenshot(s) from interrupted processing`, { duration: 5000 });
        }
      } catch (err) {
        console.error("[Preprocessing] Stuck-state reconciliation failed:", err);
      }
    }

    try {
      const data = await service.getSummary(selectedGroupId);
      if (data) {
        set({ summary: data });

        // Auto-detect running tasks across active stages and reconnect polling.
        // Must check all active stages, not just activeStage — after a page refresh
        // the store resets to the first stage even if a different stage is
        // actively running on workflow workers. Inactive stages can never be
        // running so we skip them here for free.
        const alreadyPolling = get()._pollInterval !== null;
        if (!alreadyPolling) {
          const runningStage = activeStages.find((s) => (data[s]?.running ?? 0) > 0);
          if (runningStage) {
            const runningSummary = data[runningStage]!;
            set({
              isRunningStage: true,
              activeStage: runningStage,
              stageProgress: { completed: 0, total: runningSummary.running },
              _pollCount: 0,
              _queuedCount: runningSummary.running,
              _completedBaseline: runningSummary.completed,
              _pollStage: runningStage,
            });
            get().startPolling();
          }
        }
      }
    } catch (err) {
      console.error("Failed to load preprocessing summary:", err);
    }
  },

  runStage: async (stage, screenshotIds) => {
    const { selectedGroupId, phiPreset, redactionMethod, llmEnabled, llmEndpoint, llmModel, llmApiKey } = get();
    if (!selectedGroupId && !screenshotIds) return;

    // Capture how many are already completed before this batch starts
    const summary = get().summary;
    const baseline = summary ? summary[stage]?.completed ?? 0 : 0;
    const abortController = new AbortController();
    set({ isRunningStage: true, stageProgress: null, _pollCount: 0, _queuedCount: 0, _completedBaseline: baseline, _pollStage: stage, _abortController: abortController });
    try {
      const options: RunStageOptions = {
        ...(selectedGroupId && { group_id: selectedGroupId }),
        ...(screenshotIds && { screenshot_ids: screenshotIds }),
        phi_pipeline_preset: phiPreset,
        phi_redaction_method: redactionMethod,
      };
      if (stage === "phi_detection") {
        const settings = useSettingsStore.getState();
        options.phi_ocr_engine = "leptess";  // Rust OCR via PyO3 (server) or native (Tauri)
        options.phi_ner_detector = settings.phiNerDetector;
        if (llmEnabled) {
          options.llm_endpoint = llmEndpoint;
          options.llm_model = llmModel;
          if (llmApiKey) options.llm_api_key = llmApiKey;
        }
      }
      if (stage === "ocr") {
        const settings = useSettingsStore.getState();
        options.ocr_method = settings.gridDetectionMethod;
        options.max_shift = settings.maxShift;
        options.skip_daily_totals = settings.skipDailyTotals;
      }
      if (config.isLocalMode) {
        // WASM mode: report per-screenshot progress via callback.
        // Also refresh table data so rows update live during processing.
        options.onProgress = (completed, total) => {
          set({ stageProgress: { completed, total } });
          // Refresh screenshots + summary from IndexedDB (already updated by processStage)
          get().loadScreenshots();
          get().loadSummary();
        };
        options.abortSignal = abortController.signal;
      }
      const result = await service.runStage(stage, options);
      if (stage === "phi_detection") {
        console.log("[phi_detection] dispatch result:", result);
      }
      if (result?.task_ids?.length) {
        set({ _pendingTaskIds: result.task_ids });
      }
      if (result && result.queued_count > 0) {
        toast.success(result.message);

        // Check if the work already completed synchronously (device detection,
        // cropping run in-process). The response message
        // contains "completed" for sync stages, "queued" for async workflow stages.
        const alreadyDone = config.isLocalMode || result.message?.includes("completed");

        if (alreadyDone) {
          // Work finished — just refresh and mark done.
          set({ isRunningStage: false, stageProgress: null });
          await get().loadScreenshots();
          await get().loadSummary();
        } else {
          // Server mode async: work is queued on workflow worker — poll for completion.
          set({
            stageProgress: { completed: 0, total: result.queued_count },
            _queuedCount: result.queued_count,
          });
          get().startPolling();
        }
      } else {
        // Nothing queued — done immediately
        if (result) toast.success(result.message);
        set({ isRunningStage: false });
        await get().loadScreenshots();
        await get().loadSummary();
      }
    } catch (err) {
      console.error(`Failed to run ${stage}:`, err);
      toast.error(`Failed to queue ${stage}`);
      set({ isRunningStage: false });
    }
  },

  stopStage: () => {
    const ac = get()._abortController;
    if (ac) ac.abort();
    // Force-terminate any in-flight processing workers (WASM mode)
    if (service.forceStop) service.forceStop();
    get().stopPolling();

    const { _pollStage, _pendingTaskIds, selectedGroupId } = get();
    set({ isRunningStage: false, stageProgress: null, _abortController: null, _pendingTaskIds: [] });

    // Always cancel on the backend — don't gate on _pendingTaskIds which may be empty
    if (!config.isLocalMode && selectedGroupId) {
      const stageLabel = _pollStage.replace(/_/g, " ");
      toast.loading(`Stopping ${stageLabel}...`, { id: "stage-cancel" });

      const afterCancel = () => {
        get().loadScreenshots();
        get().loadSummary();
      };

      if (_pollStage === "phi_detection") {
        api.preprocessing.cancelPhiDetection(_pendingTaskIds, selectedGroupId)
          .then((res) => { toast.success(res?.message ?? `${stageLabel} cancelled`, { id: "stage-cancel" }); afterCancel(); })
          .catch((err) => { toast.error(err instanceof Error ? err.message : "Failed to cancel", { id: "stage-cancel" }); afterCancel(); });
      } else {
        // Reset stage to pending — workflow activities that finish will see reset status
        service.resetStage(_pollStage, selectedGroupId)
          .then((res) => { toast.success(res?.message ?? `${stageLabel} stopped`, { id: "stage-cancel" }); afterCancel(); })
          .catch((err) => { toast.error(err instanceof Error ? err.message : "Failed to stop", { id: "stage-cancel" }); afterCancel(); });
      }
    } else {
      toast.success("Stage stopped");
      get().loadScreenshots();
      get().loadSummary();
    }
  },

  resetStage: async (stage) => {
    const { selectedGroupId } = get();
    if (!selectedGroupId) return;
    try {
      const result = await service.resetStage(stage, selectedGroupId);
      toast.success(result.message || `Stage ${stage.replace(/_/g, " ")} reset`);
      await get().loadScreenshots();
      await get().loadSummary();
    } catch (err) {
      console.error("Failed to reset stage:", err);
      toast.error("Failed to reset stage");
    }
  },

  skipStage: async (stage, screenshotIds) => {
    const { selectedGroupId } = get();
    if (!selectedGroupId) return;
    const action = "skip";
    try {
      const result = await service.skipStage(stage, selectedGroupId, screenshotIds);
      toast.success(result.message || `${stage.replace(/_/g, " ")} skipped`);
      await Promise.all([get().loadScreenshots(), get().loadSummary()]);
    } catch (err) {
      console.error(`Failed to ${action} stage:`, err);
      toast.error(`Failed to ${action} stage`);
    }
  },

  unskipStage: async (stage, screenshotIds) => {
    const { selectedGroupId } = get();
    if (!selectedGroupId) return;
    const action = "unskip";
    try {
      const result = await service.skipStage(stage, selectedGroupId, screenshotIds, true);
      toast.success(result.message || `${stage.replace(/_/g, " ")} unskipped`);
      await Promise.all([get().loadScreenshots(), get().loadSummary()]);
    } catch (err) {
      console.error(`Failed to ${action} stage:`, err);
      toast.error(`Failed to ${action} stage`);
    }
  },

  invalidateFromStage: async (screenshotId, stage) => {
    try {
      await service.invalidateFromStage(screenshotId, stage);
      toast.success(`Downstream stages invalidated from ${stage.replace(/_/g, " ")}`);
      await get().loadScreenshots();
      await get().loadSummary();
    } catch (err) {
      console.error("Failed to invalidate:", err);
      toast.error("Failed to invalidate stages");
    }
  },

  loadEventLog: async (screenshotId) => {
    try {
      const data = await service.getEventLog(screenshotId);
      set({ selectedScreenshotId: screenshotId, eventLog: data });
    } catch (err) {
      console.error("Failed to load event log:", err);
      toast.error("Failed to load event log");
    }
  },

  clearEventLog: () => set({ selectedScreenshotId: null, eventLog: null }),

  // Upload actions
  setUploadFiles: (files) => set({ uploadFiles: files }),
  setUploadImageType: (type) => set({ uploadImageType: type }),
  resetUploadResult: () => set({ uploadFiles: [], uploadProgress: null, uploadErrors: [] }),
  setUploadGroupId: (groupId) => set({ uploadGroupId: groupId }),

  cancelUpload: () => {
    _uploadCancelled = true;
    set({ isUploading: false, uploadErrors: ["Upload cancelled by user"] });
  },

  startBrowserUpload: async () => {
    const { uploadFiles, uploadGroupId, uploadImageType } = get();
    if (!uploadFiles.length || !uploadGroupId) return;

    _uploadCancelled = false;
    set({ isUploading: true, uploadProgress: { completed: 0, total: uploadFiles.length }, uploadErrors: [] });

    const BATCH_SIZE = 60;
    const errors: string[] = [];
    let totalCompleted = 0;

    for (let batchStart = 0; batchStart < uploadFiles.length; batchStart += BATCH_SIZE) {
      if (_uploadCancelled) break;
      const batch = uploadFiles.slice(batchStart, batchStart + BATCH_SIZE);

      // Show progress at the start of each batch so the bar moves immediately
      set({ uploadProgress: { completed: batchStart, total: uploadFiles.length } });

      const formData = new FormData();

      const metadata = {
        group_id: uploadGroupId,
        image_type: uploadImageType,
        items: batch.map((item) => ({
          participant_id: item.participant_id,
          filename: item.filename,
          original_filepath: item.original_filepath || null,
          screenshot_date: item.screenshot_date || null,
        })),
      };

      formData.append("metadata", JSON.stringify(metadata));
      for (const item of batch) {
        formData.append("files", item.file);
      }

      try {
        const result = await service.uploadBrowser(formData);
        totalCompleted += result.successful || 0;
        if (result.failed > 0) {
          for (const r of result.results || []) {
            if (!r.success && r.error) {
              errors.push(`File ${batchStart + r.index}: ${r.error}`);
            }
          }
        }
        // Surface queue failures — the response may include processing_queued
        // when the backend attempts background processing (e.g. programmatic uploads).
        const raw = result as Record<string, unknown>;
        if ("processing_queued" in raw && raw.processing_queued === false) {
          toast(
            "Upload succeeded but background processing could not be queued. Try re-running from the preprocessing tab.",
            { icon: "\u26A0\uFE0F", duration: 8000 },
          );
        }
      } catch (err) {
        errors.push(`Batch ${Math.floor(batchStart / BATCH_SIZE) + 1} failed: ${err}`);
      }

      set({ uploadProgress: { completed: totalCompleted, total: uploadFiles.length } });
    }

    // Keep uploadProgress visible so the completion screen persists.
    // uploadFiles cleared so the tag table doesn't reappear.
    set({
      isUploading: false,
      uploadErrors: errors,
      uploadFiles: [],
      uploadProgress: { completed: totalCompleted, total: uploadFiles.length },
    });

    if (errors.length === 0) {
      toast.success(`Uploaded ${totalCompleted} screenshot(s)`);
    } else {
      toast.error(`Upload completed with ${errors.length} error(s)`);
    }

    // Check storage quota after upload (WASM mode)
    if (config.isLocalMode && service.getStorageEstimate) {
      try {
        const est = await service.getStorageEstimate();
        if (est && est.percentUsed > 80) {
          toast(`Storage is ${est.percentUsed.toFixed(0)}% full. Consider deleting old groups to free space.`, { duration: 8000 });
        }
      } catch (e) { console.debug("[Upload] Storage estimate failed:", e); }
    }

    // Refresh groups and screenshots
    await get().loadGroups();
    if (uploadGroupId) {
      get().setSelectedGroupId(uploadGroupId);
    }
  },

  // Queue review actions
  enterQueue: (screenshotIds, startIndex = 0) =>
    set({ queueMode: true, queueScreenshotIds: screenshotIds, queueIndex: startIndex }),
  exitQueue: () =>
    set({ queueMode: false, queueIndex: 0, queueScreenshotIds: [] }),
  queueNext: () => {
    const { queueIndex, queueScreenshotIds } = get();
    if (queueIndex < queueScreenshotIds.length - 1) {
      set({ queueIndex: queueIndex + 1 });
    }
  },
  queuePrev: () => {
    const { queueIndex } = get();
    if (queueIndex > 0) {
      set({ queueIndex: queueIndex - 1 });
    }
  },
  queueGoTo: (index) => {
    const { queueScreenshotIds } = get();
    if (index >= 0 && index < queueScreenshotIds.length) {
      set({ queueIndex: index });
    }
  },

  // Deep-link actions
  setHighlightedScreenshotId: (id) => set({ highlightedScreenshotId: id }),
  setReturnUrl: (url) => set({ returnUrl: url }),

  startPolling: () => {
    const existing = get()._pollInterval;
    if (existing) clearInterval(existing);

    const MAX_POLL_COUNT = 450; // 15 minutes at 2s intervals

    const interval = setInterval(async () => {
      const pollCount = get()._pollCount + 1;
      set({ _pollCount: pollCount });

      // Safety: stop polling after max count to prevent infinite loops
      if (pollCount >= MAX_POLL_COUNT) {
        console.warn("[Preprocessing] Polling timed out after 15 minutes");
        get().stopPolling();
        set({ isRunningStage: false, stageProgress: null });
        const { default: toast } = await import("react-hot-toast");
        toast.error("Stage monitoring timed out after 15 minutes. Check preprocessing tab for current status.", { duration: 8000 });
        return;
      }

      // Only fetch summary during polling — the full 5000-screenshot list
      // is too expensive to transfer every 2s. Screenshots are refreshed
      // when polling stops (stage completes) or on explicit user action.
      await get().loadSummary();
      const summary = get().summary;
      if (summary) {
        const stage = get()._pollStage;
        const stageSummary = summary[stage];
        const queuedCount = get()._queuedCount;
        const baseline = get()._completedBaseline;
        // How many from THIS batch have completed (subtract pre-existing completed)
        const completedSoFar = stageSummary ? stageSummary.completed : 0;
        const batchCompleted = Math.max(0, completedSoFar - baseline);
        // Wait at least 3 polls (6s) before concluding "done" to give
        // workflow workers time to pick up activities and set status to "running"
        const minPollsBeforeComplete = 3;
        const allDone = stageSummary &&
          stageSummary.running === 0 &&
          pollCount >= minPollsBeforeComplete &&
          // Only stop if completed count actually increased from the queued batch,
          // or if there's truly nothing pending/running for this stage
          (stageSummary.pending === 0 || batchCompleted >= queuedCount);
        if (allDone) {
          // Done — refresh screenshots (skipped during polling for perf) and stop
          get().stopPolling();
          set({ isRunningStage: false, stageProgress: null });
          void get().loadScreenshots();
        } else if (stageSummary) {
          set({
            stageProgress: {
              completed: batchCompleted,
              total: queuedCount || summary.total,
            },
          });
        }
      }
    }, 2000);

    set({ _pollInterval: interval });
  },

  stopPolling: () => {
    const interval = get()._pollInterval;
    if (interval) {
      clearInterval(interval);
      set({ _pollInterval: null });
    }
  },

  // Derived helpers
  getStageStatus: (stage) => {
    const { summary } = get();
    if (summary) {
      return summary[stage];
    }
    // Compute from screenshots if no summary
    const { screenshots } = get();
    const counts: StageSummary = {
      completed: 0, pending: 0, skipped: 0, invalidated: 0,
      running: 0, failed: 0, cancelled: 0, exceptions: 0,
    };
    for (const s of screenshots) {
      const pp = (s.processing_metadata as Record<string, unknown>)?.preprocessing as Record<string, unknown> | undefined;
      const stageStatus = (pp?.stage_status as Record<string, string>)?.[stage] ?? SS.PENDING;
      if (stageStatus in counts) {
        counts[stageStatus as keyof StageSummary] += 1;
      } else {
        counts.pending += 1;
      }
    }
    return counts;
  },

  getScreenshotsForStage: (stage) => {
    const { screenshots, filter } = get();
    if (filter === "all") return screenshots;

    return screenshots.filter((s) => {
      const status = get().getScreenshotStageStatus(s, stage);
      switch (filter) {
        case "completed":
          return status === SS.COMPLETED;
        case "pending":
          return status === SS.PENDING;
        case "skipped":
          return status === SS.SKIPPED;
        case "invalidated":
          return status === SS.INVALIDATED;
        case "needs_review":
          return get().isScreenshotException(s, stage);
        default:
          return true;
      }
    });
  },

  getScreenshotStageStatus: (screenshot, stage) => {
    const pp = (screenshot.processing_metadata as Record<string, unknown>)?.preprocessing as Record<string, unknown> | undefined;
    return ((pp?.stage_status as Record<string, string>)?.[stage] ?? SS.PENDING) as StageStatus;
  },

  isScreenshotException: (screenshot, stage) => {
    // Only flag completed stages (matches backend is_exception logic)
    const status = get().getScreenshotStageStatus(screenshot, stage);
    if (status !== SS.COMPLETED) return false;

    const pp = (screenshot.processing_metadata as Record<string, unknown>)?.preprocessing as Record<string, unknown> | undefined;
    if (!pp) return false;
    const currentEvents = pp.current_events as Record<string, number | null> | undefined;
    const events = pp.events as PreprocessingEventData[] | undefined;
    if (!currentEvents || !events) return false;
    const eid = currentEvents[stage];
    if (!eid) return false;
    const event = events.find((e) => e.event_id === eid);
    if (!event) return false;
    const result = event.result;

    if (stage === "device_detection") {
      if (result.device_category === "unknown") return true;
      if ((result.confidence as number) < 0.7) return true;
    } else if (stage === "cropping") {
      if (result.is_ipad && !result.was_cropped) return true;
    } else if (stage === "phi_detection") {
      if (result.reviewed) return false; // Manually reviewed — no longer needs review
      if (result.phi_detected) return true;
      if ((result.regions_count as number) > 10) return true;
    } else if (stage === "phi_redaction") {
      if (result.phi_detected && !result.redacted) return true;
    } else if (stage === "ocr") {
      if (result.processing_status === SS.FAILED) return true;
      if (result.has_blocking_issues) return true;
      // Low alignment score
      const align = screenshot.alignment_score as number | null;
      if (typeof align === "number" && align < 0.8) return true;
      // Bar total vs OCR total mismatch
      const hourly = screenshot.extracted_hourly_data as Record<string, number> | null;
      const ocrTotal = result.extracted_total as string | null;
      if (hourly && ocrTotal) {
        let barTotal = 0;
        for (let i = 0; i < 24; i++) {
          const v = hourly[String(i)];
          if (typeof v === "number") barTotal += v;
        }
        const ocrMinutes = parseOcrTotalMinutes(ocrTotal);
        if (hasTotalsMismatchByThreshold(barTotal, ocrMinutes)) return true;
      }
    }
    return false;
  },

  getEligibleCount: (stage) => {
    const { screenshots } = get();
    // Prereqs come from the active stage list — inactive stages (e.g. PHI in
    // WASM mode) sit PENDING forever and would otherwise wedge OCR's count.
    const stageIdx = activeStages.indexOf(stage);
    const prereqs = stageIdx >= 0 ? activeStages.slice(0, stageIdx) : [];
    let eligible = 0;
    let blockedByPrereq = 0;
    for (const s of screenshots) {
      const pp = (s.processing_metadata as Record<string, unknown>)?.preprocessing as Record<string, unknown> | undefined;
      const statuses = (pp?.stage_status as Record<string, string>) ?? {};
      const thisStatus = statuses[stage] ?? SS.PENDING;
      if (thisStatus !== SS.PENDING && thisStatus !== SS.INVALIDATED && thisStatus !== SS.FAILED) continue;
      // Check prerequisites
      const prereqsMet = prereqs.every((p) => statuses[p] === SS.COMPLETED || statuses[p] === SS.SKIPPED);
      if (prereqsMet) {
        eligible++;
      } else {
        blockedByPrereq++;
      }
    }
    return { eligible, blockedByPrereq };
  },
}));
}

export type { Stage, StageStatus, FilterMode, PageMode, StageSummary, PreprocessingSummaryData, PreprocessingEventData, EventLogData, UploadFileItem, PreprocessingState };
export { STAGES };
