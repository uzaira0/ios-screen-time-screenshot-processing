import {
  PREPROCESSING_STAGES,
  type PreprocessingStages,
} from "@/core/generated/constants";

export const TOKENS = {
  SCREENSHOT_SERVICE: "IScreenshotService",
  ANNOTATION_SERVICE: "IAnnotationService",
  CONSENSUS_SERVICE: "IConsensusService",
  STORAGE_SERVICE: "IStorageService",
  PROCESSING_SERVICE: "IProcessingService",
  PREPROCESSING_PIPELINE_SERVICE: "IPreprocessingService",
  FEATURES: "Features",
} as const;

export type ServiceToken = (typeof TOKENS)[keyof typeof TOKENS];

/**
 * Declares which high-level capabilities are available in the current mode.
 * Components query this via useFeatures() instead of checking config.isLocalMode.
 */
export interface AppFeatures {
  /** Server-side study groups with processing status breakdown */
  groups: boolean;
  /** Cross-rater consensus comparison (requires server) */
  consensusComparison: boolean;
  /** Admin user management (requires server) */
  admin: boolean;
  /** Server-side preprocessing pipeline */
  preprocessing: boolean;
  /**
   * PHI detection + redaction stages are exposed.
   * WASM (browser-only) builds disable this — the pipeline collapses to
   * device detection → cropping → OCR. Server and Tauri keep it on.
   */
  phiDetection: boolean;
}

/**
 * The PHI stages — gated by `AppFeatures.phiDetection`.
 * Single source of truth so service guards, UI gating, prereq computation,
 * and deep-link validation all agree on which stages disappear.
 */
export const PHI_STAGES: readonly PreprocessingStages[] = [
  "phi_detection",
  "phi_redaction",
];

/**
 * Returns the ordered list of preprocessing stages active in the given mode.
 * Stages absent from this list are not run, not shown in the wizard, and
 * are skipped when computing prerequisites for downstream stages.
 */
export function getActiveStages(
  features: AppFeatures,
): readonly PreprocessingStages[] {
  if (features.phiDetection) return PREPROCESSING_STAGES;
  return PREPROCESSING_STAGES.filter((s) => !PHI_STAGES.includes(s));
}
