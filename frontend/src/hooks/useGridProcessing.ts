import { useCallback, useEffect, useRef, useState } from "react";
import type { GridCoordinates } from "@/types";
import { toastErrorWithRetry } from "@/utils/toastWithRetry";

interface UseGridProcessingOptions {
  onReprocess: (coords: GridCoordinates) => Promise<void>;
  onSetGrid: (coords: GridCoordinates) => void;
}

interface UseGridProcessingReturn {
  isProcessing: boolean;
  handleGridSelect: (coords: GridCoordinates) => void;
}

export function useGridProcessing(options: UseGridProcessingOptions): UseGridProcessingReturn {
  const { onReprocess, onSetGrid } = options;

  const [isProcessing, setIsProcessing] = useState(false);
  const debounceTimer = useRef<NodeJS.Timeout | null>(null);
  const currentRequestId = useRef<number>(0);

  const handleGridSelect = useCallback(
    (coords: GridCoordinates) => {
      // INSTANT: Update grid coords immediately for crop preview
      onSetGrid(coords);

      // Cancel any pending debounce timer (user still moving)
      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
      }

      // Invalidate any in-flight request by incrementing ID
      currentRequestId.current += 1;
      setIsProcessing(false);

      // Debounce (300ms) - wait for user to stop dragging before processing
      debounceTimer.current = setTimeout(async () => {
        // Capture request ID at start
        const requestId = ++currentRequestId.current;

        setIsProcessing(true);

        try {
          await onReprocess(coords);

          // Only update state if this is still the latest request
          if (requestId === currentRequestId.current) {
            setIsProcessing(false);
          }
        } catch (error) {
          // Only show error if this is still the latest request
          if (requestId === currentRequestId.current) {
            const errorMessage =
              error instanceof Error
                ? error.message
                : "Failed to reprocess with selected grid";
            toastErrorWithRetry({
              message: errorMessage,
              onRetry: () => handleGridSelect(coords),
              retryLabel: "Retry Processing",
            });
            setIsProcessing(false);
          }
        }
      }, 300);
    },
    [onReprocess, onSetGrid],
  );

  // Clean up debounce timer on unmount to prevent wasted reprocess calls
  useEffect(() => {
    return () => {
      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
      }
    };
  }, []);

  return {
    isProcessing,
    handleGridSelect,
  };
}
