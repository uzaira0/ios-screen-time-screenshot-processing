/**
 * WASM-mode preprocessing service.
 *
 * Orchestrates all 4 preprocessing stages client-side:
 *   1. Device detection — dimension-based iOS device identification
 *   2. Cropping — iPad sidebar removal via Canvas
 *   3. PHI detection — Tesseract.js OCR + NER + regex
 *   4. PHI redaction — Canvas-based redbox/blackbox/pixelate
 *
 * Data is stored in IndexedDB via the storage service.
 * Processing is synchronous (no backend) — runStage() returns after completion.
 */

import type {
  IPreprocessingService,
  PreprocessingStage,
  RunStageOptions,
  RunStageResult,
} from "@/core/interfaces/IPreprocessingService";
import type { IndexedDBStorageService } from "../storage/IndexedDBStorageService";
import type {
  Screenshot,
  Group,
  PreprocessingSummary,
  PreprocessingEvent,
  PreprocessingEventLog,
  PreprocessingDetailsResponse,
  BrowserUploadResponse,
  PHIRegionsResponse,
  PHIRegionRect,
} from "@/types";
import { detectDevice } from "./deviceDetection";
import { cropScreenshot } from "./cropping";
import type { PHIRegion } from "@/core/interfaces/IPreprocessingService";
import type { IProcessingService } from "@/core/interfaces/IProcessingService";
import { createObjectURL as cachedCreateObjectURL } from "../storage/opfsBlobStorage";

import { PREPROCESSING_STAGES, StageStatus as SS } from "@/core/generated/constants";
import { PHI_STAGES } from "@/core/di/tokens";
const STAGES: PreprocessingStage[] = [...PREPROCESSING_STAGES];

// PHI modules are dynamic-imported only when the feature is enabled, so the
// nerWorker chunk and phiDetection helpers stay tree-shakable in WASM-mode
// builds where AppFeatures.phiDetection is false.
type PhiModule = typeof import("./phiDetection");
type PhiRedactModule = typeof import("./phiRedaction");

export interface WASMPreprocessingOptions {
  /** When false, runStage("phi_*") is a no-op and PHI helpers are never imported. */
  enablePhi: boolean;
}

// ---------------------------------------------------------------------------
// Helpers to read/write preprocessing metadata on a screenshot
// ---------------------------------------------------------------------------

interface PreprocessingMeta {
  stage_status: Record<string, string>;
  events: PreprocessingEvent[];
  current_events: Record<string, number>;
}

function getPreprocessing(screenshot: Screenshot): PreprocessingMeta {
  const pm = (screenshot.processing_metadata as Record<string, unknown>) ?? {};
  const pp = (pm.preprocessing as PreprocessingMeta) ?? {
    stage_status: {},
    events: [],
    current_events: {},
  };
  return pp;
}

function setPreprocessing(screenshot: Screenshot, pp: PreprocessingMeta): Record<string, unknown> {
  const pm = { ...((screenshot.processing_metadata as Record<string, unknown>) ?? {}) };
  // Write top-level stage result keys to match server shape (PreprocessingDetailsResponse).
  // This ensures components reading preprocessing.device_detection etc. work in both modes.
  const ppOut: Record<string, unknown> = { ...pp };
  for (const [stage, eid] of Object.entries(pp.current_events)) {
    const event = pp.events.find((e) => e.event_id === eid);
    if (event) {
      ppOut[stage] = event.result;
    }
  }
  pm.preprocessing = ppOut;
  return pm;
}

function addEvent(
  pp: PreprocessingMeta,
  stage: string,
  status: string,
  result: Record<string, unknown>,
): PreprocessingMeta {
  // Derive next ID from existing events to avoid collisions across page reloads
  const maxExisting = pp.events.reduce((max, e) => Math.max(max, e.event_id), 0);
  const eid = maxExisting + 1;
  const event: PreprocessingEvent = {
    event_id: eid,
    stage,
    timestamp: new Date().toISOString(),
    source: "wasm",
    params: {},
    result,
    output_file: null,
    input_file: null,
    supersedes: null,
  };
  return {
    ...pp,
    events: [...pp.events, event],
    current_events: { ...pp.current_events, [stage]: eid },
    stage_status: { ...pp.stage_status, [stage]: status },
  };
}

/**
 * Normalize legacy events stored with `created_at` (pre-typed era) to the
 * current `PreprocessingEvent` shape.  Handles existing IndexedDB data without
 * requiring a Dexie schema migration since events are stored as an opaque JSON
 * blob inside `processing_metadata`.
 */
function normalizeEvents(events: PreprocessingEvent[]): PreprocessingEvent[] {
  return events.map((e) => {
    if (!e.timestamp && (e as Record<string, unknown>).created_at) {
      const { created_at, status, ...rest } = e as Record<string, unknown>;
      return {
        ...rest,
        timestamp: created_at as string,
        source: (rest.source as string) ?? "wasm",
        params: (rest.params as Record<string, unknown>) ?? {},
        output_file: (rest.output_file as string | null) ?? null,
        input_file: (rest.input_file as string | null) ?? null,
        supersedes: (rest.supersedes as number | null) ?? null,
      } as PreprocessingEvent;
    }
    return e;
  });
}

// ---------------------------------------------------------------------------
// Service implementation
// ---------------------------------------------------------------------------

