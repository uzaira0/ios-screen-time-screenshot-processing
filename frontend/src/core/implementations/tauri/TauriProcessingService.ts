/**
 * Tauri-native processing service — calls Rust image processing commands.
 *
 * This replaces the WASM (Tesseract.js) processing with native Rust
 * processing via Tauri IPC, giving ~23x faster image analysis.
 *
 * NOTE: The IProcessingService interface accepts ImageData | Blob, but Tauri
 * needs file paths. In Tauri mode, the frontend reads files via tauri-plugin-fs
 * and passes paths through a TauriImageRef wrapper. Methods that receive a raw
 * Blob without a path fall back to returning null/empty results.
 */

import type {
  IProcessingService,
  ProcessingConfig,
  ProcessingProgressCallback,
} from "../../interfaces/IProcessingService";
import type { HourlyData, GridCoordinates, ImageType } from "@/types";

/** Result shape returned by the Rust `process_screenshot` command. */
interface RustProcessingResult {
  hourly_values: number[] | null;
  total: number;
  title: string | null;
  total_text: string | null;
  grid_bounds: {
    upper_left_x: number;
    upper_left_y: number;
    lower_right_x: number;
    lower_right_y: number;
  } | null;
  alignment_score: number | null;
  detection_method: string;
  processing_time_ms: number;
  is_daily_total: boolean;
  issues: string[];
  has_blocking_issues: boolean;
  grid_detection_confidence: number | null;
  title_y_position: number | null;
}

/**
 * Wrapper to attach a filesystem path to an ImageData/Blob for Tauri IPC.
 * Usage: `new TauriImageRef(blob, "/path/to/file.png")`
 */
export class TauriImageRef extends Blob {
  public readonly tauriPath: string;

  constructor(source: Blob, path: string) {
    super([source]);
    this.tauriPath = path;
  }
}

/** Extract the Tauri file path from an image ref, or return null. */
function getTauriPath(imageData: ImageData | Blob): string | null {
  if (imageData instanceof TauriImageRef) {
    return imageData.tauriPath;
  }
  return null;
}

/** Convert 24-element array to HourlyData record. */
function toHourlyData(values: number[]): HourlyData {
  const data: HourlyData = {};
  for (let i = 0; i < 24 && i < values.length; i++) {
    data[String(i)] = Math.round((values[i] ?? 0) * 100) / 100;
  }
  data["total"] = values.length > 24 ? (values[24] ?? 0) : values.reduce((a, b) => a + b, 0);
  return data;
}

export class TauriProcessingService implements IProcessingService {
  private initialized = false;
  private invokeFn: ((cmd: string, args?: Record<string, unknown>) => Promise<unknown>) | null = null;

  /** Lazily cache the Tauri invoke function to avoid dynamic import on every call. */
  private async getInvoke(): Promise<(cmd: string, args?: Record<string, unknown>) => Promise<unknown>> {
    if (!this.invokeFn) {
      const mod = await import("@tauri-apps/api/core");
      this.invokeFn = mod.invoke as (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;
    }
    return this.invokeFn;
  }

  async initialize(): Promise<void> {
    await this.getInvoke();
    this.initialized = true;
  }

  isInitialized(): boolean {
    return this.initialized;
  }

  terminate(): void {
    // No worker to terminate
  }

  async processImage(
    imageData: ImageData | Blob,
    config: ProcessingConfig,
    onProgress?: ProcessingProgressCallback,
  ): Promise<{
    hourlyData: HourlyData;
    title: string | null;
    total: string | null;
    gridCoordinates?: GridCoordinates;
    gridDetectionFailed?: boolean;
    gridDetectionError?: string;
    alignmentScore?: number | null;
  }> {
    const invoke = await this.getInvoke();

    onProgress?.({ stage: "loading", progress: 0.1, message: "Loading image..." });

    const path = getTauriPath(imageData);
    if (!path) {
      throw new Error(
        "TauriProcessingService requires a TauriImageRef with a file path. " +
        "Use the Tauri file picker flow to provide images.",
      );
    }

    onProgress?.({ stage: "preprocessing", progress: 0.3, message: "Processing image..." });

    let result: RustProcessingResult;

    if (config.gridCoordinates) {
      result = await invoke("process_screenshot_with_grid", {
        path,
        upperLeft: [config.gridCoordinates.upper_left.x, config.gridCoordinates.upper_left.y],
        lowerRight: [config.gridCoordinates.lower_right.x, config.gridCoordinates.lower_right.y],
        imageType: config.imageType,
      }) as RustProcessingResult;
    } else {
      result = await invoke("process_screenshot", {
        path,
        imageType: config.imageType,
        detectionMethod: "line_based",
      }) as RustProcessingResult;
    }

    onProgress?.({ stage: "complete", progress: 1.0, message: "Done" });

    const base = {
      hourlyData: toHourlyData(result.hourly_values ?? []),
      title: result.title,
      total: result.total_text,
      alignmentScore: result.alignment_score,
    };

    if (result.grid_bounds) {
      return {
        ...base,
        gridCoordinates: {
          upper_left: { x: result.grid_bounds.upper_left_x, y: result.grid_bounds.upper_left_y },
          lower_right: { x: result.grid_bounds.lower_right_x, y: result.grid_bounds.lower_right_y },
        },
      };
    }

    return base;
  }

  async extractTitle(_imageData: ImageData | Blob): Promise<string | null> {
    // OCR title extraction requires Tesseract binding (Phase 1 decision pending)
    return null;
  }

  async extractTotal(_imageData: ImageData | Blob): Promise<string | null> {
    return null;
  }

  async extractHourlyData(
    imageData: ImageData | Blob,
    gridCoordinates: GridCoordinates,
    imageType: ImageType,
  ): Promise<HourlyData> {
    const path = getTauriPath(imageData);
    if (!path) {
      throw new Error("TauriProcessingService requires a TauriImageRef with a file path.");
    }

    const invoke = await this.getInvoke();

    const values = await invoke("extract_hourly_data", {
      path,
      upperLeft: [gridCoordinates.upper_left.x, gridCoordinates.upper_left.y],
      lowerRight: [gridCoordinates.lower_right.x, gridCoordinates.lower_right.y],
      imageType,
    }) as number[];

    return toHourlyData(values);
  }

  async detectGrid(
    imageData: ImageData | Blob,
    imageType: ImageType,
    method?: "ocr_anchored" | "line_based",
  ): Promise<GridCoordinates | null> {
    const path = getTauriPath(imageData);
    if (!path) {
      return null;
    }

    const invoke = await this.getInvoke();

    try {
      const result = await invoke("process_screenshot", {
        path,
        imageType,
        detectionMethod: method ?? "line_based",
      }) as RustProcessingResult;

      if (result.grid_bounds) {
        return {
          upper_left: { x: result.grid_bounds.upper_left_x, y: result.grid_bounds.upper_left_y },
          lower_right: { x: result.grid_bounds.lower_right_x, y: result.grid_bounds.lower_right_y },
        };
      }
    } catch (error) {
      console.error("[TauriProcessingService] detectGrid failed:", error);
    }

    return null;
  }
}
