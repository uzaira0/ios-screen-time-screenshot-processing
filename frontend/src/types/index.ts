/**
 * Type exports for the iOS Screen Time Screenshot Processing frontend.
 *
 * IMPORTANT: These types are derived from the backend Pydantic schemas via OpenAPI.
 * The source of truth is the backend - run `bun run generate:api-types` to regenerate.
 */

import type { components } from "./api-schema";

// =============================================================================
// API Schema Types - Direct re-exports from generated schema
// =============================================================================

// Core models
export type Point = components["schemas"]["Point"];
export type ProcessingIssue = components["schemas"]["ProcessingIssue"];
export type ProcessingIssueRead = components["schemas"]["ProcessingIssueRead"];

// User types
export type User = components["schemas"]["UserRead"];
export type UserLogin = components["schemas"]["UserLoginRequest"];
export type UserStatsRead = components["schemas"]["UserStatsRead"];
export type UserUpdateResponse = components["schemas"]["UserUpdateResponse"];

// Define types not exposed via OpenAPI but needed in frontend
export interface UserCreate {
  username: string;
  role?: "annotator" | "admin";
}
export interface UserUpdate {
  email?: string | null;
  role?: "annotator" | "admin" | null;
  is_active?: boolean | null;
}
export interface Token {
  access_token: string;
  token_type: string;
}

// Screenshot types
export type Screenshot = components["schemas"]["ScreenshotRead"];
export type ScreenshotDetail = components["schemas"]["ScreenshotDetail"];
export type ScreenshotUpdate = components["schemas"]["ScreenshotUpdate"];
export type ScreenshotUploadRequest =
  components["schemas"]["ScreenshotUploadRequest"];
export type ScreenshotUploadResponse =
  components["schemas"]["ScreenshotUploadResponse"];
// Paginated screenshot list response
export type ScreenshotListResponse =
  components["schemas"]["PaginatedResponse_ScreenshotRead_"];

// Group types
export type Group = components["schemas"]["GroupRead"];

// Annotation types
export type Annotation = components["schemas"]["AnnotationRead"];
export type AnnotationCreate = components["schemas"]["AnnotationCreate"];
export type AnnotationUpdate = components["schemas"]["AnnotationUpdate"];

// AnnotationUpsert is the same as AnnotationCreate (used for create-or-update endpoint)
export type AnnotationUpsert = AnnotationCreate;

// Consensus types - ConsensusResultRead not exposed via API, use ConsensusAnalysis instead
export type ConsensusResult = components["schemas"]["ConsensusAnalysis"];
export type DisagreementDetail = components["schemas"]["DisagreementDetail"];
export type ConsensusAnalysis = components["schemas"]["ConsensusAnalysis"];

// Processing types
export type ProcessingResult =
  components["schemas"]["ProcessingResultResponse"];
export type ReprocessRequest = components["schemas"]["ReprocessRequest"];

// Preprocessing types
export type PreprocessRequest = components["schemas"]["PreprocessRequest"];
export type BatchPreprocessRequest =
  components["schemas"]["BatchPreprocessRequest"];
export type BatchPreprocessResponse =
  components["schemas"]["BatchPreprocessResponse"];
export type PreprocessingDetailsResponse =
  components["schemas"]["PreprocessingDetailsResponse"];

// PHI types
export type PHIRegionsResponse = components["schemas"]["PHIRegionsResponse"];
export type BrowserUploadResponse =
  components["schemas"]["BrowserUploadResponse"];
export type PHIRegionRect = components["schemas"]["PHIRegionRect"];

// Composable pipeline types
export type StagePreprocessRequest =
  components["schemas"]["StagePreprocessRequest"];
export type StagePreprocessResponse =
  components["schemas"]["StagePreprocessResponse"];
export type PHIDetectionStageRequest =
  components["schemas"]["PHIDetectionStageRequest"];
export type PHIRedactionStageRequest =
  components["schemas"]["PHIRedactionStageRequest"];
export type InvalidateFromStageRequest =
  components["schemas"]["InvalidateFromStageRequest"];
export type PreprocessingEvent =
  components["schemas"]["PreprocessingEvent"];
export type PreprocessingEventLog =
  components["schemas"]["PreprocessingEventLog"];
export type PreprocessingStageSummary =
  components["schemas"]["PreprocessingStageSummary"];
export type PreprocessingSummary =
  components["schemas"]["PreprocessingSummary"];

// Navigation types
export type NavigationResponse = components["schemas"]["NavigationResponse"];
export type NextScreenshotResponse =
  components["schemas"]["NextScreenshotResponse"];

// Stats types
export type StatsResponse = components["schemas"]["StatsResponse"];

// Admin types
export type DeleteGroupResponse = components["schemas"]["DeleteGroupResponse"];
export type RecalculateOcrResponse =
  components["schemas"]["RecalculateOcrResponse"];
export type RecalculateOcrTotalResponse =
  components["schemas"]["RecalculateOcrTotalResponse"];

// Health/Root types
export type HealthCheckResponse = components["schemas"]["HealthCheckResponse"];
export type RootResponse = components["schemas"]["RootResponse"];

// Validation error type
export type ValidationError = components["schemas"]["ValidationError"];
export type HTTPValidationError = components["schemas"]["HTTPValidationError"];

// =============================================================================
// Enum-like Types - Extracted from schema for convenience
// =============================================================================

export type { ImageTypes as ImageType } from "@/core/generated/constants";
export type ProcessingStatus = components["schemas"]["ProcessingStatus"];
export type AnnotationStatus = components["schemas"]["AnnotationStatus"];
export type ProcessingMethod = components["schemas"]["ProcessingMethod"];
export type IssueSeverity = components["schemas"]["IssueSeverity"];