export class WASMPreprocessingService implements IPreprocessingService {
  private storage: IndexedDBStorageService;
  private processing: IProcessingService;
  private readonly enablePhi: boolean;
  /** The stage list this service treats as active — drives prereqs, resets, invalidation. */
  private readonly activeStages: readonly PreprocessingStage[];
  private phiModulePromise: Promise<PhiModule> | null = null;
  private phiRedactPromise: Promise<PhiRedactModule> | null = null;

  constructor(
    storage: IndexedDBStorageService,
    processing: IProcessingService,
    options: WASMPreprocessingOptions = { enablePhi: true },
  ) {
    this.storage = storage;
    this.processing = processing;
    this.enablePhi = options.enablePhi;
    this.activeStages = options.enablePhi
      ? STAGES
      : STAGES.filter((s) => !PHI_STAGES.includes(s));
  }

  private loadPhiModule(): Promise<PhiModule> {
    if (!this.phiModulePromise) {
      this.phiModulePromise = import("./phiDetection");
    }
    return this.phiModulePromise;
  }

  private loadPhiRedactModule(): Promise<PhiRedactModule> {
    if (!this.phiRedactPromise) {
      this.phiRedactPromise = import("./phiRedaction");
    }
    return this.phiRedactPromise;
  }

  /** Prereq stages for a given target — the active stages that run before it. */
  private prereqsFor(stage: PreprocessingStage): readonly PreprocessingStage[] {
    const idx = this.activeStages.indexOf(stage);
    if (idx < 0) return [];
    return this.activeStages.slice(0, idx);
  }

  /** Downstream stages of a given target — the active stages from it onward. */
  private downstreamFrom(stage: PreprocessingStage): readonly PreprocessingStage[] {
    const idx = this.activeStages.indexOf(stage);
    if (idx < 0) return [];
    return this.activeStages.slice(idx);
  }

  async getStorageEstimate(): Promise<import("@/core/interfaces/IStorageService").StorageEstimate | null> {
    return this.storage.getStorageEstimate();
  }

  async reconcileStuckStages(): Promise<number> {
    const screenshots = await this.storage.getAllScreenshots();
    let reconciled = 0;
    for (const s of screenshots) {
      const pp = getPreprocessing(s);
      let changed = false;
      const newStageStatus = { ...pp.stage_status };
      for (const stage of STAGES) {
        if (newStageStatus[stage] === "running") {
          newStageStatus[stage] = SS.PENDING;
          changed = true;
        }
      }
      if (changed) {
        const updatedPp: PreprocessingMeta = { ...pp, stage_status: newStageStatus };
        await this.storage.updateScreenshot(s.id as number, {
          processing_metadata: setPreprocessing(s, updatedPp),
        });
        reconciled++;
      }
    }
    return reconciled;
  }

  forceStop(): void {
    // Terminate the processing worker (kills any in-flight OCR/grid detection).
    // It will be lazily recreated on the next processImage/detectGrid call.
    this.processing.terminate();
    // Also terminate PHI detection workers — but only if they were ever loaded.
    if (this.phiModulePromise) {
      this.phiModulePromise
        .then((m) => {
          m.terminateNERWorker();
          m.terminateTesseractWorker();
        })
        .catch(() => { /* module never finished loading; nothing to terminate */ });
    }
  }

  /** Record a failed event and return when the image blob is missing from storage. */
  private async recordMissingBlob(screenshot: Screenshot, stage: PreprocessingStage): Promise<void> {
    const pp = getPreprocessing(screenshot);
    const updated = addEvent(pp, stage, SS.FAILED, {
      processing_status: "failed",
      error: "Image file missing from storage. Re-upload this screenshot.",
    });
    await this.storage.updateScreenshot(screenshot.id as number, {
      processing_metadata: setPreprocessing(screenshot, updated),
    });
  }

  async getGroups(): Promise<Group[]> {
    const screenshots = await this.storage.getAllScreenshots();
    // Group by group_id
    const groups = new Map<string, { id: string; name: string; screenshot_count: number }>();
    for (const s of screenshots) {
      const gid = s.group_id || "default";
      const existing = groups.get(gid);
      if (existing) {
        existing.screenshot_count++;
      } else {
        groups.set(gid, { id: gid, name: gid, screenshot_count: 1 });
      }
    }
    return [...groups.values()] as Group[];
  }

  async getScreenshots(params: {
    group_id: string;
    page_size?: number;
    sort_by?: string;
    sort_order?: string;
  }): Promise<{ items: Screenshot[]; total: number }> {
    const all = await this.storage.getAllScreenshots({ group_id: params.group_id });
    // Sort by id ascending by default
    const sorted = [...all].sort((a, b) => (a.id as number) - (b.id as number));
    return { items: sorted, total: sorted.length };
  }

  async getSummary(groupId: string): Promise<PreprocessingSummary> {
    const screenshots = await this.storage.getAllScreenshots({ group_id: groupId });
    const stageSummaries: Record<string, Record<string, number>> = {
      device_detection: { completed: 0, pending: 0, invalidated: 0, running: 0, failed: 0, exceptions: 0 },
      cropping: { completed: 0, pending: 0, invalidated: 0, running: 0, failed: 0, exceptions: 0 },
      phi_detection: { completed: 0, pending: 0, invalidated: 0, running: 0, failed: 0, exceptions: 0 },
      phi_redaction: { completed: 0, pending: 0, invalidated: 0, running: 0, failed: 0, exceptions: 0 },
      ocr: { completed: 0, pending: 0, invalidated: 0, running: 0, failed: 0, exceptions: 0 },
    };

    for (const s of screenshots) {
      const pp = getPreprocessing(s);
      for (const stage of STAGES) {
        const status = pp.stage_status[stage] ?? SS.PENDING;
        const stageSummary = stageSummaries[stage]!;
        if (status in stageSummary) {
          stageSummary[status] = (stageSummary[status] ?? 0) + 1;
        } else {
          stageSummary.pending = (stageSummary.pending ?? 0) + 1;
        }
      }
    }

    const summary = { total: screenshots.length, ...stageSummaries };
    return summary as PreprocessingSummary;
  }

