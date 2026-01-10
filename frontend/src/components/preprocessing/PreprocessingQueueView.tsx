import { useEffect, useMemo, useState } from "react";
import { usePreprocessingStore, useScreenshotImageUrl } from "@/hooks/usePreprocessingWithDI";
import { QueueNavigationBar } from "./QueueNavigationBar";
import { config } from "@/config";
import { PHIRegionEditor } from "./PHIRegionEditor";
import { CropAdjustModal } from "./CropAdjustModal";
import { getCurrentEvent } from "./StageReviewTable";
import { getCropRectFromEvent } from "./CroppingTab";
import { getRecentCropConfigs, getRecentPHIConfigs } from "./recentConfigHelpers";
import type { PreprocessingEventData } from "@/store/preprocessingStore";
import type { Screenshot } from "@/types";
import { Skeleton } from "@/components/ui/Skeleton";

export const PreprocessingQueueView = () => {
  const queueIndex = usePreprocessingStore((s) => s.queueIndex);
  const queueScreenshotIds = usePreprocessingStore((s) => s.queueScreenshotIds);
  const queueNext = usePreprocessingStore((s) => s.queueNext);
  const queuePrev = usePreprocessingStore((s) => s.queuePrev);
  const exitQueue = usePreprocessingStore((s) => s.exitQueue);
  const activeStage = usePreprocessingStore((s) => s.activeStage);
  const screenshots = usePreprocessingStore((s) => s.screenshots);
  const loadScreenshots = usePreprocessingStore((s) => s.loadScreenshots);
  const loadSummary = usePreprocessingStore((s) => s.loadSummary);

  const currentId = queueScreenshotIds[queueIndex];
  const currentScreenshot = useMemo(
    () => screenshots.find((s) => s.id === currentId),
    [screenshots, currentId],
  );

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't intercept when user is typing in inputs
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      if (e.key === "ArrowLeft") {
        e.preventDefault();
        queuePrev();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        queueNext();
      } else if (e.key === "Escape") {
        e.preventDefault();
        exitQueue();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [queuePrev, queueNext, exitQueue]);

  // Prefetch next 3 screenshots' images (all variants) into browser cache
  useEffect(() => {
    if (!config.apiBaseUrl) return;
    const prefetchIds = queueScreenshotIds.slice(queueIndex + 1, queueIndex + 4);
    for (const id of prefetchIds) {
      new Image().src = `${config.apiBaseUrl}/screenshots/${id}/image`;
      new Image().src = `${config.apiBaseUrl}/screenshots/${id}/stage-image?stage=cropping`;
      new Image().src = `${config.apiBaseUrl}/screenshots/${id}/original-image`;
    }
  }, [queueIndex, queueScreenshotIds]);

  const [imageRefreshKey, setImageRefreshKey] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const handleRefresh = () => {
    setIsRefreshing(true);
    Promise.all([
      loadScreenshots().catch((e) => console.error("Failed to load screenshots:", e)),
      loadSummary().catch((e) => console.error("Failed to load summary:", e)),
    ]).finally(() => setIsRefreshing(false));
    setImageRefreshKey((k) => k + 1);
  };

  // Hooks must be called unconditionally — compute all derived values here
  const initialCrop = useMemo(
    () => currentScreenshot ? getCropRectFromEvent(getCurrentEvent(currentScreenshot, "cropping")) : undefined,
    [currentScreenshot],
  );

  const recentCrops = useMemo(
    () => currentScreenshot ? getRecentCropConfigs(screenshots, currentScreenshot.id) : [],
    [screenshots, currentScreenshot],
  );

  const recentPHIConfigs = useMemo(
    () => currentScreenshot ? getRecentPHIConfigs(screenshots, currentScreenshot.id) : [],
    [screenshots, currentScreenshot],
  );

  if (!currentScreenshot) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-slate-400 dark:text-slate-500">
        <p>Screenshot not found</p>
        <button
          onClick={exitQueue}
          className="mt-4 px-4 py-2 text-sm border border-slate-300 dark:border-slate-600 rounded-md hover:bg-slate-50 dark:hover:bg-slate-700 dark:text-slate-300"
        >
          Back to Table
        </button>
      </div>
    );
  }

  const event = getCurrentEvent(currentScreenshot, activeStage);

  // Show image_write_failed warning if present in preprocessing metadata
  const ppMeta = (currentScreenshot.processing_metadata as Record<string, unknown>)?.preprocessing as Record<string, unknown> | undefined;
  const imageWriteFailed = ppMeta?.image_write_failed === true;

  // Refreshing indicator bar shown below QueueNavigationBar
  const refreshingBar = isRefreshing ? (
    <div className="h-0.5 w-full bg-primary-200 dark:bg-primary-800 overflow-hidden flex-shrink-0">
      <div className="h-full w-1/3 bg-primary-500 animate-[slide_1s_ease-in-out_infinite]" style={{ animation: "slide 1s ease-in-out infinite" }} />
      <style>{`@keyframes slide { 0% { transform: translateX(-100%); } 100% { transform: translateX(400%); } }`}</style>
    </div>
  ) : null;

  // Warning badge for image_write_failed
  const imageWriteFailedBanner = imageWriteFailed ? (
    <div className="bg-amber-50 dark:bg-amber-900/20 border-b border-amber-200 dark:border-amber-800 px-4 py-1.5 text-xs flex items-center gap-2 flex-shrink-0">
      <svg className="w-4 h-4 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
      <span className="text-amber-700 dark:text-amber-400 font-medium">Image write failed</span>
      <span className="text-amber-600 dark:text-amber-500">— the processed image could not be saved. Results may be stale.</span>
    </div>
  ) : null;

  if (activeStage === "device_detection") {
    return (
      <div className="flex flex-col h-[calc(100vh-8rem)]">
        <QueueNavigationBar currentScreenshot={currentScreenshot} />
        {refreshingBar}
        {imageWriteFailedBanner}
        <DeviceInfoPanel screenshot={currentScreenshot} event={event} refreshKey={imageRefreshKey} />
      </div>
    );
  }

  if (activeStage === "cropping") {
    return (
      <div className="flex flex-col h-[calc(100vh-8rem)]">
        <QueueNavigationBar currentScreenshot={currentScreenshot} />
        {refreshingBar}
        {imageWriteFailedBanner}
        <div className="flex-1 min-h-0">
          <CropAdjustModal
            screenshotId={currentScreenshot.id}
            isOpen={false}
            onClose={() => {}}
            onCropApplied={handleRefresh}
            initialCrop={initialCrop}
            inline
            onApplyAndNext={() => {
              handleRefresh();
              queueNext();
            }}
            recentCrops={recentCrops}
          />
        </div>
      </div>
    );
  }

  if (activeStage === "phi_detection") {
    return (
      <div className="flex flex-col h-[calc(100vh-8rem)]">
        <QueueNavigationBar currentScreenshot={currentScreenshot} />
        {refreshingBar}
        {imageWriteFailedBanner}
        <div className="flex-1 min-h-0">
          <PHIRegionEditor
            screenshotId={currentScreenshot.id}
            isOpen={false}
            onClose={() => {}}
            onRegionsSaved={handleRefresh}
            onRedactionApplied={handleRefresh}
            inline
            onSaveAndNext={() => {
              queueNext();
              // Refresh data in the background (don't block navigation)
              void loadScreenshots();
              void loadSummary();
            }}
            recentPHIConfigs={recentPHIConfigs}
          />
        </div>
      </div>
    );
  }

  if (activeStage === "phi_redaction") {
    const redactEvent = getCurrentEvent(currentScreenshot, "phi_redaction");
    const phiEvent = getCurrentEvent(currentScreenshot, "phi_detection");
    return (
      <div className="flex flex-col h-[calc(100vh-8rem)]">
        <QueueNavigationBar currentScreenshot={currentScreenshot} />
        {refreshingBar}
        {imageWriteFailedBanner}
        <div className="flex-1 min-h-0">
          <RedactionReviewPanel
            screenshot={currentScreenshot}
            redactEvent={redactEvent}
            phiEvent={phiEvent}
            onNext={queueNext}
            refreshKey={imageRefreshKey}
          />
        </div>
      </div>
    );
  }

  if (activeStage === "ocr") {
    return (
      <div className="flex flex-col h-[calc(100vh-8rem)]">
        <QueueNavigationBar currentScreenshot={currentScreenshot} />
        {refreshingBar}
        {imageWriteFailedBanner}
        <div className="flex-1 min-h-0">
          <OCRReviewPanel
            screenshot={currentScreenshot}
            event={event}
            onNext={queueNext}
            refreshKey={imageRefreshKey}
          />
        </div>
      </div>
    );
  }

  return null;
};

