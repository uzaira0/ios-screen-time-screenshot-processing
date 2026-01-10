/**
 * Pure helper functions for extracting recent crop and PHI configs
 * from screenshots' preprocessing event logs. These are extracted
 * into their own module for testability.
 */

import type { CropRect } from "./CropAdjustModal";
import type { PHIRegion, RecentPHIConfig } from "./PHIRegionEditor";
import type { PreprocessingEventData } from "@/store/preprocessingStore";

/** Minimal screenshot shape needed by the helpers. */
export interface ScreenshotLike {
  id: number;
  processing_metadata?: Record<string, unknown> | null;
}

/**
 * Scan all screenshots' events for completed manual cropping events
 * that have exact crop coordinates. Returns deduplicated CropRect[]
 * sorted most-recent-first.
 */
export function getRecentCropConfigs(
  screenshots: ScreenshotLike[],
  currentId: number,
  limit = 3,
): CropRect[] {
  const seen: CropRect[] = [];

  // Collect all crop events that have usable crop geometry, sorted by timestamp
  const allCropEvents: { rect: CropRect; timestamp: string }[] = [];

  for (const s of screenshots) {
    if (s.id === currentId) continue;
    const pp = (s.processing_metadata as Record<string, unknown>)
      ?.preprocessing as Record<string, unknown> | undefined;
    const events = pp?.events as PreprocessingEventData[] | undefined;
    if (!events) continue;

    for (const ev of events) {
      if (ev.stage !== "cropping") continue;
      const result = ev.result as Record<string, unknown> | undefined;
      if (!result) continue;

      let rect: CropRect | undefined;
      // Only manual crops have exact coordinates — auto crops don't record
      // the offset, so we can't derive a reliable reusable rect from them.
      if (result.manual) {
        const params = ev.params as Record<string, unknown> | undefined;
        if (params && typeof params.left === "number") {
          rect = {
            left: params.left as number,
            top: params.top as number,
            right: params.right as number,
            bottom: params.bottom as number,
          };
        }
      }

      if (rect) {
        allCropEvents.push({ rect, timestamp: ev.timestamp });
      }
    }
  }

  // Sort most recent first
  allCropEvents.sort((a, b) => b.timestamp.localeCompare(a.timestamp));

  // Deduplicate: exact match on all 4 values
  for (const { rect } of allCropEvents) {
    const isDup = seen.some(
      (s) =>
        s.left === rect.left &&
        s.top === rect.top &&
        s.right === rect.right &&
        s.bottom === rect.bottom,
    );
    if (!isDup) {
      seen.push(rect);
      if (seen.length >= limit) break;
    }
  }

  return seen;
}

/**
 * Scan all screenshots' events for completed phi_detection events with
 * region data. Returns deduplicated RecentPHIConfig[] sorted most-recent-first.
 * Deduplication snaps bbox coords to 20px grid before comparing.
 */
export function getRecentPHIConfigs(
  screenshots: ScreenshotLike[],
  currentId: number,
  limit = 3,
): RecentPHIConfig[] {
  const results: RecentPHIConfig[] = [];
  const seenKeys: string[] = [];

  // Collect all phi_detection events with regions, sort by timestamp
  const allPHIEvents: { regions: PHIRegion[]; timestamp: string }[] = [];

  for (const s of screenshots) {
    if (s.id === currentId) continue;
    const pp = (s.processing_metadata as Record<string, unknown>)
      ?.preprocessing as Record<string, unknown> | undefined;
    const events = pp?.events as PreprocessingEventData[] | undefined;
    if (!events) continue;

    for (const ev of events) {
      if (ev.stage !== "phi_detection") continue;
      // Only include manually saved region configs, not auto-detected results
      if (ev.source !== "manual") continue;
      const result = ev.result as Record<string, unknown> | undefined;
      const regions = result?.regions as PHIRegion[] | undefined;
      if (!regions || regions.length === 0) continue;

      allPHIEvents.push({ regions, timestamp: ev.timestamp });
    }
  }

  allPHIEvents.sort((a, b) => b.timestamp.localeCompare(a.timestamp));

  // Deduplicate: same region count + each bbox rounded to nearest 20px matches
  const snap = (v: number) => Math.round(v / 20) * 20;
  const regionKey = (r: PHIRegion) =>
    `${snap(r.x)},${snap(r.y)},${snap(r.w)},${snap(r.h)}`;

  for (const { regions } of allPHIEvents) {
    const key = regions
      .map(regionKey)
      .sort()
      .join("|");
    if (seenKeys.includes(key)) continue;
    seenKeys.push(key);

    // Build label: first 2 unique labels + count
    const uniqueLabels = [...new Set(regions.map((r) => r.label))];
    const labelPart =
      uniqueLabels.length <= 2
        ? uniqueLabels.join(", ")
        : uniqueLabels.slice(0, 2).join(", ") + "...";
    const label = `${labelPart} (${regions.length})`;

    results.push({ regions, label });
    if (results.length >= limit) break;
  }

  return results;
}
