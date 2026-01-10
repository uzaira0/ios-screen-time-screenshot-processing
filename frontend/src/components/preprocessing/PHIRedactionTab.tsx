import { useState } from "react";
import type { Screenshot } from "@/types";
import type { PreprocessingEventData } from "@/store/preprocessingStore";
import { usePreprocessingStore } from "@/hooks/usePreprocessingWithDI";
import { StageReviewTable, type ResultHeader } from "./StageReviewTable";
import { PHIRegionEditor } from "./PHIRegionEditor";

const RESULT_HEADERS: ResultHeader[] = [
  { label: "Redacted", sortKey: "redacted" },
  { label: "Regions", sortKey: "regions_redacted" },
  { label: "Method", sortKey: "method" },
  { label: "" },
];

function getResultSortValue(_s: Screenshot, event: PreprocessingEventData | null, sortKey: string): string | number | null {
  const result = event?.result as Record<string, unknown> | undefined;
  if (!result) return null;
  switch (sortKey) {
    case "redacted":
      return result.redacted ? 1 : 0;
    case "regions_redacted":
      return (result.regions_redacted as number) ?? 0;
    case "method":
      return (result.method as string) || null;
    default:
      return null;
  }
}

function PHIRedactionTabInner() {
  const [editorScreenshotId, setEditorScreenshotId] = useState<number | null>(null);
  const loadScreenshots = usePreprocessingStore((s) => s.loadScreenshots);
  const loadSummary = usePreprocessingStore((s) => s.loadSummary);

  const handleRedactionApplied = () => {
    loadScreenshots();
    loadSummary();
    setEditorScreenshotId(null);
  };

  const renderResultColumns = (_s: Screenshot, event: PreprocessingEventData | null) => {
    const result = event?.result as Record<string, unknown> | undefined;

    return (
      <>
        <td className="px-3 py-2">
          {result ? (
            result.redacted ? (
              <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400">
                Yes
              </span>
            ) : (
              <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-400">
                No
              </span>
            )
          ) : (
            <span className="text-slate-400">{"\u2014"}</span>
          )}
        </td>
        <td className="px-3 py-2 font-mono text-xs">
          {result ? (result.regions_redacted as number) : "\u2014"}
        </td>
        <td className="px-3 py-2 text-xs text-slate-600 dark:text-slate-400">
          {(result?.method as string) || "\u2014"}
        </td>
        <td className="px-3 py-2">
          <button
            onClick={() => setEditorScreenshotId(_s.id)}
            className="px-2 py-1 text-xs text-orange-600 dark:text-orange-400 border border-orange-200 dark:border-orange-700 rounded hover:bg-orange-50 dark:hover:bg-orange-900/20"
            title="Review regions and apply redaction"
          >
            Review & Redact
          </button>
        </td>
      </>
    );
  };

  return (
    <>
      <StageReviewTable
        stage="phi_redaction"
        resultHeaders={RESULT_HEADERS}
        renderResultColumns={renderResultColumns}
        getResultSortValue={getResultSortValue}
      />
      {editorScreenshotId !== null && (
        <PHIRegionEditor
          screenshotId={editorScreenshotId}
          isOpen={true}
          onClose={() => setEditorScreenshotId(null)}
          onRegionsSaved={() => { loadScreenshots(); loadSummary(); }}
          onRedactionApplied={handleRedactionApplied}
        />
      )}
    </>
  );
}

export const PHIRedactionTab = () => <PHIRedactionTabInner />;