/** Read-only panel for device detection stage — shows image + metadata */
function DeviceInfoPanel({
  screenshot,
  event,
  refreshKey,
}: {
  screenshot: { id: number; participant_id?: string | null; device_type?: string | null };
  event: PreprocessingEventData | null;
  refreshKey?: number;
}) {
  const result = event?.result as Record<string, unknown> | undefined;
  const imageUrl = useScreenshotImageUrl(screenshot.id, "getImageUrl", undefined, refreshKey);

  return (
    <div className="flex-1 flex overflow-hidden bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 min-h-0">
      {/* Image */}
      <div className="flex-1 min-h-0 min-w-0 overflow-hidden flex items-center justify-center p-4">
        {imageUrl ? (
          <img
            src={imageUrl}
            alt={`Screenshot ${screenshot.id}`}
            style={{ maxHeight: "calc(100vh - 14rem)" }}
            className="max-w-full object-contain rounded"
          />
        ) : (
          <Skeleton className="w-48 h-64" />
        )}
      </div>

      {/* Metadata sidebar */}
      <div className="w-72 border-l dark:border-slate-700 p-4 space-y-4 overflow-y-auto">
        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Device Detection</h3>

        {result ? (
          <div className="space-y-3 text-sm">
            <div>
              <span className="text-slate-500 dark:text-slate-400">Category:</span>{" "}
              <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                result.device_category === "ipad"
                  ? "bg-primary-100 text-primary-700"
                  : result.device_category === "iphone"
                    ? "bg-green-100 text-green-700"
                    : "bg-slate-100 text-slate-600"
              }`}>
                {result.device_category as string}
              </span>
            </div>
            <div>
              <span className="text-slate-500 dark:text-slate-400">Model:</span>{" "}
              <span className="text-slate-700 dark:text-slate-300">{(result.device_model as string) || "\u2014"}</span>
            </div>
            <div>
              <span className="text-slate-500 dark:text-slate-400">Confidence:</span>{" "}
              <span className={`font-mono ${
                (result.confidence as number) >= 0.9
                  ? "text-green-600"
                  : (result.confidence as number) >= 0.7
                    ? "text-yellow-600"
                    : "text-red-600"
              }`}>
                {Math.round((result.confidence as number) * 100)}%
              </span>
            </div>
            {result.orientation ? (
              <div>
                <span className="text-slate-500 dark:text-slate-400">Orientation:</span>{" "}
                <span className="text-slate-700 dark:text-slate-300">{String(result.orientation)}</span>
              </div>
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-slate-400">No detection data available</p>
        )}
      </div>
    </div>
  );
}

/** Before/after panel for redaction review — shows final redacted image + metadata */
function RedactionReviewPanel({
  screenshot,
  redactEvent,
  phiEvent,
  onNext,
  refreshKey,
}: {
  screenshot: Screenshot;
  redactEvent: PreprocessingEventData | null;
  phiEvent: PreprocessingEventData | null;
  onNext: () => void;
  refreshKey?: number;
}) {
  const redactResult = redactEvent?.result as Record<string, unknown> | undefined;
  const phiResult = phiEvent?.result as Record<string, unknown> | undefined;
  const regions = (phiResult?.regions ?? []) as Array<Record<string, unknown>>;
  const wasRedacted = redactResult?.redacted === true;
  const regionsRedacted = (redactResult?.regions_redacted as number) ?? 0;
  const method = (redactResult?.method as string) ?? "unknown";

  const afterUrl = useScreenshotImageUrl(screenshot.id, "getImageUrl", undefined, refreshKey);
  const beforeUrl = useScreenshotImageUrl(screenshot.id, "getStageImageUrl", "cropping", refreshKey);

  const [view, setView] = useState<"after" | "before">("after");
  const activeUrl = view === "after" ? afterUrl : beforeUrl;

  return (
    <div className="flex-1 flex overflow-hidden bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 min-h-0">
      {/* Image area */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        {/* Before/After toggle */}
        {wasRedacted && (
          <div className="flex items-center gap-2 px-4 py-2 border-b dark:border-slate-700 bg-slate-50 dark:bg-slate-700/50 shrink-0">
            <span className="text-xs text-slate-500 mr-1">View:</span>
            <button
              onClick={() => setView("after")}
              className={`px-3 py-1 text-xs rounded font-medium ${
                view === "after"
                  ? "bg-orange-100 text-orange-700 ring-1 ring-orange-300"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              Redacted
            </button>
            <button
              onClick={() => setView("before")}
              className={`px-3 py-1 text-xs rounded font-medium ${
                view === "before"
                  ? "bg-primary-100 text-primary-700 ring-1 ring-primary-300"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              Original
            </button>
          </div>
        )}

        <div className="flex-1 min-h-0 overflow-hidden flex items-center justify-center p-4">
          {activeUrl ? (
            <img
              src={activeUrl}
              alt={`Screenshot ${screenshot.id} — ${view === "after" ? "redacted" : "original"}`}
              style={{ maxHeight: "calc(100vh - 15rem)" }}
              className="max-w-full object-contain rounded"
            />
          ) : (
            <Skeleton className="w-48 h-64" />
          )}
        </div>
      </div>

      {/* Sidebar */}
      <div className="w-72 border-l dark:border-slate-700 flex flex-col">
        <div className="p-4 space-y-4 flex-1 overflow-y-auto">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Redaction Result</h3>

          <div className="space-y-3 text-sm">
            <div>
              <span className="text-slate-500 dark:text-slate-400">Status:</span>{" "}
              {wasRedacted ? (
                <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-700">
                  Redacted
                </span>
              ) : (
                <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-600">
                  No redaction needed
                </span>
              )}
            </div>
            <div>
              <span className="text-slate-500 dark:text-slate-400">Regions redacted:</span>{" "}
              <span className="font-mono">{regionsRedacted}</span>
            </div>
            <div>
              <span className="text-slate-500 dark:text-slate-400">Method:</span>{" "}
              <span className="text-slate-700 dark:text-slate-300">{method}</span>
            </div>
          </div>

          {/* Region list from phi_detection */}
          {regions.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-2">PHI Regions</h4>
              <div className="space-y-1">
                {regions.map((r, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs p-1.5 rounded bg-slate-50 dark:bg-slate-700/50">
                    <span className="font-mono text-slate-400 w-4">{i + 1}</span>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                      String(r.source) === "manual" ? "bg-primary-100 text-primary-600" : "bg-red-100 text-red-600"
                    }`}>
                      {String(r.label || r.type || "?")}
                    </span>
                    <span className="text-slate-500 truncate flex-1" title={String(r.text || "")}>
                      {String(r.text || "\u2014")}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {!redactEvent && (
            <p className="text-sm text-slate-400">Redaction has not been run yet for this screenshot.</p>
          )}
        </div>

        {/* Footer */}
        <div className="p-3 border-t dark:border-slate-700 space-y-2">
          <button
            onClick={() => onNext()}
            className="w-full px-3 py-2 text-xs font-medium text-white bg-green-600 rounded hover:bg-green-700"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

/** Read-only panel for OCR stage — shows image + extracted data */
function OCRReviewPanel({
  screenshot,
  event,
  onNext,
  refreshKey,
}: {
  screenshot: Screenshot;
  event: PreprocessingEventData | null;
  onNext: () => void;
  refreshKey?: number;
}) {
  const result = event?.result as Record<string, unknown> | undefined;
  const imageUrl = useScreenshotImageUrl(screenshot.id, "getImageUrl", undefined, refreshKey);
  const status = result?.processing_status as string | undefined;
  const issues = (result?.issues as Array<string | { issue_type?: string; severity?: string; description?: string; message?: string }>) ?? [];

  return (
    <div className="flex-1 flex overflow-hidden bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 min-h-0">
      {/* Image */}
      <div className="flex-1 min-h-0 min-w-0 overflow-hidden flex items-center justify-center p-4">
        {imageUrl ? (
          <img
            src={imageUrl}
            alt={`Screenshot ${screenshot.id}`}
            style={{ maxHeight: "calc(100vh - 14rem)" }}
            className="max-w-full object-contain rounded"
          />
        ) : (
          <Skeleton className="w-48 h-64" />
        )}
      </div>

      {/* Metadata sidebar */}
      <div className="w-72 border-l dark:border-slate-700 flex flex-col">
        <div className="p-4 space-y-4 flex-1 overflow-y-auto">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">OCR Results</h3>

          {result ? (
            <div className="space-y-3 text-sm">
              <div>
                <span className="text-slate-500 dark:text-slate-400">Status:</span>{" "}
                {status === "completed" ? (
                  <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                    Completed
                  </span>
                ) : status === "failed" ? (
                  <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400">
                    Failed
                  </span>
                ) : (
                  <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-700">
                    {status ?? "Unknown"}
                  </span>
                )}
              </div>
              <div>
                <span className="text-slate-500 dark:text-slate-400">Method:</span>{" "}
                <span className="text-slate-700 dark:text-slate-300">
                  {(result.processing_method as string) || "\u2014"}
                </span>
              </div>
              <div>
                <span className="text-slate-500 dark:text-slate-400">Title:</span>{" "}
                <span className="text-slate-700 dark:text-slate-300 font-mono text-xs">
                  {(result.extracted_title as string) || "\u2014"}
                </span>
              </div>
              <div>
                <span className="text-slate-500 dark:text-slate-400">Total:</span>{" "}
                <span className="text-slate-700 dark:text-slate-300 font-mono text-xs">
                  {(result.extracted_total as string) || "\u2014"}
                </span>
              </div>
              {issues.length > 0 && (
                <div>
                  <span className="text-slate-500 dark:text-slate-400">Issues:</span>
                  <ul className="mt-1 space-y-1">
                    {issues.map((issue, i) => (
                      <li key={i} className="text-xs text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 rounded px-2 py-1">
                        {typeof issue === "string" ? issue : (issue.description || issue.message || issue.issue_type || JSON.stringify(issue))}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-slate-400">OCR has not been run yet for this screenshot.</p>
          )}
        </div>

        {/* Footer */}
        <div className="p-3 border-t dark:border-slate-700 space-y-2">
          <button
            onClick={() => onNext()}
            className="w-full px-3 py-2 text-xs font-medium text-white bg-green-600 rounded hover:bg-green-700"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
