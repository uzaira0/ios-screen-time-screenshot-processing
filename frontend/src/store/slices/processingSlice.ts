import type { StateCreator } from "zustand";
import type {
  IScreenshotService,
  GridCoordinates,
  ProcessingProgress,
  ProcessingIssue,
  Screenshot,
} from "@/core";
import type { AnnotationState, ProcessingSlice, UIAnnotation } from "./types";
import { isVerifiedByCurrentUser, extractGridCoords, extractErrorMessage } from "./helpers";
import { useSettingsStore } from "@/store/settingsStore";

/**
 * Error thrown when user tries to reprocess a verified screenshot.
 * The UI should catch this and show a user-friendly message.
 */
export class VerifiedScreenshotError extends Error {
  constructor() {
    super("Cannot reprocess: you have already verified this screenshot");
    this.name = "VerifiedScreenshotError";
  }
}

/**
 * Helper to update screenshot state from reprocess result.
 * Centralizes the duplicated state update logic.
 */
function createStateUpdateFromResult(
  state: AnnotationState,
  result: {
    extracted_hourly_data?: Record<string, number> | null;
    extracted_title?: string | null;
    extracted_total?: string | null;
    processing_status?: string;
    issues?: ProcessingIssue[];
    has_blocking_issues?: boolean;
    alignment_score?: number | null;
    processing_method?: string | null;
    grid_detection_confidence?: number | null;
    grid_upper_left_x?: number | null;
    grid_upper_left_y?: number | null;
    grid_lower_right_x?: number | null;
    grid_lower_right_y?: number | null;
  },
  gridCoords?: GridCoordinates,
): Partial<AnnotationState> {
  const newGridCoords: GridCoordinates | undefined =
    gridCoords || extractGridCoords(result);

  return {
    currentAnnotation: {
      ...state.currentAnnotation,
      hourly_values: result.extracted_hourly_data || {},
      grid_coords: newGridCoords || state.currentAnnotation?.grid_coords,
    } as UIAnnotation,
    currentScreenshot: state.currentScreenshot
      ? ({
          ...state.currentScreenshot,
          processing_status: result.processing_status,
          extracted_hourly_data: result.extracted_hourly_data,
          extracted_title: result.extracted_title,
          extracted_total: result.extracted_total,
          processing_issues: result.issues,
          has_blocking_issues: result.has_blocking_issues,
          alignment_score: result.alignment_score ?? null,
          processing_method: result.processing_method,
          grid_detection_confidence: result.grid_detection_confidence,
          grid_upper_left_x: newGridCoords?.upper_left.x ?? null,
          grid_upper_left_y: newGridCoords?.upper_left.y ?? null,
          grid_lower_right_x: newGridCoords?.lower_right.x ?? null,
          grid_lower_right_y: newGridCoords?.lower_right.y ?? null,
        } as Screenshot)
      : null,
    processingIssues: result.issues || [],
    isAutoProcessed: true,
  };
}