  async runStage(stage: PreprocessingStage, options: RunStageOptions): Promise<RunStageResult> {
    // PHI stages are inert when the feature is disabled. The UI shouldn't
    // surface them, but if a deep-link or stale call hits us, no-op cleanly.
    if (!this.enablePhi && (PHI_STAGES as readonly PreprocessingStage[]).includes(stage)) {
      return {
        queued_count: 0,
        message: `${stage.replace(/_/g, " ")} is disabled in this mode`,
      };
    }

    // Always reconcile stuck 'running' rows before we start. The store
    // also calls reconcileStuckStages() on first loadSummary, but that's
    // only once-per-session — if a user starts a run, navigates away
    // mid-batch, comes back without a full reload, and clicks Run again,
    // any rows we never finished writing on the way out would still be
    // 'running' and therefore not eligible. Reconciling at runStage entry
    // makes a re-run idempotent.
    try {
      await this.reconcileStuckStages();
    } catch (e) {
      console.warn("[WASM] reconcileStuckStages on runStage entry failed:", e);
    }

    // Get eligible screenshots
    let screenshots: Screenshot[];
    if (options.screenshot_ids?.length) {
      const all = await Promise.all(
        options.screenshot_ids.map((id) => this.storage.getScreenshot(id)),
      );
      screenshots = all.filter((s): s is Screenshot => s !== null);
    } else if (options.group_id) {
      screenshots = await this.storage.getAllScreenshots({ group_id: options.group_id });
    } else {
      return { queued_count: 0, message: "No group or screenshot IDs specified" };
    }

    // Filter to eligible: status pending/invalidated/failed, prereqs met.
    // Prereqs come from the active stage list — PHI stages stay PENDING
    // forever when disabled and would otherwise wedge OCR.
    const prereqs = this.prereqsFor(stage);

    const eligible = screenshots.filter((s) => {
      const pp = getPreprocessing(s);
      const status = pp.stage_status[stage] ?? SS.PENDING;
      if (status !== SS.PENDING && status !== SS.INVALIDATED && status !== SS.FAILED) return false;
      // Check prereqs
      return prereqs.every((p) => pp.stage_status[p] === SS.COMPLETED);
    });

    if (eligible.length === 0) {
      return { queued_count: 0, message: `No eligible screenshots for ${stage.replace(/_/g, " ")}` };
    }

    let completed = 0;
    options.onProgress?.(0, eligible.length);

    // Shared failure recorder. Both the unbounded and serial paths use
    // it. Wrapping the IDB write in its own try/catch is load-bearing:
    // if updateScreenshot itself rejects (quota, version error), the
    // unbounded path's post-allSettled walk would otherwise blow up
    // partway through and leave subsequent rows with no recorded
    // failure event.
    const recordFailure = async (screenshot: Screenshot, reason: unknown): Promise<void> => {
      console.error(`[WASM] ${stage} failed for screenshot ${screenshot.id}:`, reason);
      try {
        const pp = getPreprocessing(screenshot);
        const updated = addEvent(pp, stage, SS.FAILED, {
          error: reason instanceof Error ? reason.message : String(reason),
        });
        await this.storage.updateScreenshot(screenshot.id as number, {
          processing_metadata: setPreprocessing(screenshot, updated),
        });
      } catch (writeErr) {
        console.error(`[WASM] failed to record failure event for screenshot ${screenshot.id}:`, writeErr);
      }
    };

    // device_detection and cropping are I/O bound (IndexedDB reads +
    // canvas decode) and cap at 32 concurrent to avoid flooding the
    // browser's IndexedDB connection pool and crashing the tab on large
    // batches. ocr scales with the processing-worker pool size — each
    // LepTess worker can handle one PROCESS_IMAGE at a time, so
    // dispatching poolSize-many concurrent jobs keeps every worker busy
    // without queueing. PHI stages still serialize because they share a
    // single Tesseract/NER worker per browser tab.
    const DEVICE_CROP_CONCURRENCY = 32;
    const isBoundedConcurrency =
      stage === "device_detection" || stage === "cropping";
    const ocrConcurrency = stage === "ocr" ? this.processing.getPoolSize?.() ?? 1 : 0;

    if (isBoundedConcurrency) {
      let cursor = 0;
      const runner = async () => {
        for (;;) {
          if (options.abortSignal?.aborted) return;
          const i = cursor++;
          if (i >= eligible.length) return;
          const screenshot = eligible[i]!;
          try {
            await this.processStage(screenshot, stage, options);
            completed++;
          } catch (e) {
            await recordFailure(screenshot, e);
          }
          options.onProgress?.(completed, eligible.length);
        }
      };
      await Promise.all(
        Array.from({ length: Math.min(DEVICE_CROP_CONCURRENCY, eligible.length) }, () => runner()),
      );
    } else if (ocrConcurrency > 1) {
      // Pool-sized concurrency for OCR. Use a cursor + N workers
      // pattern so each worker pulls the next eligible screenshot the
      // moment it finishes its current one. This keeps the pool fully
      // saturated even when individual screenshots take wildly
      // different OCR times (Pro Max + many apps vs iPhone SE +
      // single-app).
      let cursor = 0;
      const runner = async () => {
        for (;;) {
          if (options.abortSignal?.aborted) return;
          const i = cursor++;
          if (i >= eligible.length) return;
          const screenshot = eligible[i]!;
          try {
            await this.processStage(screenshot, stage, options);
            completed++;
          } catch (e) {
            await recordFailure(screenshot, e);
          }
          options.onProgress?.(completed, eligible.length);
        }
      };
      await Promise.all(
        Array.from({ length: Math.min(ocrConcurrency, eligible.length) }, () => runner()),
      );
    } else {
      // PHI: serialize because the Tesseract.js + NER workers are
      // singletons and not part of the LepTess pool.
      for (let i = 0; i < eligible.length; i++) {
        if (options.abortSignal?.aborted) break;
        const screenshot = eligible[i]!;
        try {
          await this.processStage(screenshot, stage, options);
          completed++;
        } catch (e) {
          await recordFailure(screenshot, e);
        }
        options.onProgress?.(completed, eligible.length);
        // Yield so the progress bar repaints between items
        await new Promise<void>((r) => { setTimeout(r, 0); });
      }
    }

    // Clean up workers after PHI detection batch
    if (stage === "phi_detection" && this.phiModulePromise) {
      const m = await this.phiModulePromise;
      m.terminateNERWorker();
      m.terminateTesseractWorker();
    }

    return {
      queued_count: completed,
      message: `Completed ${stage.replace(/_/g, " ")} for ${completed} screenshot(s)`,
      screenshot_ids: eligible.map((s) => s.id as number),
    };
  }

