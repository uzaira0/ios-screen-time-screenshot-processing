/**
 * Image Processor Worker — Emscripten Path B
 *
 * Uses the wasm32-unknown-emscripten build of the Rust pipeline which
 * includes native leptess OCR linked directly into the WASM module.
 * Image decoding is done via the browser's Canvas API (OffscreenCanvas /
 * createImageBitmap) in the main thread before the ImageData is transferred
 * here.
 *
 * Pipeline: blob → ImageData (main thread, canvas) → RGBA → _pipeline_process
 */

import type {
  WorkerMessage,
  ProcessImageMessage,
  ExtractTitleMessage,
  ExtractTotalMessage,
  ExtractHourlyDataMessage,
  DetectGridMessage,
  WorkerResponse,
} from "./types";

import type { GridCoordinates, HourlyData, HourlyValues } from "@/types";
import { emPipelineProcess, emDetectGrid, emExtractOcr } from "../emscripten/pipelineLoader";

let initialized = false;
let currentMessageId: string | undefined;

function postProgress(
  stage: "loading" | "preprocessing" | "ocr_title" | "ocr_total" | "ocr_hourly" | "complete",
  progress: number,
  message?: string,
): void {
  self.postMessage({ type: "PROGRESS", id: currentMessageId, payload: { stage, progress, message } });
}

function hourlyValuesToData(values: number[]): HourlyValues {
  const data: HourlyValues = {};
  const src = values.length >= 24 ? values.slice(0, 24) : values;
  for (let i = 0; i < 24; i++) data[i] = src[i] ?? 0;
  return data;
}

function gridBoundsToCoordinates(bounds: {
  upper_left_x: number;
  upper_left_y: number;
  lower_right_x: number;
  lower_right_y: number;
}): GridCoordinates {
  return {
    upper_left: { x: bounds.upper_left_x, y: bounds.upper_left_y },
    lower_right: { x: bounds.lower_right_x, y: bounds.lower_right_y },
  };
}

async function initialize(): Promise<void> {
  if (initialized) return;
  postProgress("loading", 10, "Loading Emscripten pipeline...");
  // Warm up the module load + tessdata fetch (singleton, cached after first call).
  // Use LineBased (method=1) on a 1×1 image — fast, just forces the WASM module to load.
  await emDetectGrid(new ImageData(1, 1), { method: 1 });
  initialized = true;
  postProgress("complete", 100, "Emscripten pipeline ready");
}

self.onmessage = async (e: MessageEvent<WorkerMessage>) => {
  const { type, id, payload } = e.data;
  currentMessageId = id;

  try {
    switch (type) {
      case "INITIALIZE":
        await initialize();
        self.postMessage({ type: "INITIALIZE_COMPLETE", id, payload: { initialized: true } });
        break;

      case "PROCESS_IMAGE": {
        const p = payload as ProcessImageMessage["payload"];
        if (!initialized) await initialize();

        postProgress("preprocessing", 20, "Running pipeline...");

        const result = await emPipelineProcess(p.imageData, p.imageType ?? "screen_time", {
          ...(p.maxShift !== undefined && { maxShift: p.maxShift }),
          ...(p.gridCoordinates !== undefined && { gridCoordinates: p.gridCoordinates }),
        });

        const hourlyData: HourlyData = hourlyValuesToData(result.hourly_values ?? Array(24).fill(0) as number[]);
        const gridCoords: GridCoordinates | undefined = result.grid_bounds
          ? gridBoundsToCoordinates(result.grid_bounds)
          : undefined;

        postProgress("complete", 100, "Done");

        // Surface ocr_error to the main thread (and console) so a silent
        // Tesseract failure — wrong tessdata path, init crash, etc. —
        // doesn't just look like 'OCR found no title'.
        if (result.ocr_error) {
          console.warn("[imageProcessor.worker] OCR error from pipeline_em:", result.ocr_error);
        }
        const response: WorkerResponse = {
          type: "PROCESS_IMAGE_COMPLETE",
          id,
          payload: {
            hourlyData,
            title: result.title ?? null,
            total: result.total_text ?? null,
            gridCoordinates: gridCoords,
            gridDetectionFailed: !result.success,
            gridDetectionError: result.error,
            alignmentScore: result.alignment_score ?? null,
          },
        };
        self.postMessage(response);
        break;
      }

      case "EXTRACT_TITLE": {
        const p = payload as ExtractTitleMessage["payload"];
        const result = await emExtractOcr(p.imageData);
        self.postMessage({ type: "EXTRACT_TITLE_COMPLETE", id, payload: { title: result.title ?? null } });
        break;
      }

      case "EXTRACT_TOTAL": {
        const p = payload as ExtractTotalMessage["payload"];
        const result = await emExtractOcr(p.imageData);
        self.postMessage({ type: "EXTRACT_TOTAL_COMPLETE", id, payload: { total: result.total_text ?? null } });
        break;
      }

      case "EXTRACT_HOURLY_DATA": {
        const p = payload as ExtractHourlyDataMessage["payload"];
        const result = await emPipelineProcess(p.imageData, p.imageType ?? "screen_time", {
          gridCoordinates: p.gridCoordinates,
        });
        const hourlyData: HourlyData = hourlyValuesToData(result.hourly_values ?? Array(24).fill(0) as number[]);
        self.postMessage({ type: "EXTRACT_HOURLY_DATA_COMPLETE", id, payload: { hourlyData } });
        break;
      }

      case "DETECT_GRID": {
        const p = payload as DetectGridMessage["payload"];
        const method = p.method === "line_based" ? 1 : 0;
        const result = await emDetectGrid(p.imageData, { method });
        const gridCoords: GridCoordinates | null = result.success && result.bounds
          ? gridBoundsToCoordinates(result.bounds)
          : null;
        self.postMessage({ type: "DETECT_GRID_COMPLETE", id, payload: { gridCoordinates: gridCoords } });
        break;
      }

      default:
        throw new Error(`Unknown message type: ${type}`);
    }
  } catch (error) {
    const response: WorkerResponse = {
      type: "ERROR",
      id,
      error: error instanceof Error ? error.message : String(error),
    };
    self.postMessage(response);
  }
};

export {};
