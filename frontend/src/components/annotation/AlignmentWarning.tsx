interface AlignmentWarningProps {
  alignmentScore: number | null | undefined;
}

export function AlignmentWarning({ alignmentScore }: AlignmentWarningProps) {
  // Don't show if alignment is good or not available
  if (alignmentScore === null || alignmentScore === undefined || alignmentScore >= 0.8) {
    return null;
  }

  const isSevere = alignmentScore < 0.5;

  return (
    <div
      className={`border-b border-slate-100 dark:border-slate-700 pb-2 rounded-md p-2 ${
        isSevere
          ? "ring-2 ring-red-500 bg-red-50 dark:bg-red-900/20"
          : "ring-2 ring-yellow-500 bg-yellow-50 dark:bg-yellow-900/20"
      }`}
    >
      <div className="flex items-center gap-2">
        <svg
          className={`w-5 h-5 ${
            isSevere ? "text-red-600" : "text-yellow-600"
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
        <div>
          <div
            className={`text-xs font-medium ${
              isSevere ? "text-red-700 dark:text-red-400" : "text-yellow-700 dark:text-yellow-400"
            }`}
          >
            {isSevere ? "Poor Bar Alignment" : `Low alignment (${(alignmentScore * 100).toFixed(0)}%)`}
          </div>
          <div className="text-xs text-slate-600 dark:text-slate-400">
            {isSevere
              ? `Score: ${(alignmentScore * 100).toFixed(0)}% — Bars may not match graph. Adjust grid position.`
              : "Verify bar values carefully. Consider adjusting grid position."}
          </div>
        </div>
      </div>
    </div>
  );
}