  private async processStage(
    screenshot: Screenshot,
    stage: PreprocessingStage,
    options: RunStageOptions,
  ): Promise<void> {
    const id = screenshot.id as number;
    const blob = await this.storage.getImageBlob(id);

    switch (stage) {
      case "device_detection": {
        // Get image dimensions — try stored metadata first to avoid full decode
        let width: number, height: number;
        const metadata = screenshot as unknown as Record<string, unknown>;
        if (typeof metadata.image_width === "number" && typeof metadata.image_height === "number" &&
            metadata.image_width > 0 && metadata.image_height > 0) {
          width = metadata.image_width;
          height = metadata.image_height;
        } else if (blob) {
          const bmp = await createImageBitmap(blob);
          width = bmp.width;
          height = bmp.height;
          bmp.close();
        } else {
          console.warn(`[WASM] device_detection: No dimensions or blob for screenshot ${id}`);
          width = 0;
          height = 0;
        }

        const result = detectDevice(width, height);

        const pp = getPreprocessing(screenshot);
        const updated = addEvent(pp, stage, SS.COMPLETED, {
          device_model: result.model ?? "unknown",
          device_family: result.family ?? "unknown",
          device_category: result.category,
          confidence: result.confidence,
          orientation: result.orientation,
          dimensions: { width, height },
          needs_cropping: result.needsCropping ?? false,
        });

        await this.storage.updateScreenshot(id, {
          processing_metadata: setPreprocessing(screenshot, updated),
        });
        break;
      }

      case "cropping": {
        if (!blob) { await this.recordMissingBlob(screenshot, stage); return; }

        // Use the preserved original if available (handles re-runs after reset)
        const originalBlob = await this.storage.getStageBlob(id, "original");
        const sourceBlob = originalBlob ?? blob;

        const cropResult = await cropScreenshot(sourceBlob);
        const pp = getPreprocessing(screenshot);

        if (cropResult.wasCropped) {
          // Preserve original only once, before first overwrite
          if (!originalBlob) {
            await this.storage.saveStageBlob(id, "original", sourceBlob);
          }
          // Save cropped blob as current + stage snapshot
          await this.storage.saveImageBlob(id, cropResult.croppedBlob);
          await this.storage.saveStageBlob(id, "cropping", cropResult.croppedBlob);
        } else {
          // Even if not cropped, save a snapshot so getStageImageUrl("cropping") works
          await this.storage.saveStageBlob(id, "cropping", sourceBlob);
        }

        const detectionEvent = pp.events.find(
          (e) => e.stage === "device_detection" && e.event_id === pp.current_events.device_detection,
        );
        const updated = addEvent(pp, stage, SS.COMPLETED, {
          was_cropped: cropResult.wasCropped,
          was_patched: false,
          original_dimensions: [cropResult.originalDimensions.width, cropResult.originalDimensions.height],
          cropped_dimensions: [cropResult.croppedDimensions.width, cropResult.croppedDimensions.height],
          device_model: cropResult.deviceModel,
          is_ipad: detectionEvent?.result?.device_category === "ipad",
        });

        await this.storage.updateScreenshot(id, {
          processing_metadata: setPreprocessing(screenshot, updated),
        });
        break;
      }

      case "phi_detection": {
        if (!blob) { await this.recordMissingBlob(screenshot, stage); return; }

        const { detectPHI } = await this.loadPhiModule();
        const phiResult = await detectPHI(blob, {
          llmEndpoint: options.llm_endpoint,
          llmModel: options.llm_model,
          llmApiKey: options.llm_api_key,
        });

        const pp = getPreprocessing(screenshot);
        const updated = addEvent(pp, stage, SS.COMPLETED, {
          phi_detected: phiResult.regions.length > 0,
          regions_count: phiResult.regions.length,
          phi_entities: phiResult.regions,
          ocr_text: phiResult.ocrText,
          ocr_confidence: phiResult.ocrConfidence,
          ner_status: phiResult.nerStatus,
          reviewed: false,
        });

        await this.storage.updateScreenshot(id, {
          processing_metadata: setPreprocessing(screenshot, updated),
        });
        break;
      }

      case "phi_redaction": {
        if (!blob) { await this.recordMissingBlob(screenshot, stage); return; }

        // Get PHI regions from the detection stage
        const pp = getPreprocessing(screenshot);
        const detectionEventId = pp.current_events.phi_detection;
        const detectionEvent = pp.events.find((e) => e.event_id === detectionEventId);
        const regions = (detectionEvent?.result?.phi_entities ?? []) as PHIRegion[];

        if (regions.length === 0) {
          // No PHI to redact
          const updated = addEvent(pp, stage, SS.COMPLETED, {
            phi_detected: false,
            redacted: false,
            redaction_method: options.phi_redaction_method ?? "redbox",
            regions_redacted: 0,
          });
          await this.storage.updateScreenshot(id, {
            processing_metadata: setPreprocessing(screenshot, updated),
          });
          break;
        }

        const method = (options.phi_redaction_method ?? "redbox") as "redbox" | "blackbox" | "pixelate";
        const { redactImage } = await this.loadPhiRedactModule();
        const redactedBlob = await redactImage(blob, regions, method);

        // Save redacted image as current + stage snapshot
        await this.storage.saveImageBlob(id, redactedBlob);
        await this.storage.saveStageBlob(id, "phi_redaction", redactedBlob);

        const updated = addEvent(pp, stage, SS.COMPLETED, {
          phi_detected: true,
          redacted: true,
          redaction_method: method,
          regions_redacted: regions.length,
        });

        await this.storage.updateScreenshot(id, {
          processing_metadata: setPreprocessing(screenshot, updated),
        });
        break;
      }

      case "ocr": {
        if (!blob) { await this.recordMissingBlob(screenshot, stage); return; }
        const _ocrT0 = performance.now();

        const ocrMethod = (options.ocr_method ?? "line_based") as "ocr_anchored" | "line_based";

        // Determine image type from screenshot metadata
        const metadata = screenshot as unknown as Record<string, unknown>;
        const imageType = (metadata.image_type as "battery" | "screen_time") ?? "screen_time";

        let ocrResult: {
          hourlyData: unknown;
          title: string | null;
          total: string | null;
          gridCoordinates?: unknown;
          gridDetectionFailed?: boolean;
          gridDetectionError?: string;
          alignmentScore?: number | null;
        };

        // Detect grid using the user's chosen method first, then fall back to the other.
        // Line-based detection doesn't need Tesseract, so we skip initialize() here —
        // it will be called lazily before processImage() which needs OCR for title/total.
        const fallbackMethod = ocrMethod === "line_based" ? "ocr_anchored" : "line_based";
        const _gridT0 = performance.now();
        let grid = await this.processing.detectGrid(blob, imageType, ocrMethod);
        if (!grid) {
          grid = await this.processing.detectGrid(blob, imageType, fallbackMethod);
        }
        console.log(`[BENCH] OCR stage - grid detection: ${(performance.now() - _gridT0).toFixed(0)}ms`);

        if (!grid) {
          // Both methods failed — record the failure
          const ppOcr = getPreprocessing(screenshot);
          const updated = addEvent(ppOcr, stage, SS.COMPLETED, {
            processing_status: "failed",
            processing_method: ocrMethod,
            extracted_title: null,
            extracted_total: null,
            grid_detection_confidence: 0,
            has_blocking_issues: true,
            issues: ["Failed to detect grid with both line_based and ocr_anchored methods"],
          });
          await this.storage.updateScreenshot(id, {
            processing_metadata: setPreprocessing(screenshot, updated),
          });
          break;
        }

        try {
          // Initialize Tesseract now — processImage needs it for title/total OCR
          const _initT0 = performance.now();
          if (!this.processing.isInitialized()) {
            await this.processing.initialize();
          }
          console.log(`[BENCH] OCR stage - Tesseract init check: ${(performance.now() - _initT0).toFixed(0)}ms`);
          const _procT0 = performance.now();
          ocrResult = await this.processing.processImage(blob, {
            imageType,
            gridCoordinates: grid,
            maxShift: options.max_shift ?? 5,
          });
          console.log(`[BENCH] OCR stage - processImage: ${(performance.now() - _procT0).toFixed(0)}ms`);
          console.log(`[BENCH] OCR stage - TOTAL: ${(performance.now() - _ocrT0).toFixed(0)}ms`);
        } catch (err) {
          const ppOcr = getPreprocessing(screenshot);
          const updated = addEvent(ppOcr, stage, SS.COMPLETED, {
            processing_status: "failed",
            processing_method: ocrMethod,
            extracted_title: null,
            extracted_total: null,
            grid_detection_confidence: 0,
            has_blocking_issues: true,
            issues: [err instanceof Error ? err.message : String(err)],
          });
          await this.storage.updateScreenshot(id, {
            processing_metadata: setPreprocessing(screenshot, updated),
          });
          break;
        }

        // Auto-skip daily total images if setting is enabled
        if (options.skip_daily_totals && ocrResult.title === "Daily Total") {
          const ppSkip = getPreprocessing(screenshot);
          const skippedEvent = addEvent(ppSkip, stage, SS.COMPLETED, {
            processing_status: "skipped",
            processing_method: ocrMethod,
            extracted_title: "Daily Total",
            extracted_total: null,
            is_daily_total: true,
          });
          await this.storage.updateScreenshot(id, {
            processing_metadata: setPreprocessing(screenshot, skippedEvent),
            extracted_title: "Daily Total",
            processing_status: "skipped",
            processed_at: new Date().toISOString(),
          } as Partial<Screenshot>);
          break;
        }

        const ppOcr = getPreprocessing(screenshot);
        const updated = addEvent(ppOcr, stage, SS.COMPLETED, {
          processing_status: ocrResult.gridDetectionFailed ? "failed" : "completed",
          processing_method: ocrMethod,
          extracted_title: ocrResult.title,
          extracted_total: ocrResult.total,
          grid_coordinates: ocrResult.gridCoordinates ?? null,
          extracted_hourly_data: ocrResult.hourlyData ?? null,
          grid_detection_confidence: ocrResult.gridDetectionFailed ? 0 : 1,
          has_blocking_issues: ocrResult.gridDetectionFailed ?? false,
          issues: ocrResult.gridDetectionError ? [ocrResult.gridDetectionError] : [],
        });

        // Save all extracted data to the screenshot record so the annotation
        // queue can read grid coordinates, hourly data, title, and total.
        const gridCoords = ocrResult.gridCoordinates as { upper_left: { x: number; y: number }; lower_right: { x: number; y: number } } | undefined;
        await this.storage.updateScreenshot(id, {
          processing_metadata: setPreprocessing(screenshot, updated),
          extracted_title: ocrResult.title,
          extracted_total: ocrResult.total,
          extracted_hourly_data: ocrResult.hourlyData as Record<string, number> | null,
          grid_upper_left_x: gridCoords?.upper_left?.x ?? null,
          grid_upper_left_y: gridCoords?.upper_left?.y ?? null,
          grid_lower_right_x: gridCoords?.lower_right?.x ?? null,
          grid_lower_right_y: gridCoords?.lower_right?.y ?? null,
          alignment_score: ocrResult.alignmentScore ?? null,
          processing_status: ocrResult.gridDetectionFailed ? "failed" : "completed",
          processed_at: new Date().toISOString(),
        } as Partial<Screenshot>);
        break;
      }
    }
  }

