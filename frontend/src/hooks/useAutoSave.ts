import { useEffect, useRef, useState, useCallback } from "react";
import toast from "react-hot-toast";

interface UseAutoSaveOptions {
  screenshotId: number | undefined;
  hourlyData: Record<string, number> | undefined;
  extractedTitle: string | null | undefined;
  gridCoordsValid: boolean;
  notes: string;
  onSave: (notes: string) => Promise<void>;
}

interface UseAutoSaveReturn {
  isSaving: boolean;
  lastSaved: Date | null;
  timeSinceLastSave: string;
  /** Number of consecutive save failures. Resets on success or screenshot change. */
  saveFailCount: number;
  /** Last error message from a failed save attempt. */
  lastError: string | null;
  /** True if there are unsaved changes (edits made since last successful save). */
  hasUnsavedChanges: boolean;
  /** Manually trigger a save (e.g., from a "Retry" button). */
  retrySave: () => void;
}

export function useAutoSave(options: UseAutoSaveOptions): UseAutoSaveReturn {
  const { screenshotId, hourlyData, extractedTitle, gridCoordsValid, notes, onSave } = options;

  const [isSaving, setIsSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const [timeSinceLastSave, setTimeSinceLastSave] = useState<string>("");
  const [saveFailCount, setSaveFailCount] = useState(0);
  const [lastError, setLastError] = useState<string | null>(null);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  // Track previous values to only save on actual changes (not on initial load or navigation)
  const prevHourlyDataRef = useRef<string>("");
  const prevTitleRef = useRef<string | null | undefined>(undefined);
  const prevScreenshotIdRef = useRef<number | null>(null);
  // Guard against concurrent saves; pendingSaveRef triggers a re-save after completion
  const isSavingRef = useRef(false);
  const pendingSaveRef = useRef(false);
  // Stable ref for notes so it doesn't trigger re-saves
  const notesRef = useRef(notes);
  notesRef.current = notes;
  // Stable ref for onSave to avoid dependency churn
  const onSaveRef = useRef(onSave);
  onSaveRef.current = onSave;

  // Serialize hourly_data to detect deep changes
  const hourlyDataJson = JSON.stringify(hourlyData || {});

  // Reset save status when screenshot changes
  useEffect(() => {
    setLastSaved(null);
    setTimeSinceLastSave("");
    setSaveFailCount(0);
    setLastError(null);
    setHasUnsavedChanges(false);
  }, [screenshotId]);

  // Update time since last save every second
  useEffect(() => {
    if (!lastSaved) {
      setTimeSinceLastSave("");
      return;
    }

    let prevStr = "";
    const updateTime = () => {
      const now = new Date();
      const diffMs = now.getTime() - lastSaved.getTime();
      const diffSeconds = Math.floor(diffMs / 1000);

      let newStr: string;
      if (diffSeconds < 3) {
        newStr = "just now";
      } else if (diffSeconds < 60) {
        newStr = `${diffSeconds}s ago`;
      } else if (diffSeconds < 3600) {
        const minutes = Math.floor(diffSeconds / 60);
        newStr = `${minutes}m ago`;
      } else {
        const hours = Math.floor(diffSeconds / 3600);
        newStr = `${hours}h ago`;
      }
      // Only trigger re-render when the display string actually changes
      if (newStr !== prevStr) {
        prevStr = newStr;
        setTimeSinceLastSave(newStr);
      }
    };

    updateTime();
    // Check every 5 seconds — granularity is sufficient for "Xs ago" display
    const interval = setInterval(updateTime, 5000);

    return () => clearInterval(interval);
  }, [lastSaved]);

  const doSave = useCallback(async () => {
    if (isSavingRef.current) {
      // Another save is in-flight — mark pending so it re-saves after completion
      pendingSaveRef.current = true;
      return;
    }
    isSavingRef.current = true;
    pendingSaveRef.current = false;
    setIsSaving(true);
    try {
      await onSaveRef.current(notesRef.current);
      setLastSaved(new Date());
      setSaveFailCount(0);
      setLastError(null);
      setHasUnsavedChanges(false);
      toast("Saved", { duration: 1500, position: "bottom-center", style: { fontSize: "12px", padding: "4px 12px", background: "#334155", color: "#e2e8f0" } });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Save failed";
      console.error("[AutoSave] Failed:", message);
      setSaveFailCount((c) => c + 1);
      setLastError(message);
      // hasUnsavedChanges stays true — user needs to know
    } finally {
      isSavingRef.current = false;
      setIsSaving(false);
      // If data changed while we were saving, save again with latest state
      if (pendingSaveRef.current) {
        pendingSaveRef.current = false;
        doSave();
      }
    }
  }, []);

  // Auto-save effect — fires on hourly data or title changes
  useEffect(() => {
    if (!screenshotId || !gridCoordsValid || !hourlyData) {
      return;
    }

    // Don't save if no hourly data
    if (Object.keys(hourlyData).length === 0) {
      return;
    }

    // Circuit breaker: stop auto-saving after 3 consecutive failures
    // User can manually retry via the "Retry" button
    if (saveFailCount >= 3) {
      return;
    }

    // If screenshot changed, just update refs without saving (data was just loaded)
    if (prevScreenshotIdRef.current !== screenshotId) {
      prevScreenshotIdRef.current = screenshotId;
      prevHourlyDataRef.current = hourlyDataJson;
      prevTitleRef.current = extractedTitle;
      return;
    }

    // Check if actual edits were made
    const hourlyDataChanged = prevHourlyDataRef.current !== hourlyDataJson;
    const titleChanged = prevTitleRef.current !== extractedTitle;

    // Update refs for next comparison
    prevHourlyDataRef.current = hourlyDataJson;
    prevTitleRef.current = extractedTitle;

    // Only save if something actually changed
    if (!hourlyDataChanged && !titleChanged) {
      return;
    }

    setHasUnsavedChanges(true);

    // Debounce title-only changes (user is typing) — save after 800ms of no typing
    // Hourly data changes save immediately (discrete clicks, not continuous input)
    if (titleChanged && !hourlyDataChanged) {
      const timer = setTimeout(doSave, 800);
      return () => clearTimeout(timer);
    }
    doSave();
    // notes and onSave excluded — we use refs for both to avoid triggering re-saves
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hourlyDataJson, screenshotId, extractedTitle, gridCoordsValid, hourlyData, doSave, saveFailCount]);

  const retrySave = useCallback(() => {
    doSave();
  }, [doSave]);

  return {
    isSaving,
    lastSaved,
    timeSinceLastSave,
    saveFailCount,
    lastError,
    hasUnsavedChanges,
    retrySave,
  };
}
