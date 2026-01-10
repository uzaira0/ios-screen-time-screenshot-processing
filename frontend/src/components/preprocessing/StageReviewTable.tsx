import { memo, useCallback, useEffect, useMemo, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { usePreprocessingStore, useScreenshotImageUrl } from "@/hooks/usePreprocessingWithDI";
import type { Stage, StageStatus, PreprocessingEventData } from "@/store/preprocessingStore";
import type { Screenshot } from "@/types";
import { Skeleton } from "@/components/ui/Skeleton";

type SortDirection = "asc" | "desc";

export interface ResultHeader {
  label: string;
  /** If provided, column is sortable. This key is passed to getResultSortValue. */
  sortKey?: string;
}

interface StageReviewTableProps {
  stage: Stage;
  renderResultColumns: (screenshot: Screenshot, event: PreprocessingEventData | null) => React.ReactNode;
  resultHeaders: ResultHeader[];
  /** Return a comparable value for a result column. Strings are compared via localeCompare, numbers numerically. */
  getResultSortValue?: (screenshot: Screenshot, event: PreprocessingEventData | null, sortKey: string) => string | number | null;
}

const STATUS_BADGES: Record<StageStatus, { label: string; classes: string }> = {
  completed: { label: "Done", classes: "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400" },
  invalidated: { label: "Invalidated", classes: "bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-400" },
  pending: { label: "Pending", classes: "bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400" },
  running: { label: "Running", classes: "bg-primary-100 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400" },
  failed: { label: "Failed", classes: "bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400" },
  cancelled: { label: "Cancelled", classes: "bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400" },
};

const STATUS_SORT_ORDER: Record<StageStatus, number> = {
  running: 0,
  failed: 1,
  pending: 2,
  invalidated: 3,
  cancelled: 4,
  completed: 5,
};

export function getCurrentEvent(screenshot: Screenshot, stage: Stage): PreprocessingEventData | null {
  const pp = (screenshot.processing_metadata as Record<string, unknown>)?.preprocessing as Record<string, unknown> | undefined;
  if (!pp) return null;
  const currentEvents = pp.current_events as Record<string, number | null> | undefined;
  const events = pp.events as PreprocessingEventData[] | undefined;
  if (!currentEvents || !events) return null;
  const eid = currentEvents[stage];
  if (!eid) return null;
  return events.find((e) => e.event_id === eid) ?? null;
}

function SortIcon({ column, sortColumn, sortDirection }: { column: string; sortColumn: string; sortDirection: SortDirection }) {
  if (column !== sortColumn) {
    return <span className="text-slate-300 ml-1">&#8597;</span>;
  }
  return <span className="text-primary-600 ml-1">{sortDirection === "asc" ? "\u25B2" : "\u25BC"}</span>;
}

const ROW_HEIGHT = 56; // px — matches py-2 + h-14 thumbnail

interface RowProps {
  screenshot: Screenshot;
  stage: Stage;
  status: StageStatus;
  isException: boolean;
  event: PreprocessingEventData | null;
  isHighlighted: boolean;
  highlightedRef: React.Ref<HTMLTableRowElement>;
  onEnterQueue: (screenshotId: number) => void;
  onLoadLog: (id: number) => void;
  renderResultColumns: (screenshot: Screenshot, event: PreprocessingEventData | null) => React.ReactNode;
  imageVersion: number;
}

const TableRow = memo(function TableRow({
  screenshot,
  status,
  isException,
  event,
  isHighlighted,
  highlightedRef,
  onEnterQueue,
  onLoadLog,
  renderResultColumns,
  imageVersion,
}: RowProps) {
  const badge = STATUS_BADGES[status] ?? STATUS_BADGES.pending;
  const imageUrl = useScreenshotImageUrl(screenshot.id, "getImageUrl", undefined, imageVersion);
  const ppMeta = (screenshot.processing_metadata as Record<string, unknown>)?.preprocessing as Record<string, unknown> | undefined;
  const imageWriteFailed = ppMeta?.image_write_failed === true;
  return (
    <tr
      ref={isHighlighted ? highlightedRef : undefined}
      className={`border-b border-slate-100 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/50 ${
        isHighlighted ? "bg-primary-50 dark:bg-primary-900/20 ring-2 ring-primary-300" : ""
      } ${isException ? "bg-yellow-50 dark:bg-yellow-900/20" : ""} ${
        status === "invalidated" ? "bg-orange-50/40 dark:bg-orange-900/20" : ""
      }`}
    >
      <td className="px-3 py-2">
        <button
          onClick={() => onEnterQueue(screenshot.id)}
          className="block cursor-pointer hover:ring-2 hover:ring-primary-300 rounded transition-shadow"
          title="Open in review queue"
          aria-label={`Review screenshot ${screenshot.id} in queue`}
        >
          {imageUrl ? (
            <img
              src={imageUrl}
              alt={`Screenshot ${screenshot.id}`}
              className="w-10 h-14 object-cover rounded bg-slate-200"
              loading="lazy"
              onError={(e) => { e.currentTarget.src = ""; }}
            />
          ) : (
            <Skeleton className="w-10 h-14" />
          )}
        </button>
      </td>
      <td className="px-3 py-2 font-mono text-slate-600 dark:text-slate-400">{screenshot.id}</td>
      <td className="px-3 py-2">{screenshot.participant_id || "\u2014"}</td>
      <td className="px-3 py-2">
        <div className="flex items-center gap-1.5">
          <span
            className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${badge.classes}`}
          >
            {badge.label}
          </span>
          {isException && (
            <span className="text-yellow-500" title="Needs review">!</span>
          )}
          {status === "invalidated" && (
            <span className="text-orange-400 text-xs" title="Upstream stage was re-run. Click Run to update.">(stale)</span>
          )}
          {status === "running" && (
            <span className="inline-block w-3 h-3 border-2 border-slate-300 border-t-primary-500 rounded-full animate-spin" />
          )}
          {imageWriteFailed && (
            <span
              className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400"
              title="Image write failed during preprocessing — processed image may be stale"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              Write failed
            </span>
          )}
        </div>
      </td>
      {renderResultColumns(screenshot, event)}
      <td className="px-3 py-2">
        <button
          onClick={() => onLoadLog(screenshot.id)}
          className="px-2 py-1 text-xs text-slate-500 dark:text-slate-400 hover:text-primary-600 hover:bg-slate-100 dark:hover:bg-slate-700 rounded"
          title="View event log"
          aria-label={`View event log for screenshot ${screenshot.id}`}
        >
          Log
        </button>
      </td>
    </tr>
  );
});

export const StageReviewTable = ({
  stage,
  renderResultColumns,
  resultHeaders,
  getResultSortValue,
}: StageReviewTableProps) => {
  const allScreenshots = usePreprocessingStore((s) => s.screenshots);
  const filter = usePreprocessingStore((s) => s.filter);
  const getScreenshotStageStatus = usePreprocessingStore((s) => s.getScreenshotStageStatus);
  const isScreenshotException = usePreprocessingStore((s) => s.isScreenshotException);
  const loadEventLog = usePreprocessingStore((s) => s.loadEventLog);
  const highlightedScreenshotId = usePreprocessingStore((s) => s.highlightedScreenshotId);
  const setHighlightedScreenshotId = usePreprocessingStore((s) => s.setHighlightedScreenshotId);
  const enterQueue = usePreprocessingStore((s) => s.enterQueue);
  const imageVersion = usePreprocessingStore((s) => s.imageVersion);

  const sortColumn = usePreprocessingStore((s) => s.tableSortColumn[stage] ?? "id");
  const sortDirection = usePreprocessingStore((s) => s.tableSortDirection[stage] ?? "asc") as SortDirection;
  const setTableSort = usePreprocessingStore((s) => s.setTableSort);

  const handleSort = (column: string) => {
    if (sortColumn === column) {
      setTableSort(stage, column, sortDirection === "asc" ? "desc" : "asc");
    } else {
      setTableSort(stage, column, "asc");
    }
  };

  // Memoize filtered + sorted screenshots
  const screenshots = useMemo(() => {
    let filtered = allScreenshots;
    if (filter !== "all") {
      filtered = allScreenshots.filter((s) => {
        const status = getScreenshotStageStatus(s, stage);
        switch (filter) {
          case "completed": return status === "completed";
          case "pending": return status === "pending";
          case "invalidated": return status === "invalidated";
          case "needs_review": return isScreenshotException(s, stage);
          default: return true;
        }
      });
    }

    const sorted = [...filtered].sort((a, b) => {
      let cmp = 0;
      switch (sortColumn) {
        case "id":
          cmp = a.id - b.id;
          break;
        case "participant":
          cmp = (a.participant_id || "").localeCompare(b.participant_id || "");
          break;
        case "status": {
          const sa = getScreenshotStageStatus(a, stage);
          const sb = getScreenshotStageStatus(b, stage);
          cmp = (STATUS_SORT_ORDER[sa] ?? 99) - (STATUS_SORT_ORDER[sb] ?? 99);
          break;
        }
        default: {
          // Result column sort via getResultSortValue callback
          if (getResultSortValue) {
            const eventA = getCurrentEvent(a, stage);
            const eventB = getCurrentEvent(b, stage);
            const valA = getResultSortValue(a, eventA, sortColumn);
            const valB = getResultSortValue(b, eventB, sortColumn);
            // nulls sort last
            if (valA == null && valB == null) cmp = 0;
            else if (valA == null) cmp = 1;
            else if (valB == null) cmp = -1;
            else if (typeof valA === "number" && typeof valB === "number") cmp = valA - valB;
            else cmp = String(valA).localeCompare(String(valB));
          }
          break;
        }
      }
      return sortDirection === "asc" ? cmp : -cmp;
    });

    return sorted;
  }, [allScreenshots, filter, stage, getScreenshotStageStatus, isScreenshotException, sortColumn, sortDirection, getResultSortValue]);

  // Stable screenshot ID list for queue entry
  const screenshotIds = useMemo(() => screenshots.map((s) => s.id), [screenshots]);

  const handleEnterQueue = useCallback((screenshotId: number) => {
    const idx = screenshotIds.indexOf(screenshotId);
    enterQueue(screenshotIds, idx >= 0 ? idx : 0);
  }, [screenshotIds, enterQueue]);

  const highlightedRef = useRef<HTMLTableRowElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to highlighted screenshot
  useEffect(() => {
    if (highlightedScreenshotId && highlightedRef.current) {
      highlightedRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
      const timer = setTimeout(() => setHighlightedScreenshotId(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [highlightedScreenshotId, setHighlightedScreenshotId]);

  // Virtualizer — only render visible rows + overscan buffer
  const virtualizer = useVirtualizer({
    count: screenshots.length,
    getScrollElement: () => scrollContainerRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 20,
  });

  const sortableThClass = "px-3 py-2 cursor-pointer select-none hover:text-slate-700 dark:hover:text-slate-300 transition-colors";

  return (
    <div
      ref={scrollContainerRef}
      className="overflow-auto"
      style={{ maxHeight: "70vh" }}
    >
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-white dark:bg-slate-800 z-10">
          <tr className="border-b border-slate-200 dark:border-slate-700 text-left text-slate-500 dark:text-slate-400">
            <th className="px-3 py-2 w-16">Thumb</th>
            <th className={`${sortableThClass} w-16`} onClick={() => handleSort("id")}>
              ID <SortIcon column="id" sortColumn={sortColumn} sortDirection={sortDirection} />
            </th>
            <th className={sortableThClass} onClick={() => handleSort("participant")}>
              Participant <SortIcon column="participant" sortColumn={sortColumn} sortDirection={sortDirection} />
            </th>
            <th className={`${sortableThClass} w-28`} onClick={() => handleSort("status")}>
              Status <SortIcon column="status" sortColumn={sortColumn} sortDirection={sortDirection} />
            </th>
            {resultHeaders.map((h) => {
              if (h.sortKey) {
                return (
                  <th key={h.label} className={sortableThClass} onClick={() => handleSort(h.sortKey!)}>
                    {h.label} <SortIcon column={h.sortKey} sortColumn={sortColumn} sortDirection={sortDirection} />
                  </th>
                );
              }
              return <th key={h.label} className="px-3 py-2">{h.label}</th>;
            })}
            <th className="px-3 py-2 w-16">Log</th>
          </tr>
        </thead>
        <tbody>
          {screenshots.length === 0 ? (
            <tr>
              <td
                colSpan={4 + resultHeaders.length + 1}
                className="px-3 py-8 text-center text-slate-400 dark:text-slate-500"
              >
                No screenshots match current filter
              </td>
            </tr>
          ) : (
            <>
              {/* Spacer for items above the virtual window */}
              {virtualizer.getVirtualItems().length > 0 && (
                <tr style={{ height: virtualizer.getVirtualItems()[0]?.start ?? 0 }} >
                  <td colSpan={5 + resultHeaders.length} />
                </tr>
              )}
              {virtualizer.getVirtualItems().map((virtualRow: { index: number; start: number; size: number }) => {
                const s = screenshots[virtualRow.index]!;
                const status = getScreenshotStageStatus(s, stage);
                const isException = isScreenshotException(s, stage);
                const event = getCurrentEvent(s, stage);
                const isHighlighted = s.id === highlightedScreenshotId;

                return (
                  <TableRow
                    key={s.id}
                    screenshot={s}
                    stage={stage}
                    status={status}
                    isException={isException}
                    event={event}
                    isHighlighted={isHighlighted}
                    highlightedRef={highlightedRef}
                    onEnterQueue={handleEnterQueue}
                    onLoadLog={loadEventLog}
                    renderResultColumns={renderResultColumns}
                    imageVersion={imageVersion}
                  />
                );
              })}
              {/* Spacer for items below the virtual window */}
              {virtualizer.getVirtualItems().length > 0 && (
                <tr style={{
                  height: virtualizer.getTotalSize() -
                    (virtualizer.getVirtualItems().at(-1)!.start + virtualizer.getVirtualItems().at(-1)!.size)
                }}>
                  <td colSpan={5 + resultHeaders.length} />
                </tr>
              )}
            </>
          )}
        </tbody>
      </table>
    </div>
  );
};
