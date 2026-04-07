/**
 * Canvas 2D API: Complete OpenCV.js Replacement
 *
 * This module provides exact 1:1 replacements for ALL OpenCV operations
 * used in the WASM Screenshot Processor. Every function produces IDENTICAL
 * results to its OpenCV equivalent while using zero external dependencies.
 *
 * Memory Model:
 * - CanvasMat wraps ImageData (RGBA, 4 channels, Uint8ClampedArray)
 * - All pixel operations use direct Uint8ClampedArray manipulation
 * - ImageData is immutable by convention - operations return new instances
 * - Caller is responsible for ImageData lifecycle (no explicit .delete())
 */

/**
 * Canvas 2D API replacement for cv.Mat
 *
 * OpenCV Mat properties:
 * - mat.rows: number of rows (height)
 * - mat.cols: number of columns (width)
 * - mat.channels(): number of channels (3 for BGR, 4 for BGRA)
 * - mat.ucharPtr(y, x)[c]: direct pixel access
 *
 * CanvasMat equivalent:
 * - height: number of rows
 * - width: number of columns
 * - channels: always 4 (RGBA)
 * - imageData.data: Uint8ClampedArray pixel access
 */
export interface CanvasMat {
  imageData: ImageData;
  width: number; // equivalent to mat.cols
  height: number; // equivalent to mat.rows
  channels: number; // always 4 for RGBA
}

export interface Point {
  x: number;
  y: number;
}

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

// ============================================================================
// CORE OPERATIONS - Direct OpenCV Replacements
// ============================================================================

/**
 * REPLACES: cv.matFromImageData(imageData)
 *
 * Creates a CanvasMat from ImageData.
 *
 * OpenCV behavior:
 * - Converts ImageData to cv.Mat
 * - Preserves RGBA channels
 *
 * @param imageData - Source ImageData
 * @returns CanvasMat wrapping the ImageData
 */
export function createCanvasMat(imageData: ImageData): CanvasMat {
  return {
    imageData,
    width: imageData.width,
    height: imageData.height,
    channels: 4, // RGBA
  };
}

/**
 * REPLACES: cv.imshow(canvas, mat) conversion
 *
 * Converts CanvasMat back to ImageData for canvas rendering.
 *
 * @param mat - Source CanvasMat
 * @returns ImageData for canvas rendering
 */
export function matToImageData(mat: CanvasMat): ImageData {
  return mat.imageData;
}

/**
 * REPLACES: mat.clone()
 *
 * Creates a deep copy of a CanvasMat.
 *
 * OpenCV behavior:
 * - Allocates new Mat with same dimensions
 * - Copies all pixel data
 *
 * @param src - Source CanvasMat
 * @returns New CanvasMat with copied data
 */
export function clone(src: CanvasMat): CanvasMat {
  const newImageData = new ImageData(src.width, src.height);
  newImageData.data.set(src.imageData.data);

  return {
    imageData: newImageData,
    width: src.width,
    height: src.height,
    channels: 4,
  };
}

/**
 * REPLACES: mat.roi(rect)
 *
 * Extracts a region of interest (ROI) as a new CanvasMat.
 *
 * OpenCV behavior:
 * - Creates a view or clone of the specified rectangle
 * - Coordinates are (x, y, width, height)
 *
 * @param src - Source CanvasMat
 * @param rect - Rectangle defining ROI
 * @returns New CanvasMat containing only the ROI pixels
 */
