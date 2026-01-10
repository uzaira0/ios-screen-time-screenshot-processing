/**
 * Bar Extraction - Canvas 2D API Implementation
 *
 * This is a DROP-IN REPLACEMENT for barExtraction.ts that uses Canvas 2D API
 * instead of OpenCV.js. All function signatures and behaviors are identical.
 *
 * ZERO OpenCV dependencies - pure Canvas 2D API.
 */

import type { GridCoordinates, HourlyData } from "@/types";
import type { CanvasMat } from "./canvasImageUtils";
import { clone, extractROI, getPixel } from "./canvasImageUtils";
import {
  darkenNonWhite,
  reduceColorCount,
  scaleUp,
  isClose,
  removeAllBut,
} from "./imageUtils.canvas";

const SCALE_AMOUNT = 4;
const NUM_HOURS = 24;
const MAX_MINUTES = 60;
const LOWER_GRID_BUFFER = 2;

/**
 * Preprocesses an image for bar extraction (expensive, do once).
 *
 * Steps: battery color filter → darken → reduce to 2 colors → scale up 4×.
 * The result can then be used with extractHourlyDataFromPreprocessed()
 * for fast ROI extraction at different grid offsets.
 */
export function preprocessForExtraction(
  imageMat: CanvasMat,
  gridCoords: GridCoordinates,
  isBattery: boolean,
): CanvasMat {
  const { upper_left, lower_right } = gridCoords;
  const roiX = upper_left.x;
  const roiY = upper_left.y;
  const roiWidth = lower_right.x - upper_left.x;
  const roiHeight = lower_right.y - upper_left.y;

  let processedImg = clone(imageMat);

  if (isBattery) {
    const darkBlueRemoved = removeAllBut(processedImg, [255, 121, 0], 30);
    processedImg = darkBlueRemoved;

    const roiRegion = extractROI(processedImg, {
      x: roiX, y: roiY, width: roiWidth, height: roiHeight,
    });

    let darkBlueSum = 0;
    const roiPixels = roiRegion.imageData.data;
    for (let i = 0; i < roiPixels.length; i += 4) {
      darkBlueSum += 255 - roiPixels[i]!;
      darkBlueSum += 255 - roiPixels[i + 1]!;
      darkBlueSum += 255 - roiPixels[i + 2]!;
    }

    if (darkBlueSum < 10) {
      processedImg = clone(imageMat);
      const lightBlueRemoved = removeAllBut(processedImg, [0, 255 - 121, 255], 30);
      processedImg = lightBlueRemoved;
    }
  }

  const darkened = darkenNonWhite(processedImg);
  const reduced = reduceColorCount(darkened, 2);
  return scaleUp(reduced, SCALE_AMOUNT);
}

/**
 * Extracts hourly data from an already-preprocessed (scaled) image.
 * This is the fast path — just ROI extraction + bar height analysis.
 */
export function extractHourlyDataFromPreprocessed(
  scaled: CanvasMat,
  gridCoords: GridCoordinates,
): HourlyData {
  const roiX = gridCoords.upper_left.x * SCALE_AMOUNT;
  const roiY = gridCoords.upper_left.y * SCALE_AMOUNT;
  const roiWidth = (gridCoords.lower_right.x - gridCoords.upper_left.x) * SCALE_AMOUNT;
  const roiHeight = (gridCoords.lower_right.y - gridCoords.upper_left.y) * SCALE_AMOUNT;

  const roi = extractROI(scaled, { x: roiX, y: roiY, width: roiWidth, height: roiHeight });

  const hourlyData: HourlyData = {};
  const sliceWidthFloat = roiWidth / NUM_HOURS;

  for (let hour = 0; hour < NUM_HOURS; hour++) {
    const sliceX = Math.floor(hour * sliceWidthFloat);
    const sliceWidth = Math.floor(sliceWidthFloat);
    const slice = extractROI(roi, { x: sliceX, y: 0, width: sliceWidth, height: roiHeight });
    const middleColumn = Math.floor(sliceWidth / 2);
    hourlyData[hour] = analyzeBarHeight(slice, middleColumn, roiHeight);
  }

  return hourlyData;
}

/**
 * Extracts hourly usage data from bar graph.
 *
 * Algorithm:
 * 1. Extract grid region
 * 2. For battery mode: filter for specific bar colors
 * 3. Darken non-white pixels
 * 4. Reduce to 2 colors (binary)
 * 5. Scale up 4x for better accuracy
 * 6. Divide into 24 hourly slices
 * 7. Analyze bar height in each slice
 */
export function extractHourlyData(
  imageMat: CanvasMat,
  gridCoords: GridCoordinates,
  isBattery: boolean,
): HourlyData {
  const scaled = preprocessForExtraction(imageMat, gridCoords, isBattery);
  return extractHourlyDataFromPreprocessed(scaled, gridCoords);
}

