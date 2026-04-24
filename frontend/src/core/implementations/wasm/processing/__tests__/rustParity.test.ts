/**
 * Rust golden-snapshot parity tests.
 *
 * Locks in the exact numeric outputs from the Rust pipeline
 * (crates/processing/tests/snapshots/) for all 4 fixture images.
 *
 * Full WASM canvas pipeline parity (running the TS implementation on actual
 * pixel data) requires a browser canvas context and is covered by
 * tests/wasm-smoke.spec.ts (Playwright).
 */

import { describe, it, expect, beforeAll } from "bun:test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// ── Types mirroring the Rust PipelineSnapshot struct ─────────────────────────

interface GridBounds {
  upper_left_x: number;
  upper_left_y: number;
  lower_right_x: number;
  lower_right_y: number;
}

interface PipelineSnapshot {
  success: boolean;
  hourly_values: number[] | null;
  total: number;
  alignment_score: number | null;
  grid_bounds: GridBounds | null;
  detection_method: string;
  is_daily_total: boolean;
}

// ── Path helper ───────────────────────────────────────────────────────────────

const SNAPSHOTS_DIR = resolve(
  __dirname,
  // __tests__ → processing → wasm → implementations → core → src → frontend → repo root
  "../../../../../../..",
  "crates/processing/tests/snapshots",
);

function loadSnapshot(name: string): PipelineSnapshot {
  const path = resolve(SNAPSHOTS_DIR, `${name}_pipeline.json`);
  return JSON.parse(readFileSync(path, "utf-8")) as PipelineSnapshot;
}

// ── Golden values (from crates/processing/tests/snapshots/) ──────────────────

const GOLDEN: Record<
  string,
  {
    hourly: number[];
    total: number;
    alignmentScore: number;
    gridBounds: GridBounds;
  }
> = {
  IMG_0806: {
    hourly: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 15, 37, 24, 11, 3, 0, 0],
    total: 90,
    alignmentScore: 0.960586,
    gridBounds: { upper_left_x: 83, upper_left_y: 811, lower_right_x: 721, lower_right_y: 991 },
  },
  IMG_0807: {
    hourly: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 13, 37, 0, 0, 0, 0, 0],
    total: 50,
    alignmentScore: 0.957583,
    gridBounds: { upper_left_x: 83, upper_left_y: 394, lower_right_x: 721, lower_right_y: 574 },
  },
  IMG_0808: {
    hourly: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 22, 10, 0, 0, 0],
    total: 32,
    alignmentScore: 0.957071,
    gridBounds: { upper_left_x: 84, upper_left_y: 394, lower_right_x: 722, lower_right_y: 574 },
  },
  IMG_0809: {
    hourly: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
    total: 1,
    alignmentScore: 0.958333,
    gridBounds: { upper_left_x: 84, upper_left_y: 394, lower_right_x: 722, lower_right_y: 574 },
  },
};

// ── Load all snapshots at module level ────────────────────────────────────────

const SNAPS: Record<string, PipelineSnapshot> = {};

beforeAll(() => {
  for (const name of Object.keys(GOLDEN)) {
    SNAPS[name] = loadSnapshot(name);
  }
});

// ── Per-fixture tests ─────────────────────────────────────────────────────────

for (const [name, expected] of Object.entries(GOLDEN)) {
  describe(`${name} golden snapshot`, () => {
    it("pipeline succeeded", () => {
      expect(SNAPS[name]!.success).toBe(true);
    });

    it("has exactly 24 hourly values", () => {
      expect(SNAPS[name]!.hourly_values).not.toBeNull();
      expect(SNAPS[name]!.hourly_values!).toHaveLength(24);
    });

    it("hourly values match Rust golden output exactly", () => {
      expect(SNAPS[name]!.hourly_values).toEqual(expected.hourly);
    });

    it("total equals sum of hourly values", () => {
      const snap = SNAPS[name]!;
      const sum = snap.hourly_values!.reduce((a, b) => a + b, 0);
      expect(snap.total).toBe(sum);
      expect(snap.total).toBe(expected.total);
    });

    it("detection method is line_based", () => {
      expect(SNAPS[name]!.detection_method).toBe("line_based");
    });

    it("is_daily_total is false (all fixtures are app pages)", () => {
      expect(SNAPS[name]!.is_daily_total).toBe(false);
    });

    it("grid bounds match Rust golden output", () => {
      expect(SNAPS[name]!.grid_bounds).not.toBeNull();
      expect(SNAPS[name]!.grid_bounds).toEqual(expected.gridBounds);
    });

    it("grid ROI is non-degenerate", () => {
      const b = SNAPS[name]!.grid_bounds!;
      expect(b.lower_right_x - b.upper_left_x).toBeGreaterThan(0);
      expect(b.lower_right_y - b.upper_left_y).toBeGreaterThan(0);
    });

    it("alignment score is in valid range [0, 1]", () => {
      const score = SNAPS[name]!.alignment_score;
      expect(score).not.toBeNull();
      expect(score!).toBeGreaterThanOrEqual(0);
      expect(score!).toBeLessThanOrEqual(1);
    });

    it("alignment score matches expected (rounded to 6dp)", () => {
      const rounded = Math.round(SNAPS[name]!.alignment_score! * 1e6) / 1e6;
      expect(rounded).toBe(expected.alignmentScore);
    });
  });
}

// ── Cross-fixture consistency ─────────────────────────────────────────────────

describe("cross-fixture consistency", () => {
  it("total = sum(hourly_values) for all fixtures", () => {
    for (const name of Object.keys(GOLDEN)) {
      const snap = SNAPS[name]!;
      const sum = snap.hourly_values!.reduce((a, b) => a + b, 0);
      expect(snap.total).toBe(sum);
    }
  });

  it("IMG_0807/0808/0809 have consistent grid width (same screen format)", () => {
    const widths = ["IMG_0807", "IMG_0808", "IMG_0809"].map((name) => {
      const b = SNAPS[name]!.grid_bounds!;
      return b.lower_right_x - b.upper_left_x;
    });
    expect(Math.abs(widths[0]! - widths[1]!)).toBeLessThanOrEqual(2);
    expect(Math.abs(widths[1]! - widths[2]!)).toBeLessThanOrEqual(2);
  });

  it("all fixtures have non-zero active hours (bars exist)", () => {
    for (const name of Object.keys(GOLDEN)) {
      const snap = SNAPS[name]!;
      const nonZero = snap.hourly_values!.filter((v) => v > 0).length;
      expect(nonZero).toBeGreaterThan(0);
    }
  });

  it("all fixtures have alignment score > 0.95 (high-quality bar detection)", () => {
    for (const name of Object.keys(GOLDEN)) {
      expect(SNAPS[name]!.alignment_score!).toBeGreaterThan(0.95);
    }
  });
});