  async resetStage(stage: PreprocessingStage, groupId: string): Promise<{ message: string; count?: number }> {
    const screenshots = await this.storage.getAllScreenshots({ group_id: groupId });
    const downstreamStages = this.downstreamFrom(stage);
    let count = 0;

    for (const s of screenshots) {
      const pp = getPreprocessing(s);
      let changed = false;
      const newStageStatus = { ...pp.stage_status };
      const newCurrentEvents = { ...pp.current_events };
      for (const ds of downstreamStages) {
        if (newStageStatus[ds] && newStageStatus[ds] !== SS.PENDING) {
          newStageStatus[ds] = SS.PENDING;
          delete newCurrentEvents[ds];
          changed = true;
        }
      }
      if (changed) {
        const updatedPp: PreprocessingMeta = {
          ...pp,
          stage_status: newStageStatus,
          current_events: newCurrentEvents,
        };
        await this.storage.updateScreenshot(s.id as number, {
          processing_metadata: setPreprocessing(s, updatedPp),
        });
        count++;
      }
    }

    return { message: `Reset ${stage.replace(/_/g, " ")} for ${count} screenshot(s)`, count };
  }

  async skipStage(stage: PreprocessingStage, groupId: string, screenshotIds?: number[], unskip?: boolean): Promise<{ message: string; count?: number }> {
    const screenshots = await this.storage.getAllScreenshots({ group_id: groupId });
    const targets = screenshotIds ? screenshots.filter(s => screenshotIds.includes(s.id as number)) : screenshots;
    let count = 0;

    for (const s of targets) {
      const pp = getPreprocessing(s);
      const current = pp.stage_status[stage] ?? SS.PENDING;
      const newStageStatus = { ...pp.stage_status };

      if (unskip) {
        if (current !== SS.SKIPPED) continue;
        newStageStatus[stage] = SS.PENDING;
      } else {
        if (!(current === SS.PENDING || current === SS.INVALIDATED || current === SS.FAILED || current === SS.CANCELLED)) continue;
        newStageStatus[stage] = SS.SKIPPED;
      }

      const updatedPp: PreprocessingMeta = { ...pp, stage_status: newStageStatus };
      await this.storage.updateScreenshot(s.id as number, {
        processing_metadata: setPreprocessing(s, updatedPp),
      });
      count++;
    }

    const action = unskip ? "Unskipped" : "Skipped";
    return { message: `${action} ${stage.replace(/_/g, " ")} for ${count} screenshot(s)`, count };
  }

