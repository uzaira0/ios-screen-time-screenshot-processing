/**
 * Line-Based Grid Detection - Canvas 2D API Implementation
 *
 * Port of the Python line_based_detection module. Detects the daily hourly
 * chart by finding horizontal/vertical grid lines — NO OCR required.
 *
 * Algorithm (Combined Strategy):
 * 1. Lookup table for x/width/height hints based on screen resolution
 * 2. Horizontal line detection: find rows with many gray pixels (~200 value)
 * 3. Vertical line validation: count dotted vertical lines (4-5 = daily chart)
 * 4. Color validation: reject cyan bars (pickups chart)
 * 5. X-boundary refinement from detected vertical line positions
 */

import type { GridCoordinates } from "@/types";
import type { CanvasMat } from "./canvasImageUtils";

// ---------------------------------------------------------------------------
// Resolution lookup table (ported from Python lookup.py)
// Keys: "widthxheight", Values: { x, width, height } (y varies with scroll)
// ---------------------------------------------------------------------------

const LOOKUP_TABLE: Record<string, { x: number; width: number; height: number }> = {
  "640x1136":  { x: 30,  width: 510,  height: 180 },
  "750x1334":  { x: 60,  width: 560,  height: 180 },
  "750x1624":  { x: 60,  width: 560,  height: 180 },
  "828x1792":  { x: 70,  width: 620,  height: 180 },
  "848x2266":  { x: 70,  width: 640,  height: 180 },
  "858x2160":  { x: 70,  width: 640,  height: 180 },
  "896x2048":  { x: 70,  width: 670,  height: 180 },
  "906x2160":  { x: 70,  width: 690,  height: 180 },
  "960x2079":  { x: 80,  width: 720,  height: 270 },
  "980x2160":  { x: 80,  width: 730,  height: 180 },
  "990x2160":  { x: 80,  width: 740,  height: 180 },
  "1000x2360": { x: 80,  width: 790,  height: 180 },
  "1028x2224": { x: 80,  width: 820,  height: 180 },
  "1028x2388": { x: 80,  width: 820,  height: 180 },
  "1170x2532": { x: 90,  width: 880,  height: 270 },
  "1258x2732": { x: 80,  width: 1020, height: 180 },
};

// ---------------------------------------------------------------------------
// Tuning constants (ported from Python strategies)
// ---------------------------------------------------------------------------

// Horizontal line detection
const H_GRAY_MIN = 195;
const H_GRAY_MAX = 210;
const H_MIN_WIDTH_PCT = 0.35;
const H_MIN_LINES = 4;
const H_MAX_LINES = 8;
const H_MAX_SPACING_DEV = 10;

// Vertical line detection
const V_GRAY_MIN = 190;
const V_GRAY_MAX = 215;
const V_MIN_HEIGHT_PCT = 0.4;
const V_EXPECTED_LINES = new Set([3, 4, 5]);
const V_SPACING_TOLERANCE = 0.25;

// Edge refinement
const EDGE_GRAY_MIN = 190;
const EDGE_GRAY_MAX = 220;
const EDGE_MIN_COVERAGE = 0.3;

// Color validation (OpenCV HSV: H 0-180, S 0-255, V 0-255)
const BLUE_HUE_MIN = 100;
const BLUE_HUE_MAX = 130;
const CYAN_HUE_MIN = 80;
const MIN_SATURATION = 50;
const MIN_VALUE = 50;
const MIN_BLUE_RATIO = 0.5;

// ---------------------------------------------------------------------------
// Grayscale helper — extract single-channel gray array from RGBA CanvasMat
// Uses same formula as Python: 0.114*R + 0.587*G + 0.299*B (BT.601 with BGR weights)
// ---------------------------------------------------------------------------

function toGrayscaleArray(mat: CanvasMat): Uint8Array {
  const { data } = mat.imageData;
  const len = mat.width * mat.height;
  const gray = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    const off = i * 4;
    // Python uses [0.114, 0.587, 0.299] on BGR channels
    // Canvas is RGBA, so: R=data[off], G=data[off+1], B=data[off+2]
    gray[i] = Math.round(
      data[off]! * 0.299 + data[off + 1]! * 0.587 + data[off + 2]! * 0.114,
    );
  }
  return gray;
}

