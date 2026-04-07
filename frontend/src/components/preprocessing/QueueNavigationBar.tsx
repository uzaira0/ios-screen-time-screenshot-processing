import { useState } from "react";
import { usePreprocessingStore } from "@/hooks/usePreprocessingWithDI";
import type { Screenshot } from "@/types";

interface QueueNavigationBarProps {
  currentScreenshot: Screenshot | undefined;
}

export const QueueNavigationBar = ({ currentScreenshot }: QueueNavigationBarProps) => {
  const queueIndex = usePreprocessingStore((s) => s.queueIndex);
  const queueScreenshotIds = usePreprocessingStore((s) => s.queueScreenshotIds);
  const queueNext = usePreprocessingStore((s) => s.queueNext);
  const queuePrev = usePreprocessingStore((s) => s.queuePrev);
  const exitQueue = usePreprocessingStore((s) => s.exitQueue);
  const queueGoTo = usePreprocessingStore((s) => s.queueGoTo);

  const total = queueScreenshotIds.length;
  const isFirst = queueIndex === 0;
  const isLast = queueIndex >= total - 1;
  const progressPct = total > 1 ? ((queueIndex) / (total - 1)) * 100 : 100;

  const [jumpInput, setJumpInput] = useState("");
  const [showJump, setShowJump] = useState(false);

  const [jumpError, setJumpError] = useState(false);

  const handleJump = () => {
    const id = parseInt(jumpInput, 10);
    if (isNaN(id)) return;
    const idx = queueScreenshotIds.indexOf(id);
    if (idx >= 0) {
      queueGoTo(idx);
      setJumpInput("");
      setShowJump(false);
      setJumpError(false);
    } else {
      setJumpError(true);
    }
  };

  return (
    <div className="shrink-0">
      <div className="flex items-center gap-3 px-4 py-2 bg-slate-50 dark:bg-slate-700/50 border-b border-slate-200 dark:border-slate-700">
        <button
          onClick={exitQueue}
          className="px-3 py-1.5 text-sm text-slate-600 dark:text-slate-300 border border-slate-300 dark:border-slate-600 rounded-md hover:bg-slate-100 dark:hover:bg-slate-600"
        >
          &larr; Back to Table
        </button>

        <div className="flex items-center gap-1 ml-4">
          <button
            onClick={queuePrev}
            disabled={isFirst}
            className="px-2 py-1 text-sm border border-slate-300 dark:border-slate-600 rounded-md hover:bg-slate-100 dark:hover:bg-slate-600 dark:text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed"
            aria-label="Previous screenshot"
          >
            &larr;
          </button>
          <span className="px-3 py-1 text-sm font-medium text-slate-700 dark:text-slate-300 min-w-[80px] text-center">
            {queueIndex + 1} / {total}
          </span>
          <button
            onClick={queueNext}
            disabled={isLast}
            className="px-2 py-1 text-sm border border-slate-300 dark:border-slate-600 rounded-md hover:bg-slate-100 dark:hover:bg-slate-600 dark:text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed"
            aria-label="Next screenshot"
          >
            &rarr;
          </button>
        </div>

        {currentScreenshot && (
          <div className="flex items-center gap-3 ml-4 text-sm text-slate-500 dark:text-slate-400">
            <span className="font-mono">#{currentScreenshot.id}</span>
            {currentScreenshot.participant_id && (
              <span>{currentScreenshot.participant_id}</span>
            )}
            {currentScreenshot.screenshot_date && (
              <span>{currentScreenshot.screenshot_date}</span>
            )}
          </div>
        )}

        <div className="ml-auto flex items-center gap-3">
          {showJump ? (
            <form
              onSubmit={(e) => { e.preventDefault(); handleJump(); }}
              className="flex items-center gap-1"
            >
              <input
                type="number"
                value={jumpInput}
                onChange={(e) => { setJumpInput(e.target.value); setJumpError(false); }}
                placeholder="ID"
                className={`w-20 text-xs border rounded px-2 py-1 dark:bg-slate-700 dark:text-slate-200 ${jumpError ? "border-red-400 dark:border-red-500" : "border-slate-300 dark:border-slate-600"}`}
                autoFocus
                onBlur={() => { if (!jumpInput) { setShowJump(false); setJumpError(false); } }}
                onKeyDown={(e) => { if (e.key === "Escape") { setShowJump(false); setJumpInput(""); setJumpError(false); } }}
              />
              <button type="submit" className="text-xs px-2 py-1 text-primary-600 hover:text-primary-700 font-medium">Go</button>
            </form>
          ) : (
            <button
              onClick={() => setShowJump(true)}
              className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
              title="Jump to screenshot ID"
            >
              Go to ID
            </button>
          )}
          <span className="text-xs text-slate-400 dark:text-slate-500">
            &larr; &rarr; navigate &middot; Esc exit &middot; ? shortcuts
          </span>
        </div>
      </div>
      {/* Progress bar */}
      <div className="h-0.5 bg-slate-200 dark:bg-slate-600">
        <div
          className="h-full bg-primary-500 transition-all duration-200"
          style={{ width: `${progressPct}%` }}
        />
      </div>
    </div>
  );
};
