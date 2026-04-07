import type { Screenshot } from "@/types";
import type { PreprocessingEventData } from "@/store/preprocessingStore";
import { StageReviewTable, type ResultHeader } from "./StageReviewTable";

const RESULT_HEADERS: ResultHeader[] = [
  { label: "Device", sortKey: "device_category" },
  { label: "Model", sortKey: "device_model" },
  { label: "Conf", sortKey: "confidence" },
  { label: "Orientation", sortKey: "orientation" },
];

function getResultSortValue(_s: Screenshot, event: PreprocessingEventData | null, sortKey: string): string | number | null {
  const result = event?.result as Record<string, unknown> | undefined;
  if (!result) return null;
  const val = result[sortKey];
  if (val == null) return null;
  if (typeof val === "number") return val;
  return String(val);
}

function renderResultColumns(_s: Screenshot, event: PreprocessingEventData | null) {
  const result = event?.result as Record<string, unknown> | undefined;

  return (
    <>
      <td className="px-3 py-2">
        {result ? (
          <span
            className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
              result.device_category === "ipad"
                ? "bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-400"
                : result.device_category === "iphone"
                  ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                  : "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-400"
            }`}
          >
            {result.device_category as string}
          </span>
        ) : (
          <span className="text-slate-400">{"\u2014"}</span>
        )}
      </td>
      <td className="px-3 py-2 text-slate-600 dark:text-slate-400 text-xs">
        {(result?.device_model as string) || "\u2014"}
      </td>
      <td className="px-3 py-2">
        {result ? (
          <span
            className={`font-mono text-xs ${
              (result.confidence as number) >= 0.9
                ? "text-green-600"
                : (result.confidence as number) >= 0.7
                  ? "text-yellow-600"
                  : "text-red-600"
            }`}
          >
            {Math.round((result.confidence as number) * 100)}%
          </span>
        ) : (
          "\u2014"
        )}
      </td>
      <td className="px-3 py-2 text-slate-600 dark:text-slate-400 text-xs">
        {(result?.orientation as string) || "\u2014"}
      </td>
    </>
  );
}

export const DeviceDetectionTab = () => {
  return (
    <StageReviewTable
      stage="device_detection"
      resultHeaders={RESULT_HEADERS}
      renderResultColumns={renderResultColumns}
      getResultSortValue={getResultSortValue}
    />
  );
};
