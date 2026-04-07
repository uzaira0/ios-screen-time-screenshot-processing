import { api } from "@/services/apiClient";
import { config } from "@/config";
import type {
  IPreprocessingService,
  PreprocessingStage,
  RunStageOptions,
  RunStageResult,
} from "@/core/interfaces/IPreprocessingService";
import type {
  Group,
  Screenshot,
  PreprocessingSummary,
  PreprocessingEventLog,
  PreprocessingDetailsResponse,
  BrowserUploadResponse,
  PHIRegionsResponse,
  PHIRegionRect,
} from "@/types";

/**
 * Server-mode preprocessing service.
 * Thin wrapper delegating all calls to the existing api.preprocessing / api.groups / api.screenshots methods.
 */
export class ServerPreprocessingService implements IPreprocessingService {
  async getGroups(): Promise<Group[]> {
    return api.groups.list() as Promise<Group[]>;
  }

  async getScreenshots(params: {
    group_id: string;
    page_size?: number;
    sort_by?: string;
    sort_order?: string;
  }): Promise<{ items: Screenshot[]; total: number }> {
    return api.screenshots.list(params) as Promise<{ items: Screenshot[]; total: number }>;
  }

  async getSummary(groupId: string): Promise<PreprocessingSummary> {
    return api.preprocessing.getSummary(groupId) as Promise<PreprocessingSummary>;
  }

  async runStage(stage: PreprocessingStage, options: RunStageOptions): Promise<RunStageResult> {
    return api.preprocessing.runStage(stage, options);
  }

  async resetStage(stage: PreprocessingStage, groupId: string): Promise<{ message: string; count?: number }> {
    return api.preprocessing.resetStage(stage, groupId) as Promise<{ message: string; count?: number }>;
  }

  async invalidateFromStage(screenshotId: number, stage: string): Promise<void> {
    await api.preprocessing.invalidateFromStage(screenshotId, stage);
  }

  async getEventLog(screenshotId: number): Promise<PreprocessingEventLog> {
    return api.preprocessing.getEventLog(screenshotId) as Promise<PreprocessingEventLog>;
  }

  async getScreenshot(screenshotId: number): Promise<Screenshot | null> {
    return api.screenshots.getById(screenshotId) as Promise<Screenshot | null>;
  }

  async uploadBrowser(formData: FormData): Promise<BrowserUploadResponse> {
    return api.preprocessing.uploadBrowser(formData) as Promise<BrowserUploadResponse>;
  }

  async getOriginalImageUrl(screenshotId: number): Promise<string> {
    return api.preprocessing.getOriginalImageUrl(screenshotId);
  }

  async applyManualCrop(
    screenshotId: number,
    crop: { left: number; top: number; right: number; bottom: number },
  ): Promise<void> {
    await api.preprocessing.applyManualCrop(screenshotId, crop);
  }

  async getPHIRegions(screenshotId: number): Promise<PHIRegionsResponse> {
    return api.preprocessing.getPHIRegions(screenshotId) as Promise<PHIRegionsResponse>;
  }

  async savePHIRegions(screenshotId: number, body: { regions: PHIRegionRect[]; preset: string }): Promise<void> {
    await api.preprocessing.savePHIRegions(screenshotId, body);
  }

  async applyRedaction(screenshotId: number, body: { regions: PHIRegionRect[]; redaction_method: string }): Promise<void> {
    await api.preprocessing.applyRedaction(screenshotId, body);
  }

  async getDetails(screenshotId: number): Promise<PreprocessingDetailsResponse | null> {
    return api.preprocessing.getDetails(screenshotId) as Promise<PreprocessingDetailsResponse | null>;
  }

  async getStageImageUrl(screenshotId: number, stage: string): Promise<string> {
    return `${config.apiBaseUrl}/screenshots/${screenshotId}/stage-image?stage=${stage}`;
  }

  async getImageUrl(screenshotId: number): Promise<string> {
    return `${config.apiBaseUrl}/screenshots/${screenshotId}/image`;
  }
}