// =============================================================================
// Derived Types - Aliases for convenience
// =============================================================================

/** Hourly values: hour (0-23) -> minutes (0-60) */
export type HourlyValues = Record<string, number>;

/** Queue statistics (alias for StatsResponse) */
export type QueueStats = StatsResponse;

// =============================================================================
// UI-Only Types (not in backend)
// =============================================================================

/** API error response structure */
export interface ApiError {
  detail: string;
}

/** Processing progress for long-running operations (WASM mode) */
export interface ProcessingProgress {
  stage: string;
  progress: number;
  message?: string;
}

/** Consensus data structure for UI display */
export interface Consensus {
  screenshot_id: number;
  total_annotations: number;
  consensus_data: HourlyValues;
  disagreements: {
    hour: number;
    values: {
      annotator_id: number;
      annotator_username: string;
      value: number;
    }[];
    consensus_value: number;
  }[];
  agreement_percentage: number;
}

/** Login credentials */
export interface LoginCredentials {
  username: string;
}

/** Auth response */
export interface AuthResponse {
  access_token: string;
  token_type: string;
}

/** Request params for screenshot list */
export interface ScreenshotListParams {
  page?: number;
  page_size?: number;
  group_id?: string;
  processing_status?: ProcessingStatus;
  annotation_status?: AnnotationStatus;
  /** Filter by current user's verification (True=verified by me, False=not verified by me) */
  verified_by_me?: boolean;
  /** Filter for screenshots verified by others but not current user */
  verified_by_others?: boolean;
  /** Filter for screenshots where bar total differs from OCR total */
  totals_mismatch?: boolean;
  search?: string;
  sort_by?: "id" | "uploaded_at" | "processing_status";
  sort_order?: "asc" | "desc";
}

/** Request params for screenshot navigation */
export interface NavigationParams {
  group_id?: string;
  processing_status?: ProcessingStatus;
  /** Filter by current user's verification (True=verified by me, False=not verified by me) */
  verified_by_me?: boolean;
  /** Filter for screenshots verified by others but not current user */
  verified_by_others?: boolean;
  /** Filter for screenshots where bar total differs from OCR total */
  totals_mismatch?: boolean;
  direction?: "current" | "next" | "prev";
}

// =============================================================================
// Legacy Aliases (for backward compatibility)
// =============================================================================

/**
 * @deprecated Use Point directly. Grid coordinates use Point type.
 * This provides a familiar interface for code expecting upper_left/lower_right.
 */
export interface GridCoordinates {
  upper_left: Point;
  lower_right: Point;
}

/** @deprecated Use HourlyValues instead */
export type HourlyData = HourlyValues;

// =============================================================================
// Utility Functions
// =============================================================================

/**
 * Convert screenshot's flat grid fields to GridCoordinates object.
 */
export function screenshotToGridCoordinates(
  screenshot: Screenshot,
): GridCoordinates | undefined {
  if (
    screenshot.grid_upper_left_x == null ||
    screenshot.grid_upper_left_y == null ||
    screenshot.grid_lower_right_x == null ||
    screenshot.grid_lower_right_y == null
  ) {
    return undefined;
  }
  return {
    upper_left: {
      x: screenshot.grid_upper_left_x,
      y: screenshot.grid_upper_left_y,
    },
    lower_right: {
      x: screenshot.grid_lower_right_x,
      y: screenshot.grid_lower_right_y,
    },
  };
}

/**
 * Convert annotation's grid fields to GridCoordinates object.
 */
export function annotationToGridCoordinates(
  annotation: Annotation,
): GridCoordinates | undefined {
  if (!annotation.grid_upper_left || !annotation.grid_lower_right) {
    return undefined;
  }
  return {
    upper_left: annotation.grid_upper_left,
    lower_right: annotation.grid_lower_right,
  };
}

/**
 * Convert GridCoordinates to flat fields for screenshot-style API requests.
 */
export function gridCoordinatesToFlat(coords: GridCoordinates): {
  grid_upper_left_x: number;
  grid_upper_left_y: number;
  grid_lower_right_x: number;
  grid_lower_right_y: number;
} {
  return {
    grid_upper_left_x: coords.upper_left.x,
    grid_upper_left_y: coords.upper_left.y,
    grid_lower_right_x: coords.lower_right.x,
    grid_lower_right_y: coords.lower_right.y,
  };
}

/**
 * Convert GridCoordinates to Point-based fields for annotation API requests.
 */
export function gridCoordinatesToPoints(coords: GridCoordinates): {
  grid_upper_left: Point;
  grid_lower_right: Point;
} {
  return {
    grid_upper_left: coords.upper_left,
    grid_lower_right: coords.lower_right,
  };
}

// =============================================================================
// Constants
// =============================================================================

export const IMAGE_TYPES = {
  BATTERY: "battery" as const,
  SCREEN_TIME: "screen_time" as const,
};

export const PROCESSING_STATUSES = {
  PENDING: "pending" as const,
  PROCESSING: "processing" as const,
  COMPLETED: "completed" as const,
  FAILED: "failed" as const,
  SKIPPED: "skipped" as const,
};

export const ANNOTATION_STATUSES = {
  PENDING: "pending" as const,
  ANNOTATED: "annotated" as const,
  VERIFIED: "verified" as const,
  SKIPPED: "skipped" as const,
};

export const PROCESSING_METHODS = {
  OCR_ANCHORED: "ocr_anchored" as const,
  LINE_BASED: "line_based" as const,
  MANUAL: "manual" as const,
};
