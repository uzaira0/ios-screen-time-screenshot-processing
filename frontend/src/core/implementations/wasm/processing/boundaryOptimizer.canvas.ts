/**
 * Boundary Optimizer - Canvas 2D API Implementation
 *
 * Port of Python boundary_optimizer.py. After initial grid detection,
 * tries small shifts in x, y, and width to find the grid position where
 * extracted bar totals best match the OCR total.
 */

import type { GridCoordinates, HourlyData } from "@/types";
import type { CanvasMat } from "./canvasImageUtils";
import { extractHourlyData, preprocessForExtraction, extractHourlyDataFromPreprocessed } from "./barExtraction.canvas";

const SCALE_AMOUNT = 4;
const NUM_HOURS = 24;
const MAX_MINUTES = 60;
const LOWER_GRID_BUFFER = 2;

/**
 * Compute the sum of all 24 bar heights directly from the scaled image buffer.
 * ZERO allocations — reads pixels via index math on the Uint8ClampedArray.
 *
 * This replaces extractHourlyDataFromPreprocessed + sumHourlyData in the
 * optimizer's inner loop, avoiding 25 ImageData allocations per iteration.
 */
function computeBarTotalDirect(
  data: Uint8ClampedArray,
  scaledWidth: number,
  roiX: number,
  roiY: number,
  roiWidth: number,
  roiHeight: number,
): number {
  const sliceWidthFloat = roiWidth / NUM_HOURS;
  const lowerBound = roiHeight - LOWER_GRID_BUFFER;
  let totalMinutes = 0;

  for (let hour = 0; hour < NUM_HOURS; hour++) {
    const sliceX = Math.floor(hour * sliceWidthFloat);
    const sliceW = Math.floor(sliceWidthFloat);
    // Middle column in absolute scaled-image coordinates
    const colX = roiX + sliceX + Math.floor(sliceW / 2);

    // Scan top-to-bottom, same logic as analyzeBarHeight
    let counter = 0;
    for (let row = 0; row < roiHeight; row++) {
      const absY = roiY + row;
      const idx = (absY * scaledWidth + colX) * 4;
      const r = data[idx]!;
      const g = data[idx + 1]!;
      const b = data[idx + 2]!;

      // Black pixel (bar) — all channels 0
      if (r === 0 && g === 0 && b === 0) {
        counter++;
      }

      // White pixel (background) — reset if not near bottom
      if (row < lowerBound && r >= 253 && g >= 253 && b >= 253) {
        counter = 0;
      }
    }

    totalMinutes += Math.floor((MAX_MINUTES * counter) / roiHeight);
  }

  return totalMinutes;
}

// ---------------------------------------------------------------------------
// Parse OCR total string to minutes
// ---------------------------------------------------------------------------

const DIGIT_MAP: Record<string, string> = {
  O: "0", o: "0", Q: "0",
  l: "1", I: "1", "|": "1",
  Z: "2", z: "2",
  A: "4",
  S: "5", s: "5",
  G: "6", b: "6",
  T: "7",
  B: "8",
  g: "9", q: "9",
};

function normalizeOcrDigits(text: string): string {
  return text.replace(/[OoQlI|ZzASsGbTBgq]/g, (ch) => DIGIT_MAP[ch] ?? ch);
}

export function parseOcrTotal(ocrTotal: string): number | null {
  if (!ocrTotal || ocrTotal === "N/A") return null;

  const text = normalizeOcrDigits(ocrTotal).trim().toLowerCase();
  let totalMinutes = 0;

  const hourMatch = text.match(/(\d{1,2})\s*h/);
  if (hourMatch) totalMinutes += parseInt(hourMatch[1]!, 10) * 60;

  const minMatch = text.match(/(\d{1,2})\s*m(?!s)/);
  if (minMatch) totalMinutes += parseInt(minMatch[1]!, 10);

  if (totalMinutes === 0) {
    const secMatch = text.match(/(\d{1,2})\s*s/);
    if (secMatch) return 0;
  }

  return totalMinutes > 0 ? totalMinutes : null;
}

