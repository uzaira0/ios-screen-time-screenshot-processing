import type { Annotation, Consensus, HourlyData } from "@/types";
import type {
  IConsensusService,
  GroupVerificationSummary,
  ScreenshotTierItem,
  VerificationTier,
} from "@/core/interfaces";
import type { IStorageService } from "@/core/interfaces";
import { db } from "./storage/database";

export class WASMConsensusService implements IConsensusService {
  private storageService: IStorageService;

  constructor(storageService: IStorageService) {
    this.storageService = storageService;
  }

  async getForScreenshot(screenshotId: number): Promise<Consensus> {
    const annotations =
      await this.storageService.getAnnotationsByScreenshot(screenshotId);
    return computeConsensus(screenshotId, annotations);
  }

  async getGroupsWithTiers(): Promise<GroupVerificationSummary[]> {
    const allScreenshots = await db.screenshots.toArray();
    const allAnnotations = await db.annotations.toArray();

    // Group annotations by screenshot_id
    const annotationsByScreenshot = groupAnnotationsByScreenshot(allAnnotations);

    // Group screenshots and classify by verification tier
    const groupMap = new Map<
      string,
      GroupVerificationSummary
    >();

    for (const s of allScreenshots) {
      const gid = s.group_id || "ungrouped";
      let group = groupMap.get(gid);
      if (!group) {
        group = {
          id: gid,
          name: gid === "ungrouped" ? "Ungrouped" : gid,
          image_type:
            (s.image_type as "battery" | "screen_time") || "screen_time",
          single_verified: 0,
          agreed: 0,
          disputed: 0,
          total_verified: 0,
          total_screenshots: 0,
        };
        groupMap.set(gid, group);
      }

      group.total_screenshots++;

      const annotations = annotationsByScreenshot.get(s.id!) || [];
      if (annotations.length >= 1) {
        group.total_verified++;

        if (annotations.length === 1) {
          group.single_verified++;
        } else {
          // 2+ annotations — compute consensus in-memory (no DB query)
          const consensus = computeConsensus(s.id!, annotations);
          if (consensus.disagreements.length > 0) {
            group.disputed++;
          } else {
            group.agreed++;
          }
        }
      }
    }

    return Array.from(groupMap.values());
  }

  async getScreenshotsByTier(
    groupId: string,
    tier: VerificationTier,
  ): Promise<ScreenshotTierItem[]> {
    // Get screenshots for this group
    const screenshots =
      groupId === "ungrouped"
        ? await db.screenshots.filter((s) => !s.group_id).toArray()
        : await db.screenshots.where("group_id").equals(groupId).toArray();

    const screenshotIds = screenshots.map((s) => s.id!);
    const groupAnnotations = await db.annotations
      .where("screenshot_id")
      .anyOf(screenshotIds)
      .toArray();
    const annotationsByScreenshot = groupAnnotationsByScreenshot(groupAnnotations);

    const results: ScreenshotTierItem[] = [];

    for (const s of screenshots) {
      const annotations = annotationsByScreenshot.get(s.id!) || [];
      if (annotations.length === 0) continue;

      let matchesTier = false;
      let hasDifferences = false;

      if (tier === "single_verified" && annotations.length === 1) {
        matchesTier = true;
      } else if (annotations.length >= 2) {
        // Compute consensus in-memory — reuse result for both match check and has_differences
        const consensus = computeConsensus(s.id!, annotations);
        hasDifferences = consensus.disagreements.length > 0;

        if (tier === "disputed" && hasDifferences) matchesTier = true;
        if (tier === "agreed" && !hasDifferences) matchesTier = true;
      }

      if (matchesTier) {
        results.push({
          id: s.id!,
          file_path: "",
          participant_id: s.participant_id || null,
          screenshot_date: s.uploaded_at || null,
          verifier_count: annotations.length,
          has_differences: hasDifferences,
          extracted_title: s.extracted_title || null,
        });
      }
    }

    return results;
  }
}

/** Group annotations by screenshot_id for O(1) lookup */
function groupAnnotationsByScreenshot(
  annotations: Annotation[],
): Map<number, Annotation[]> {
  const map = new Map<number, Annotation[]>();
  for (const ann of annotations) {
    const list = map.get(ann.screenshot_id);
    if (list) {
      list.push(ann);
    } else {
      map.set(ann.screenshot_id, [ann]);
    }
  }
  return map;
}

/** Pure computation — no DB queries */
function computeConsensus(
  screenshotId: number,
  annotations: Annotation[],
): Consensus {
  if (annotations.length === 0) {
    return {
      screenshot_id: screenshotId,
      total_annotations: 0,
      consensus_data: {},
      disagreements: [],
      agreement_percentage: 100,
    };
  }

  const consensusData: HourlyData = {};
  const disagreements: Consensus["disagreements"] = [];

  for (let hour = 0; hour < 24; hour++) {
    const hourValues = annotations.map((a, idx) => ({
      annotator_id: a.user_id || idx + 1,
      annotator_username: `user-${a.user_id || idx + 1}`,
      value: a.hourly_values?.[hour] ?? 0,
    }));

    const values = hourValues.map((v) => v.value);

    // Use the most common value, or first value if all different
    const valueCounts = values.reduce(
      (acc, val) => {
        acc[val] = (acc[val] || 0) + 1;
        return acc;
      },
      {} as Record<number, number>,
    );

    const consensusValue = Number(
      Object.entries(valueCounts).sort(
        ([, a], [, b]) => (b as number) - (a as number),
      )[0]?.[0] ?? "0",
    );

    consensusData[hour] = consensusValue;

    const uniqueValues = [...new Set(values)];
    if (uniqueValues.length > 1) {
      disagreements.push({
        hour,
        values: hourValues,
        consensus_value: consensusValue,
      });
    }
  }

  const agreedHours = 24 - disagreements.length;
  const agreementPercentage = Math.round((agreedHours / 24) * 100);

  return {
    screenshot_id: screenshotId,
    total_annotations: annotations.length,
    consensus_data: consensusData,
    disagreements,
    agreement_percentage: agreementPercentage,
  };
}
