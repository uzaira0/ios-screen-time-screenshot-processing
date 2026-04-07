interface SaveStatusIndicatorProps {
  isSaving: boolean;
  lastSaved: Date | null;
  timeSinceLastSave: string;
  saveFailCount?: number;
  lastError?: string | null;
  hasUnsavedChanges?: boolean;
  onRetry?: () => void;
}

export function SaveStatusIndicator({
  isSaving,
  lastSaved,
  timeSinceLastSave,
  saveFailCount = 0,
  lastError,
  hasUnsavedChanges = false,
  onRetry,
}: SaveStatusIndicatorProps) {
  // Error state — save failed
  if (saveFailCount > 0 && lastError) {
    return (
      <div
        className="text-xs text-center py-2 px-3 rounded-md bg-red-50 text-red-700 border border-red-200 dark:bg-red-900/20 dark:text-red-400 dark:border-red-700"
        data-testid="auto-save-status"
        title={lastError}
      >
        <span className="flex items-center justify-center gap-1.5">
          <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
          </svg>
          <span>
            Save failed{saveFailCount > 1 ? ` (${saveFailCount}x)` : ""}
            {onRetry && (
              <button
                onClick={onRetry}
                className="ml-1.5 underline font-medium hover:text-red-800 dark:hover:text-red-300"
              >
                Retry
              </button>
            )}
          </span>
        </span>
      </div>
    );
  }

  return (
    <div
      className={`text-xs text-center py-2 px-3 rounded-md transition-all duration-300 ${
        isSaving
          ? "bg-primary-50 text-primary-700 border border-primary-200 dark:bg-primary-900/20 dark:text-primary-400 dark:border-primary-700"
          : lastSaved
            ? hasUnsavedChanges
              ? "bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-900/20 dark:text-amber-400 dark:border-amber-700"
              : "bg-green-50 text-green-700 border border-green-200 dark:bg-green-900/20 dark:text-green-400 dark:border-green-700"
            : "bg-slate-50 text-slate-500 border border-slate-200 dark:bg-slate-700/50 dark:text-slate-400 dark:border-slate-600"
      }`}
      data-testid="auto-save-status"
    >
      {isSaving ? (
        <span className="flex items-center justify-center gap-2">
          <div className="animate-spin h-3 w-3 border-2 border-primary-500 border-t-transparent rounded-full"></div>
          <span className="font-medium">Saving changes...</span>
        </span>
      ) : lastSaved ? (
        <span className="flex items-center justify-center gap-1">
          <svg
            className="w-4 h-4 text-green-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M5 13l4 4L19 7"
            />
          </svg>
          <span className="font-medium">Saved {timeSinceLastSave}</span>
        </span>
      ) : (
        <span className="flex items-center justify-center gap-1">
          <svg
            className="w-3 h-3 text-slate-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"
            />
          </svg>
          Auto-save enabled
        </span>
      )}
    </div>
  );
}