export const createProcessingSlice = (
  screenshotService: IScreenshotService,
): StateCreator<AnnotationState, [], [], ProcessingSlice> => (set, get) => ({
  // State
  processingProgress: null,
  isTesseractInitialized: false,
  isInitializingTesseract: false,

  // Actions
  reprocessWithGrid: async (coords: GridCoordinates) => {
    const { currentScreenshot } = get();
    if (!currentScreenshot) {
      throw new Error("No screenshot loaded");
    }

    // Throw error if user has already verified - UI should catch and show toast
    if (isVerifiedByCurrentUser(currentScreenshot)) {
      throw new VerifiedScreenshotError();
    }

    // Skip reprocessing if grid coordinates unchanged
    const hasExistingGrid =
      currentScreenshot.grid_upper_left_x !== null &&
      currentScreenshot.grid_lower_right_x !== null;
    const gridUnchanged =
      hasExistingGrid &&
      coords.upper_left.x === currentScreenshot.grid_upper_left_x &&
      coords.upper_left.y === currentScreenshot.grid_upper_left_y &&
      coords.lower_right.x === currentScreenshot.grid_lower_right_x &&
      coords.lower_right.y === currentScreenshot.grid_lower_right_y;

    if (gridUnchanged) {
      set({ isLoading: false, processingProgress: null });
      return;
    }

    set({ isLoading: true, error: null, processingProgress: null });
    try {
      // Grid adjustment does NOT use optimization - only button clicks do
      const result = await screenshotService.reprocess(
        currentScreenshot.id,
        coords,
        (progress) => {
          set({ processingProgress: progress });
        },
        0, // No optimization when manually adjusting grid
      );

      if (result.success && result.extracted_hourly_data) {
        // Preserve the existing OCR total — grid drag only changes bar values, not OCR
        const existingTotal = get().currentScreenshot?.extracted_total;
        set((state) => {
          const update = createStateUpdateFromResult(state, result, coords);
          if (existingTotal && update.currentScreenshot) {
            (update.currentScreenshot as Record<string, unknown>).extracted_total = existingTotal;
          }
          return update;
        });
      } else {
        set({ processingIssues: result.issues || [] });
      }
    } catch (error: unknown) {
      const message = extractErrorMessage(error, "Failed to reprocess screenshot");
      set({ error: message });
      throw error;
    } finally {
      set({ isLoading: false, processingProgress: null });
    }
  },

  reprocessWithLineBased: async () => {
    const { currentScreenshot } = get();
    if (!currentScreenshot) {
      throw new Error("No screenshot loaded");
    }

    // Throw error if user has already verified - UI should catch and show toast
    if (isVerifiedByCurrentUser(currentScreenshot)) {
      throw new VerifiedScreenshotError();
    }

    set({ isLoading: true, error: null, processingProgress: null });
    try {
      const maxShift = useSettingsStore.getState().maxShift;
      const result = await screenshotService.reprocessWithMethod(
        currentScreenshot.id,
        "line_based",
        (progress) => {
          set({ processingProgress: progress });
        },
        maxShift,
      );

      if (result.success && result.extracted_hourly_data) {
        set((state) => createStateUpdateFromResult(state, result));
      } else {
        set({ processingIssues: result.issues || [] });
      }
    } catch (error: unknown) {
      const message = extractErrorMessage(error, "Failed to reprocess with line-based detection");
      set({ error: message });
      throw error;
    } finally {
      set({ isLoading: false, processingProgress: null });
    }
  },

  reprocessWithOcrAnchored: async () => {
    const { currentScreenshot } = get();
    if (!currentScreenshot) {
      throw new Error("No screenshot loaded");
    }

    // Throw error if user has already verified - UI should catch and show toast
    if (isVerifiedByCurrentUser(currentScreenshot)) {
      throw new VerifiedScreenshotError();
    }

    set({ isLoading: true, error: null, processingProgress: null });
    try {
      const maxShift = useSettingsStore.getState().maxShift;
      const result = await screenshotService.reprocessWithMethod(
        currentScreenshot.id,
        "ocr_anchored",
        (progress) => {
          set({ processingProgress: progress });
        },
        maxShift,
      );

      if (result.success && result.extracted_hourly_data) {
        set((state) => createStateUpdateFromResult(state, result));
      } else {
        set({ processingIssues: result.issues || [] });
      }
    } catch (error: unknown) {
      const message = extractErrorMessage(error, "Failed to reprocess with OCR-anchored detection");
      set({ error: message });
      throw error;
    } finally {
      set({ isLoading: false, processingProgress: null });
    }
  },

  recalculateOcrTotal: async () => {
    const { currentScreenshot } = get();
    if (!currentScreenshot) return null;

    try {
      const newTotal = await screenshotService.recalculateOcr(
        currentScreenshot.id,
      );

      if (newTotal) {
        set({
          currentScreenshot: {
            ...currentScreenshot,
            extracted_total: newTotal,
          },
        });
      }

      return newTotal;
    } catch (error: unknown) {
      const message = extractErrorMessage(error, "Failed to recalculate OCR total");
      set({ error: message });
      throw error;
    }
  },

  setProcessingProgress: (progress: ProcessingProgress | null) => {
    set({ processingProgress: progress });
  },

  clearProcessingProgress: () => {
    set({ processingProgress: null });
  },

  setTesseractInitialized: (initialized: boolean) => {
    set({ isTesseractInitialized: initialized });
  },

  setInitializingTesseract: (initializing: boolean) => {
    set({ isInitializingTesseract: initializing });
  },

});
