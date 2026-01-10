import type { Screenshot, NavigationParams, GridCoordinates, ProcessingIssue } from "@/core";
import type { VerificationFilterType, UIAnnotation } from "./types";
import { initialAnnotation } from "./types";
import { useAuthStore } from "../authStore";

/** Any object with the 4 flat grid coordinate fields. */
type HasGridFields = {
  grid_upper_left_x?: number | null;
  grid_upper_left_y?: number | null;
  grid_lower_right_x?: number | null;
  grid_lower_right_y?: number | null;
};

/**
 * Extract grid coordinates from flat fields into a GridCoordinates object.
 * Returns undefined if upper_left_x or lower_right_x are null/undefined.
 */
export function extractGridCoords(obj: HasGridFields): GridCoordinates | undefined {
  if (obj.grid_upper_left_x == null || obj.grid_lower_right_x == null) {
    return undefined;
  }
  return {
    upper_left: {
      x: obj.grid_upper_left_x,
      y: obj.grid_upper_left_y ?? 0,
    },
    lower_right: {
      x: obj.grid_lower_right_x,
      y: obj.grid_lower_right_y ?? 0,
    },
  };
}

/**
 * Check if current user has verified a screenshot.
 * Both userId and verified_by_user_ids are typed as numbers.
 */
export const isVerifiedByCurrentUser = (
  screenshot: Screenshot | null,
): boolean => {
  if (!screenshot?.verified_by_user_ids) return false;
  const userId = useAuthStore.getState().userId;
  if (userId === null) return false;
  return screenshot.verified_by_user_ids.includes(userId);
};

/**
 * Extract a user-friendly error message from an unknown caught error.
 * Handles axios-style errors (response.data.detail), standard Error objects, and fallbacks.
 */
type AxiosLikeError = Error & { response?: { data?: { detail?: string }; status?: number } };

export function extractErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error) {
    const axiosLike = error as AxiosLikeError;
    return axiosLike.response?.data?.detail || error.message || fallback;
  }
  if (typeof error === "string") return error;
  return fallback;
}

/** Extract HTTP status code from an axios-like error, or undefined if unavailable. */
export function extractErrorStatus(error: unknown): number | undefined {
  if (error instanceof Error) {
    return (error as AxiosLikeError).response?.status;
  }
  return undefined;
}

/**
 * Convert a VerificationFilterType to API query parameters.
 * Centralizes filter-to-API conversion to avoid duplication.
 */
export function filterToApiParams(
  filter: VerificationFilterType,
): Pick<NavigationParams, "verified_by_me" | "verified_by_others" | "totals_mismatch"> {
  switch (filter) {
    case "verified_by_me":
      return { verified_by_me: true };
    case "not_verified_by_me":
      return { verified_by_me: false };
    case "verified_by_others":
      return { verified_by_others: true };
    case "totals_mismatch":
      return { totals_mismatch: true };
    case "all":
    default:
      return {};
  }
}

/** Build prefilled annotation, processing issues, and auto-processed flag from screenshot data. */
export function buildAnnotationFromScreenshot(screenshot: Screenshot): {
  annotation: UIAnnotation;
  processingIssues: ProcessingIssue[];
  isAutoProcessed: boolean;
} {
  const annotation: UIAnnotation = { ...initialAnnotation };
  let isAutoProcessed = false;

  if (screenshot.extracted_hourly_data) {
    annotation.hourly_values = screenshot.extracted_hourly_data;
    isAutoProcessed = true;
  }

  const gridCoords = extractGridCoords(screenshot);
  if (gridCoords) {
    annotation.grid_coords = gridCoords;
  }

  const processingIssues: ProcessingIssue[] =
    screenshot.processing_issues && screenshot.processing_issues.length > 0
      ? screenshot.processing_issues
      : [];

  return { annotation, processingIssues, isAutoProcessed };
}