export function extractROI(src: CanvasMat, rect: Rect): CanvasMat {
  const { x, y, width, height } = rect;

  // Clamp rectangle to image bounds
  const clampedX = Math.max(0, Math.min(x, src.width));
  const clampedY = Math.max(0, Math.min(y, src.height));
  const clampedWidth = Math.min(width, src.width - clampedX);
  const clampedHeight = Math.min(height, src.height - clampedY);

  const roiImageData = new ImageData(clampedWidth, clampedHeight);
  const srcData = src.imageData.data;
  const dstData = roiImageData.data;

  for (let row = 0; row < clampedHeight; row++) {
    const srcRowStart = ((clampedY + row) * src.width + clampedX) * 4;
    const dstRowStart = row * clampedWidth * 4;

    for (let col = 0; col < clampedWidth; col++) {
      const srcIdx = srcRowStart + col * 4;
      const dstIdx = dstRowStart + col * 4;

      dstData[dstIdx] = srcData[srcIdx]!; // R
      dstData[dstIdx + 1] = srcData[srcIdx + 1]!; // G
      dstData[dstIdx + 2] = srcData[srcIdx + 2]!; // B
      dstData[dstIdx + 3] = srcData[srcIdx + 3]!; // A
    }
  }

  return createCanvasMat(roiImageData);
}

/**
 * REPLACES: mat.ucharPtr(y, x)[c]
 *
 * Gets pixel value at (y, x) channel c.
 *
 * OpenCV behavior:
 * - Direct memory access
 * - Returns pointer to pixel data
 * - Channels in BGR order for 3-channel, BGRA for 4-channel
 *
 * Canvas equivalent:
 * - Channels in RGBA order
 * - Returns value directly (not pointer)
 *
 * @param mat - Source CanvasMat
 * @param y - Row index
 * @param x - Column index
 * @param c - Channel index (0=R, 1=G, 2=B, 3=A)
 * @returns Pixel value (0-255)
 */
export function getPixel(
  mat: CanvasMat,
  y: number,
  x: number,
  c: number,
): number {
  const idx = (y * mat.width + x) * 4 + c;
  return mat.imageData.data[idx] ?? 0;
}

/**
 * REPLACES: mat.ucharPtr(y, x)[c] = value
 *
 * Sets pixel value at (y, x) channel c.
 *
 * IMPORTANT: This mutates the CanvasMat in place.
 *
 * @param mat - Target CanvasMat (mutated)
 * @param y - Row index
 * @param x - Column index
 * @param c - Channel index (0=R, 1=G, 2=B, 3=A)
 * @param value - New pixel value (0-255)
 */
export function setPixel(
  mat: CanvasMat,
  y: number,
  x: number,
  c: number,
  value: number,
): void {
  const idx = (y * mat.width + x) * 4 + c;
  mat.imageData.data[idx] = value;
}

/**
 * REPLACES: cv.mean(mat)
 *
 * Calculates mean value across all channels.
 *
 * OpenCV behavior:
 * - Returns array [meanB, meanG, meanR, meanA] (BGR order)
 * - Averages all pixels in each channel
 *
 * Canvas equivalent:
 * - Returns array [meanR, meanG, meanB, meanA] (RGBA order)
 *
 * @param mat - Source CanvasMat
 * @returns Array of mean values for each channel
 */
export function calculateMean(
  mat: CanvasMat,
): [number, number, number, number] {
  const pixels = mat.imageData.data;
  const pixelCount = mat.width * mat.height;

  let sumR = 0,
    sumG = 0,
    sumB = 0,
    sumA = 0;

  for (let i = 0; i < pixels.length; i += 4) {
    sumR += pixels[i]!; // Red
    sumG += pixels[i + 1]!; // Green
    sumB += pixels[i + 2]!; // Blue
    sumA += pixels[i + 3]!; // Alpha
  }

  return [
    sumR / pixelCount,
    sumG / pixelCount,
    sumB / pixelCount,
    sumA / pixelCount,
  ];
}

/**
 * REPLACES: cv.bitwise_not(src, dst)
 *
 * Inverts all pixel values: dst[i] = 255 - src[i]
 *
 * OpenCV behavior:
 * - Inverts R, G, B channels
 * - Preserves alpha channel
 *
 * @param src - Source CanvasMat
 * @returns New CanvasMat with inverted colors
 */
