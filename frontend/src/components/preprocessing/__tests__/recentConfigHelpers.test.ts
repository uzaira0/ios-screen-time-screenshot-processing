import { describe, test, expect } from "vitest";
import { getRecentCropConfigs, getRecentPHIConfigs } from "../recentConfigHelpers";
import type { ScreenshotLike } from "../recentConfigHelpers";

// ---------------------------------------------------------------------------
// Factory helpers for building test screenshots with preprocessing events
// ---------------------------------------------------------------------------

function makeScreenshot(
  id: number,
  events: Array<Record<string, unknown>> = [],
): ScreenshotLike {
  return {
    id,
    processing_metadata: {
      preprocessing: {
        events,
        current_events: {},
        stage_status: {},
      },
    },
  };
}

function manualCropEvent(
  left: number,
  top: number,
  right: number,
  bottom: number,
  timestamp = "2025-01-01T00:00:00Z",
): Record<string, unknown> {
  return {
    event_id: Math.floor(Math.random() * 1000),
    stage: "cropping",
    timestamp,
    source: "manual",
    params: { left, top, right, bottom },
    result: { was_cropped: true, manual: true },
    output_file: null,
    input_file: null,
  };
}

function autoCropEvent(
  timestamp = "2025-01-01T00:00:00Z",
): Record<string, unknown> {
  return {
    event_id: Math.floor(Math.random() * 1000),
    stage: "cropping",
    timestamp,
    source: "auto",
    params: {},
    result: {
      was_cropped: true,
      original_dimensions: [2048, 2732],
      cropped_dimensions: [1536, 2048],
    },
    output_file: null,
    input_file: null,
  };
}

function phiEvent(
  regions: Array<{ x: number; y: number; w: number; h: number; label: string }>,
  timestamp = "2025-01-01T00:00:00Z",
): Record<string, unknown> {
  return {
    event_id: Math.floor(Math.random() * 1000),
    stage: "phi_detection",
    timestamp,
    source: "manual",
    params: {},
    result: {
      phi_detected: regions.length > 0,
      regions_count: regions.length,
      regions: regions.map((r) => ({
        x: r.x,
        y: r.y,
        w: r.w,
        h: r.h,
        label: r.label,
        source: "auto",
        confidence: 0.95,
        text: "",
      })),
    },
    output_file: null,
    input_file: null,
  };
}

// ---------------------------------------------------------------------------
// getRecentCropConfigs
// ---------------------------------------------------------------------------