  async invalidateFromStage(screenshotId: number, stage: string): Promise<void> {
    const screenshot = await this.storage.getScreenshot(screenshotId);
    if (!screenshot) return;

    const downstream = this.downstreamFrom(stage as PreprocessingStage);
    if (downstream.length === 0) return;
    const pp = getPreprocessing(screenshot);
    const newStageStatus = { ...pp.stage_status };

    for (const ds of downstream) {
      if (newStageStatus[ds] && newStageStatus[ds] !== SS.PENDING) {
        newStageStatus[ds] = SS.INVALIDATED;
      }
    }

    await this.storage.updateScreenshot(screenshotId, {
      processing_metadata: setPreprocessing(screenshot, { ...pp, stage_status: newStageStatus }),
    });
  }

  async getEventLog(screenshotId: number): Promise<PreprocessingEventLog> {
    const screenshot = await this.storage.getScreenshot(screenshotId);
    if (!screenshot) return { screenshot_id: screenshotId, base_file_path: "", events: [], stage_status: {}, current_events: {} };

    const pp = getPreprocessing(screenshot);
    return {
      screenshot_id: screenshotId,
      base_file_path: `wasm://screenshot/${screenshotId}`,
      events: normalizeEvents(pp.events),
      stage_status: pp.stage_status,
      current_events: pp.current_events,
    };
  }