// ---------------------------------------------------------------------------
// Cluster nearby positions (ported from Python base.py)
// ---------------------------------------------------------------------------

function clusterPositions(positions: number[], maxGap: number): number[] {
  if (positions.length === 0) return [];
  const sorted = [...positions].sort((a, b) => a - b);
  const clusters: number[] = [];
  let current = [sorted[0]!];

  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i]! - current[current.length - 1]! <= maxGap) {
      current.push(sorted[i]!);
    } else {
      clusters.push(Math.round(current.reduce((a, b) => a + b, 0) / current.length));
      current = [sorted[i]!];
    }
  }
  clusters.push(Math.round(current.reduce((a, b) => a + b, 0) / current.length));
  return clusters;
}

// ---------------------------------------------------------------------------
// Step 1: Find horizontal grid lines (ported from horizontal_lines.py)
// ---------------------------------------------------------------------------

function findHorizontalLines(
  gray: Uint8Array,
  imgWidth: number,
  imgHeight: number,
  xStart: number,
  xEnd: number,
): number[] {
  const lineYPositions: number[] = [];
  const regionW = xEnd - xStart;

  for (let y = 0; y < imgHeight; y++) {
    let grayPixels = 0;
    for (let x = xStart; x < xEnd; x++) {
      const v = gray[y * imgWidth + x]!;
      if (v >= H_GRAY_MIN && v <= H_GRAY_MAX) grayPixels++;
    }
    if (grayPixels > regionW * H_MIN_WIDTH_PCT) {
      lineYPositions.push(y);
    }
  }

  return clusterPositions(lineYPositions, 3);
}

// ---------------------------------------------------------------------------
// Step 2: Find evenly-spaced groups (ported from horizontal_lines.py)
// ---------------------------------------------------------------------------

interface LineGroup {
  yStart: number;
  yEnd: number;
  numLines: number;
  meanSpacing: number;
  maxDeviation: number;
  heightScore: number;
  lines: number[];
}

function findEvenlySpacedGroups(
  lines: number[],
  expectedHeight: number | null,
): LineGroup[] {
  const groups: LineGroup[] = [];

  for (let startIdx = 0; startIdx <= lines.length - H_MIN_LINES; startIdx++) {
    const maxEnd = Math.min(startIdx + H_MAX_LINES + 1, lines.length + 1);
    for (let endIdx = startIdx + H_MIN_LINES; endIdx < maxEnd; endIdx++) {
      const group = lines.slice(startIdx, endIdx);
      const spacings: number[] = [];
      for (let i = 0; i < group.length - 1; i++) {
        spacings.push(group[i + 1]! - group[i]!);
      }
      const meanSpacing = spacings.reduce((a, b) => a + b, 0) / spacings.length;
      const maxDev = Math.max(...spacings.map((s) => Math.abs(s - meanSpacing)));

      if (maxDev > H_MAX_SPACING_DEV) continue;
      if (meanSpacing < 20 || meanSpacing > 150) continue;

      const groupHeight = group[group.length - 1]! - group[0]!;
      let heightScore = 1.0;
      if (expectedHeight) {
        const heightError = Math.abs(groupHeight - expectedHeight);
        heightScore = Math.max(0.5, 1.0 - heightError / expectedHeight);
      }

      groups.push({
        yStart: group[0]!,
        yEnd: group[group.length - 1]!,
        numLines: group.length,
        meanSpacing,
        maxDeviation: maxDev,
        heightScore,
        lines: group,
      });
    }
  }

  // Sort: most lines desc, height score desc, deviation asc
  groups.sort((a, b) =>
    a.numLines !== b.numLines
      ? b.numLines - a.numLines
      : a.heightScore !== b.heightScore
        ? b.heightScore - a.heightScore
        : a.maxDeviation - b.maxDeviation,
  );

  // Remove overlapping groups
  const result: LineGroup[] = [];
  for (const g of groups) {
    const overlaps = result.some((existing) => {
      const overlapStart = Math.max(g.yStart, existing.yStart);
      const overlapEnd = Math.min(g.yEnd, existing.yEnd);
      return overlapEnd > overlapStart;
    });
    if (!overlaps) result.push(g);
  }

  return result;
}

