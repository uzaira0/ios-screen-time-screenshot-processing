import { api, getAuthHeaders } from "@/services/apiClient";
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
import type { IScreenshotService, ProcessingProgressCallback } from "../../interfaces";

/**
 * Server-side screenshot service using openapi-fetch apiClient.
 * No axios dependency - uses type-safe API client.
 */
export class APIScreenshotService implements IScreenshotService {
  constructor(_baseURL?: string) {
    // baseURL is no longer needed - apiClient handles this
  }

  async getNext(
    groupId?: string,
    processingStatus?: string,
  ): Promise<Screenshot | null> {
    const result = await api.screenshots.getNext({
      ...(groupId && { group: groupId }),
      ...(processingStatus && { processing_status: processingStatus }),
    });
    return result?.screenshot ?? null;
  }

  async getById(id: number): Promise<Screenshot> {
    return api.screenshots.getById(id) as Promise<Screenshot>;
  }

  async getAll(status?: string, skip = 0, limit = 50): Promise<Screenshot[]> {
    const result = await api.screenshots.list({
      ...(status && { processing_status: status }),
      page: Math.floor(skip / limit) + 1,
      page_size: limit,
    });
    return result?.items ?? [];
  }

  async addScreenshots(
    file: File,
    imageType: ImageType,
    options?: {
      groupId?: string;
      participantId?: string;
      screenshotDate?: string;
      originalFilepath?: string;
    },
  ): Promise<Screenshot> {
    const groupId = options?.groupId || "default";
    const metadata = JSON.stringify({
      group_id: groupId,
      image_type: imageType,
      items: [{
        original_filepath: options?.originalFilepath || file.name,
        participant_id: options?.participantId,
        screenshot_date: options?.screenshotDate,
      }],
    });

    const formData = new FormData();
    formData.append("metadata", metadata);
    formData.append("files", file);

    const result = await api.preprocessing.uploadBrowser(formData);
    const item = result?.results?.[0];
    if (!item?.screenshot_id) {
      throw new Error("Upload failed: no screenshot ID returned");
    }
    return this.getById(item.screenshot_id);
  }

  async getImageUrl(screenshotId: number): Promise<string> {
    return api.screenshots.getImageUrl(screenshotId);
  }

  async getProcessingResult(screenshotId: number): Promise<ProcessingResult> {
    // Get screenshot and return it as ProcessingResult.
    // Screenshot and ProcessingResult share most fields (extracted_hourly_data, etc.)
    // but are separate schema types. The cast is intentional for API compatibility.
    const screenshot = await this.getById(screenshotId);
    return screenshot as unknown as ProcessingResult;
  }

  async reprocess(
    screenshotId: number,
    coords: GridCoordinates,
    _onProgress?: ProcessingProgressCallback,
    maxShift?: number,
  ): Promise<ProcessingResult> {
    return api.screenshots.reprocess(screenshotId, {
      grid_upper_left_x: coords.upper_left.x,
      grid_upper_left_y: coords.upper_left.y,
      grid_lower_right_x: coords.lower_right.x,
      grid_lower_right_y: coords.lower_right.y,
      max_shift: maxShift ?? 5,
    }) as Promise<ProcessingResult>;
  }

  async reprocessWithMethod(
    screenshotId: number,
    method: "ocr_anchored" | "line_based",
    _onProgress?: ProcessingProgressCallback,
    maxShift?: number,
  ): Promise<ProcessingResult> {
    return api.screenshots.reprocess(screenshotId, {
      processing_method: method,
      max_shift: maxShift ?? 5,
    }) as Promise<ProcessingResult>;
  }

  async skip(screenshotId: number, _reason?: string): Promise<void> {
    await api.screenshots.skip(screenshotId);
    // Skip reason stored client-side only for now; server skip endpoint
    // would need a backend change to accept a reason parameter.
  }

  async updateTitle(screenshotId: number, title: string): Promise<void> {
    await api.screenshots.update(screenshotId, { extracted_title: title });
  }

  async updateHourlyData(
    screenshotId: number,
    hourlyData: Record<string, number>,
  ): Promise<void> {
    await api.screenshots.update(screenshotId, { extracted_hourly_data: hourlyData });
  }

  async processIfNeeded(screenshot: Screenshot): Promise<Screenshot> {
    // In server mode, processing happens server-side
    return screenshot;
  }

  async getStats(): Promise<QueueStats> {
    return api.screenshots.getStats() as Promise<QueueStats>;
  }

  async getList(params: ScreenshotListParams): Promise<ScreenshotListResponse> {
    return api.screenshots.list(params) as Promise<ScreenshotListResponse>;
  }

  async navigate(
    screenshotId: number,
    params: NavigationParams,
  ): Promise<NavigationResponse> {
    return api.screenshots.navigate(screenshotId, params) as Promise<NavigationResponse>;
  }

  async verify(
    screenshotId: number,
    gridCoords?: GridCoordinates,
  ): Promise<Screenshot> {
    return api.screenshots.verify(screenshotId, gridCoords) as Promise<Screenshot>;
  }

  async unverify(screenshotId: number): Promise<Screenshot> {
    return api.screenshots.unverify(screenshotId) as Promise<Screenshot>;
  }

  async recalculateOcr(screenshotId: number): Promise<string | null> {
    const result = await api.screenshots.recalculateOcr(screenshotId);
    return result?.extracted_total ?? null;
  }

  async getGroups(): Promise<Group[]> {
    const groups = await api.groups.list();
    return (groups ?? []) as Group[];
  }

  async deleteGroup(groupId: string): Promise<{ screenshots_deleted: number; annotations_deleted: number }> {
    const result = await api.admin.deleteGroup(groupId);
    return result;
  }

  async updateGridCoords(_screenshotId: number, _coords: GridCoordinates | null): Promise<void> {
    // Server mode: grid coords are persisted via annotation submission
  }

  async exportCSV(): Promise<string> {
    const csvUrl = api.export.getCSVUrl();
    const response = await fetch(csvUrl, { headers: getAuthHeaders() });
    if (!response.ok) throw new Error("Export failed");
    return response.text();
  }
}
