import { useState } from "react";
import type { Screenshot } from "@/types";
import type { PreprocessingEventData } from "@/store/preprocessingStore";
import { usePreprocessingStore } from "@/hooks/usePreprocessingWithDI";
import { StageReviewTable, type ResultHeader } from "./StageReviewTable";
import { CropAdjustModal } from "./CropAdjustModal";

interface CropRect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

const RESULT_HEADERS: ResultHeader[] = [
  { label: "Device", sortKey: "crop_device" },
  { label: "Cropped", sortKey: "was_cropped" },
  { label: "Patched", sortKey: "was_patched" },
  { label: "Original Size", sortKey: "original_area" },
  { label: "Cropped Size", sortKey: "cropped_area" },
  { label: "" },
];

function getResultSortValue(s: Screenshot, event: PreprocessingEventData | null, sortKey: string): string | number | null {
  const result = event?.result as Record<string, unknown> | undefined;
  if (!result) return null;
  switch (sortKey) {
    case "crop_device": {
      const params = event?.params as Record<string, unknown> | undefined;
      return (params?.auto_detected_device as string) || s.device_type || null;
    }
    case "was_cropped":
      return result.was_cropped ? 1 : 0;
    case "was_patched":
      return result.was_patched ? 1 : 0;
    case "original_area": {
      const dims = result.original_dimensions as number[] | undefined;
      return dims?.length === 2 ? dims[0]! * dims[1]! : null;
    }
    case "cropped_area": {
      const dims = result.cropped_dimensions as number[] | undefined;
      return dims?.length === 2 ? dims[0]! * dims[1]! : null;
    }
    default:
      return null;
  }
}

/** Extract crop bounds from a cropping event result. Auto-crop is right-aligned (removes left sidebar). */
export function getCropRectFromEvent(event: PreprocessingEventData | null): CropRect | undefined {
  if (!event) return undefined;
  const result = event.result as Record<string, unknown> | undefined;
  if (!result?.was_cropped) return undefined;

  // If manual crop, params has the exact bounds
  if (result.manual) {
    const params = event.params as Record<string, unknown> | undefined;
    if (params && typeof params.left === "number") {
      return {
        left: params.left as number,
        top: params.top as number,
        right: params.right as number,
        bottom: params.bottom as number,
      };
    }
  }

  // Auto-crop: right-aligned (removes left sidebar)
  const origDims = result.original_dimensions as number[] | undefined;
  const croppedDims = result.cropped_dimensions as number[] | undefined;
  if (origDims?.length === 2 && croppedDims?.length === 2) {
    const origW = origDims[0]!;
    const origH = origDims[1]!;
    const cropW = croppedDims[0]!;
    const cropH = croppedDims[1]!;
    return {
      left: origW - cropW,
      top: origH - cropH, // typically 0
      right: origW,
      bottom: origH,
    };
  }

  return undefined;
}

function CroppingTabInner() {
  const [cropModalScreenshotId, setCropModalScreenshotId] = useState<number | null>(null);
  const [cropModalInitialCrop, setCropModalInitialCrop] = useState<CropRect | undefined>(undefined);
  const loadScreenshots = usePreprocessingStore((s) => s.loadScreenshots);
  const loadSummary = usePreprocessingStore((s) => s.loadSummary);

  const handleCropApplied = () => {
    loadScreenshots();
    loadSummary();
  };

  const renderResultColumns = (s: Screenshot, event: PreprocessingEventData | null) => {
    const result = event?.result as Record<string, unknown> | undefined;
    const params = event?.params as Record<string, unknown> | undefined;

    return (
      <>
        <td className="px-3 py-2 text-xs">
          {(params?.auto_detected_device as string) || s.device_type || "\u2014"}
        </td>
        <td className="px-3 py-2">
          {result ? (
            result.was_cropped ? (
              <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                {result.manual ? "Manual" : "Yes"}
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
        <td className="px-3 py-2">
          {result ? (
            result.was_patched ? (
              <span className="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400">
                Yes
              </span>
            ) : (
              <span className="text-slate-400 text-xs">No</span>
            )
          ) : (
            <span className="text-slate-400">{"\u2014"}</span>
          )}
        </td>
        <td className="px-3 py-2 text-xs text-slate-600 dark:text-slate-400">
          {result?.original_dimensions
            ? `${(result.original_dimensions as number[])[0]} x ${(result.original_dimensions as number[])[1]}`
            : "\u2014"}
        </td>
        <td className="px-3 py-2 text-xs text-slate-600 dark:text-slate-400">
          {result?.cropped_dimensions
            ? `${(result.cropped_dimensions as number[])[0]} x ${(result.cropped_dimensions as number[])[1]}`
            : "\u2014"}
        </td>
        <td className="px-3 py-2">
          <button
            onClick={() => {
              setCropModalScreenshotId(s.id);
              setCropModalInitialCrop(getCropRectFromEvent(event));
            }}
            className="px-2 py-1 text-xs text-primary-600 dark:text-primary-400 border border-primary-200 dark:border-primary-700 rounded hover:bg-primary-50 dark:hover:bg-primary-900/20"
            title="Adjust crop manually"
          >
            Edit Crop
          </button>
        </td>
      </>
    );
  };

  return (
    <>
      <StageReviewTable
        stage="cropping"
        resultHeaders={RESULT_HEADERS}
        renderResultColumns={renderResultColumns}
        getResultSortValue={getResultSortValue}
      />
      {cropModalScreenshotId !== null && (
        <CropAdjustModal
          screenshotId={cropModalScreenshotId}
          isOpen={true}
          onClose={() => {
            setCropModalScreenshotId(null);
            setCropModalInitialCrop(undefined);
          }}
          onCropApplied={handleCropApplied}
          initialCrop={cropModalInitialCrop}
        />
      )}
    </>
  );
}

export const CroppingTab = () => <CroppingTabInner />;
