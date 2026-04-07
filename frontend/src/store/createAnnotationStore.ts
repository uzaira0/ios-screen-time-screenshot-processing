import { create } from "zustand";
import type {
  IScreenshotService,
  IAnnotationService,
  IConsensusService,
} from "@/core";
import type { ProcessingStatus } from "@/types";
import {
  type AnnotationState,
  createScreenshotSlice,
  createAnnotationSlice,
  createProcessingSlice,
  createNavigationSlice,
  createSharedSlice,
} from "./slices";

/**
 * Creates an annotation store with all slices combined.
 *
 * The store is split into logical slices for maintainability:
 * - Screenshot: Loading, stats, skip functionality
 * - Annotation: Grid coords, hourly values, submission
 * - Processing: Reprocessing, OCR, progress tracking
 * - Navigation: Next/prev, list management, verification
 * - Shared: Reset, error clearing
 *
 * Each slice has access to the full state via `get()`, allowing
 * cross-slice interactions (e.g., loadNextScreenshot calls loadConsensus).
 */
export function createAnnotationStore(
  screenshotService: IScreenshotService,
  annotationService: IAnnotationService,
  consensusService: IConsensusService,
  groupId?: string,
  processingStatus?: ProcessingStatus,
) {
  return create<AnnotationState>()((...args) => ({
    // Screenshot slice: Loading, stats, skip
    ...createScreenshotSlice(screenshotService, groupId, processingStatus)(
      ...args,
    ),

    // Annotation slice: Grid, hourly values, submission
    ...createAnnotationSlice(
      screenshotService,
      annotationService,
      consensusService,
    )(...args),

    // Processing slice: Reprocessing, OCR, progress
    ...createProcessingSlice(screenshotService)(...args),

    // Navigation slice: Navigation, verification, filtering
    ...createNavigationSlice(screenshotService, annotationService, groupId, processingStatus)(
      ...args,
    ),

    // Shared slice: Reset, clear error
    ...createSharedSlice(...args),
  }));
}
