import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useNavigate, Link } from "react-router";
import { useAnnotation } from "@/hooks/useAnnotationWithDI";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";
import { useAutoSave } from "@/hooks/useAutoSave";
import { useGridProcessing } from "@/hooks/useGridProcessing";
import { useAuth } from "@/hooks/useAuth";
import { GridSelector } from "./GridSelector";
import { CroppedGraphViewer } from "./CroppedGraphViewer";
import { HourlyUsageEditor } from "./HourlyUsageEditor";
import { HourlyUsageOverlay } from "./HourlyUsageOverlay";
import { IssueDisplay } from "./IssueDisplay";
import { DuplicateWarning } from "./DuplicateWarning";
import { ScreenshotSelector } from "./ScreenshotSelector";
import { VerificationFilter } from "./VerificationFilter";
import { ProcessingStatusFilter } from "./ProcessingStatusFilter";
import { SaveStatusIndicator } from "./SaveStatusIndicator";
import { Skeleton } from "@/components/ui/Skeleton";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";
import { TotalsDisplay } from "./TotalsDisplay";
import { AlignmentWarning } from "./AlignmentWarning";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import type { ProcessingStatus } from "@/types";
import type { FilterStatus } from "@/constants/processingStatus";
import type { VerificationFilterType } from "@/store/slices/types";
import { PreprocessingSummary } from "./PreprocessingSummary";
import { useScreenshotImage } from "@/hooks/useScreenshotImage";
import { PHIRegionEditor } from "@/components/preprocessing/PHIRegionEditor";
import { Modal } from "@/components/ui/Modal";
import { CropAdjustModal } from "@/components/preprocessing/CropAdjustModal";
import { getCropRectFromEvent } from "@/components/preprocessing/CroppingTab";
import { getCurrentEvent } from "@/components/preprocessing/StageReviewTable";
import { useConsensusService } from "@/core/hooks/useServices";
import type { Consensus } from "@/types";
import toast from "react-hot-toast";
import { config } from "@/config";

type ProcessingMethod = "ocr_anchored" | "line_based";

export type GraphDisplayMode = "separate" | "overlay";

/** Module-level frozen empty object so every component that reads
 *  `hourlyValues` while annotation is still loading sees the same
 *  reference instead of a fresh `{}` per workspace render. */
const EMPTY_HOURLY: Record<number, number> = Object.freeze({}) as Record<number, number>;

interface AnnotationWorkspaceProps {
  groupId?: string | undefined;
  processingStatus?: ProcessingStatus | undefined;
  initialScreenshotId?: number | undefined;
  initialFilter?: VerificationFilterType | undefined;
}

