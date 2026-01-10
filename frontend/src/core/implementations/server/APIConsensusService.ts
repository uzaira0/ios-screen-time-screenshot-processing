import { api } from "@/services/apiClient";
import type { Consensus } from "@/types";
import type {
  IConsensusService,
  GroupVerificationSummary,
  ScreenshotTierItem,
  VerificationTier,
} from "../../interfaces";

/**
 * Server-side consensus service using openapi-fetch apiClient.
 * No axios dependency - uses type-safe API client.
 */
export class APIConsensusService implements IConsensusService {
  constructor(_baseURL?: string) {
    // baseURL is no longer needed - apiClient handles this
  }

  async getForScreenshot(screenshotId: number): Promise<Consensus> {
    const result = await api.consensus.getForScreenshot(screenshotId);
    // ConsensusAnalysis (API) and Consensus (UI) have different shapes but
    // the backend response is consumed directly by the UI. Double cast needed
    // until these types are unified.
    return result as unknown as Consensus;
  }

  async getGroupsWithTiers(): Promise<GroupVerificationSummary[]> {
    return api.consensus.getGroupsWithTiers();
  }

  async getScreenshotsByTier(
    groupId: string,
    tier: VerificationTier,
  ): Promise<ScreenshotTierItem[]> {
    return api.consensus.getScreenshotsByTier(groupId, tier);
  }
}
