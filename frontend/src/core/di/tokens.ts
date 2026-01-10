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
}