export const AnnotationWorkspace = ({
  groupId,
  processingStatus,
  initialScreenshotId,
  initialFilter,
}: AnnotationWorkspaceProps) => {
  const navigate = useNavigate();
  const { username } = useAuth();
  const {
    screenshot,
    annotation,
    isLoading,
    noScreenshots,
    processingIssues,
    loadNext,
    loadById,
    updateHour,
    saveOnly,
    skip,
    reprocessWithGrid,
    setGrid,
    setTitle,
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
    verifyCurrentScreenshot,
    unverifyCurrentScreenshot,
    recalculateOcrTotal,
    reprocessWithLineBased,
    reprocessWithOcrAnchored,
    error,
    clearError,
  } = useAnnotation(groupId, processingStatus);

  const [imageRefreshKey, setImageRefreshKey] = useState(0);
  const imageUrl = useScreenshotImage(screenshot?.id || 0, imageRefreshKey);

  // Stabilize the data references that get passed into the heavy
  // overlay/editor children. The previous inline `annotation?.hourly_values || {}`
  // and `... || null` literals minted a fresh `{}` / `null` reference
  // on every workspace render — which made HourlyUsageOverlay (canvas
  // redraw + image reload) and the editor rerender even when nothing
  // about their inputs had actually changed. Each navigation churned
  // them four or five times in a row.
  const hourlyValues = useMemo(
    () => annotation?.hourly_values ?? EMPTY_HOURLY,
    [annotation?.hourly_values],
  );
  const gridCoords = annotation?.grid_coords ?? null;

  const [notes, setNotes] = useState("");
  const [displayMode, setDisplayMode] = useState<GraphDisplayMode>(() => {
    try {
      const v = localStorage.getItem("annotate-display-mode");
      return v === "separate" || v === "overlay" ? v : "overlay";
    } catch { return "overlay"; }
  });
  const [isRecalculatingOcr, setIsRecalculatingOcr] = useState(false);
  const [reprocessingMethod, setReprocessingMethod] =
    useState<ProcessingMethod | null>(null);
  const [phiEditorOpen, setPHIEditorOpen] = useState(false);
  const [cropEditorOpen, setCropEditorOpen] = useState(false);
  const [skipMenuOpen, setSkipMenuOpen] = useState(false);
  const [helpDismissed, setHelpDismissed] = useState(() => {
    try { return localStorage.getItem("annotation-help-dismissed") === "1"; } catch { return false; }
  });
  const [shortcutsHintDismissed, setShortcutsHintDismissed] = useState(() => {
    try { return localStorage.getItem("shortcuts-hint-dismissed") === "1"; } catch { return false; }
  });
  const skipMenuRef = useRef<HTMLDivElement>(null);
  const [consensus, setConsensus] = useState<Consensus | null>(null);
  const consensusService = useConsensusService();

  // Show global error toast when store error changes
  useEffect(() => {
    if (error) {
      toast.error(error);
      clearError();
    }
  }, [error, clearError]);

  // Load consensus data when screenshot has multiple verifiers
  useEffect(() => {
    if (!screenshot?.id || !screenshot.verified_by_usernames || screenshot.verified_by_usernames.length < 2) {
      setConsensus(null);
      return;
    }
    let cancelled = false;
    consensusService.getForScreenshot(screenshot.id)
      .then((data) => { if (!cancelled) setConsensus(data); })
      .catch((e) => { console.error("Failed to load consensus:", e); if (!cancelled) setConsensus(null); });
    return () => { cancelled = true; };
  }, [screenshot?.id, screenshot?.verified_by_usernames?.length, consensusService]);

  // Close skip dropdown when clicking outside
  useEffect(() => {
    if (!skipMenuOpen) return;
    const handleOutsideClick = (e: MouseEvent) => {
      if (skipMenuRef.current && !skipMenuRef.current.contains(e.target as Node)) {
        setSkipMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [skipMenuOpen]);

  // Check if THIS USER has verified the screenshot (read-only mode for them)
  // Use username-based check as it's more reliable than userId which can get stale
  const isVerifiedByMe = !!(
    username &&
    screenshot?.verified_by_usernames?.includes(username)
  );

  // Get ALL verifiers' usernames
  const allVerifierUsernames = screenshot?.verified_by_usernames || [];

  // Grid processing hook with debounce
  const { isProcessing, handleGridSelect } = useGridProcessing({
    onReprocess: reprocessWithGrid,
    onSetGrid: setGrid,
  });

  // Auto-save hook
  const gridCoordsValid =
    annotation?.grid_coords &&
    !(
      annotation.grid_coords.upper_left.x === 0 &&
      annotation.grid_coords.lower_right.x === 0
    );

  const { isSaving, lastSaved, timeSinceLastSave, saveFailCount, lastError, hasUnsavedChanges, retrySave } = useAutoSave({
    screenshotId: screenshot?.id,
    hourlyData: annotation?.hourly_values,
    extractedTitle: screenshot?.extracted_title,
    gridCoordsValid: !!gridCoordsValid,
    notes,
    onSave: saveOnly,
  });

  // Warn on tab close/refresh if there are unsaved changes
  useEffect(() => {
    if (!hasUnsavedChanges) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [hasUnsavedChanges]);

  // Initial load: if a filter is set (URL param or localStorage), use setVerificationFilter
  // which internally loads the screenshot list and first screenshot. Otherwise load directly.
  useEffect(() => {
    // Determine the filter to apply
    let filterToApply: VerificationFilterType | undefined;
    if (initialFilter) {
      filterToApply = initialFilter;
    } else {
      try {
        const saved = localStorage.getItem("annotate-verification-filter");
        const valid: VerificationFilterType[] = ["all", "verified_by_me", "not_verified_by_me", "verified_by_others", "totals_mismatch"];
        if (saved && (valid as string[]).includes(saved) && saved !== "all") {
          filterToApply = saved as VerificationFilterType;
        }
      } catch { /* ignore */ }
    }

    if (filterToApply) {
      // setVerificationFilter loads the list + first screenshot internally — no separate calls needed
      setVerificationFilter(filterToApply);
    } else {
      if (initialScreenshotId) {
        loadById(initialScreenshotId);
      } else {
        loadNext();
      }
      loadScreenshotList();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupId, processingStatus, initialScreenshotId, initialFilter]);

  // Persist displayMode and verificationFilter
  useEffect(() => {
    try { localStorage.setItem("annotate-display-mode", displayMode); } catch { /* ignore */ }
  }, [displayMode]);
  useEffect(() => {
    try { localStorage.setItem("annotate-verification-filter", verificationFilter); } catch { /* ignore */ }
  }, [verificationFilter]);

  // Update URL when screenshot changes
  useEffect(() => {
    if (screenshot?.id) {
      const searchParams = new URLSearchParams();
      if (groupId) searchParams.set("group", groupId);
      if (processingStatus)
        searchParams.set("processing_status", processingStatus);
      const search = searchParams.toString();
      const newUrl = `/annotate/${screenshot.id}${search ? `?${search}` : ""}`;
      navigate(newUrl, { replace: true });
    }
  }, [screenshot?.id, groupId, processingStatus, navigate]);
  // Note: navigate is stable from react-router-dom

  const handleRecalculateOcr = useCallback(async () => {
    if (isRecalculatingOcr) return;
    setIsRecalculatingOcr(true);
    try {
      const newTotal = await recalculateOcrTotal();
      if (newTotal) {
        toast.success(`OCR total updated: ${newTotal}`);
      } else {
        toast.error("Could not extract OCR total");
      }
    } catch (error) {
      toast.error("Failed to recalculate OCR total");
    } finally {
      setIsRecalculatingOcr(false);
    }
  }, [recalculateOcrTotal, isRecalculatingOcr]);

  const handleReprocess = useCallback(
    async (method: ProcessingMethod) => {
      if (reprocessingMethod) return;
      setReprocessingMethod(method);
      try {
        if (method === "line_based") {
          await reprocessWithLineBased();
          toast.success("Line-based detection completed");
        } else {
          await reprocessWithOcrAnchored();
          toast.success("OCR-anchored detection completed");
        }
      } catch (error) {
        const methodName =
          method === "line_based" ? "Line-based" : "OCR-anchored";
        const message =
          error instanceof Error
            ? error.message
            : `${methodName} detection failed`;
        toast.error(message);
      } finally {
        setReprocessingMethod(null);
      }
    },
    [reprocessWithLineBased, reprocessWithOcrAnchored, reprocessingMethod],
  );

  const [isVerifying, setIsVerifying] = useState(false);
  const [mismatchInfo, setMismatchInfo] = useState<{ barStr: string; ocrStr: string; onConfirm: () => void; onCancel: () => void } | null>(null);
  const handleVerificationToggle = useCallback(async () => {
    if (!screenshot || isVerifying) return;
    setIsVerifying(true);
    try {
      if (isVerifiedByMe) {
        await unverifyCurrentScreenshot();
        toast.success("Your verification removed");
      } else {
        // Check if title is required and missing
        if (
          screenshot.image_type === "screen_time" &&
          !screenshot.extracted_title
        ) {
          toast.error("Cannot verify: App/Title is required");
          return;
        }
        // Check if bar total and OCR total mismatch
        // Skip check if grid reprocessing is in progress (values are stale)
        // Round each hourly value before summing — matches what the user sees in the UI
        if (!isProcessing && screenshot.extracted_total && annotation?.hourly_values) {
          const { parseOcrTotalMinutes, formatMinutes } = await import("@/utils/formatters");
          const ocrMinutes = parseOcrTotalMinutes(screenshot.extracted_total);
          const barTotal = Object.values(annotation.hourly_values).reduce((sum, v) => sum + Math.round(Number(v) || 0), 0);
          // Stricter threshold for verify dialog — warn on any mismatch >= 2 minutes
          if (ocrMinutes !== null && Math.abs(barTotal - ocrMinutes) >= 2) {
            const barStr = formatMinutes(barTotal);
            // Show modal and wait for user decision
            const proceed = await new Promise<boolean>((resolve) => {
              setMismatchInfo({ barStr, ocrStr: screenshot.extracted_total!, onConfirm: () => resolve(true), onCancel: () => resolve(false) });
            });
            setMismatchInfo(null);
            if (!proceed) return;
          }
        }
        await verifyCurrentScreenshot();
        toast.success("Screenshot verified by you");
      }
    } catch (error) {
      console.error("[handleVerificationToggle] Failed:", error);
      toast.error(isVerifiedByMe ? "Failed to remove verification" : "Failed to verify screenshot");
    } finally {
      setIsVerifying(false);
    }
  }, [
    screenshot,
    annotation,
    isVerifiedByMe,
    isVerifying,
    isProcessing,
    verifyCurrentScreenshot,
    unverifyCurrentScreenshot,
  ]);

  // Handler for changing processing status filter
  const handleProcessingStatusChange = useCallback(
    (newStatus: ProcessingStatus | "all") => {
      const searchParams = new URLSearchParams();
      if (groupId) searchParams.set("group", groupId);
      if (newStatus !== "all") searchParams.set("processing_status", newStatus);
      const search = searchParams.toString();
      navigate(`/annotate${search ? `?${search}` : ""}`, { replace: false });
    },
    [groupId, navigate]
  );

  useKeyboardShortcuts([
    {
      key: "Escape",
      handler: () => {
        if (!isLoading) skip();
      },
    },
    {
      key: "ArrowLeft",
      handler: () => {
        if (hasPrev) navigatePrev();
      },
    },
    {
      key: "ArrowRight",
      handler: () => {
        if (hasNext) navigateNext();
      },
    },
    {
      key: "v",
      handler: handleVerificationToggle,
    },
    {
      key: "p",
      handler: () => {
        if (!isVerifiedByMe) setPHIEditorOpen(true);
      },
    },
    {
      key: "c",
      handler: () => {
        if (!isVerifiedByMe) setCropEditorOpen(true);
      },
    },
  ]);

  if (noScreenshots) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center max-w-md">
          <div className="text-6xl mb-4">All Done!</div>
          <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-2">
            No Screenshots in Queue
          </h2>
          <p className="text-slate-600 dark:text-slate-400 mb-6">
            {groupId ? (
              <>No screenshots match the current filter for group <span className="font-semibold">{groupId}</span>.</>
            ) : (
              "No screenshots match the current filter."
            )}
          </p>

          {/* Filter controls */}
          <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-4 space-y-4 text-left">
            <div>
              <div className="text-xs text-slate-500 dark:text-slate-400 mb-2 font-medium">Processing Status</div>
              <ProcessingStatusFilter
                value={(processingStatus as FilterStatus) || "all"}
                onChange={handleProcessingStatusChange}
              />
            </div>
            <div>
              <div className="text-xs text-slate-500 dark:text-slate-400 mb-2 font-medium">Verification Status</div>
              <VerificationFilter
                value={verificationFilter}
                onChange={setVerificationFilter}
              />
            </div>
          </div>

          <div className="flex items-center justify-center gap-3 mt-6">
            <button
              onClick={() => navigate("/")}
              className="px-4 py-2 text-sm bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 rounded hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
            >
              Back to Groups
            </button>
            {!config.isLocalMode && (
              <Link
                to="/upload"
                className="px-4 py-2 text-sm bg-primary-600 text-white rounded hover:bg-primary-700 transition-colors"
              >
                Go to Upload
              </Link>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (!screenshot) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto mb-4"></div>
          <p className="text-slate-600 dark:text-slate-400">Loading screenshot...</p>
        </div>
      </div>
    );
  }

  const progressPercent = totalInFilter > 0 ? ((currentIndex + 1) / totalInFilter) * 100 : 0;

  return (
    <ErrorBoundary fallback={
      <div className="flex items-center justify-center h-96">
        <div className="text-center max-w-md p-6">
          <p className="text-xl font-bold text-slate-900 dark:text-slate-100 mb-2">Something went wrong</p>
          <p className="text-slate-600 dark:text-slate-400 mb-4">Try reloading the page.</p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-primary-600 text-white rounded hover:bg-primary-700"
          >
            Reload Page
          </button>
        </div>
      </div>
    }>
    <div className="flex flex-col h-full" role="main" aria-label="Annotation workspace" data-testid="annotation-workspace">
      {/* Progress bar */}
      {totalInFilter > 0 && (
        <div className="h-1 w-full bg-slate-200 dark:bg-slate-700 flex-shrink-0" title={`${currentIndex + 1} of ${totalInFilter}`}>
          <div
            className="h-full bg-primary-500 transition-all duration-300"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      )}
      {/* First-visit help banner */}
      {!helpDismissed && (
        <div className="flex items-center justify-between gap-2 px-3 py-2 bg-blue-50 dark:bg-blue-900/30 border-b border-blue-200 dark:border-blue-800 text-sm text-blue-800 dark:text-blue-200 flex-shrink-0">
          <span>Drag the blue grid to align with the bar graph. Review hourly values (0-60 min) and app title, then click Verify. Press <kbd className="px-1 py-0.5 text-xs font-mono bg-blue-100 dark:bg-blue-800 rounded">?</kbd> for shortcuts.</span>
          <button
            onClick={() => { setHelpDismissed(true); try { localStorage.setItem("annotation-help-dismissed", "1"); } catch { /* ignore */ } }}
            className="text-blue-600 dark:text-blue-300 hover:text-blue-800 dark:hover:text-blue-100 flex-shrink-0 p-0.5"
            aria-label="Dismiss help"
          >
            &#x2715;
          </button>
        </div>
      )}
      <div className="flex gap-1 flex-1 min-h-0">
      {/* Left Column - Grid Selector */}
      <div className="flex-1">
        <div className="bg-white dark:bg-slate-800 h-full p-1 flex items-center justify-center relative">
          <div className="w-full max-w-xl">
            {imageUrl ? (
              <GridSelector
                imageUrl={imageUrl}
                onGridSelect={handleGridSelect}
                initialCoords={gridCoords ?? undefined}
                disabled={isVerifiedByMe}
                imageType={screenshot.image_type}
                extractedTitle={screenshot.extracted_title}
                onTitleChange={setTitle}
                data-testid="grid-selector"
              />
            ) : (
              <Skeleton className="w-full aspect-[9/16] max-h-[70vh]" />
            )}
          </div>
        </div>
      </div>

      {/* Center Column - Cropped Graph + Hourly Bars */}
      <div className="flex-[2]">
        <div className="bg-white dark:bg-slate-800 h-full flex flex-col relative">
          {/* Screenshot metadata header */}
          <div className="bg-slate-100 dark:bg-slate-700 px-4 py-2 rounded-t text-sm flex-shrink-0 border-b border-slate-200 dark:border-slate-600 text-center space-y-1">
            <div className="flex items-center justify-center gap-4 text-slate-700 dark:text-slate-300">
              {screenshot.group_id && (
                <span><span className="font-semibold text-slate-500">Group:</span> {screenshot.group_id}</span>
              )}
              {processingStatus && (
                <span><span className="font-semibold text-slate-500">Subgroup:</span> <span className="capitalize">{processingStatus}</span></span>
              )}
              {screenshot.participant_id && (
                <span><span className="font-semibold text-slate-500">ID:</span> {screenshot.participant_id}</span>
              )}
              {screenshot.screenshot_date && (
                <span><span className="font-semibold text-slate-500">Date:</span> {screenshot.screenshot_date}</span>
              )}
              <span className="text-slate-400 font-mono">#{screenshot.id}</span>
            </div>
            {screenshot.original_filepath && (
              <div className="text-xs text-slate-600 dark:text-slate-400">
                <span className="font-semibold text-slate-500">Source:</span> {screenshot.original_filepath}
              </div>
            )}
          </div>
          {/* Preprocessing status banner */}
          {(() => {
            const pp = (screenshot.processing_metadata as Record<string, unknown>)?.preprocessing as Record<string, unknown> | undefined;
            const stageStatus = pp?.stage_status as Record<string, string> | undefined;
            if (!stageStatus) return null;
            const problemStages = Object.entries(stageStatus).filter(
              ([, st]) => st === "invalidated" || st === "failed",
            );
            if (problemStages.length === 0) return null;
            const stageNames = problemStages.map(([s]) => s.replace(/_/g, " ")).join(", ");
            return (
              <div className="bg-amber-50 border-b border-amber-200 px-4 py-2 text-sm flex items-center gap-2">
                <span className="text-amber-600">
                  Preprocessing issue: {stageNames} {problemStages.length === 1 ? "is" : "are"} {problemStages[0]![1]}.
                </span>
                <Link
                  to={`/preprocessing?screenshot_id=${screenshot.id}&returnUrl=${encodeURIComponent(`/annotate/${screenshot.id}`)}`}
                  className="text-primary-600 hover:text-primary-800 underline text-xs font-medium"
                >
                  Fix in Preprocessing &rarr;
                </Link>
              </div>
            );
          })()}
          {consensus && (
            <div className="bg-primary-50 dark:bg-primary-900/20 border-b border-primary-200 dark:border-primary-800 px-4 py-1.5 text-xs flex items-center gap-3">
              <span className="font-medium text-primary-700 dark:text-primary-400">
                Consensus ({consensus.total_annotations} annotations, {consensus.agreement_percentage}% agreement)
              </span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500" /> Agree</span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-yellow-500" /> Minor diff</span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500" /> Major diff</span>
            </div>
          )}
          <div className="flex-1 flex items-center justify-center p-4 min-h-0">
            <div className="w-full">
              {!imageUrl ? (
                <Skeleton className="w-full" height="12rem" />
              ) : displayMode === "overlay" ? (
                <HourlyUsageOverlay
                  data={hourlyValues}
                  onChange={updateHour}
                  imageUrl={imageUrl}
                  gridCoords={gridCoords}
                  {...(consensus ? { consensus } : {})}
                  readOnly={isVerifiedByMe}
                />
              ) : (
                <>
                  <CroppedGraphViewer
                    imageUrl={imageUrl}
                    gridCoords={gridCoords}
                    targetWidth={800}
                  />
                  <HourlyUsageEditor
                    data={hourlyValues}
                    onChange={updateHour}
                    readOnly={isVerifiedByMe}
                  />
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Right Column - Info Panel */}
      <div className="flex-1">
        <div className="bg-white dark:bg-slate-800 p-2 h-full flex items-center justify-center">
          <div className="w-full space-y-2 overflow-y-auto max-h-full px-1">
            {/* Screenshot Navigator */}
            <div className="border-b border-slate-100 dark:border-slate-700 pb-2">
              <ScreenshotSelector
                currentScreenshot={screenshot}
                screenshotList={screenshotList}
                currentIndex={currentIndex}
                totalInFilter={totalInFilter}
                hasNext={hasNext}
                hasPrev={hasPrev}
                onNavigateNext={navigateNext}
                onNavigatePrev={navigatePrev}
                onSelectScreenshot={loadById}
                onSearch={(search) => loadScreenshotList({ search })}
                onLoadMore={loadMoreScreenshots}
                isLoading={isLoading}
                currentUsername={username}
              />
            </div>

            {/* Filters */}
            <CollapsibleSection title="Filters" storageKey="annotation-filters">
              <div className="space-y-2">
                <div>
                  <div className="text-xs text-slate-500 dark:text-slate-400 mb-1">Status</div>
                  <ProcessingStatusFilter
                    value={(processingStatus as FilterStatus) || "all"}
                    onChange={handleProcessingStatusChange}
                  />
                </div>
                <div>
                  <div className="text-xs text-slate-500 dark:text-slate-400 mb-1">Verified</div>
                  <VerificationFilter
                    value={verificationFilter}
                    onChange={setVerificationFilter}
                  />
                </div>
              </div>
            </CollapsibleSection>

            {/* Alignment Score Warning */}
            <AlignmentWarning alignmentScore={screenshot.alignment_score} />

            {/* Preprocessing Summary */}
            <PreprocessingSummary
              processingMetadata={screenshot.processing_metadata}
              onEditPHI={() => setPHIEditorOpen(true)}
              onEditCrop={() => setCropEditorOpen(true)}
            />

            {/* Tools — always visible so users discover PHI redaction / crop adjustment */}
            <CollapsibleSection title="Tools (P / C)" storageKey="annotation-tools">
              <div className="flex gap-1">
                <button
                  onClick={() => setPHIEditorOpen(true)}
                  disabled={isVerifiedByMe}
                  className="flex-1 px-2 py-1.5 text-xs font-medium border border-red-200 dark:border-red-800 rounded bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/30 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-1"
                  title="Review and redact personal health information (P)"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                  </svg>
                  Redact PHI
                </button>
                <button
                  onClick={() => setCropEditorOpen(true)}
                  disabled={isVerifiedByMe}
                  className="flex-1 px-2 py-1.5 text-xs font-medium border border-purple-200 dark:border-purple-800 rounded bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-400 hover:bg-purple-100 dark:hover:bg-purple-900/30 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-1"
                  title="Adjust the crop boundaries (C)"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                  Adjust Crop
                </button>
              </div>
            </CollapsibleSection>

            {/* Totals Display */}
            <TotalsDisplay
              ocrTotal={screenshot.extracted_total}
              hourlyData={hourlyValues}
              isProcessing={isProcessing}
              onRecalculateOcr={handleRecalculateOcr}
              isRecalculatingOcr={isRecalculatingOcr}
              showRecalculateButton={
                !isVerifiedByMe && screenshot.image_type === "screen_time"
              }
            />

            {/* View Mode Toggle */}
            <CollapsibleSection title="View Mode" storageKey="annotation-view-mode">
              <div className="flex gap-1">
                <button
                  onClick={() => setDisplayMode("overlay")}
                  className={`flex-1 px-2 py-1 text-xs rounded ${
                    displayMode === "overlay"
                      ? "bg-primary-600 text-white"
                      : "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600"
                  }`}
                >
                  Overlay
                </button>
                <button
                  onClick={() => setDisplayMode("separate")}
                  className={`flex-1 px-2 py-1 text-xs rounded ${
                    displayMode === "separate"
                      ? "bg-primary-600 text-white"
                      : "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600"
                  }`}
                >
                  Separate
                </button>
              </div>
            </CollapsibleSection>

            {/* Potential Duplicate Warning */}
            {screenshot?.potential_duplicate_of && (
              <div className="border-b border-slate-100 dark:border-slate-700 pb-2">
                <DuplicateWarning
                  duplicateId={screenshot.potential_duplicate_of}
                  duplicateStatus={(screenshot as Record<string, unknown>).duplicate_status as string | null}
                  onSkipThis={async () => {
                    await skip();
                  }}
                  onGoToDuplicate={() => {
                    if (screenshot?.potential_duplicate_of) {
                      loadById(screenshot.potential_duplicate_of);
                    }
                  }}
                  isLoading={isLoading}
                />
              </div>
            )}

            {/* Issues */}
            {processingIssues && processingIssues.length > 0 && (
              <div className="border-b border-slate-100 dark:border-slate-700 pb-2">
                <IssueDisplay issues={processingIssues} />
              </div>
            )}

            {/* Reprocessing Buttons */}
            <CollapsibleSection title="Reprocess Grid" storageKey="annotation-reprocess" defaultOpen={false}>
              <div className={isVerifiedByMe ? "opacity-50" : ""}>
              <div className="flex gap-1">
                <button
                  onClick={() => handleReprocess("ocr_anchored")}
                  disabled={
                    isVerifiedByMe || reprocessingMethod !== null || isLoading
                  }
                  className={`flex-1 py-2 px-2 text-xs border rounded flex items-center justify-center gap-1 ${
                    screenshot?.processing_method === "ocr_anchored"
                      ? "bg-purple-100 text-purple-800 border-purple-300"
                      : "bg-purple-50 text-purple-700 border-purple-200 hover:bg-purple-100"
                  } disabled:opacity-50 disabled:cursor-not-allowed`}
                  title={
                    isVerifiedByMe
                      ? "Unverify to reprocess"
                      : "Reprocess using OCR text anchors"
                  }
                >
                  {reprocessingMethod === "ocr_anchored" ? (
                    <div className="animate-spin h-3 w-3 border-2 border-purple-600 border-t-transparent rounded-full" />
                  ) : (
                    <svg
                      className="w-3 h-3"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                      />
                    </svg>
                  )}
                  OCR
                </button>
                <button
                  onClick={() => handleReprocess("line_based")}
                  disabled={
                    isVerifiedByMe || reprocessingMethod !== null || isLoading
                  }
                  className={`flex-1 py-2 px-2 text-xs border rounded flex items-center justify-center gap-1 ${
                    screenshot?.processing_method === "line_based"
                      ? "bg-primary-100 text-primary-800 border-primary-300"
                      : "bg-primary-50 text-primary-700 border-primary-200 hover:bg-primary-100"
                  } disabled:opacity-50 disabled:cursor-not-allowed`}
                  title={
                    isVerifiedByMe
                      ? "Unverify to reprocess"
                      : "Reprocess using visual line detection"
                  }
                >
                  {reprocessingMethod === "line_based" ? (
                    <div className="animate-spin h-3 w-3 border-2 border-primary-600 border-t-transparent rounded-full" />
                  ) : (
                    <svg
                      className="w-3 h-3"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                      />
                    </svg>
                  )}
                  Lines
                </button>
              </div>
              <div className="text-xs text-slate-400 dark:text-slate-500 mt-1 text-center">
                {isVerifiedByMe
                  ? "Verified (read-only)"
                  : screenshot?.processing_method
                    ? `Current: ${screenshot.processing_method === "ocr_anchored" ? "OCR" : screenshot.processing_method === "line_based" ? "Lines" : screenshot.processing_method}`
                    : "Click to detect grid"}
              </div>
              </div>
            </CollapsibleSection>

            {/* Notes */}
            <CollapsibleSection title="Notes" storageKey="annotation-notes" defaultOpen={false}>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full px-2 py-1 border border-slate-300 dark:border-slate-600 rounded text-sm focus:outline-none focus:ring-1 focus:ring-primary-500 resize-none dark:bg-slate-700 dark:text-slate-200"
                placeholder="Optional notes..."
                rows={2}
              />
            </CollapsibleSection>

            {/* Action Buttons */}
            <div className="pt-2 space-y-2">
              {/* Verify Button */}
              {(() => {
                const isMissingTitle =
                  screenshot.image_type === "screen_time" &&
                  !screenshot.extracted_title;
                const canVerify = !isMissingTitle || isVerifiedByMe;
                return (
                  <button
                    onClick={handleVerificationToggle}
                    disabled={!canVerify || isVerifying}
                    data-testid={isVerifiedByMe ? "unverify-button" : "verify-button"}
                    aria-label={isVerifiedByMe ? "Remove verification" : "Mark screenshot as verified"}
                    title={
                      isMissingTitle && !isVerifiedByMe
                        ? "Cannot verify: App/Title is required"
                        : undefined
                    }
                    className={`w-full py-2 text-sm font-medium rounded transition-colors ${
                      isVerifiedByMe
                        ? "bg-green-600 text-white hover:bg-green-700"
                        : canVerify
                          ? "bg-green-100 text-green-700 hover:bg-green-200 border border-green-300 dark:bg-green-900/20 dark:text-green-400 dark:hover:bg-green-900/30 dark:border-green-700"
                          : "bg-slate-100 text-slate-400 border border-slate-200 cursor-not-allowed dark:bg-slate-700 dark:text-slate-500 dark:border-slate-600"
                    }`}
                  >
                    {isVerifying
                      ? "Verifying..."
                      : isVerifiedByMe
                        ? "Verified (V to undo)"
                        : isMissingTitle
                          ? "Title required to verify"
                          : "Mark as Verified (V)"}
                  </button>
                );
              })()}

              {/* Verifiers Info */}
              {allVerifierUsernames.length > 0 && (
                <div className="text-xs text-center text-primary-700 bg-primary-50 rounded py-1">
                  Verified by: {allVerifierUsernames.join(", ")}
                </div>
              )}

              {/* Skip Button with reasons dropdown */}
              <div className="relative" ref={skipMenuRef}>
                <div className="flex">
                  <button
                    onClick={() => skip()}
                    disabled={isLoading}
                    className="flex-1 py-2 text-sm bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-l hover:bg-slate-200 dark:hover:bg-slate-600 disabled:opacity-50"
                    aria-label="Skip this screenshot"
                    title="Skip this screenshot"
                  >
                    Skip (Esc)
                  </button>
                  <button
                    onClick={() => setSkipMenuOpen((o) => !o)}
                    disabled={isLoading}
                    className="px-2 py-2 text-sm bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-r border-l border-slate-200 dark:border-slate-600 hover:bg-slate-200 dark:hover:bg-slate-600 disabled:opacity-50"
                    title="Skip with reason"
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                  </button>
                </div>
                {skipMenuOpen && (
                  <div className="absolute bottom-full left-0 right-0 mb-1 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded shadow-lg z-20">
                    {["Duplicate", "Bad quality", "Wrong type", "Daily total", "Other"].map((reason) => (
                      <button
                        key={reason}
                        onClick={() => { setSkipMenuOpen(false); skip(reason.toLowerCase().replace(/ /g, "_")); }}
                        className="w-full text-left px-3 py-1.5 text-xs text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 first:rounded-t last:rounded-b"
                      >
                        {reason}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Auto-save Status */}
              <SaveStatusIndicator
                isSaving={isSaving}
                lastSaved={lastSaved}
                timeSinceLastSave={timeSinceLastSave}
                saveFailCount={saveFailCount}
                lastError={lastError}
                hasUnsavedChanges={hasUnsavedChanges}
                onRetry={retrySave}
              />

              <div className="text-xs text-slate-400 dark:text-slate-500 text-center space-y-1">
                <div>
                  <strong>←/→</strong> navigate | <strong>V</strong> verify |{" "}
                  <strong>Esc</strong> skip | <strong>P</strong> PHI |{" "}
                  <strong>C</strong> crop
                </div>
                <div>
                  <strong>WASD</strong> move grid | <strong>Shift+WASD</strong>{" "}
                  move 10px | <strong>Ctrl+WASD</strong> resize
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      {/* PHI Region Editor Modal */}
      {screenshot && (
        <PHIRegionEditor
          key={`phi-${screenshot.id}`}
          screenshotId={screenshot.id}
          isOpen={phiEditorOpen}
          onClose={() => setPHIEditorOpen(false)}
          onRegionsSaved={() => {
            setPHIEditorOpen(false);
            loadById(screenshot.id);
          }}
          onRedactionApplied={() => {
            setPHIEditorOpen(false);
            loadById(screenshot.id);
            setImageRefreshKey((k) => k + 1);
          }}
        />
      )}

      {/* Crop Adjust Modal */}
      {screenshot && (
        <CropAdjustModal
          key={`crop-${screenshot.id}`}
          screenshotId={screenshot.id}
          isOpen={cropEditorOpen}
          onClose={() => setCropEditorOpen(false)}
          onCropApplied={() => {
            setCropEditorOpen(false);
            loadById(screenshot.id);
            setImageRefreshKey((k) => k + 1);
          }}
          initialCrop={getCropRectFromEvent(getCurrentEvent(screenshot, "cropping"))}
        />
      )}
      {/* Shortcuts hint */}
      {!shortcutsHintDismissed && (
        <button
          onClick={() => { setShortcutsHintDismissed(true); try { localStorage.setItem("shortcuts-hint-dismissed", "1"); } catch { /* ignore */ } }}
          className="fixed bottom-4 right-4 text-xs text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
        >
          Press ? for shortcuts
        </button>
      )}
      </div>
    </div>
    {/* Totals mismatch confirmation modal */}
    <Modal
      open={!!mismatchInfo}
      onOpenChange={(open) => { if (!open) mismatchInfo?.onCancel(); }}
      title="Totals Mismatch"
      size="sm"
    >
      {mismatchInfo && (
        <>
          <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">
            The bar total <span className="font-semibold text-slate-900 dark:text-slate-100">{mismatchInfo.barStr}</span> doesn&apos;t
            match the OCR total <span className="font-semibold text-slate-900 dark:text-slate-100">{mismatchInfo.ocrStr}</span>.
          </p>
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">
            You may want to adjust the grid position first. Verify anyway?
          </p>
          <div className="flex justify-end gap-3">
            <button
              onClick={mismatchInfo.onCancel}
              className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-700 rounded-md hover:bg-slate-200 dark:hover:bg-slate-600"
            >
              Go Back
            </button>
            <button
              onClick={mismatchInfo.onConfirm}
              className="px-4 py-2 text-sm font-medium text-white bg-amber-600 rounded-md hover:bg-amber-700"
            >
              Verify Anyway
            </button>
          </div>
        </>
      )}
    </Modal>
    </ErrorBoundary>
  );
};
