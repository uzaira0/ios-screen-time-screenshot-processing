import { useState } from "react";
import type { Screenshot } from "@/types";
import type { PreprocessingEventData } from "@/store/preprocessingStore";
import { usePreprocessingStore } from "@/hooks/usePreprocessingWithDI";
import { StageReviewTable, type ResultHeader } from "./StageReviewTable";
import { PHIRegionEditor } from "./PHIRegionEditor";

const RESULT_HEADERS: ResultHeader[] = [
  { label: "PHI Found", sortKey: "phi_detected" },
  { label: "Regions", sortKey: "regions_count" },
  { label: "Preset", sortKey: "preset" },
  { label: "" },
];

function getResultSortValue(_s: Screenshot, event: PreprocessingEventData | null, sortKey: string): string | number | null {
  const result = event?.result as Record<string, unknown> | undefined;
  if (!result) return null;
  switch (sortKey) {
    case "phi_detected":
      return result.phi_detected ? 1 : 0;
    case "regions_count":
      return (result.regions_count as number) ?? 0;
    case "preset":
      return (result.preset as string) || null;
    default:
      return null;
  }
}

function PHIDetectionTabInner() {
  const [editorScreenshotId, setEditorScreenshotId] = useState<number | null>(null);
  const loadScreenshots = usePreprocessingStore((s) => s.loadScreenshots);
  const loadSummary = usePreprocessingStore((s) => s.loadSummary);

  const handleRegionsSaved = () => {
    loadScreenshots();
    loadSummary();
  };

  const renderResultColumns = (_s: Screenshot, event: PreprocessingEventData | null) => {
    const result = event?.result as Record<string, unknown> | undefined;

    return (
      <>
        <td className="px-3 py-2">
          {result ? (
            result.phi_detected ? (
              <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400">
                Yes
              </span>
            ) : (
              <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                Clean
              </span>
            )
          ) : (
            <span className="text-slate-400">{"\u2014"}</span>
          )}
        </td>
        <td className="px-3 py-2 font-mono text-xs">
          {result ? (result.regions_count as number) : "\u2014"}
        </td>
        <td className="px-3 py-2 text-xs text-slate-600 dark:text-slate-400">
          {(result?.preset as string) || "\u2014"}
        </td>
        <td className="px-3 py-2">
          <button
            onClick={() => setEditorScreenshotId(_s.id)}
            className="px-2 py-1 text-xs text-primary-600 dark:text-primary-400 border border-primary-200 dark:border-primary-700 rounded hover:bg-primary-50 dark:hover:bg-primary-900/20"
            title="Edit PHI regions"
          >
            Edit Regions
          </button>
        </td>
      </>
    );
  };

  return (
    <>
      <StageReviewTable
        stage="phi_detection"
        resultHeaders={RESULT_HEADERS}
        renderResultColumns={renderResultColumns}
        getResultSortValue={getResultSortValue}
      />
      {editorScreenshotId !== null && (
        <PHIRegionEditor
          screenshotId={editorScreenshotId}
          isOpen={true}
          onClose={() => setEditorScreenshotId(null)}
          onRegionsSaved={handleRegionsSaved}
          onRedactionApplied={() => { handleRegionsSaved(); setEditorScreenshotId(null); }}
        />
      )}
    </>
  );
}

export const PHIDetectionTab = () => <PHIDetectionTabInner />;
