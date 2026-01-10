import type { StateCreator } from "zustand";
import type { AnnotationState, SharedSlice } from "./types";
import { initialAnnotation } from "./types";

export const createSharedSlice: StateCreator<
  AnnotationState,
  [],
  [],
  SharedSlice
> = (set) => ({
  reset: () => {
    set({
      currentScreenshot: null,
      currentAnnotation: { ...initialAnnotation },
      consensus: null,
      error: null,
      processingIssues: [],
      isAutoProcessed: false,
      processingProgress: null,
    });
  },

  clearError: () => set({ error: null }),
});
