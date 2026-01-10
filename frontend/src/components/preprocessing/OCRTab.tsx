import { useNavigate } from "react-router";
import type { Screenshot } from "@/types";
import type { PreprocessingEventData } from "@/store/preprocessingStore";
import { StageReviewTable, type ResultHeader } from "./StageReviewTable";
import { formatMinutes, parseOcrTotalMinutes, calculateTotalMinutes, hasTotalsMismatchByThreshold } from "@/utils/formatters";

/** Compute bar total from extracted_hourly_data {"0": 5, "1": 0, ...}. */
function computeBarTotal(hourlyData: Record<string, number> | null | undefined): number | null {
  if (!hourlyData) return null;
  return calculateTotalMinutes(hourlyData);
}

const RESULT_HEADERS: ResultHeader[] = [
  { label: "Status", sortKey: "processing_status" },
  { label: "Title", sortKey: "extracted_title" },
  { label: "OCR Total", sortKey: "extracted_total" },
  { label: "Bar Total", sortKey: "bar_total" },
  { label: "Align %", sortKey: "alignment_score" },
  { label: "Method", sortKey: "processing_method" },
  { label: "Issues", sortKey: "issues_count" },
];

function getResultSortValue(s: Screenshot, event: PreprocessingEventData | null, sortKey: string): string | number | null {
  const result = event?.result as Record<string, unknown> | undefined;
  if (!result && sortKey !== "bar_total" && sortKey !== "alignment_score") return null;
  switch (sortKey) {
    case "processing_status":
      return (result?.processing_status as string) || null;
    case "extracted_title":
      return (result?.extracted_title as string) || null;
    case "extracted_total":
      return parseOcrTotalMinutes(result?.extracted_total as string) ?? null;
    case "bar_total":
      return computeBarTotal(s.extracted_hourly_data as Record<string, number> | undefined) ?? null;
    case "alignment_score":
      return (s.alignment_score as number) ?? null;
    case "processing_method":
      return (result?.processing_method as string) || null;
    case "issues_count":
      return ((result?.issues as string[]) ?? []).length;
    default:
      return null;
  }
}

function OCRTabInner() {
  const navigate = useNavigate();

  const renderResultColumns = (s: Screenshot, event: PreprocessingEventData | null) => {
    const result = event?.result as Record<string, unknown> | undefined;
    const status = result?.processing_status as string | undefined;
    const issues = (result?.issues as string[]) ?? [];
    const ocrTotal = (result?.extracted_total as string) || null;
    const ocrMinutes = parseOcrTotalMinutes(ocrTotal);
    const barTotal = computeBarTotal(s.extracted_hourly_data as Record<string, number> | undefined);
    const alignmentScore = s.alignment_score as number | null | undefined;

    // Mismatch detection: flag if bar total differs from OCR total by >10% or >5min
    const hasMismatch = barTotal != null && hasTotalsMismatchByThreshold(barTotal, ocrMinutes);

    const lowAlignment = typeof alignmentScore === "number" && alignmentScore < 0.8;

    return (
      <>
        <td className="px-3 py-2">
          {result ? (
            status === "completed" ? (
              <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                hasMismatch || lowAlignment
                  ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                  : "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
              }`}>
                {hasMismatch || lowAlignment ? "Review" : "OK"}
              </span>
            ) : status === "failed" ? (
              <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400">
                Failed
              </span>
            ) : status === "skipped" ? (
              <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-400">
                Daily
              </span>
            ) : (
              <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400">
                {status ?? "Unknown"}
              </span>
            )
          ) : (
            <span className="text-slate-400">{"\u2014"}</span>
          )}
        </td>
        <td className="px-3 py-2 text-xs max-w-[200px] truncate" title={result?.extracted_title as string ?? ""}>
          <button
            onClick={(e) => { e.stopPropagation(); navigate(`/annotate/${s.id}`); }}
            className="text-left hover:text-primary-600 hover:underline cursor-pointer"
            title={`Open annotation page for screenshot ${s.id}`}
          >
            {(result?.extracted_title as string) || "\u2014"}
          </button>
        </td>
        <td className={`px-3 py-2 text-xs font-mono ${hasMismatch ? "text-red-600 dark:text-red-400 font-bold" : ""}`}>
          {ocrTotal || "\u2014"}
        </td>
        <td className={`px-3 py-2 text-xs font-mono ${hasMismatch ? "text-red-600 dark:text-red-400 font-bold" : ""}`}>
          {barTotal != null ? formatMinutes(barTotal) : "\u2014"}
        </td>
        <td className={`px-3 py-2 text-xs font-mono ${lowAlignment ? "text-red-600 dark:text-red-400 font-bold" : "text-slate-600 dark:text-slate-400"}`}>
          {typeof alignmentScore === "number" ? `${Math.round(alignmentScore * 100)}%` : "\u2014"}
        </td>
        <td className="px-3 py-2 text-xs text-slate-600 dark:text-slate-400">
          {(result?.processing_method as string) || "\u2014"}
        </td>
        <td className="px-3 py-2 text-xs">
          {issues.length > 0 ? (
            <span className="text-amber-600 dark:text-amber-400" title={issues.join("; ")}>
              {issues.length} issue{issues.length !== 1 ? "s" : ""}
            </span>
          ) : result ? (
            <span className="text-slate-400">None</span>
          ) : (
            "\u2014"
          )}
        </td>
      </>
    );
  };

  return (
    <StageReviewTable
      stage="ocr"
      resultHeaders={RESULT_HEADERS}
      renderResultColumns={renderResultColumns}
      getResultSortValue={getResultSortValue}
    />
  );
}

export const OCRTab = OCRTabInner;