/**
 * Analyzes bar height by scanning vertical column.
 *
 * Identical to OpenCV version.
 *
 * Algorithm:
 * 1. Scan from top to bottom in middle column
 * 2. Count consecutive black pixels (bar height)
 * 3. Reset counter when hitting white pixel (background)
 * 4. Convert pixel count to minutes (0-60 scale)
 *
 * @param slice - Image slice for one hour
 * @param middleColumn - X coordinate of column to analyze
 * @param maxHeight - Maximum height in pixels
 * @returns Usage in minutes (0-60)
 */
function analyzeBarHeight(
  slice: CanvasMat,
  middleColumn: number,
  maxHeight: number,
): number {
  let counter = 0;

  for (let y = 0; y < maxHeight; y++) {
    const pixel = [
      getPixel(slice, y, middleColumn, 0), // R
      getPixel(slice, y, middleColumn, 1), // G
      getPixel(slice, y, middleColumn, 2), // B
    ];

    const pixelSum = pixel.reduce((sum, val) => sum + val, 0);

    // Black pixel (bar)
    if (pixelSum === 0) {
      counter++;
    }

    // White pixel (background) - reset counter if not near bottom
    if (
      isClose(pixel, [255, 255, 255], 2) &&
      y < maxHeight - LOWER_GRID_BUFFER
    ) {
      counter = 0;
    }
  }

  const minutes = Math.floor((MAX_MINUTES * counter) / maxHeight);

  return minutes;
}

/**
 * Line extraction mode.
 */
export const LineExtractionMode = {
  HORIZONTAL: "HORIZONTAL",
  VERTICAL: "VERTICAL",
} as const;
export type LineExtractionMode = (typeof LineExtractionMode)[keyof typeof LineExtractionMode];

/**
 * Extracts horizontal or vertical line position.
 *
 * Identical to OpenCV version.
 *
 * Used for grid detection - finds the most common colored line
 * in a region.
 *
 * @param img - Source image
 * @param x0 - Left X coordinate
 * @param x1 - Right X coordinate
 * @param y0 - Top Y coordinate
 * @param y1 - Bottom Y coordinate
 * @param mode - HORIZONTAL or VERTICAL
 * @returns Line position (row index for horizontal, column index for vertical)
 */
export function extractLine(
  img: CanvasMat,
  x0: number,
  x1: number,
  y0: number,
  y1: number,
  mode: LineExtractionMode,
): number {
  const subImage = extractROI(img, {
    x: x0,
    y: y0,
    width: x1 - x0,
    height: y1 - y0,
  });

  const reduced = reduceColorCount(subImage, 2);

  const pixelValue = getMostCommonPixelValue(reduced);

  if (!pixelValue || pixelValue.length === 0) {
    return 0;
  }

  let result = 0;

  if (mode === LineExtractionMode.HORIZONTAL) {
    // Scan rows from top to bottom
    for (let i = 0; i < reduced.height; i++) {
      let rowScore = 0;
      for (let j = 0; j < reduced.width; j++) {
        const pixel = [
          getPixel(reduced, i, j, 0), // R
          getPixel(reduced, i, j, 1), // G
          getPixel(reduced, i, j, 2), // B
        ];
        if (isClose(pixel, pixelValue)) {
          rowScore++;
        }
      }
      // If >50% of row matches, this is the line
      if (rowScore > 0.5 * reduced.width) {
        result = i;
        break;
      }
    }
  } else if (mode === LineExtractionMode.VERTICAL) {
    // Scan columns from left to right
    for (let j = 0; j < reduced.width; j++) {
      let colScore = 0;
      for (let i = 0; i < reduced.height; i++) {
        const pixel = [
          getPixel(reduced, i, j, 0), // R
          getPixel(reduced, i, j, 1), // G
          getPixel(reduced, i, j, 2), // B
        ];
        if (isClose(pixel, pixelValue)) {
          colScore++;
        }
      }
      // If >25% of column matches, this is the line
      if (colScore > 0.25 * reduced.height) {
        result = j;
        break;
      }
    }
  }

  return result;
}

/**
 * Gets the second most common pixel value.
 *
 * Identical to OpenCV version.
 *
 * Used to find the grid line color (most common is usually background).
 *
 * @param src - Source image
 * @returns Second most common pixel as [R, G, B] or null
 */
function getMostCommonPixelValue(src: CanvasMat): number[] | null {
  const pixelCounts = new Map<string, { pixel: number[]; count: number }>();
  const pixels = src.imageData.data;

  for (let i = 0; i < pixels.length; i += 4) {
    const pixel = [pixels[i]!, pixels[i + 1]!, pixels[i + 2]!]; // RGB only
    const key = pixel.join(",");

    const existing = pixelCounts.get(key);
    if (existing) {
      existing.count++;
    } else {
      pixelCounts.set(key, { pixel, count: 1 });
    }
  }

  const sorted = Array.from(pixelCounts.values()).sort(
    (a, b) => a.count - b.count,
  );

  if (sorted.length <= 1) {
    return null;
  }

  // Return second-to-last (second most common)
  const result = sorted[sorted.length - 2];
  return result ? result.pixel : null;
}

