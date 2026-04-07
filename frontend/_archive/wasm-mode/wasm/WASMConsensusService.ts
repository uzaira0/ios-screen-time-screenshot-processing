import type { Consensus, HourlyData } from "../../models";
import type { IConsensusService } from "../../interfaces";
import type { IStorageService } from "../../interfaces";

export class WASMConsensusService implements IConsensusService {
  private storageService: IStorageService;

  constructor(storageService: IStorageService) {
    this.storageService = storageService;
  }

  async getForScreenshot(screenshotId: number): Promise<Consensus> {
    const annotations =
      await this.storageService.getAnnotationsByScreenshot(screenshotId);

    if (annotations.length === 0) {
      throw new Error("No annotations found for screenshot");
    }

    const consensusData: HourlyData = {};
    const disagreements: Array<{
      hour: number;
      values: {
        annotator_id: number;
        annotator_username: string;
        value: number;
      }[];
      consensus_value: number;
    }> = [];

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

      const consensusValue = parseInt(
        Object.entries(valueCounts).sort(
          ([, a], [, b]) => (b as number) - (a as number),
        )[0]?.[0] ?? "0",
      );

      consensusData[hour] = consensusValue;

      // Track disagreements if values differ
      const uniqueValues = [...new Set(values)];
      if (uniqueValues.length > 1) {
        disagreements.push({
          hour,
          values: hourValues,
          consensus_value: consensusValue,
        });
      }
    }

    const totalHours = 24;
    const agreedHours = totalHours - disagreements.length;
    const agreementPercentage = Math.round((agreedHours / totalHours) * 100);

    return {
      screenshot_id: screenshotId,
      total_annotations: annotations.length,
      consensus_data: consensusData,
      disagreements,
      agreement_percentage: agreementPercentage,
    };
  }
}