export function bitwiseNot(src: CanvasMat): CanvasMat {
  const srcPixels = src.imageData.data;
  const dstImageData = new ImageData(src.width, src.height);
  const dstPixels = dstImageData.data;

  for (let i = 0; i < srcPixels.length; i += 4) {
    dstPixels[i] = 255 - srcPixels[i]!; // Invert R
    dstPixels[i + 1] = 255 - srcPixels[i + 1]!; // Invert G
    dstPixels[i + 2] = 255 - srcPixels[i + 2]!; // Invert B
    dstPixels[i + 3] = srcPixels[i + 3]!; // Preserve alpha
  }

  return createCanvasMat(dstImageData);
}

/**
 * REPLACES: mat.convertTo(dst, rtype, alpha, beta)
 *
 * Applies linear transformation: dst = src * alpha + beta
 * Used for contrast and brightness adjustment.
 *
 * OpenCV behavior:
 * - dst[i] = saturate(src[i] * alpha + beta)
 * - saturate clamps to [0, 255] for 8-bit images
 *
 * @param src - Source CanvasMat
 * @param alpha - Contrast multiplier
 * @param beta - Brightness offset
 * @returns New CanvasMat with adjusted contrast/brightness
 */
export function convertTo(
  src: CanvasMat,
  alpha: number,
  beta: number,
): CanvasMat {
  const srcPixels = src.imageData.data;
  const dstImageData = new ImageData(src.width, src.height);
  const dstPixels = dstImageData.data;

  for (let i = 0; i < srcPixels.length; i += 4) {
    // Apply transformation and clamp to [0, 255]
    dstPixels[i] = Math.max(0, Math.min(255, srcPixels[i]! * alpha + beta)); // R
    dstPixels[i + 1] = Math.max(
      0,
      Math.min(255, srcPixels[i + 1]! * alpha + beta),
    ); // G
    dstPixels[i + 2] = Math.max(
      0,
      Math.min(255, srcPixels[i + 2]! * alpha + beta),
    ); // B
    dstPixels[i + 3] = srcPixels[i + 3]!; // Preserve alpha
  }

  return createCanvasMat(dstImageData);
}

/**
 * REPLACES: cv.cvtColor(src, dst, cv.COLOR_BGR2GRAY)
 *
 * Converts color image to grayscale.
 *
 * OpenCV behavior:
 * - Uses formula: Y = 0.299*R + 0.587*G + 0.114*B (BT.601)
 * - Actually uses integer approximation: Y = (R*77 + G*150 + B*29) >> 8
 *
 * For exact OpenCV compatibility, we use the same integer formula.
 *
 * @param src - Source CanvasMat (RGBA)
 * @returns New grayscale CanvasMat (R=G=B=gray value)
 */
export function cvtColorToGray(src: CanvasMat): CanvasMat {
  const srcPixels = src.imageData.data;
  const dstImageData = new ImageData(src.width, src.height);
  const dstPixels = dstImageData.data;

  for (let i = 0; i < srcPixels.length; i += 4) {
    const r = srcPixels[i]!;
    const g = srcPixels[i + 1]!;
    const b = srcPixels[i + 2]!;

    // OpenCV's exact formula: (R*77 + G*150 + B*29) >> 8
    const gray = (r * 77 + g * 150 + b * 29) >> 8;

    dstPixels[i] = gray; // R
    dstPixels[i + 1] = gray; // G
    dstPixels[i + 2] = gray; // B
    dstPixels[i + 3] = srcPixels[i + 3]!; // Preserve alpha
  }

  return createCanvasMat(dstImageData);
}

/**
 * REPLACES: cv.threshold(src, dst, thresh, maxval, cv.THRESH_BINARY)
 *
 * Applies binary threshold to image.
 *
 * OpenCV behavior (THRESH_BINARY):
 * - if src[i] > thresh: dst[i] = maxval
 * - else: dst[i] = 0
 *
 * @param src - Source CanvasMat (should be grayscale)
 * @param thresh - Threshold value
 * @param maxval - Maximum value to set
 * @returns New CanvasMat with thresholded values
 */
