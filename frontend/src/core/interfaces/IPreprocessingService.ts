import type {
  Group,
  Screenshot,
  PreprocessingSummary,
  PreprocessingEventLog,
  PreprocessingDetailsResponse,
  BrowserUploadResponse,
  PHIRegionsResponse,
  PHIRegionRect,
} from "@/types";
import type { PreprocessingStages } from "@/core/generated/constants";

export type PreprocessingStage = PreprocessingStages;

/** A PHI region detected in an image, with bounding box and metadata. */
export interface PHIRegion {
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
  source: string;
  confidence: number;
  text: string;
}

export interface RunStageOptions {
  group_id?: string;
  screenshot_ids?: number[];
  phi_pipeline_preset?: string;
  phi_redaction_method?: string;
  phi_ocr_engine?: string;
  phi_ner_detector?: string;
  llm_endpoint?: string;
  llm_model?: string;
  llm_api_key?: string;
  ocr_method?: string;
  max_shift?: number;
  skip_daily_totals?: boolean;
  /** Called after each screenshot completes (WASM mode only). */
  onProgress?: (completed: number, total: number) => void;
  /** Signal to abort processing (WASM mode only). */
  abortSignal?: AbortSignal;
}

export interface RunStageResult {
  queued_count: number;
  message: string;
  screenshot_ids?: number[];
  task_ids?: string[];
}

export interface IPreprocessingService {
  getGroups(): Promise<Group[]>;
  getScreenshots(params: {
    group_id: string;
    page_size?: number;
    sort_by?: string;
    sort_order?: string;
  }): Promise<{ items: Screenshot[]; total: number }>;
  getSummary(groupId: string): Promise<PreprocessingSummary>;
  runStage(stage: PreprocessingStage, options: RunStageOptions): Promise<RunStageResult>;
  resetStage(stage: PreprocessingStage, groupId: string): Promise<{ message: string; count?: number }>;
  invalidateFromStage(screenshotId: number, stage: string): Promise<void>;
  getEventLog(screenshotId: number): Promise<PreprocessingEventLog>;
  getScreenshot(screenshotId: number): Promise<Screenshot | null>;
  uploadBrowser(formData: FormData): Promise<BrowserUploadResponse>;
  getOriginalImageUrl(screenshotId: number): Promise<string>;
  applyManualCrop(screenshotId: number, crop: { left: number; top: number; right: number; bottom: number }): Promise<void>;
  getPHIRegions(screenshotId: number): Promise<PHIRegionsResponse>;
  savePHIRegions(screenshotId: number, body: { regions: PHIRegionRect[]; preset: string }): Promise<void>;
  applyRedaction(screenshotId: number, body: { regions: PHIRegionRect[]; redaction_method: string }): Promise<void>;
  getDetails(screenshotId: number): Promise<PreprocessingDetailsResponse | null>;
  getStageImageUrl(screenshotId: number, stage: string): Promise<string>;
  /** Get the current image URL for a screenshot (latest processed version). */
  getImageUrl(screenshotId: number): Promise<string>;
  /** Force-stop any in-progress processing (terminates workers). No-op in server mode. */
  forceStop?(): void;
}