// ---------------------------------------------------------------------------
// Step 3: Count vertical dotted lines in a region (ported from vertical_lines.py)
// ---------------------------------------------------------------------------

function countVerticalLines(
  gray: Uint8Array,
  imgWidth: number,
  xStart: number,
  width: number,
  yStart: number,
  yEnd: number,
): { count: number; positions: number[] } {
  const regionH = yEnd - yStart;
  if (regionH <= 0 || width <= 0) return { count: 0, positions: [] };

  const verticalPositions: number[] = [];

  for (let x = 0; x < width; x++) {
    let grayPixels = 0;
    for (let y = yStart; y < yEnd; y++) {
      const v = gray[y * imgWidth + (xStart + x)]!;
      if (v >= V_GRAY_MIN && v <= V_GRAY_MAX) grayPixels++;
    }
    if (grayPixels > regionH * V_MIN_HEIGHT_PCT) {
      verticalPositions.push(x);
    }
  }

  if (verticalPositions.length === 0) return { count: 0, positions: [] };

  const clusters = clusterPositions(verticalPositions, 5);
  return { count: clusters.length, positions: clusters };
}

// ---------------------------------------------------------------------------
// Step 3b: Validate a candidate region as daily chart (vertical lines)
// ---------------------------------------------------------------------------

interface ValidationResult {
  isDaily: boolean;
  confidence: number;
  vCount: number;
  vPositions: number[];
  meanSpacing?: number;
}

function validateRegionVertical(
  gray: Uint8Array,
  imgWidth: number,
  xStart: number,
  width: number,
  yStart: number,
  yEnd: number,
): ValidationResult {
  const { count, positions } = countVerticalLines(gray, imgWidth, xStart, width, yStart, yEnd);

  if (!V_EXPECTED_LINES.has(count)) {
    return { isDaily: false, confidence: 0, vCount: count, vPositions: positions };
  }

  if (positions.length < 2) {
    return { isDaily: false, confidence: 0, vCount: count, vPositions: positions };
  }

  const spacings: number[] = [];
  for (let i = 0; i < positions.length - 1; i++) {
    spacings.push(positions[i + 1]! - positions[i]!);
  }
  const meanSpacing = spacings.reduce((a, b) => a + b, 0) / spacings.length;
  const expectedSpacing = width / 4;

  const spacingError = Math.abs(meanSpacing - expectedSpacing) / expectedSpacing;
  if (spacingError > V_SPACING_TOLERANCE) {
    return { isDaily: false, confidence: 0, vCount: count, vPositions: positions, meanSpacing };
  }

  const maxDeviation = Math.max(...spacings.map((s) => Math.abs(s - meanSpacing)));
  if (maxDeviation > meanSpacing * 0.15) {
    return { isDaily: false, confidence: 0, vCount: count, vPositions: positions, meanSpacing };
  }

  let confidence = 0.8 + (1 - spacingError) * 0.1 + (1 - maxDeviation / meanSpacing) * 0.1;
  confidence = Math.min(0.99, confidence);

  return { isDaily: true, confidence, vCount: count, vPositions: positions, meanSpacing };
}

// ---------------------------------------------------------------------------
// Step 4: Color validation — reject pickups (cyan) charts (ported from color_validation.py)
// Canvas uses RGBA, we need to convert to HSV manually
// ---------------------------------------------------------------------------

function rgbToHsv(r: number, g: number, b: number): [number, number, number] {
  // Returns OpenCV-compatible HSV: H 0-180, S 0-255, V 0-255
  const rf = r / 255, gf = g / 255, bf = b / 255;
  const max = Math.max(rf, gf, bf);
  const min = Math.min(rf, gf, bf);
  const d = max - min;

  let h = 0;
  if (d > 0) {
    if (max === rf) h = ((gf - bf) / d) % 6;
    else if (max === gf) h = (bf - rf) / d + 2;
    else h = (rf - gf) / d + 4;
    h = Math.round(h * 30); // Scale to 0-180 (OpenCV convention)
    if (h < 0) h += 180;
  }

  const s = max > 0 ? Math.round((d / max) * 255) : 0;
  const v = Math.round(max * 255);

  return [h, s, v];
}