  async getScreenshot(screenshotId: number): Promise<Screenshot | null> {
    return this.storage.getScreenshot(screenshotId);
  }

  async uploadBrowser(_formData: FormData): Promise<BrowserUploadResponse> {
    // In WASM mode, uploads go through the WASMScreenshotService
    // This is a compatibility shim — the preprocessing upload tab
    // calls this but in WASM mode we handle uploads differently
    throw new Error("Browser upload not supported in WASM mode — use drag-and-drop on the home page");
  }

  async getOriginalImageUrl(screenshotId: number): Promise<string> {
    // Prefer the preserved original (saved before cropping), fall back to current
    const originalBlob = await this.storage.getStageBlob(screenshotId, "original");
    const blob = originalBlob ?? await this.storage.getImageBlob(screenshotId);
    if (!blob) throw new Error(`No image blob for screenshot ${screenshotId}`);
    return URL.createObjectURL(blob);
  }

  async applyManualCrop(
    screenshotId: number,
    crop: { left: number; top: number; right: number; bottom: number },
  ): Promise<void> {
    // For manual crop, use the original image (not a previously cropped one)
    const originalBlob = await this.storage.getStageBlob(screenshotId, "original");
    const blob = originalBlob ?? await this.storage.getImageBlob(screenshotId);
    if (!blob) throw new Error("No image blob for manual crop");

    // Preserve original if not already saved
    if (!originalBlob) {
      await this.storage.saveStageBlob(screenshotId, "original", blob);
    }

    const bitmap = await createImageBitmap(blob);
    const origWidth = bitmap.width;
    const origHeight = bitmap.height;
    // crop.left/top/right/bottom are absolute pixel coordinates (matching server contract)
    const cropWidth = crop.right - crop.left;
    const cropHeight = crop.bottom - crop.top;

    if (cropWidth <= 0 || cropHeight <= 0) {
      bitmap.close();
      throw new Error(`Invalid crop dimensions: ${cropWidth}x${cropHeight}`);
    }

    const canvas = new OffscreenCanvas(cropWidth, cropHeight);
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      bitmap.close();
      throw new Error(`Failed to get 2D context for ${cropWidth}x${cropHeight} OffscreenCanvas`);
    }
    ctx.drawImage(bitmap, crop.left, crop.top, cropWidth, cropHeight, 0, 0, cropWidth, cropHeight);
    bitmap.close();

    const croppedBlob = await canvas.convertToBlob({ type: "image/png" });
    await this.storage.saveImageBlob(screenshotId, croppedBlob);
    await this.storage.saveStageBlob(screenshotId, "cropping", croppedBlob);

