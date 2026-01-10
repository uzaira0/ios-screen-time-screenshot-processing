/**
 * Image Utilities - Canvas 2D API Implementation
 *
 * This is a DROP-IN REPLACEMENT for imageUtils.ts that uses Canvas 2D API
 * instead of OpenCV.js. All function signatures and behaviors are identical.
 *
 * ZERO OpenCV dependencies - pure Canvas 2D API.
 */

import {
  type CanvasMat,
  type Point,
  type Rect,
  createCanvasMat,
  reduceColorCount as canvasReduceColorCount,
  scaleUp as canvasScaleUp,
  isClose as canvasIsClose,
  getMostCommonPixel as canvasGetMostCommonPixel,
  removeAllBut as canvasRemoveAllBut,
  darkenNonWhite as canvasDarkenNonWhite,
  adjustContrastBrightness as canvasAdjustContrastBrightness,
  convertDarkMode as canvasConvertDarkMode,
  extractRegion as canvasExtractRegion,
  blobToImageData as canvasBlobToImageData,
  matToBlob as canvasMatToBlob,
  matToImageData as canvasMatToImageData,
} from "./canvasImageUtils";

// Re-export types for compatibility
export type { Point, Rect, CanvasMat };

// ============================================================================
// PUBLIC API - Identical to imageUtils.ts
// ============================================================================

/**
 * Converts dark mode screenshots to light mode.
 *
 * Identical to OpenCV version.
 *
 * @param src - Source CanvasMat
 * @returns Converted CanvasMat
 */
export function convertDarkMode(src: CanvasMat): CanvasMat {
  return canvasConvertDarkMode(src);
}

/**
 * Adjusts contrast and brightness.
 *
 * Identical to OpenCV version.
 *
 * @param src - Source CanvasMat
 * @param contrast - Contrast multiplier (default: 1.0)
 * @param brightness - Brightness offset (default: 0)
 * @returns Adjusted CanvasMat
 */
export function adjustContrastBrightness(
  src: CanvasMat,
  contrast: number = 1.0,
  brightness: number = 0,
): CanvasMat {
  return canvasAdjustContrastBrightness(src, contrast, brightness);
}

/**
 * Darkens all non-white pixels to black.
 *
 * Identical to OpenCV version.
 *
 * @param src - Source CanvasMat
 * @returns CanvasMat with non-white pixels darkened
 */
export function darkenNonWhite(src: CanvasMat): CanvasMat {
  return canvasDarkenNonWhite(src);
}

/**
 * Reduces the number of distinct colors in the image.
 *
 * Identical to OpenCV version.
 *
 * @param src - Source CanvasMat
 * @param numColors - Number of color levels
 * @returns CanvasMat with reduced color count
 */
export function reduceColorCount(src: CanvasMat, numColors: number): CanvasMat {
  return canvasReduceColorCount(src, numColors);
}

/**
 * Scales image up by a factor.
 *
 * Identical to OpenCV version.
 *
 * @param src - Source CanvasMat
 * @param scaleFactor - Scale multiplier
 * @returns Scaled CanvasMat
 */
export function scaleUp(src: CanvasMat, scaleFactor: number): CanvasMat {
  return canvasScaleUp(src, scaleFactor);
}

/**
 * Checks if two pixel arrays are close within threshold.
 *
 * Identical to OpenCV version.
 *
 * @param pixel1 - First pixel array
 * @param pixel2 - Second pixel array
 * @param threshold - Maximum difference per channel (default: 1)
 * @returns True if pixels are close
 */
export function isClose(
  pixel1: number[],
  pixel2: number[],
  threshold: number = 1,
): boolean {
  return canvasIsClose(pixel1, pixel2, threshold);
}

/**
 * Finds the most common pixel value in the image.
 *
 * Identical to OpenCV version.
 *
 * @param src - Source CanvasMat
 * @param index - Index in sorted list (default: -1 for most common)
 * @returns Most common pixel as [R, G, B] or null
 */
export function getMostCommonPixel(
  src: CanvasMat,
  index: number = -1,
): number[] | null {
  return canvasGetMostCommonPixel(src, index);
}

/**
 * Removes all pixels except those matching target color.
 *
 * Identical to OpenCV version.
 *
 * @param src - Source CanvasMat
 * @param targetColor - Target color as [R, G, B]
 * @param threshold - Maximum Euclidean distance (default: 30)
 * @returns CanvasMat with filtered colors
 */
export function removeAllBut(
  src: CanvasMat,
  targetColor: number[],
  threshold: number = 30,
): CanvasMat {
  return canvasRemoveAllBut(src, targetColor, threshold);
}

/**
 * Converts Blob to ImageData.
 *
 * Identical to OpenCV version.
 *
 * @param blob - Image blob
 * @returns ImageData
 */
export async function blobToImageData(blob: Blob): Promise<ImageData> {
  return canvasBlobToImageData(blob);
}

/**
 * Converts ImageData to CanvasMat.
 *
 * Identical to OpenCV version (replaces imageDataToMat).
 *
 * @param imageData - Source ImageData
 * @returns CanvasMat
 */
export function imageDataToMat(imageData: ImageData): CanvasMat {
  return createCanvasMat(imageData);
}

/**
 * Converts CanvasMat to ImageData.
 *
 * Identical to OpenCV version.
 *
 * @param mat - Source CanvasMat
 * @returns ImageData
 */
export function matToImageData(mat: CanvasMat): ImageData {
  return canvasMatToImageData(mat);
}

/**
 * Converts CanvasMat to Blob.
 *
 * Identical to OpenCV version.
 *
 * @param mat - Source CanvasMat
 * @returns PNG Blob
 */
export async function matToBlob(mat: CanvasMat): Promise<Blob> {
  return canvasMatToBlob(mat);
}

/**
 * Extracts a region of interest.
 *
 * Identical to OpenCV version.
 *
 * @param src - Source CanvasMat
 * @param rect - Rectangle defining ROI
 * @returns CanvasMat containing ROI
 */
export function extractRegion(src: CanvasMat, rect: Rect): CanvasMat {
  return canvasExtractRegion(src, rect);
}
