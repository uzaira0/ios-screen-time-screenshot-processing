/**
 * Bar Extraction - Canvas 2D API Implementation
 *
 * This is a DROP-IN REPLACEMENT for barExtraction.ts that uses Canvas 2D API
 * instead of OpenCV.js. All function signatures and behaviors are identical.
 *
 * ZERO OpenCV dependencies - pure Canvas 2D API.
 */

import type { GridCoordinates, HourlyData } from "../../../models";
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
 * Extracts hourly usage data from bar graph.
 *
 * Identical to OpenCV version.
 *
 * Algorithm:
 * 1. Extract grid region
 * 2. For battery mode: filter for specific bar colors
 * 3. Darken non-white pixels
 * 4. Reduce to 2 colors (binary)
 * 5. Scale up 4x for better accuracy
 * 6. Divide into 24 hourly slices
 * 7. Analyze bar height in each slice
 *
 * @param imageMat - Source image as CanvasMat
 * @param gridCoords - Grid coordinates (upper_left, lower_right)
 * @param isBattery - True for battery screenshots, false for screen time
 * @returns Hourly data object mapping hour (0-23) to minutes (0-60)
 */
export function extractHourlyData(
  imageMat: CanvasMat,
  gridCoords: GridCoordinates,
  isBattery: boolean,
): HourlyData {
  const { upper_left, lower_right } = gridCoords;

  const roiX = upper_left.x;
  const roiY = upper_left.y;
  const roiWidth = lower_right.x - upper_left.x;
  const roiHeight = lower_right.y - upper_left.y;

  let processedImg = clone(imageMat);

  if (isBattery) {
    // Check for dark blue bars ([255, 121, 0] in BGR = [0, 121, 255] in RGB)
    const darkBlueRemoved = removeAllBut(processedImg, [255, 121, 0], 30);
    processedImg = darkBlueRemoved;

    const roiRegion = extractROI(processedImg, {
      x: roiX,
      y: roiY,
      width: roiWidth,
      height: roiHeight,
    });

    // Calculate sum of dark blue pixels (inverted, so 255 - value)
    let darkBlueSum = 0;
    const roiPixels = roiRegion.imageData.data;
    for (let i = 0; i < roiPixels.length; i += 4) {
      darkBlueSum += 255 - roiPixels[i]!; // R
      darkBlueSum += 255 - roiPixels[i + 1]!; // G
      darkBlueSum += 255 - roiPixels[i + 2]!; // B
    }

    // If no dark blue bars found, try light blue bars
    if (darkBlueSum < 10) {
      processedImg = clone(imageMat);
      // Light blue: [0, 255-121, 255] in RGB = [0, 134, 255]
      const lightBlueRemoved = removeAllBut(
        processedImg,
        [0, 255 - 121, 255],
        30,
      );
      processedImg = lightBlueRemoved;
    }
  }

  const darkened = darkenNonWhite(processedImg);

  const reduced = reduceColorCount(darkened, 2);

  const scaled = scaleUp(reduced, SCALE_AMOUNT);

  const scaledRoiX = roiX * SCALE_AMOUNT;
  const scaledRoiY = roiY * SCALE_AMOUNT;
  const scaledRoiWidth = roiWidth * SCALE_AMOUNT;
  const scaledRoiHeight = roiHeight * SCALE_AMOUNT;

  const roi = extractROI(scaled, {
    x: scaledRoiX,
    y: scaledRoiY,
    width: scaledRoiWidth,
    height: scaledRoiHeight,
  });

  const hourlyData: HourlyData = {};
  const sliceWidthFloat = scaledRoiWidth / NUM_HOURS;

  for (let hour = 0; hour < NUM_HOURS; hour++) {
    const sliceX = Math.floor(hour * sliceWidthFloat);
    const sliceWidth = Math.floor(sliceWidthFloat);

    const slice = extractROI(roi, {
      x: sliceX,
      y: 0,
      width: sliceWidth,
      height: scaledRoiHeight,
    });

    const middleColumn = Math.floor(sliceWidth / 2);
    const minutes = analyzeBarHeight(slice, middleColumn, scaledRoiHeight);

    hourlyData[hour] = minutes;
  }

  return hourlyData;
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
 * Line extraction mode enum.
 */
export enum LineExtractionMode {
  HORIZONTAL = "HORIZONTAL",
  VERTICAL = "VERTICAL",
}

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