function validateColorRegion(
  mat: CanvasMat,
  xStart: number,
  yStart: number,
  width: number,
  height: number,
): boolean {
  const { data } = mat.imageData;
  const imgW = mat.width;
  let blueCount = 0;
  let cyanCount = 0;

  for (let y = yStart; y < yStart + height; y++) {
    for (let x = xStart; x < xStart + width; x++) {
      const off = (y * imgW + x) * 4;
      const r = data[off]!, g = data[off + 1]!, b = data[off + 2]!;
      const [h, s, v] = rgbToHsv(r, g, b);

      if (s < MIN_SATURATION || v < MIN_VALUE) continue;

      if (h >= BLUE_HUE_MIN && h <= BLUE_HUE_MAX) blueCount++;
      else if (h >= CYAN_HUE_MIN && h < BLUE_HUE_MIN) cyanCount++;
    }
  }

  const total = blueCount + cyanCount;
  if (total === 0) return true; // No colored bars — allow
  return blueCount / total >= MIN_BLUE_RATIO;
}

// ---------------------------------------------------------------------------
// Step 5: Refine x-boundaries (ported from combined.py)
// ---------------------------------------------------------------------------

function findGridEdges(
  gray: Uint8Array,
  imgWidth: number,
  xStart: number,
  xEnd: number,
  yStart: number,
  yEnd: number,
): { left: number | null; right: number | null } {
  const regionH = yEnd - yStart;
  if (regionH <= 0) return { left: null, right: null };

  const verticalLineX: number[] = [];
  for (let x = xStart; x < xEnd; x++) {
    let grayPixels = 0;
    for (let y = yStart; y < yEnd; y++) {
      const v = gray[y * imgWidth + x]!;
      if (v >= EDGE_GRAY_MIN && v <= EDGE_GRAY_MAX) grayPixels++;
    }
    if (grayPixels >= regionH * EDGE_MIN_COVERAGE) {
      verticalLineX.push(x);
    }
  }

  if (verticalLineX.length < 2) return { left: null, right: null };

  // Cluster
  const clusters: number[] = [];
  let current = [verticalLineX[0]!];
  for (let i = 1; i < verticalLineX.length; i++) {
    if (verticalLineX[i]! - current[current.length - 1]! <= 3) {
      current.push(verticalLineX[i]!);
    } else {
      clusters.push(Math.round(current.reduce((a, b) => a + b, 0) / current.length));
      current = [verticalLineX[i]!];
    }
  }
  clusters.push(Math.round(current.reduce((a, b) => a + b, 0) / current.length));

  if (clusters.length < 2) return { left: null, right: null };

  // Parity: Rust picks clusters closest to the search window boundaries, not
  // first/last — using first/last picks up gray UI elements at the extreme edges
  // as false grid boundaries (see line_based.rs find_grid_edges comment).
  const left = clusters.reduce((best, c) => Math.abs(c - xStart) < Math.abs(best - xStart) ? c : best, clusters[0]!);
  const right = clusters.reduce((best, c) => Math.abs(c - xEnd) < Math.abs(best - xEnd) ? c : best, clusters[clusters.length - 1]!);

  if (right <= left) return { left: null, right: null };

  return { left, right };
}

function refineXBoundaries(
  gray: Uint8Array,
  imgWidth: number,
  _imgHeight: number,
  xStart: number,
  width: number,
  yStart: number,
  yEnd: number,
  vPositions: number[],
): { x: number; width: number } {
  const searchMargin = 50;
  const searchXStart = Math.max(0, xStart - searchMargin);
  const searchXEnd = Math.min(imgWidth, xStart + width + searchMargin);

  const { left, right } = findGridEdges(gray, imgWidth, searchXStart, searchXEnd, yStart, yEnd);

  if (left !== null && right !== null && right > left) {
    return { x: left, width: right - left };
  }

  // Fallback: extrapolate from vertical line positions
  if (vPositions.length >= 3) {
    const spacings: number[] = [];
    for (let i = 0; i < vPositions.length - 1; i++) {
      spacings.push(vPositions[i + 1]! - vPositions[i]!);
    }
    const spacing = spacings.reduce((a, b) => a + b, 0) / spacings.length;

    let leftEdge = Math.round(vPositions[0]! - spacing) + xStart;
    let rightEdge = Math.round(vPositions[vPositions.length - 1]! + spacing) + xStart;

    leftEdge = Math.max(0, leftEdge);
    rightEdge = Math.min(imgWidth, rightEdge);

    if (rightEdge > leftEdge) {
      return { x: leftEdge, width: rightEdge - leftEdge };
    }
  }

  return { x: xStart, width };
}