    // Update cropping event and migrate grid coordinates in a single write
    const screenshot = await this.storage.getScreenshot(screenshotId);
    if (screenshot) {
      // Migrate grid coordinates from original image space to cropped image space
      const gridUpdate: Record<string, number | null> = {};
      if (screenshot.grid_upper_left_x != null && screenshot.grid_lower_right_x != null) {
        const newULX = (screenshot.grid_upper_left_x ?? 0) - crop.left;
        const newULY = (screenshot.grid_upper_left_y ?? 0) - crop.top;
        const newLRX = (screenshot.grid_lower_right_x ?? 0) - crop.left;
        const newLRY = (screenshot.grid_lower_right_y ?? 0) - crop.top;

        // Check if grid is still within the cropped region
        if (newLRX > 0 && newLRY > 0 && newULX < cropWidth && newULY < cropHeight) {
          gridUpdate.grid_upper_left_x = Math.max(0, newULX);
          gridUpdate.grid_upper_left_y = Math.max(0, newULY);
          gridUpdate.grid_lower_right_x = Math.min(cropWidth, newLRX);
          gridUpdate.grid_lower_right_y = Math.min(cropHeight, newLRY);
        } else {
          // Grid falls entirely outside cropped region — reset
          gridUpdate.grid_upper_left_x = null;
          gridUpdate.grid_upper_left_y = null;
          gridUpdate.grid_lower_right_x = null;
          gridUpdate.grid_lower_right_y = null;
        }
      }

      const pp = getPreprocessing(screenshot);
      const updated = addEvent(pp, "cropping", SS.COMPLETED, {
        was_cropped: true,
        was_patched: false,
        manual: true,
        crop_region: crop,
        original_dimensions: [origWidth, origHeight],
        cropped_dimensions: [cropWidth, cropHeight],
      });
      await this.storage.updateScreenshot(screenshotId, {
        processing_metadata: setPreprocessing(screenshot, updated),
        ...gridUpdate,
      });
    }
  }

  async getPHIRegions(screenshotId: number): Promise<PHIRegionsResponse> {
    if (!this.enablePhi) return { regions: [], source: null, event_id: null };
    const screenshot = await this.storage.getScreenshot(screenshotId);
    if (!screenshot) return { regions: [], source: null, event_id: null };

    const pp = getPreprocessing(screenshot);
    const detectionEventId = pp.current_events.phi_detection;
    const detectionEvent = pp.events.find((e) => e.event_id === detectionEventId);
    return {
      regions: (detectionEvent?.result?.phi_entities ?? []) as PHIRegionRect[],
      source: "wasm",
      event_id: detectionEventId ?? null,
    };
  }

  async savePHIRegions(screenshotId: number, body: { regions: PHIRegionRect[]; preset: string }): Promise<void> {
    if (!this.enablePhi) {
      throw new Error("PHI editing is disabled in this mode");
    }
    const screenshot = await this.storage.getScreenshot(screenshotId);
    if (!screenshot) throw new Error(`Screenshot ${screenshotId} not found`);

    const pp = getPreprocessing(screenshot);
    const updated = addEvent(pp, "phi_detection", SS.COMPLETED, {
      phi_detected: body.regions?.length > 0,
      regions_count: body.regions?.length ?? 0,
      phi_entities: body.regions ?? [],
      reviewed: true,
    });

    await this.storage.updateScreenshot(screenshotId, {
      processing_metadata: setPreprocessing(screenshot, updated),
    });
  }

  async applyRedaction(screenshotId: number, body: { regions: PHIRegionRect[]; redaction_method: string }): Promise<void> {
    if (!this.enablePhi) {
      throw new Error("PHI redaction is disabled in this mode");
    }
    const blob = await this.storage.getImageBlob(screenshotId);
    if (!blob) throw new Error("No image blob for redaction");

    const regions = (body.regions ?? []) as PHIRegion[];
    const method = (body.redaction_method ?? "redbox") as "redbox" | "blackbox" | "pixelate";

    const { redactImage } = await this.loadPhiRedactModule();
    const redactedBlob = await redactImage(blob, regions, method);
    await this.storage.saveImageBlob(screenshotId, redactedBlob);
    await this.storage.saveStageBlob(screenshotId, "phi_redaction", redactedBlob);

    const screenshot = await this.storage.getScreenshot(screenshotId);
    if (screenshot) {
      const pp = getPreprocessing(screenshot);
      const updated = addEvent(pp, "phi_redaction", SS.COMPLETED, {
        phi_detected: regions.length > 0,
        redacted: true,
        redaction_method: method,
        regions_redacted: regions.length,
      });
      await this.storage.updateScreenshot(screenshotId, {
        processing_metadata: setPreprocessing(screenshot, updated),
      });
    }
  }

  async getDetails(screenshotId: number): Promise<PreprocessingDetailsResponse | null> {
    const screenshot = await this.storage.getScreenshot(screenshotId);
    if (!screenshot) return null;
    const pp = getPreprocessing(screenshot);
    // Build a PreprocessingDetailsResponse from the stored metadata
    const devEvent = pp.events.find((e) => e.event_id === pp.current_events.device_detection);
    const cropEvent = pp.events.find((e) => e.event_id === pp.current_events.cropping);
    const phiDetEvent = pp.events.find((e) => e.event_id === pp.current_events.phi_detection);
    const phiRedEvent = pp.events.find((e) => e.event_id === pp.current_events.phi_redaction);
    return {
      has_preprocessing: Object.keys(pp.stage_status).length > 0,
      device_detection: devEvent?.result ?? null,
      cropping: cropEvent?.result ?? null,
      phi_detection: phiDetEvent?.result ?? null,
      phi_redaction: phiRedEvent?.result ?? null,
      stage_status: pp.stage_status,
      current_events: pp.current_events,
    } as PreprocessingDetailsResponse;
  }

  // Track blob URLs created from stage blobs so callers can revoke them
  private stageBlobUrls = new Map<string, string>();

  async getStageImageUrl(screenshotId: number, stage: string): Promise<string> {
    // Only image-modifying stages (cropping, phi_redaction) save snapshots
    if (stage === "cropping" || stage === "phi_redaction") {
      const stageBlob = await this.storage.getStageBlob(screenshotId, stage);
      if (stageBlob) {
        const key = `${screenshotId}:${stage}`;
        // Don't revoke the previous URL — another component may still be displaying it.
        // Just overwrite the map entry. The old URL will be cleaned up when the map
        // is bounded (see size cap below) or when cleanup() is called.
        const url = URL.createObjectURL(stageBlob);
        this.stageBlobUrls.set(key, url);
        // Bound map size — just drop old entries without revoking, since
        // components may still reference the URLs. The useScreenshotImageUrl
        // hook revokes blob URLs on unmount/re-fetch via its cleanup function.
        if (this.stageBlobUrls.size > 100) {
          const keysToDelete = [...this.stageBlobUrls.keys()].slice(0, 50);
          for (const k of keysToDelete) {
            this.stageBlobUrls.delete(k);
          }
        }
        return url;
      }
    }
    // Fall back to current image
    return this.getImageUrl(screenshotId);
  }

  async getImageUrl(screenshotId: number): Promise<string> {
    const url = await cachedCreateObjectURL(screenshotId);
    if (!url) throw new Error(`No image blob for screenshot ${screenshotId}`);
    return url;
  }
}