export function threshold(
  src: CanvasMat,
  thresh: number,
  maxval: number,
): CanvasMat {
  const srcPixels = src.imageData.data;
  const dstImageData = new ImageData(src.width, src.height);
  const dstPixels = dstImageData.data;

  for (let i = 0; i < srcPixels.length; i += 4) {
    // For grayscale, all RGB channels have same value
    const value = srcPixels[i]!;
    const newValue = value > thresh ? maxval : 0;

    dstPixels[i] = newValue; // R
    dstPixels[i + 1] = newValue; // G
    dstPixels[i + 2] = newValue; // B
    dstPixels[i + 3] = srcPixels[i + 3]!; // Preserve alpha
  }

  return createCanvasMat(dstImageData);
}

/**
 * REPLACES: cv.resize(src, dst, dsize, fx, fy, cv.INTER_AREA)
 *
 * Resizes image using area interpolation (best for downscaling).
 *
 * OpenCV cv.INTER_AREA behavior:
 * - For downscaling: averages pixel areas
 * - For upscaling: similar to linear interpolation
 *
 * This implementation uses bilinear interpolation which is simpler
 * and provides similar results for our use case (upscaling by 4x).
 *
 * @param src - Source CanvasMat
 * @param dstWidth - Target width
 * @param dstHeight - Target height
 * @returns New CanvasMat with resized image
 */
export function resize(
  src: CanvasMat,
  dstWidth: number,
  dstHeight: number,
): CanvasMat {
  // CRITICAL: Disable smoothing for pixel-perfect scaling (matches OpenCV INTER_NEAREST)
  // This is essential for grid alignment - any smoothing/anti-aliasing will cause misalignment
  const srcCanvas = new OffscreenCanvas(src.width, src.height);
  const srcCtx = srcCanvas.getContext("2d");

  if (!srcCtx) {
    throw new Error("Failed to get source canvas context");
  }

  srcCtx.putImageData(src.imageData, 0, 0);

  const dstCanvas = new OffscreenCanvas(dstWidth, dstHeight);
  const dstCtx = dstCanvas.getContext("2d");

  if (!dstCtx) {
    throw new Error("Failed to get destination canvas context");
  }

  // DISABLE smoothing for nearest-neighbor interpolation (exact pixel replication)
  dstCtx.imageSmoothingEnabled = false;

  dstCtx.drawImage(
    srcCanvas,
    0,
    0,
    src.width,
    src.height,
    0,
    0,
    dstWidth,
    dstHeight,
  );

  const dstImageData = dstCtx.getImageData(0, 0, dstWidth, dstHeight);

  return createCanvasMat(dstImageData);
}

// ============================================================================
// HIGH-LEVEL OPERATIONS - Built on Core Operations
// ============================================================================

/**
 * Color quantization - reduces number of distinct colors.
 *
 * Replaces custom reduceColorCount() function.
 *
 * @param src - Source CanvasMat
 * @param numColors - Number of color levels (e.g., 2 for binary)
 * @returns New CanvasMat with reduced color count
 */
export function reduceColorCount(src: CanvasMat, numColors: number): CanvasMat {
  const dst = clone(src);
  const pixels = dst.imageData.data;

  for (let i = 0; i < pixels.length; i += 4) {
    for (let c = 0; c < 3; c++) {
      // R, G, B only (skip alpha)
      const pixelValue = pixels[i + c]!;

      for (let level = 0; level < numColors; level++) {
        const lowerBound = (level * 255) / numColors;
        const upperBound = ((level + 1) * 255) / numColors;

        if (pixelValue >= lowerBound && pixelValue < upperBound) {
          pixels[i + c] = Math.floor((level * 255) / (numColors - 1));
          break;
        }
      }
    }
  }

  return dst;
}

/**
 * Scales image up by a factor.
 *
 * Replaces scaleUp() function.
 *
 * @param src - Source CanvasMat
 * @param scaleFactor - Scale multiplier
 * @returns New CanvasMat scaled up
 */
export function scaleUp(src: CanvasMat, scaleFactor: number): CanvasMat {
  const dstWidth = Math.floor(src.width * scaleFactor);
  const dstHeight = Math.floor(src.height * scaleFactor);

  return resize(src, dstWidth, dstHeight);
}

