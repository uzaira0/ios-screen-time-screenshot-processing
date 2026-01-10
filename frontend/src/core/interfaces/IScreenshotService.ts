import type {
  Screenshot,
  Group,
  GridCoordinates,
  ProcessingResult,
  QueueStats,
  ImageType,
  ScreenshotListResponse,
  ScreenshotListParams,
  NavigationResponse,
  NavigationParams,
} from "@/types";
import type { ProcessingProgress } from "./IProcessingService";

export type ProcessingProgressCallback = (progress: ProcessingProgress) => void;

export interface IScreenshotService {
  getNext(
    groupId?: string,
    processingStatus?: string,
  ): Promise<Screenshot | null>;

  getById(id: number): Promise<Screenshot>;

  getAll(status?: string, skip?: number, limit?: number): Promise<Screenshot[]>;

  addScreenshots(
    file: File,
    imageType: ImageType,
    options?: {
      groupId?: string;
      participantId?: string;
      screenshotDate?: string;
      originalFilepath?: string;
    },
  ): Promise<Screenshot>;

  /**
   * Get URL for displaying a screenshot image.
   * Always returns a Promise for consistency across implementations.
   * - Server mode: Returns API URL (resolves immediately)
   * - WASM mode: Returns blob URL from IndexedDB (async)
   */
  getImageUrl(screenshotId: number): Promise<string>;

  getProcessingResult(screenshotId: number): Promise<ProcessingResult>;

  reprocess(
    screenshotId: number,
    coords: GridCoordinates,
    onProgress?: ProcessingProgressCallback,
    maxShift?: number,
  ): Promise<ProcessingResult>;

  /**
   * Reprocess screenshot using a specific processing method.
   * - "ocr_anchored": Uses "12 AM" and "60" text anchors (default)
   * - "line_based": Uses visual line patterns without OCR for grid detection
   * @param maxShift - Maximum pixels to shift grid for optimization (0=disabled, default=10)
   */
  reprocessWithMethod(
    screenshotId: number,
    method: "ocr_anchored" | "line_based",
    onProgress?: ProcessingProgressCallback,
    maxShift?: number,
  ): Promise<ProcessingResult>;

  skip(screenshotId: number, reason?: string): Promise<void>;

  updateTitle(screenshotId: number, title: string): Promise<void>;

  /**
   * Update screenshot's hourly data directly (for manual edits).
   */
  updateHourlyData(
    screenshotId: number,
    hourlyData: Record<string, number>,
  ): Promise<void>;

  /**
   * Process screenshot if it doesn't have title/total extracted yet.
   * Returns the updated screenshot with processing results.
   */
  processIfNeeded(screenshot: Screenshot): Promise<Screenshot>;

  getStats(): Promise<QueueStats>;

  /**
   * Get paginated list of screenshots with filtering.
   */
  getList(params: ScreenshotListParams): Promise<ScreenshotListResponse>;

  /**
   * Navigate to next/prev screenshot within filtered results.
   */
  navigate(
    screenshotId: number,
    params: NavigationParams,
  ): Promise<NavigationResponse>;

  /**
   * Mark screenshot as verified by current user.
   * Optionally saves the current grid coordinates to freeze them at verification time.
   */
  verify(
    screenshotId: number,
    gridCoords?: GridCoordinates,
  ): Promise<Screenshot>;

  /**
   * Remove verification mark from screenshot for current user.
   */
  unverify(screenshotId: number): Promise<Screenshot>;

  /**
   * Recalculate OCR total for a screenshot.
   * Re-runs OCR extraction on the original image.
   * Returns the new extracted_total value or null if extraction failed.
   */
  recalculateOcr(screenshotId: number): Promise<string | null>;

  /**
   * List all groups with screenshot counts.
   * Server: queries /screenshots/groups
   * WASM: aggregates from IndexedDB screenshots by group_id
   */
  getGroups(): Promise<Group[]>;

  /**
   * Delete a group and all its screenshots, annotations, and blobs.
   * Server: calls DELETE /admin/groups/{id}
   * WASM: deletes from IndexedDB + OPFS by group_id
   * Returns count of deleted screenshots and annotations.
   */
  deleteGroup(groupId: string): Promise<{ screenshots_deleted: number; annotations_deleted: number }>;

  /**
   * Export annotations as CSV data string.
   * Server: fetches from /screenshots/export/csv
   * WASM: generates CSV from local IndexedDB data
   */
  exportCSV(): Promise<string>;

  /**
   * Persist grid coordinates to storage (IndexedDB in WASM, no-op in server mode).
   * Used to auto-save grid selection so it survives reload/navigation/crop.
   */
  updateGridCoords(
    screenshotId: number,
    coords: GridCoordinates | null,
  ): Promise<void>;
}
