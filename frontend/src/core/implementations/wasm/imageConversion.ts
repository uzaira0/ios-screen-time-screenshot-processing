/**
 * Optimized Image Conversion Utilities
 *
 * Delegates to canvasImageUtils for the primary implementation,
 * adding browser fallback for environments without OffscreenCanvas.
 */

import { blobToImageData } from "./processing/canvasImageUtils";

/**
 * Convert Blob to ImageData using modern APIs (GPU-accelerated).
 * Delegates to canvasImageUtils.blobToImageData.
 */
export { blobToImageData as convertBlobToImageData } from "./processing/canvasImageUtils";

/**
 * Fallback for browsers that don't support OffscreenCanvas
 *
 * @param blob - Image blob
 * @returns ImageData
 */
export async function convertBlobToImageDataFallback(blob: Blob): Promise<ImageData> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(blob);

    img.onload = () => {
      try {
        const canvas = document.createElement('canvas');
        canvas.width = img.width;
        canvas.height = img.height;

        const ctx = canvas.getContext('2d');
        if (!ctx) {
          throw new Error('Failed to get 2D context');
        }

        ctx.drawImage(img, 0, 0);
        const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);

        URL.revokeObjectURL(url);
        resolve(imageData);
      } catch (error) {
        URL.revokeObjectURL(url);
        reject(error);
      }
    };

    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('Failed to load image'));
    };

    img.src = url;
  });
}

/**
 * Smart conversion with feature detection.
 * Uses optimized path (canvasImageUtils) if available, falls back to legacy approach.
 */
export async function smartConvertBlobToImageData(blob: Blob): Promise<ImageData> {
  if (typeof OffscreenCanvas !== 'undefined') {
    try {
      return await blobToImageData(blob);
    } catch (error) {
      console.warn('Optimized conversion failed, using fallback:', error);
      return await convertBlobToImageDataFallback(blob);
    }
  }

  return await convertBlobToImageDataFallback(blob);
}