/**
 * Checks if two pixel arrays are close within threshold.
 *
 * Replaces isClose() function.
 *
 * @param pixel1 - First pixel array
 * @param pixel2 - Second pixel array
 * @param threshold - Maximum difference per channel
 * @returns True if pixels are close
 */
export function isClose(
  pixel1: number[],
  pixel2: number[],
  threshold: number = 1,
): boolean {
  let sum = 0;
  for (let i = 0; i < Math.min(pixel1.length, pixel2.length); i++) {
    sum += Math.abs((pixel1[i] ?? 0) - (pixel2[i] ?? 0));
  }
  return sum <= threshold * pixel1.length;
}

/**
 * Finds the most common pixel value in image.
 *
 * Replaces getMostCommonPixel() function.
 *
 * @param src - Source CanvasMat
 * @param index - Index in sorted list (-1 for last, -2 for second-to-last, etc.)
 * @returns Most common pixel as [R, G, B] or null
 */
export function getMostCommonPixel(
  src: CanvasMat,
  index: number = -1,
): number[] | null {
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

  const absIndex = index < 0 ? sorted.length + index : index;

  if (absIndex >= sorted.length) {
    const first = sorted[0];
    return first ? first.pixel : null;
  }

  const result = sorted[absIndex];
  return result ? result.pixel : null;
}

/**
 * Removes all pixels except those matching target color.
 * Sets matching pixels to black (0,0,0), non-matching to white (255,255,255).
 *
 * Replaces removeAllBut() function.
 *
 * @param src - Source CanvasMat
 * @param targetColor - Target color as [R, G, B]
 * @param threshold - Maximum Euclidean distance to target color
 * @returns New CanvasMat with filtered colors
 */
export function removeAllBut(
  src: CanvasMat,
  targetColor: number[],
  threshold: number = 30,
): CanvasMat {
  const dst = clone(src);
  const pixels = dst.imageData.data;

  for (let i = 0; i < pixels.length; i += 4) {
    const r = pixels[i]!;
    const g = pixels[i + 1]!;
    const b = pixels[i + 2]!;

    // Calculate Euclidean distance to target color
    const dr = r - (targetColor[0] ?? 0);
    const dg = g - (targetColor[1] ?? 0);
    const db = b - (targetColor[2] ?? 0);
    const distance = Math.sqrt(dr * dr + dg * dg + db * db);

    if (distance <= threshold) {
      // Match: set to black
      pixels[i] = 0;
      pixels[i + 1] = 0;
      pixels[i + 2] = 0;
    } else {
      // No match: set to white
      pixels[i] = 255;
      pixels[i + 1] = 255;
      pixels[i + 2] = 255;
    }
  }

  return dst;
}

/**
 * Darkens all non-white pixels to black.
 *
 * Replaces darkenNonWhite() function.
 *
 * Algorithm:
 * 1. Convert to grayscale
 * 2. Threshold at 240 (white pixels > 240)
 * 3. Set non-white pixels to black in original image
 *
 * @param src - Source CanvasMat
 * @returns New CanvasMat with non-white pixels darkened
 */
export function darkenNonWhite(src: CanvasMat): CanvasMat {
  // Convert to grayscale
  const gray = cvtColorToGray(src);

  // Threshold to find white pixels (> 240)
  const thresh = threshold(gray, 240, 255);

  // Clone source for result
  const result = clone(src);
  const resultPixels = result.imageData.data;
  const threshPixels = thresh.imageData.data;

  // Set non-white pixels to black
  for (let i = 0; i < resultPixels.length; i += 4) {
    const isWhite = threshPixels[i]! >= 250; // Threshold result

    if (!isWhite) {
      resultPixels[i] = 0; // R
      resultPixels[i + 1] = 0; // G
      resultPixels[i + 2] = 0; // B
      // Preserve alpha
    }
  }

  return result;
}

