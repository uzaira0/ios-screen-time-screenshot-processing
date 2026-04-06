import type { StateCreator } from "zustand";
import type {
  IAnnotationService,
  IScreenshotService,
  IConsensusService,
  GridCoordinates,
  HourlyData,
} from "@/core";
import type { AnnotationState, AnnotationSlice } from "./types";
import { initialAnnotation } from "./types";
import { extractErrorMessage } from "./helpers";

export const createAnnotationSlice = (
  screenshotService: IScreenshotService,
  annotationService: IAnnotationService,
  consensusService: IConsensusService,
): StateCreator<AnnotationState, [], [], AnnotationSlice> => (set, get) => ({
  // State
  currentAnnotation: { ...initialAnnotation },
  processingIssues: [],
  isAutoProcessed: false,
  consensus: null,

  // Actions
  setGridCoordinates: (coords: GridCoordinates) => {
    set((state) => ({
      currentAnnotation: {
        ...state.currentAnnotation,
        grid_coords: coords,
      },
    }));
    // Persist grid coords to storage so they survive reload/navigation
    const { currentScreenshot } = get();
    if (currentScreenshot) {
      screenshotService.updateGridCoords(currentScreenshot.id, coords).catch((err) => {
        console.error("[setGridCoordinates] Failed to persist:", err);
        set({ error: "Failed to save grid coordinates — changes may be lost on reload" });
      });
    }
  },

  setHourlyValues: (data: HourlyData) => {
    set((state) => ({
      currentAnnotation: {
        ...state.currentAnnotation,
        hourly_values: data,
      },
    }));
  },

  updateHourValue: (hour: number, value: number) => {
    set((state) => {
      const hourlyData = { ...state.currentAnnotation?.hourly_values };
      if (value < 0 || value > 60) return state;

      hourlyData[hour] = value;

      return {
        currentAnnotation: {
          ...state.currentAnnotation,
          hourly_values: hourlyData,
        },
      };
    });
  },

  setExtractedTitle: (title: string) => {
    set((state) => {
      if (!state.currentScreenshot) return state;
      return {
        currentScreenshot: {
          ...state.currentScreenshot,
          extracted_title: title,
        },
      };
    });
  },

  saveAnnotation: async (notes?: string) => {
    const { currentScreenshot, currentAnnotation } = get();

    if (!currentScreenshot || !currentAnnotation?.grid_coords) {
      throw new Error("Missing required data");
    }

    // Note: intentionally NOT setting isLoading here — saveAnnotation is called
    // by both manual submit and auto-save. Setting isLoading would briefly disable
    // UI buttons during every auto-save tick, which is disruptive. The manual submit
    // flow (handleSubmit) manages its own loading state via the button.
    try {
      // Convert UIAnnotation to AnnotationCreate format for the API
      await annotationService.create({
        screenshot_id: currentScreenshot.id,
        hourly_values: currentAnnotation.hourly_values || {},
        extracted_title: currentScreenshot.extracted_title || null,
        extracted_total: currentScreenshot.extracted_total || null,
        grid_upper_left: currentAnnotation.grid_coords.upper_left,
        grid_lower_right: currentAnnotation.grid_coords.lower_right,
        notes: notes || currentAnnotation.notes || null,
      });

      // Save title and hourly data in parallel — non-fatal side effects.
      // These update the screenshot model (not the annotation), so failures
      // should not trip the auto-save circuit breaker or mask the successful annotation save.
      const sideEffects: Promise<unknown>[] = [];
      if (currentScreenshot.extracted_title !== undefined) {
        sideEffects.push(
          screenshotService.updateTitle(
            currentScreenshot.id,
            currentScreenshot.extracted_title || "",
          ).catch((err) => console.error("[saveAnnotation] updateTitle failed:", err)),
        );
      }
      if (currentAnnotation.hourly_values) {
        sideEffects.push(
          screenshotService.updateHourlyData(
            currentScreenshot.id,
            currentAnnotation.hourly_values,
          ).catch((err) => console.error("[saveAnnotation] updateHourlyData failed:", err)),
        );
      }
      if (sideEffects.length > 0) {
        await Promise.all(sideEffects);
      }
    } catch (error: unknown) {
      const message = extractErrorMessage(error, "Failed to save annotation");
      // Backup to localStorage as safety net (annotation is ~1KB)
      try {
        const backup = {
          screenshot_id: currentScreenshot.id,
          hourly_values: currentAnnotation.hourly_values || {},
          extracted_title: currentScreenshot.extracted_title || null,
          extracted_total: currentScreenshot.extracted_total || null,
          grid_upper_left: currentAnnotation.grid_coords.upper_left,
          grid_lower_right: currentAnnotation.grid_coords.lower_right,
          notes: notes || currentAnnotation.notes || null,
          saved_at: new Date().toISOString(),
        };
        const existing = JSON.parse(localStorage.getItem("unsaved-annotations") || "[]");
        existing.push(backup);
        localStorage.setItem("unsaved-annotations", JSON.stringify(existing));
        set({ error: `${message}. Saved locally — will retry on next load.` });
      } catch {
        set({ error: message });
      }
      throw error;
    }
  },

  recoverUnsavedAnnotations: async () => {
    try {
      const raw = localStorage.getItem("unsaved-annotations");
      if (!raw) return;
      const backups: Array<Record<string, unknown>> = JSON.parse(raw);
      if (!Array.isArray(backups) || backups.length === 0) return;

      const remaining: Array<Record<string, unknown>> = [];
      for (const backup of backups) {
        try {
          await annotationService.create({
            screenshot_id: backup.screenshot_id as number,
            hourly_values: (backup.hourly_values as Record<string, number>) || {},
            extracted_title: (backup.extracted_title as string) || null,
            extracted_total: (backup.extracted_total as string) || null,
            grid_upper_left: backup.grid_upper_left as { x: number; y: number },
            grid_lower_right: backup.grid_lower_right as { x: number; y: number },
            notes: (backup.notes as string) || null,
          });
        } catch {
          remaining.push(backup);
        }
      }

      if (remaining.length === 0) {
        localStorage.removeItem("unsaved-annotations");
        console.log(`[Annotations] Recovered ${backups.length} unsaved annotation(s)`);
      } else {
        localStorage.setItem("unsaved-annotations", JSON.stringify(remaining));
        console.warn(`[Annotations] ${remaining.length} annotation(s) still failed to save`);
      }
    } catch (e) {
      console.warn("[Annotations] Clearing corrupted backup:", e);
      localStorage.removeItem("unsaved-annotations");
    }
  },

  loadConsensus: async (screenshotId: number) => {
    try {
      const consensus = await consensusService.getForScreenshot(screenshotId);
      set({ consensus });
    } catch (error) {
      console.error("Failed to load consensus:", error);
      set({ error: extractErrorMessage(error, "Failed to load consensus data") });
    }
  },
});
