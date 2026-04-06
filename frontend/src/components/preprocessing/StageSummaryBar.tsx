import { useMemo } from "react";
import { usePreprocessingStore } from "@/hooks/usePreprocessingWithDI";
import type { FilterMode } from "@/store/preprocessingStore";
import type { Screenshot } from "@/types";
import { PREPROCESSING_STAGES } from "@/core/generated/constants";

const FILTER_DEFS: { id: FilterMode; label: string; color: string }[] = [
  { id: "all", label: "All", color: "text-slate-700 bg-slate-100" },
  { id: "needs_review", label: "Needs Review", color: "text-yellow-700 bg-yellow-50" },
  { id: "invalidated", label: "Invalidated", color: "text-orange-700 bg-orange-50" },
  { id: "completed", label: "Completed", color: "text-green-700 bg-green-50" },
  { id: "skipped", label: "Skipped", color: "text-purple-700 bg-purple-50" },
  { id: "pending", label: "Pending", color: "text-slate-500 bg-slate-50" },
];

export const StageSummaryBar = () => {
  const filter = usePreprocessingStore((s) => s.filter);
  const setFilter = usePreprocessingStore((s) => s.setFilter);
  const activeStage = usePreprocessingStore((s) => s.activeStage);
  const screenshots = usePreprocessingStore((s) => s.screenshots);
  const getStageStatus = usePreprocessingStore((s) => s.getStageStatus);
  const getEligibleCount = usePreprocessingStore((s) => s.getEligibleCount);
  const summary = usePreprocessingStore((s) => s.summary);
  const isRunningStage = usePreprocessingStore((s) => s.isRunningStage);
  const stageProgress = usePreprocessingStore((s) => s.stageProgress);
  const runStage = usePreprocessingStore((s) => s.runStage);
  const resetStage = usePreprocessingStore((s) => s.resetStage);
  const skipStage = usePreprocessingStore((s) => s.skipStage);
  const unskipStage = usePreprocessingStore((s) => s.unskipStage);

  const stopStage = usePreprocessingStore((s) => s.stopStage);
  const enterQueue = usePreprocessingStore((s) => s.enterQueue);
  const getScreenshotsForStage = usePreprocessingStore((s) => s.getScreenshotsForStage);

  const counts = summary ? summary[activeStage] : getStageStatus(activeStage);
  const total = summary?.total ?? screenshots.length;

  // Count for each filter
  const filterCounts: Record<FilterMode, number> = {
    all: total,
    needs_review: counts.exceptions,
    invalidated: counts.invalidated,
    completed: counts.completed,
    skipped: counts.skipped ?? 0,
    pending: counts.pending,
  };

  // Eligible = pending/invalidated AND prerequisites completed
  const { eligible, blockedByPrereq } = useMemo(
    () => getEligibleCount(activeStage),
    [getEligibleCount, activeStage, screenshots],
  );

  // Stage label for the run button
  const stageLabel = activeStage.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  // Previous stage label for the "blocked" message
  const STAGE_LABELS: Record<string, string> = {
    device_detection: "Device Detection",
    cropping: "Cropping",
    phi_detection: "PHI Detection",
    phi_redaction: "PHI Redaction",
  };
  // Stages with prerequisites (all except the first one)
  const STAGE_ORDER = PREPROCESSING_STAGES.slice(0, -1);
  const stageIdx = STAGE_ORDER.indexOf(activeStage);
  const prevStageLabel = stageIdx > 0 ? STAGE_LABELS[STAGE_ORDER[stageIdx - 1]!] : null;

  return (
    <div className="flex flex-wrap items-center gap-2 p-3 bg-slate-50 dark:bg-slate-700/50 rounded-lg" role="toolbar" aria-label="Preprocessing stage controls">
      {/* Filter toggles */}
      <div className="flex items-center gap-1">
        {FILTER_DEFS.map((f) => {
          const count = filterCounts[f.id];
          if (f.id !== "all" && count === 0) return null;
          return (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                filter === f.id
                  ? `${f.color} ring-1 ring-current`
                  : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-600"
              }`}
            >
              {f.label} ({count})
            </button>
          );
        })}
      </div>

      {/* Progress bar + stop button when running */}
      {isRunningStage && (
        <div className="flex items-center gap-2 ml-2">
          {stageProgress && (
            <>
              <div className="w-32 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary-600 rounded-full transition-all"
                  style={{ width: `${(stageProgress.completed / stageProgress.total) * 100}%` }}
                />
              </div>
              <span className="text-xs text-slate-500">
                {stageProgress.completed}/{stageProgress.total}
              </span>
            </>
          )}
          <span className="inline-block w-3 h-3 border-2 border-slate-300 border-t-primary-600 rounded-full animate-spin" />
          <button
            onClick={stopStage}
            className="px-2.5 py-1 text-xs font-medium text-red-700 bg-red-50 border border-red-200 rounded-md hover:bg-red-100 transition-colors"
          >
            Stop
          </button>
        </div>
      )}

      {/* Blocked-by-prerequisite hint */}
      {!isRunningStage && blockedByPrereq > 0 && (
        <span className="text-xs text-amber-600 ml-2">
          {blockedByPrereq} blocked — complete {prevStageLabel} first
        </span>
      )}

      {/* Review queue button */}
      {total > 0 && (
        <button
          onClick={() => {
            const filtered = getScreenshotsForStage(activeStage);
            if (filtered.length > 0) {
              enterQueue(filtered.map((s: Screenshot) => s.id));
            }
          }}
          className="ml-2 px-3 py-1.5 text-sm font-medium text-primary-700 bg-primary-50 border border-primary-200 rounded-md hover:bg-primary-100 transition-colors"
        >
          Review ({filterCounts[filter]})
        </button>
      )}

      {/* Reset button — always available when not running and there are any non-pending screenshots */}
      {!isRunningStage && (total - counts.pending > 0) && (
        <button
          onClick={() => resetStage(activeStage)}
          className="ml-auto px-4 py-1.5 text-sm font-medium text-orange-700 bg-orange-50 border border-orange-200 rounded-md hover:bg-orange-100 dark:bg-orange-900/20 dark:text-orange-400 dark:border-orange-800 dark:hover:bg-orange-900/30 transition-colors"
        >
          Reset {stageLabel} ({total - counts.pending})
        </button>
      )}

      {/* Skip button — skip all eligible screenshots for this stage */}
      {!isRunningStage && eligible > 0 && (
        <button
          onClick={() => skipStage(activeStage)}
          className="px-4 py-1.5 text-sm font-medium text-purple-700 bg-purple-50 border border-purple-200 rounded-md hover:bg-purple-100 dark:bg-purple-900/20 dark:text-purple-400 dark:border-purple-800 dark:hover:bg-purple-900/30 transition-colors"
        >
          Skip {stageLabel} ({eligible})
        </button>
      )}

      {/* Unskip button — restore skipped screenshots to pending */}
      {!isRunningStage && (counts.skipped ?? 0) > 0 && (
        <button
          onClick={() => unskipStage(activeStage)}
          className="px-4 py-1.5 text-sm font-medium text-purple-700 bg-purple-50 border border-purple-200 rounded-md hover:bg-purple-100 dark:bg-purple-900/20 dark:text-purple-400 dark:border-purple-800 dark:hover:bg-purple-900/30 transition-colors"
        >
          Unskip ({counts.skipped})
        </button>
      )}

      {/* Run button */}
      <button
        onClick={() => runStage(activeStage)}
        disabled={isRunningStage || eligible === 0}
        className={`${eligible === 0 && counts.completed > 0 ? "" : "ml-auto "}px-4 py-1.5 bg-primary-600 text-white text-sm font-medium rounded-md hover:bg-primary-700 disabled:bg-slate-400 disabled:text-slate-200 disabled:cursor-not-allowed transition-colors`}
      >
        {isRunningStage
          ? "Running..."
          : `Run ${stageLabel} on ${eligible} screenshot${eligible !== 1 ? "s" : ""}`}
      </button>
    </div>
  );
};