// ---------------------------------------------------------------------------
// 7→1 OCR correction (common OCR confusion)
// ---------------------------------------------------------------------------

function generate71Alternatives(ocrTotal: string): Array<{ text: string; desc: string }> {
  const alts: Array<{ text: string; desc: string }> = [{ text: ocrTotal, desc: "original" }];
  const positions = [...ocrTotal].reduce<number[]>((acc, ch, i) => {
    if (ch === "7") acc.push(i);
    return acc;
  }, []);

  if (positions.length === 0) return alts;

  for (const pos of positions) {
    alts.push({
      text: ocrTotal.slice(0, pos) + "1" + ocrTotal.slice(pos + 1),
      desc: `7->1 at ${pos}`,
    });
  }

  if (positions.length > 1) {
    alts.push({ text: ocrTotal.replace(/7/g, "1"), desc: "all 7->1" });
  }

  return alts;
}

function correctOcrTotalWithBarHint(
  ocrTotal: string,
  barTotalMinutes: number,
): { correctedTotal: string; correctedMinutes: number } {
  const alts = generate71Alternatives(ocrTotal);
  let bestTotal = ocrTotal;
  let bestMinutes = parseOcrTotal(ocrTotal) ?? 0;
  let bestDiff = Math.abs(bestMinutes - barTotalMinutes);

  for (const { text } of alts.slice(1)) {
    const mins = parseOcrTotal(text);
    if (mins === null) continue;
    const diff = Math.abs(mins - barTotalMinutes);
    if (diff < bestDiff) {
      bestTotal = text;
      bestMinutes = mins;
      bestDiff = diff;
    }
  }

  return { correctedTotal: bestTotal, correctedMinutes: bestMinutes };
}

// ---------------------------------------------------------------------------
// Optimization result
// ---------------------------------------------------------------------------

export interface OptimizationResult {
  bounds: GridCoordinates;
  barTotalMinutes: number;
  ocrTotalMinutes: number;
  /** OCR total string after 7→1 correction (if improved match) */
  correctedTotal: string;
  shiftX: number;
  shiftY: number;
  shiftWidth: number;
  iterations: number;
  converged: boolean;
  hourlyData: HourlyData;
}

// ---------------------------------------------------------------------------
// Main optimizer
// ---------------------------------------------------------------------------

/**
 * Optimize grid boundaries to match OCR total.
 *
 * Brute-forces small shifts in x, y, and width to find the grid position
 * where extracted bar totals best match the OCR-extracted total.
 *
 * @param image - Source image (CanvasMat)
 * @param initialBounds - Initial grid coordinates from detection
 * @param ocrTotal - OCR-extracted total string (e.g., "1h 31m")
 * @param maxShift - Maximum pixels to shift in each direction (0 = disabled)
 * @param isBattery - Whether this is a battery screenshot
 * @returns Optimized result with best grid bounds and hourly data
 */