/**
 * Compute alignment score between visual bar graph and computed hourly values.
 *
 * Port of Python's compute_bar_alignment_score() from bar_extraction.py.
 * Uses HSV-based blue bar detection to measure visual bars, then compares
 * with computed values using normalized MAE + shift penalty.
 *
 * @param roi - The cropped graph region (CanvasMat, RGB format)
 * @param hourlyValues - Computed bar values for each hour (object with 24 keys)
 * @returns Score from 0.0 to 1.0 where 1.0 = perfect alignment
 */
export function computeBarAlignmentScore(
  roi: CanvasMat,
  hourlyValues: HourlyData,
): number {
  try {
    const numSlices = 24;
    const roiHeight = roi.height;
    const roiWidth = roi.width;

    if (roiWidth === 0 || roiHeight === 0) return 0.0;

    // Ensure exactly 24 values
    const values: number[] = [];
    for (let i = 0; i < 24; i++) {
      values.push(hourlyValues[i] ?? 0);
    }

    const roiData = roi.imageData.data;

    // Extract bar heights from image using HSV-based blue bar detection
    const extractedHeights: number[] = [];
    const sliceWidth = Math.floor(roiWidth / numSlices);

    for (let i = 0; i < numSlices; i++) {
      const midStart = i * sliceWidth + Math.floor(sliceWidth / 4);
      const midEnd = Math.min(i * sliceWidth + Math.floor(3 * sliceWidth / 4), roiWidth);

      let barHeight = 0;
      // Scan top to bottom, find first row with blue pixel
      for (let y = 0; y < roiHeight; y++) {
        let hasBlue = false;
        for (let x = midStart; x < midEnd; x++) {
          const idx = (y * roiWidth + x) * 4;
          const r = roiData[idx]!;
          const g = roiData[idx + 1]!;
          const b = roiData[idx + 2]!;

          // Convert RGB to HSV
          const rn = r / 255, gn = g / 255, bn = b / 255;
          const max = Math.max(rn, gn, bn);
          const min = Math.min(rn, gn, bn);
          const delta = max - min;

          let h = 0;
          if (delta > 0) {
            if (max === rn) h = 60 * (((gn - bn) / delta) % 6);
            else if (max === gn) h = 60 * ((bn - rn) / delta + 2);
            else h = 60 * ((rn - gn) / delta + 4);
            if (h < 0) h += 360;
          }
          const s = max > 0 ? (delta / max) * 255 : 0;
          const v = max * 255;

          // OpenCV HSV: hue 0-180 (half-degree), so divide by 2
          const hOcv = h / 2;

          // Blue bars: hue 90-130, saturation > 50, value > 100
          if (hOcv >= 90 && hOcv <= 130 && s > 50 && v > 100) {
            hasBlue = true;
            break;
          }
        }
        if (hasBlue) {
          barHeight = roiHeight - y;
          break;
        }
      }

      extractedHeights.push((barHeight / roiHeight) * 60);
    }

    // Compare extracted vs computed
    let extractedSum = 0, computedSum = 0;
    for (let i = 0; i < 24; i++) {
      extractedSum += extractedHeights[i]!;
      computedSum += values[i]!;
    }

    if (extractedSum === 0 && computedSum === 0) return 1.0;
    if (extractedSum === 0 || computedSum === 0) {
      return Math.max(extractedSum, computedSum) > 30 ? 0.1 : 0.3;
    }

    // Normalize and compute MAE
    let extractedMax = 0, computedMax = 0;
    for (let i = 0; i < 24; i++) {
      if (extractedHeights[i]! > extractedMax) extractedMax = extractedHeights[i]!;
      if (values[i]! > computedMax) computedMax = values[i]!;
    }

    let maeSum = 0;
    const extractedNorm: number[] = [];
    const computedNorm: number[] = [];
    for (let i = 0; i < 24; i++) {
      const en = extractedHeights[i]! / (extractedMax + 1e-10);
      const cn = values[i]! / (computedMax + 1e-10);
      extractedNorm.push(en);
      computedNorm.push(cn);
      maeSum += Math.abs(en - cn);
    }
    let score = 1.0 - maeSum / 24;

    // Shift detection penalty
    let extractedFirst = -1, computedFirst = -1;
    for (let i = 0; i < 24; i++) {
      if (extractedFirst < 0 && extractedNorm[i]! > 0.1) extractedFirst = i;
      if (computedFirst < 0 && computedNorm[i]! > 0.1) computedFirst = i;
    }
    if (extractedFirst >= 0 && computedFirst >= 0) {
      const startDiff = Math.abs(extractedFirst - computedFirst);
      if (startDiff >= 2) {
        const shiftPenalty = Math.min(startDiff * 0.15, 0.5);
        score = Math.max(0.0, score - shiftPenalty);
      }
    }

    return score;
  } catch {
    return 0.5;
  }
}
