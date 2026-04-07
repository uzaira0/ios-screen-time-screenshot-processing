import { useCallback, useMemo, useEffect, useRef } from "react";
import { useShallow } from "zustand/react/shallow";
import type { GridCoordinates } from "@/core";
import type { ProcessingStatus } from "@/types";
import {
  useScreenshotService,
  useAnnotationService,
  useConsensusService,
} from "@/core";
import { createAnnotationStore } from "@/store/createAnnotationStore";
import { VerifiedScreenshotError } from "@/store/slices/processingSlice";
import toast from "react-hot-toast";
import { toastErrorWithRetry } from "@/utils/toastWithRetry";
import { config } from "@/config";

// Store instances keyed by groupId + processingStatus (undefined = no filter)
// Each entry tracks the store and its reference count
interface StoreEntry {
  store: ReturnType<typeof createAnnotationStore>;
  refCount: number;
}
const storeInstances = new Map<string, StoreEntry>();

// Cleanup delay to allow for quick re-mounts (e.g., React strict mode)
const CLEANUP_DELAY_MS = 5000;

export const useAnnotation = (groupId?: string, processingStatus?: ProcessingStatus) => {
  const screenshotService = useScreenshotService();
  const annotationService = useAnnotationService();
  const consensusService = useConsensusService();

  // Track the cache key for cleanup
  const cacheKeyRef = useRef<string | null>(null);

  const store = useMemo(() => {
    // Use groupId + processingStatus as key
    const cacheKey = `${groupId || ""}:${processingStatus || ""}`;
    cacheKeyRef.current = cacheKey;

    const existing = storeInstances.get(cacheKey);
    if (existing) {
      existing.refCount++;
      return existing.store;
    }

    const newStore = createAnnotationStore(
      screenshotService,
      annotationService,
      consensusService,
      groupId,
      processingStatus,
    );
    storeInstances.set(cacheKey, { store: newStore, refCount: 1 });
    return newStore;
  }, [
    screenshotService,
    annotationService,
    consensusService,
    groupId,
    processingStatus,
  ]);

  // Cleanup store when component unmounts
  useEffect(() => {
    const currentKey = cacheKeyRef.current;

    return () => {
      if (!currentKey) return;

      // Delayed cleanup to handle React strict mode double-mount
      setTimeout(() => {
        const entry = storeInstances.get(currentKey);
        if (entry) {
          entry.refCount--;
          if (entry.refCount <= 0) {
            storeInstances.delete(currentKey);
            if (config.isDev) {
              console.log(
                `[useAnnotation] Cleaned up store for key: ${currentKey}`,
              );
            }
          }
        }
      }, CLEANUP_DELAY_MS);
    };
  }, [groupId, processingStatus]);

  // Select reactive data with useShallow (triggers re-render only when data changes)
  const {
    currentScreenshot,
    currentAnnotation,
    consensus,
    queueStats,
    isLoading,
    noScreenshots,
    error,
    processingIssues,
    isAutoProcessed,
    processingProgress,
    isTesseractInitialized,
    isInitializingTesseract,
    currentIndex,
    totalInFilter,
    hasNext,
    hasPrev,
    screenshotList,
    verificationFilter,
  } = store(
    useShallow((state) => ({
      currentScreenshot: state.currentScreenshot,
      currentAnnotation: state.currentAnnotation,
      consensus: state.consensus,
      queueStats: state.queueStats,
      isLoading: state.isLoading,
      noScreenshots: state.noScreenshots,
      error: state.error,
      processingIssues: state.processingIssues,
      isAutoProcessed: state.isAutoProcessed,
      processingProgress: state.processingProgress,
      isTesseractInitialized: state.isTesseractInitialized,
      isInitializingTesseract: state.isInitializingTesseract,
      currentIndex: state.currentIndex,
      totalInFilter: state.totalInFilter,
      hasNext: state.hasNext,
      hasPrev: state.hasPrev,
      screenshotList: state.screenshotList,
      verificationFilter: state.verificationFilter,
    })),
  );

  // Action selectors — no useShallow needed since action refs are stable
  const loadNextScreenshot = store((s) => s.loadNextScreenshot);
  const loadScreenshot = store((s) => s.loadScreenshot);
  const loadQueueStats = store((s) => s.loadQueueStats);
  const setGridCoordinates = store((s) => s.setGridCoordinates);
  const setHourlyValues = store((s) => s.setHourlyValues);
  const updateHourValue = store((s) => s.updateHourValue);
  const setExtractedTitle = store((s) => s.setExtractedTitle);
  const saveAnnotation = store((s) => s.saveAnnotation);
  const skipScreenshot = store((s) => s.skipScreenshot);
  const storeReprocessWithGrid = store((s) => s.reprocessWithGrid);
  const storeReprocessWithLineBased = store((s) => s.reprocessWithLineBased);
  const storeReprocessWithOcrAnchored = store((s) => s.reprocessWithOcrAnchored);
  const clearError = store((s) => s.clearError);
  const setProcessingProgress = store((s) => s.setProcessingProgress);
  const clearProcessingProgress = store((s) => s.clearProcessingProgress);
  const setTesseractInitialized = store((s) => s.setTesseractInitialized);
  const setInitializingTesseract = store((s) => s.setInitializingTesseract);
  const navigateNext = store((s) => s.navigateNext);
  const navigatePrev = store((s) => s.navigatePrev);
  const loadScreenshotList = store((s) => s.loadScreenshotList);
  const loadMoreScreenshots = store((s) => s.loadMoreScreenshots);
  const setVerificationFilter = store((s) => s.setVerificationFilter);
  const verifyCurrentScreenshot = store((s) => s.verifyCurrentScreenshot);
  const unverifyCurrentScreenshot = store((s) => s.unverifyCurrentScreenshot);
  const recalculateOcrTotal = store((s) => s.recalculateOcrTotal);

  const isSubmittingRef = useRef(false);
  const handleSubmit = useCallback(
    async (notes?: string) => {
      if (isSubmittingRef.current) return;
      isSubmittingRef.current = true;
      try {
        if (config.isDev) {
          console.log("[useAnnotation.handleSubmit] Starting submission...");
        }
        await saveAnnotation(notes);
        toast.success(config.isLocalMode ? "Annotation saved!" : "Annotation submitted!");
        if (config.isDev) {
          console.log("[useAnnotation.handleSubmit] Loading next screenshot...");
        }
        await loadQueueStats();
        await navigateNext();
        if (config.isDev) {
          console.log("[useAnnotation.handleSubmit] Next screenshot loaded");
        }
      } catch (err: unknown) {
        console.error("[useAnnotation.handleSubmit] Error:", err);
        const errorMessage =
          err instanceof Error ? err.message : "Failed to save annotation";
        toastErrorWithRetry({
          message: errorMessage,
          // eslint-disable-next-line react-hooks/immutability
          onRetry: () => handleSubmit(notes),
          retryLabel: "Retry",
        });
      } finally {
        isSubmittingRef.current = false;
      }
    },
    [saveAnnotation, navigateNext, loadQueueStats],
  );

  // Save without navigating (used by auto-save — no confirmation dialogs)
  const handleSaveOnly = useCallback(
    async (notes?: string) => {
      try {
        await saveAnnotation(notes);
      } catch (err: unknown) {
        console.error("[useAnnotation.handleSaveOnly] Error:", err);
        throw err;
      }
    },
    [saveAnnotation],
  );

  const handleSkip = useCallback(async (reason?: string) => {
    try {
      if (config.isDev) {
        console.log("[useAnnotation.handleSkip] Starting skip...", reason ? `reason: ${reason}` : "");
      }
      await skipScreenshot(reason);
      toast.success(reason ? `Skipped: ${reason}` : "Screenshot skipped");
      if (config.isDev) {
        console.log("[useAnnotation.handleSkip] Skip completed");
      }
    } catch (err: unknown) {
      console.error("[useAnnotation.handleSkip] Error:", err);
      const errorMessage =
        err instanceof Error ? err.message : "Failed to skip screenshot";
      toastErrorWithRetry({
        message: errorMessage,
        // eslint-disable-next-line react-hooks/immutability
        onRetry: () => handleSkip(reason),
        retryLabel: "Retry Skip",
      });
    }
  }, [skipScreenshot]);

  const handleSetGrid = useCallback(
    (coords: GridCoordinates) => {
      // setGridCoordinates also persists to IndexedDB via updateGridCoords (in annotationSlice)
      setGridCoordinates(coords);
    },
    [setGridCoordinates],
  );

  const handleReprocessWithGrid = useCallback(
    async (coords: GridCoordinates) => {
      try {
        await storeReprocessWithGrid(coords);
      } catch (error) {
        if (error instanceof VerifiedScreenshotError) {
          toast.error("Cannot reprocess: you have already verified this screenshot");
        } else {
          throw error;
        }
      }
    },
    [storeReprocessWithGrid],
  );

  const handleReprocessWithLineBased = useCallback(async () => {
    try {
      await storeReprocessWithLineBased();
    } catch (error) {
      if (error instanceof VerifiedScreenshotError) {
        toast.error("Cannot reprocess: you have already verified this screenshot");
      } else {
        throw error;
      }
    }
  }, [storeReprocessWithLineBased]);

  const handleReprocessWithOcrAnchored = useCallback(async () => {
    try {
      await storeReprocessWithOcrAnchored();
    } catch (error) {
      if (error instanceof VerifiedScreenshotError) {
        toast.error("Cannot reprocess: you have already verified this screenshot");
      } else {
        throw error;
      }
    }
  }, [storeReprocessWithOcrAnchored]);

  return {
    screenshot: currentScreenshot,
    annotation: currentAnnotation,
    consensus,
    queueStats,
    isLoading,
    noScreenshots,
    error,
    processingIssues,
    isAutoProcessed,
    loadNext: loadNextScreenshot,
    loadById: loadScreenshot,
    loadQueueStats,
    setGrid: handleSetGrid,
    setHourlyValues,
    updateHour: updateHourValue,
    setTitle: setExtractedTitle,
    submit: handleSubmit,
    saveOnly: handleSaveOnly,
    skip: handleSkip,
    reprocessWithGrid: handleReprocessWithGrid,
    reprocessWithLineBased: handleReprocessWithLineBased,
    reprocessWithOcrAnchored: handleReprocessWithOcrAnchored,
    clearError,
    // NEW: Progress tracking
    processingProgress,
    isTesseractInitialized,
    isInitializingTesseract,
    setProcessingProgress,
    clearProcessingProgress,
    setTesseractInitialized,
    setInitializingTesseract,
    // NEW: Navigation
    currentIndex,
    totalInFilter,
    hasNext,
    hasPrev,
    screenshotList,
    verificationFilter,
    navigateNext,
    navigatePrev,
    loadScreenshotList,
    loadMoreScreenshots,
    setVerificationFilter,
    // NEW: Verification
    verifyCurrentScreenshot,
    unverifyCurrentScreenshot,
    // OCR recalculation
    recalculateOcrTotal,
  };
};
