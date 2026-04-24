import { describe, it, expect } from "bun:test";
import { selectBoundaryClusters } from "../lineBasedDetection.canvas";

// ── selectBoundaryClusters ────────────────────────────────────────────────────
// Rust reference: find_grid_edges (line_based.rs) picks clusters nearest to
// xStart (left edge) and xEnd (right edge), not simply first/last.

describe("selectBoundaryClusters", () => {
  it("returns null when fewer than 2 clusters", () => {
    expect(selectBoundaryClusters([], 0, 500)).toBeNull();
    expect(selectBoundaryClusters([100], 0, 500)).toBeNull();
  });

  it("returns null when right <= left", () => {
    // If nearest-to-xStart happens to be >= nearest-to-xEnd
    expect(selectBoundaryClusters([300, 100], 400, 50)).toBeNull();
  });

  it("two clusters → picks both as left and right", () => {
    const result = selectBoundaryClusters([80, 720], 0, 800);
    expect(result).toEqual({ left: 80, right: 720 });
  });

  it("picks cluster nearest to xStart, not first element", () => {
    // Clusters: [5, 200, 400], xStart=150, xEnd=500
    // Nearest to xStart=150: |5-150|=145, |200-150|=50, |400-150|=250 → 200 wins
    // Old code (first): would return 5
    const result = selectBoundaryClusters([5, 200, 400], 150, 500);
    expect(result!.left).toBe(200);
  });

  it("picks cluster nearest to xEnd, not last element", () => {
    // Clusters: [80, 400, 700], xStart=0, xEnd=450
    // Nearest to xEnd=450: |80-450|=370, |400-450|=50, |700-450|=250 → 400 wins
    // Old code (last): would return 700
    const result = selectBoundaryClusters([80, 400, 700], 0, 450);
    expect(result!.right).toBe(400);
  });

  // ── critical regression: first/last vs boundary-nearest ───────────────────

  it("regression: clusters at extremes get ignored when inner clusters are closer to boundaries", () => {
    // This is the scenario the Rust fix targets:
    // Gray UI chrome at x=5 and x=795 appear as clusters, but the real
    // grid boundaries are at x=83 and x=721.
    // xStart=50, xEnd=750
    // Clusters: [5, 83, 721, 795]
    // left: |5-50|=45, |83-50|=33, |721-50|=671, |795-50|=745 → 83 wins
    // right: |5-750|=745, |83-750|=667, |721-750|=29, |795-750|=45 → 721 wins
    const result = selectBoundaryClusters([5, 83, 721, 795], 50, 750);
    expect(result).toEqual({ left: 83, right: 721 });
  });

  it("regression: old first/last code would have returned the wrong clusters", () => {
    const clusters = [5, 83, 721, 795];
    const result = selectBoundaryClusters(clusters, 50, 750);
    // Old code returned clusters[0]=5 and clusters[last]=795
    expect(result!.left).not.toBe(5);
    expect(result!.right).not.toBe(795);
    // New code returns the boundary-nearest
    expect(result!.left).toBe(83);
    expect(result!.right).toBe(721);
  });

  it("real fixture-derived values: IMG_0806 grid bounds", () => {
    // Rust golden: upper_left_x=83, lower_right_x=721
    // UI chrome clusters at x=5 and x=800; real grid at x=100 and x=700.
    // xStart=80, xEnd=720: |5-80|=75 vs |100-80|=20 → 100 wins left
    //                       |700-720|=20 vs |800-720|=80 → 700 wins right
    const clusters = [5, 100, 700, 800];
    const result = selectBoundaryClusters(clusters, 80, 720);
    expect(result!.left).toBe(100);
    expect(result!.right).toBe(700);
  });

  it("symmetric case: tie-breaking follows reduce initial value", () => {
    // reduce for LEFT initializes with clusters[0]=100; ties don't replace → 100 wins
    // reduce for RIGHT initializes with clusters[last]=300; ties don't replace → 300 wins
    const result = selectBoundaryClusters([100, 200, 300], 150, 250);
    // |100-150|=50, |200-150|=50 → tie → keeps initial 100
    expect(result!.left).toBe(100);
    // |200-250|=50, |300-250|=50 → tie → keeps initial 300
    expect(result!.right).toBe(300);
    // still a valid result since left < right
    expect(result!.left).toBeLessThan(result!.right);
  });

  it("all clusters equidistant — just needs left < right", () => {
    const result = selectBoundaryClusters([100, 300], 100, 300);
    expect(result).not.toBeNull();
    expect(result!.left).toBeLessThan(result!.right);
  });
});