// ---------------------------------------------------------------------------
// Main: Combined line-based detection (ported from combined.py)
// ---------------------------------------------------------------------------

export interface LineBasedResult {
  gridCoordinates: GridCoordinates | null;
  confidence: number;
  diagnostics: Record<string, unknown>;
}

/**
 * Detect the daily chart grid using line-based detection (no OCR).
 *
 * @param imageMat - Source image (RGBA CanvasMat, should be dark-mode converted)
 * @returns Detection result with grid coordinates, confidence, and diagnostics
 */
export function detectGridLineBased(imageMat: CanvasMat): LineBasedResult {
  const w = imageMat.width;
  const h = imageMat.height;
  const resolution = `${w}x${h}`;

  // Step 1: Lookup table
  const hints = LOOKUP_TABLE[resolution];
  if (!hints) {
    return {
      gridCoordinates: null,
      confidence: 0,
      diagnostics: {
        error: `Resolution ${resolution} not in lookup table`,
        availableResolutions: Object.keys(LOOKUP_TABLE),
      },
    };
  }

  const gray = toGrayscaleArray(imageMat);
  const xStart = hints.x;
  const width = hints.width;
  const xEnd = Math.min(xStart + width, w);
  const expectedHeight = hints.height;

  // Step 2: Find horizontal lines
  const hLines = findHorizontalLines(gray, w, h, xStart, xEnd);

  if (hLines.length < H_MIN_LINES) {
    return {
      gridCoordinates: null,
      confidence: 0,
      diagnostics: { error: `Only ${hLines.length} horizontal lines (need ${H_MIN_LINES}+)`, linesFound: hLines },
    };
  }

  // Step 2b: Find evenly-spaced groups
  const groups = findEvenlySpacedGroups(hLines, expectedHeight);

  if (groups.length === 0) {
    return {
      gridCoordinates: null,
      confidence: 0,
      diagnostics: { error: "No evenly-spaced horizontal line groups", linesFound: hLines },
    };
  }

  // Step 3: Validate each group with vertical line detection + color validation
  let bestResult: {
    yStart: number;
    yEnd: number;
    confidence: number;
    vCount: number;
    vPositions: number[];
  } | null = null;

  for (const group of groups) {
    const vResult = validateRegionVertical(gray, w, xStart, width, group.yStart, group.yEnd);

    if (!vResult.isDaily) continue;

    // Step 4: Color validation
    const colorValid = validateColorRegion(imageMat, xStart, group.yStart, width, group.yEnd - group.yStart);
    if (!colorValid) continue;

    if (!bestResult || vResult.confidence > bestResult.confidence) {
      bestResult = {
        yStart: group.yStart,
        yEnd: group.yEnd,
        confidence: vResult.confidence,
        vCount: vResult.vCount,
        vPositions: vResult.vPositions,
      };
    }
  }

  if (!bestResult) {
    return {
      gridCoordinates: null,
      confidence: 0,
      diagnostics: {
        error: "No candidate region matches daily chart pattern",
        candidatesChecked: groups.length,
        hLines,
      },
    };
  }

  // Step 5: Refine x boundaries
  const refined = refineXBoundaries(
    gray, w, h,
    xStart, width,
    bestResult.yStart, bestResult.yEnd,
    bestResult.vPositions,
  );

  const gridCoordinates: GridCoordinates = {
    upper_left: { x: refined.x, y: bestResult.yStart },
    lower_right: { x: refined.x + refined.width, y: bestResult.yEnd },
  };

  return {
    gridCoordinates,
    confidence: bestResult.confidence,
    diagnostics: {
      strategy: "combined_line_based",
      vLineCount: bestResult.vCount,
      vLinePositions: bestResult.vPositions,
      originalX: xStart,
      originalWidth: width,
      refinedX: refined.x,
      refinedWidth: refined.width,
      resolution,
    },
  };
}
