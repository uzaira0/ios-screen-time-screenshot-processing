import type { Consensus } from "@/types";
import type { components } from "@/types/api-schema";

/** Re-export from OpenAPI schema — Pydantic is the single source of truth */
export type GroupVerificationSummary =
  components["schemas"]["GroupVerificationSummary"];
export type ScreenshotTierItem = components["schemas"]["ScreenshotTierItem"];

export type VerificationTier = "single_verified" | "agreed" | "disputed";

export interface IConsensusService {
  getForScreenshot(screenshotId: number): Promise<Consensus>;

  /**
   * Get all groups with verification tier breakdown.
   * Server: queries /consensus/groups
   * WASM: aggregates from local annotations
   */
  getGroupsWithTiers(): Promise<GroupVerificationSummary[]>;

  /**
   * Get screenshots in a specific verification tier for a group.
   * Server: queries /consensus/groups/{id}/screenshots
   * WASM: filters local screenshots by annotation count
   */
  getScreenshotsByTier(
    groupId: string,
    tier: VerificationTier,
  ): Promise<ScreenshotTierItem[]>;
}
