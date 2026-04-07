import type {
  Screenshot,
  Consensus,
  GridCoordinates,
  HourlyData,
  QueueStats,
  ProcessingIssue,
  ProcessingProgress,
  ScreenshotListResponse,
  ScreenshotListParams,
} from "@/core";

// UI-specific annotation type that includes grid_coords for easier manipulation
export interface UIAnnotation {
  grid_coords?: GridCoordinates;
  hourly_values?: HourlyData;
  notes?: string;
}

// ============================================================================
// SCREENSHOT SLICE
// ============================================================================
export interface ScreenshotSlice {
  currentScreenshot: Screenshot | null;
  isLoading: boolean;
  noScreenshots: boolean;
  error: string | null;
  queueStats: QueueStats | null;

  loadNextScreenshot: () => Promise<void>;
  loadScreenshot: (id: number) => Promise<void>;
  loadQueueStats: () => Promise<void>;
  skipScreenshot: (reason?: string) => Promise<void>;
}

// ============================================================================
// ANNOTATION SLICE
// ============================================================================
export interface AnnotationSlice {
  currentAnnotation: UIAnnotation | null;
  processingIssues: ProcessingIssue[];
  isAutoProcessed: boolean;
  consensus: Consensus | null;

  setGridCoordinates: (coords: GridCoordinates) => void;
  setHourlyValues: (data: HourlyData) => void;
  updateHourValue: (hour: number, value: number) => void;
  setExtractedTitle: (title: string) => void;
  saveAnnotation: (notes?: string) => Promise<void>;
  loadConsensus: (screenshotId: number) => Promise<void>;
}

// ============================================================================
// PROCESSING SLICE
// ============================================================================
export interface ProcessingSlice {
  processingProgress: ProcessingProgress | null;
  isTesseractInitialized: boolean;
  isInitializingTesseract: boolean;

  reprocessWithGrid: (coords: GridCoordinates) => Promise<void>;
  reprocessWithLineBased: () => Promise<void>;
  reprocessWithOcrAnchored: () => Promise<void>;
  recalculateOcrTotal: () => Promise<string | null>;
  setProcessingProgress: (progress: ProcessingProgress | null) => void;
  clearProcessingProgress: () => void;
  setTesseractInitialized: (initialized: boolean) => void;
  setInitializingTesseract: (initializing: boolean) => void;
}

// ============================================================================
// NAVIGATION SLICE
// ============================================================================

/**
 * Verification filter type for user-specific filtering.
 * - 'all': Show all screenshots
 * - 'verified_by_me': Only show screenshots verified by current user
 * - 'not_verified_by_me': Only show screenshots NOT verified by current user
 * - 'verified_by_others': Only show screenshots verified by others but NOT by current user
 * - 'totals_mismatch': Only show screenshots needing attention — bar/OCR mismatch or missing title (server-side filter)
 */
export type VerificationFilterType =
  | "all"
  | "verified_by_me"
  | "not_verified_by_me"
  | "verified_by_others"
  | "totals_mismatch";

export interface NavigationSlice {
  currentIndex: number;
  totalInFilter: number;
  hasNext: boolean;
  hasPrev: boolean;
  screenshotList: ScreenshotListResponse | null;
  verificationFilter: VerificationFilterType;

  navigateNext: () => Promise<void>;
  navigatePrev: () => Promise<void>;
  loadScreenshotList: (params?: ScreenshotListParams) => Promise<void>;
  loadMoreScreenshots: () => Promise<void>;
  setVerificationFilter: (value: VerificationFilterType) => void;
  verifyCurrentScreenshot: () => Promise<void>;
  unverifyCurrentScreenshot: () => Promise<void>;
}

// ============================================================================
// SHARED SLICE
// ============================================================================
export interface SharedSlice {
  reset: () => void;
  clearError: () => void;
}

// ============================================================================
// COMBINED STATE
// ============================================================================
export type AnnotationState = ScreenshotSlice &
  AnnotationSlice &
  ProcessingSlice &
  NavigationSlice &
  SharedSlice;

// Initial annotation value
export const initialAnnotation: UIAnnotation = {
  grid_coords: {
    upper_left: { x: 0, y: 0 },
    lower_right: { x: 0, y: 0 },
  },
  hourly_values: {},
  notes: "",
};