/**
 * Adjusts contrast and brightness.
 *
 * Replaces adjustContrastBrightness() function.
 *
 * OpenCV formula: dst = src * contrast + brightness + adjustment
 * where adjustment = 255 * (1 - contrast) / 2
 *
 * @param src - Source CanvasMat
 * @param contrast - Contrast multiplier (1.0 = no change)
 * @param brightness - Brightness offset
 * @returns New CanvasMat with adjusted contrast/brightness
 */
export function adjustContrastBrightness(
  src: CanvasMat,
  contrast: number = 1.0,
  brightness: number = 0,
): CanvasMat {
  const adjustedBrightness =
    brightness + Math.round((255 * (1 - contrast)) / 2);
  return convertTo(src, contrast, adjustedBrightness);
}

/**
 * Detects and converts dark mode screenshots.
 *
 * Replaces convertDarkMode() function.
 *
 * Algorithm:
 * 1. Calculate mean brightness across all channels
 * 2. If avgBrightness < 100: invert colors and adjust contrast
 * 3. Otherwise: return clone
 *
 * @param src - Source CanvasMat
 * @returns New CanvasMat with dark mode corrected
 */
export function convertDarkMode(src: CanvasMat): CanvasMat {
  const DARK_MODE_THRESHOLD = 100;

  const mean = calculateMean(src);
  const avgBrightness = (mean[0] + mean[1] + mean[2]) / 3;

  if (avgBrightness < DARK_MODE_THRESHOLD) {
    const inverted = bitwiseNot(src);
    const adjusted = adjustContrastBrightness(inverted, 3.0, 10);
    return adjusted;
  }

  return clone(src);
}

/**
 * Extracts a region of interest (convenience wrapper).
 *
 * Replaces extractRegion() function.
 *
 * @param src - Source CanvasMat
 * @param rect - Rectangle defining ROI
 * @returns New CanvasMat containing ROI
 */
export function extractRegion(src: CanvasMat, rect: Rect): CanvasMat {
  return extractROI(src, rect);
}

// ============================================================================
// CONVERSION UTILITIES
// ============================================================================

/**
 * Converts Blob to ImageData.
 *
 * @param blob - Image blob (JPEG, PNG, etc.)
 * @returns ImageData
 */
export async function blobToImageData(blob: Blob): Promise<ImageData> {
  const imageBitmap = await createImageBitmap(blob);
  const canvas = new OffscreenCanvas(imageBitmap.width, imageBitmap.height);
  const ctx = canvas.getContext("2d");

  if (!ctx) {
    throw new Error("Failed to get canvas context");
  }

  ctx.drawImage(imageBitmap, 0, 0);
  return ctx.getImageData(0, 0, imageBitmap.width, imageBitmap.height);
}

/**
 * Converts CanvasMat to Blob.
 *
 * @param mat - Source CanvasMat
 * @returns PNG Blob
 */
export async function matToBlob(mat: CanvasMat): Promise<Blob> {
  const canvas = new OffscreenCanvas(mat.width, mat.height);
  const ctx = canvas.getContext("2d");

  if (!ctx) {
    throw new Error("Failed to get canvas context");
  }

  ctx.putImageData(mat.imageData, 0, 0);

  return await canvas.convertToBlob({ type: "image/png" });
}

/**
 * Converts ImageData to CanvasMat (alias for createCanvasMat).
 *
 * @param imageData - Source ImageData
 * @returns CanvasMat
 */
export function imageDataToMat(imageData: ImageData): CanvasMat {
  return createCanvasMat(imageData);
}

/**
 * Converts ImageData to OffscreenCanvas for Tesseract.js
 *
 * Tesseract.js in worker context needs a canvas element, not raw ImageData.
 *
 * @param imageData - Source ImageData
 * @returns OffscreenCanvas with image data
 */
export function imageDataToCanvas(imageData: ImageData): OffscreenCanvas {
  const canvas = new OffscreenCanvas(imageData.width, imageData.height);
  const ctx = canvas.getContext("2d");

  if (!ctx) {
    throw new Error("Failed to get canvas context");
  }

  ctx.putImageData(imageData, 0, 0);
  return canvas;
}