export function optimizeBoundaries(
  image: CanvasMat,
  initialBounds: GridCoordinates,
  ocrTotal: string,
  maxShift: number = 10,
  isBattery: boolean = false,
): OptimizationResult {
  const targetMinutes = parseOcrTotal(ocrTotal);

  // If we can't parse the OCR total, just extract with original bounds
  if (targetMinutes === null) {
    const hourlyData = extractHourlyData(image, initialBounds, isBattery);
    const barTotal = sumHourlyData(hourlyData);
    return {
      bounds: initialBounds,
      barTotalMinutes: barTotal,
      ocrTotalMinutes: 0,
      correctedTotal: ocrTotal,
      shiftX: 0,
      shiftY: 0,
      shiftWidth: 0,
      iterations: 0,
      converged: false,
      hourlyData,
    };
  }

  const imgW = image.width;
  const imgH = image.height;

  let bestBounds = initialBounds;
  let bestDiff = Infinity;
  let bestBarTotal = 0;
  let bestShiftX = 0;
  let bestShiftY = 0;
  let bestShiftWidth = 0;
  let bestHourlyData: HourlyData = {};
  let iterations = 0;

  const origX = initialBounds.upper_left.x;
  const origY = initialBounds.upper_left.y;
  const origW = initialBounds.lower_right.x - initialBounds.upper_left.x;
  const origH = initialBounds.lower_right.y - initialBounds.upper_left.y;

  // Preprocess the image ONCE (clone → color filter → darken → reduce → scale 4×).
  const scaled = preprocessForExtraction(image, initialBounds, isBattery);
  const scaledData = scaled.imageData.data;
  const scaledWidth = scaled.width;

  // Try different shifts: Y step=1 (fine), X/width step=2 (coarser)
  // Inner loop uses computeBarTotalDirect for ZERO allocations — reads pixels
  // directly from the scaled image's Uint8ClampedArray via index math.
  for (let shiftX = -maxShift; shiftX <= maxShift; shiftX += 2) {
    for (let shiftY = -maxShift; shiftY <= maxShift; shiftY += 1) {
      for (let shiftWidth = -maxShift; shiftWidth <= maxShift; shiftWidth += 2) {
        iterations++;

        const newX = origX + shiftX;
        const newY = origY + shiftY;
        const newW = origW + shiftWidth;

        // Validate bounds
        if (newX < 0 || newY < 0 || newW <= 0) continue;
        if (newX + newW > imgW) continue;
        if (newY + origH > imgH) continue;

        // Compute bar total directly from buffer — no ROI extraction needed
        const roiX = newX * SCALE_AMOUNT;
        const roiY = newY * SCALE_AMOUNT;
        const roiWidth = newW * SCALE_AMOUNT;
        const roiHeight = origH * SCALE_AMOUNT;

        const barTotal = computeBarTotalDirect(
          scaledData, scaledWidth, roiX, roiY, roiWidth, roiHeight,
        );
        const diff = Math.abs(barTotal - targetMinutes);

        // Tie-breaker: prefer smaller shifts (horizontal penalized 5x)
        const shiftPenalty = 5 * Math.abs(shiftX) + Math.abs(shiftY) + 5 * Math.abs(shiftWidth);
        const bestShiftPenalty = 5 * Math.abs(bestShiftX) + Math.abs(bestShiftY) + 5 * Math.abs(bestShiftWidth);

        const isBetter = diff < bestDiff || (diff === bestDiff && shiftPenalty < bestShiftPenalty);

        if (isBetter) {
          bestDiff = diff;
          bestBounds = {
            upper_left: { x: newX, y: newY },
            lower_right: { x: newX + newW, y: newY + origH },
          };
          bestBarTotal = barTotal;
          bestShiftX = shiftX;
          bestShiftY = shiftY;
          bestShiftWidth = shiftWidth;

          // Early exit on exact match at origin
          if (diff === 0 && shiftPenalty === 0) {
            // Only extract full hourly data for the winning result
            bestHourlyData = extractHourlyDataFromPreprocessed(scaled, bestBounds);
            return {
              bounds: bestBounds,
              barTotalMinutes: bestBarTotal,
              ocrTotalMinutes: targetMinutes,
              correctedTotal: ocrTotal,
              shiftX: bestShiftX,
              shiftY: bestShiftY,
              shiftWidth: bestShiftWidth,
              iterations,
              converged: true,
              hourlyData: bestHourlyData,
            };
          }
        }
      }
    }
  }

  // Extract full hourly data only for the final best result
  bestHourlyData = extractHourlyDataFromPreprocessed(scaled, bestBounds);

  // Apply 7→1 OCR correction — pick the total string closest to bar total
  const { correctedTotal, correctedMinutes } = correctOcrTotalWithBarHint(ocrTotal, bestBarTotal);
  const finalDiff = Math.abs(bestBarTotal - correctedMinutes);

  return {
    bounds: bestBounds,
    barTotalMinutes: bestBarTotal,
    ocrTotalMinutes: correctedMinutes,
    correctedTotal,
    shiftX: bestShiftX,
    shiftY: bestShiftY,
    shiftWidth: bestShiftWidth,
    iterations,
    converged: finalDiff <= 1,
    hourlyData: bestHourlyData,
  };
}

function sumHourlyData(data: HourlyData): number {
  return Object.values(data).reduce((sum, v) => sum + (v ?? 0), 0);
}
