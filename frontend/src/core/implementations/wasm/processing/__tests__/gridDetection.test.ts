import { describe, it, expect } from "bun:test";
import {
  computeLeftAnchorCoords,
  computeRightAnchorCoords,
} from "../gridDetection.canvas";

// BUFFER = 25, MAXIMUM_OFFSET = 100 (internal constants mirrored here for clarity)
const B = 25;

// ── computeLeftAnchorCoords ───────────────────────────────────────────────────
// Rust reference: find_left_anchor (ocr_anchored.rs lines 58-126)
//   fallback 1 (no horizontal)          → (x - buffer, y + h)   line 122
//   fallback 2 (horizontal, no vertical) → (x - buffer, lowerLeftY) line 117

describe("computeLeftAnchorCoords", () => {
  it("no horizontal line found → returns (x-BUFFER, y+h)", () => {
    const result = computeLeftAnchorCoords(100, 200, 30, null, 100, null, 100);
    expect(result).toEqual({ x: 100 - B, y: 230 });
  });

  it("horizontal found, vertical found → computes exact coords", () => {
    // lineRow=5, movingIndex=3 → lowerLeftY = y - B + lineRow - movingIndex + 1
    //                                        = 200 - 25 + 5 - 3 + 1 = 178
    // lineCol=8, vMovingIndex=2 → lowerLeftX = x - B + lineCol - vMovingIndex + 1
    //                                        = 100 - 25 + 8 - 2 + 1 = 82
    const result = computeLeftAnchorCoords(100, 200, 30, 5, 3, 8, 2);
    expect(result).toEqual({ x: 82, y: 178 });
  });

  it("horizontal found, no vertical → x falls back to x-BUFFER, y uses lineRow", () => {
    // lowerLeftY = 200 - 25 + 5 - 3 + 1 = 178; lowerLeftX = x - B = 75
    const result = computeLeftAnchorCoords(100, 200, 30, 5, 3, null, 100);
    expect(result).toEqual({ x: 100 - B, y: 178 });
  });

  it("zero-based text position produces sensible coordinates", () => {
    const result = computeLeftAnchorCoords(0, 0, 20, null, 100, null, 100);
    expect(result).toEqual({ x: -B, y: 20 });
  });

  it("horizontal line found at row 1 with movingIndex 1 → lowerLeftY = y - B + 1", () => {
    const result = computeLeftAnchorCoords(50, 100, 15, 1, 1, null, 100);
    // lowerLeftY = 100 - 25 + 1 - 1 + 1 = 76
    expect(result.y).toBe(76);
    expect(result.x).toBe(50 - B);
  });
});

// ── computeRightAnchorCoords ──────────────────────────────────────────────────
// Rust reference: find_right_anchor (ocr_anchored.rs lines 131-187)
//   fallback 1 (no horizontal)           → (x - buffer, y)           line 183
//   fallback 2 (horizontal, no vertical) → (x - buffer, upperRightY) line 178

describe("computeRightAnchorCoords", () => {
  it("no horizontal line found → returns (x-BUFFER, y)", () => {
    const result = computeRightAnchorCoords(300, 150, null, 100, null, 100);
    expect(result).toEqual({ x: 300 - B, y: 150 });
  });

  it("horizontal found, vertical found → computes exact coords", () => {
    // lineRow=4, movingIndex=2 → upperRightY = y + lineRow - movingIndex + 1
    //                                        = 150 + 4 - 2 + 1 = 153
    // lineCol=6, vMovingIndex=3 → upperRightX = x - B + lineCol - vMovingIndex + 1
    //                                         = 300 - 25 + 6 - 3 + 1 = 279
    const result = computeRightAnchorCoords(300, 150, 4, 2, 6, 3);
    expect(result).toEqual({ x: 279, y: 153 });
  });

  it("horizontal found, no vertical → x falls back to x-BUFFER, y uses lineRow", () => {
    // upperRightY = 150 + 4 - 2 + 1 = 153; upperRightX = x - B = 275
    const result = computeRightAnchorCoords(300, 150, 4, 2, null, 100);
    expect(result).toEqual({ x: 300 - B, y: 153 });
  });

  it("zero-based text position produces sensible coordinates", () => {
    const result = computeRightAnchorCoords(0, 0, null, 100, null, 100);
    expect(result).toEqual({ x: -B, y: 0 });
  });

  it("horizontal line at row 1 movingIndex 1 → upperRightY = y + 1", () => {
    const result = computeRightAnchorCoords(200, 80, 1, 1, null, 100);
    // upperRightY = 80 + 1 - 1 + 1 = 81
    expect(result.y).toBe(81);
    expect(result.x).toBe(200 - B);
  });
});

// ── regression: the exact broken values from before the fix ──────────────────

describe("regression: pre-fix bogus values must not appear", () => {
  it("left anchor no-horizontal fallback is NOT y - (MAXIMUM_OFFSET - 1)", () => {
    // Old broken formula: y + (null||0) - movingIndex + 1 = y - 99 (when movingIndex=100)
    const result = computeLeftAnchorCoords(100, 200, 30, null, 100, null, 100);
    expect(result.y).not.toBe(200 - 100 + 1); // old broken value: 101
    expect(result.y).toBe(230); // correct: y + h
  });

  it("right anchor no-horizontal fallback is NOT y - (MAXIMUM_OFFSET - 1)", () => {
    // Old broken formula: y + (null||0) - movingIndex + 1 = y - 99
    const result = computeRightAnchorCoords(300, 150, null, 100, null, 100);
    expect(result.y).not.toBe(150 - 100 + 1); // old broken value: 51
    expect(result.y).toBe(150); // correct: y
  });

  it("left anchor no-vertical fallback x is NOT x - BUFFER - (MAXIMUM_OFFSET - 1)", () => {
    // Old broken formula: x - BUFFER + (null||0) - movingIndex + 1 = x - 124
    const result = computeLeftAnchorCoords(100, 200, 30, 5, 3, null, 100);
    expect(result.x).not.toBe(100 - B - 100 + 1); // old broken value: -24
    expect(result.x).toBe(100 - B); // correct: x - BUFFER
  });

  it("right anchor no-vertical fallback x is NOT x - BUFFER - (MAXIMUM_OFFSET - 1)", () => {
    const result = computeRightAnchorCoords(300, 150, 4, 2, null, 100);
    expect(result.x).not.toBe(300 - B - 100 + 1); // old broken value: 176
    expect(result.x).toBe(300 - B); // correct: x - BUFFER
  });
});