describe("getRecentCropConfigs", () => {
  test("returns empty when no screenshots have manual crop events", () => {
    const screenshots = [
      makeScreenshot(1, [autoCropEvent()]),
      makeScreenshot(2, [autoCropEvent()]),
    ];
    const result = getRecentCropConfigs(screenshots, 99);
    expect(result).toEqual([]);
  });

  test("returns empty when all screenshots lack preprocessing metadata", () => {
    const screenshots: ScreenshotLike[] = [
      { id: 1, processing_metadata: null },
      { id: 2 },
    ];
    const result = getRecentCropConfigs(screenshots, 99);
    expect(result).toEqual([]);
  });

  test("extracts manual crop rects from events", () => {
    const screenshots = [
      makeScreenshot(1, [manualCropEvent(100, 0, 800, 1200)]),
      makeScreenshot(2, [manualCropEvent(50, 10, 900, 1100)]),
    ];
    const result = getRecentCropConfigs(screenshots, 99);
    expect(result).toHaveLength(2);
    expect(result[0]).toEqual({ left: 100, top: 0, right: 800, bottom: 1200 });
    expect(result[1]).toEqual({ left: 50, top: 10, right: 900, bottom: 1100 });
  });

  test("excludes current screenshot's events", () => {
    const screenshots = [
      makeScreenshot(1, [manualCropEvent(100, 0, 800, 1200)]),
      makeScreenshot(2, [manualCropEvent(50, 10, 900, 1100)]),
    ];
    // currentId=1 → should exclude screenshot 1's event
    const result = getRecentCropConfigs(screenshots, 1);
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({ left: 50, top: 10, right: 900, bottom: 1100 });
  });

  test("deduplicates identical crop rects", () => {
    const screenshots = [
      makeScreenshot(1, [manualCropEvent(100, 0, 800, 1200, "2025-01-03T00:00:00Z")]),
      makeScreenshot(2, [manualCropEvent(100, 0, 800, 1200, "2025-01-02T00:00:00Z")]),
      makeScreenshot(3, [manualCropEvent(200, 0, 900, 1300, "2025-01-01T00:00:00Z")]),
    ];
    const result = getRecentCropConfigs(screenshots, 99);
    expect(result).toHaveLength(2);
    expect(result[0]).toEqual({ left: 100, top: 0, right: 800, bottom: 1200 });
    expect(result[1]).toEqual({ left: 200, top: 0, right: 900, bottom: 1300 });
  });

  test("returns most recent first", () => {
    const screenshots = [
      makeScreenshot(1, [manualCropEvent(100, 0, 800, 1200, "2025-01-01T00:00:00Z")]),
      makeScreenshot(2, [manualCropEvent(200, 0, 900, 1300, "2025-01-03T00:00:00Z")]),
      makeScreenshot(3, [manualCropEvent(300, 0, 700, 1100, "2025-01-02T00:00:00Z")]),
    ];
    const result = getRecentCropConfigs(screenshots, 99);
    expect(result).toHaveLength(3);
    // Most recent timestamp first
    expect(result[0]).toEqual({ left: 200, top: 0, right: 900, bottom: 1300 });
    expect(result[1]).toEqual({ left: 300, top: 0, right: 700, bottom: 1100 });
    expect(result[2]).toEqual({ left: 100, top: 0, right: 800, bottom: 1200 });
  });

  test("respects limit parameter", () => {
    const screenshots = [
      makeScreenshot(1, [manualCropEvent(100, 0, 800, 1200, "2025-01-04T00:00:00Z")]),
      makeScreenshot(2, [manualCropEvent(200, 0, 900, 1300, "2025-01-03T00:00:00Z")]),
      makeScreenshot(3, [manualCropEvent(300, 0, 700, 1100, "2025-01-02T00:00:00Z")]),
      makeScreenshot(4, [manualCropEvent(400, 0, 600, 1000, "2025-01-01T00:00:00Z")]),
    ];
    const result = getRecentCropConfigs(screenshots, 99, 2);
    expect(result).toHaveLength(2);
  });

  test("ignores auto crop events (no manual flag)", () => {
    const screenshots = [
      makeScreenshot(1, [autoCropEvent("2025-01-02T00:00:00Z")]),
      makeScreenshot(2, [manualCropEvent(50, 10, 900, 1100, "2025-01-01T00:00:00Z")]),
    ];
    const result = getRecentCropConfigs(screenshots, 99);
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({ left: 50, top: 10, right: 900, bottom: 1100 });
  });

  test("handles screenshots with multiple crop events", () => {
    const screenshots = [
      makeScreenshot(1, [
        manualCropEvent(100, 0, 800, 1200, "2025-01-01T00:00:00Z"),
        manualCropEvent(150, 0, 850, 1250, "2025-01-02T00:00:00Z"),
      ]),
    ];
    const result = getRecentCropConfigs(screenshots, 99);
    expect(result).toHaveLength(2);
    // Both events from same screenshot, sorted by timestamp
    expect(result[0]).toEqual({ left: 150, top: 0, right: 850, bottom: 1250 });
    expect(result[1]).toEqual({ left: 100, top: 0, right: 800, bottom: 1200 });
  });

  test("handles empty screenshots array", () => {
    const result = getRecentCropConfigs([], 99);
    expect(result).toEqual([]);
  });

  test("ignores events with missing params", () => {
    const screenshots: ScreenshotLike[] = [
      {
        id: 1,
        processing_metadata: {
          preprocessing: {
            events: [
              {
                event_id: 1,
                stage: "cropping",
                timestamp: "2025-01-01T00:00:00Z",
                source: "manual",
                params: {},
                result: { was_cropped: true, manual: true },
              },
            ],
            current_events: {},
            stage_status: {},
          },
        },
      },
    ];
    const result = getRecentCropConfigs(screenshots, 99);
    expect(result).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// getRecentPHIConfigs
// ---------------------------------------------------------------------------

describe("getRecentPHIConfigs", () => {
  test("returns empty when no screenshots have PHI events", () => {
    const screenshots = [
      makeScreenshot(1, [autoCropEvent()]),
      makeScreenshot(2, []),
    ];
    const result = getRecentPHIConfigs(screenshots, 99);
    expect(result).toEqual([]);
  });

  test("extracts PHI region configs from events", () => {
    const regions = [
      { x: 100, y: 200, w: 300, h: 50, label: "PERSON" },
      { x: 100, y: 300, w: 200, h: 40, label: "EMAIL_ADDRESS" },
    ];
    const screenshots = [makeScreenshot(1, [phiEvent(regions)])];
    const result = getRecentPHIConfigs(screenshots, 99);
    expect(result).toHaveLength(1);
    expect(result[0]!.regions).toHaveLength(2);
    expect(result[0]!.label).toBe("PERSON, EMAIL_ADDRESS (2)");
  });

  test("excludes current screenshot", () => {
    const regions = [{ x: 100, y: 200, w: 300, h: 50, label: "PERSON" }];
    const screenshots = [
      makeScreenshot(1, [phiEvent(regions)]),
      makeScreenshot(2, [phiEvent(regions)]),
    ];
    const result = getRecentPHIConfigs(screenshots, 1);
    expect(result).toHaveLength(1);
  });

  test("deduplicates configs with same regions (within 20px snap)", () => {
    const regionsA = [{ x: 100, y: 200, w: 300, h: 50, label: "PERSON" }];
    // snap(v) = Math.round(v/20)*20; values must round to the SAME grid point.
    // snap(105)=100, snap(195)=200, snap(308)=300, snap(55)=60 → all match A.
    const regionsB = [{ x: 105, y: 195, w: 308, h: 55, label: "PERSON" }];
    const screenshots = [
      makeScreenshot(1, [phiEvent(regionsA, "2025-01-02T00:00:00Z")]),
      makeScreenshot(2, [phiEvent(regionsB, "2025-01-01T00:00:00Z")]),
    ];
    const result = getRecentPHIConfigs(screenshots, 99);
    expect(result).toHaveLength(1); // deduped
  });

  test("keeps configs with different regions", () => {
    const regionsA = [{ x: 100, y: 200, w: 300, h: 50, label: "PERSON" }];
    const regionsB = [{ x: 500, y: 600, w: 200, h: 80, label: "EMAIL_ADDRESS" }];
    const screenshots = [
      makeScreenshot(1, [phiEvent(regionsA)]),
      makeScreenshot(2, [phiEvent(regionsB)]),
    ];
    const result = getRecentPHIConfigs(screenshots, 99);
    expect(result).toHaveLength(2);
  });

  test("builds label with first 2 unique labels + count", () => {
    const regions = [
      { x: 100, y: 200, w: 300, h: 50, label: "PERSON" },
      { x: 100, y: 300, w: 200, h: 40, label: "EMAIL_ADDRESS" },
      { x: 100, y: 400, w: 250, h: 45, label: "PHONE_NUMBER" },
    ];
    const screenshots = [makeScreenshot(1, [phiEvent(regions)])];
    const result = getRecentPHIConfigs(screenshots, 99);
    expect(result[0]!.label).toBe("PERSON, EMAIL_ADDRESS... (3)");
  });

  test("builds label for single label type", () => {
    const regions = [
      { x: 100, y: 200, w: 300, h: 50, label: "PERSON" },
    ];
    const screenshots = [makeScreenshot(1, [phiEvent(regions)])];
    const result = getRecentPHIConfigs(screenshots, 99);
    expect(result[0]!.label).toBe("PERSON (1)");
  });

  test("builds label for two label types", () => {
    const regions = [
      { x: 100, y: 200, w: 300, h: 50, label: "PERSON" },
      { x: 100, y: 300, w: 200, h: 40, label: "DATE_TIME" },
    ];
    const screenshots = [makeScreenshot(1, [phiEvent(regions)])];
    const result = getRecentPHIConfigs(screenshots, 99);
    expect(result[0]!.label).toBe("PERSON, DATE_TIME (2)");
  });

  test("ignores events with empty regions", () => {
    const screenshots = [makeScreenshot(1, [phiEvent([])])];
    const result = getRecentPHIConfigs(screenshots, 99);
    expect(result).toEqual([]);
  });

  test("respects limit parameter", () => {
    const screenshots = [
      makeScreenshot(1, [phiEvent([{ x: 10, y: 10, w: 50, h: 50, label: "A" }], "2025-01-03T00:00:00Z")]),
      makeScreenshot(2, [phiEvent([{ x: 100, y: 100, w: 50, h: 50, label: "B" }], "2025-01-02T00:00:00Z")]),
      makeScreenshot(3, [phiEvent([{ x: 200, y: 200, w: 50, h: 50, label: "C" }], "2025-01-01T00:00:00Z")]),
    ];
    const result = getRecentPHIConfigs(screenshots, 99, 2);
    expect(result).toHaveLength(2);
  });

  test("returns most recent first", () => {
    const screenshots = [
      makeScreenshot(1, [phiEvent([{ x: 10, y: 10, w: 50, h: 50, label: "OLD" }], "2025-01-01T00:00:00Z")]),
      makeScreenshot(2, [phiEvent([{ x: 100, y: 100, w: 50, h: 50, label: "NEW" }], "2025-01-03T00:00:00Z")]),
    ];
    const result = getRecentPHIConfigs(screenshots, 99);
    expect(result).toHaveLength(2);
    expect(result[0]!.label).toContain("NEW");
    expect(result[1]!.label).toContain("OLD");
  });

  test("handles empty screenshots array", () => {
    const result = getRecentPHIConfigs([], 99);
    expect(result).toEqual([]);
  });

  test("handles screenshots with no preprocessing metadata", () => {
    const screenshots: ScreenshotLike[] = [
      { id: 1, processing_metadata: null },
      { id: 2, processing_metadata: undefined },
      { id: 3 },
    ];
    const result = getRecentPHIConfigs(screenshots, 99);
    expect(result).toEqual([]);
  });
});
