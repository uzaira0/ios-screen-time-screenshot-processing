import type { PHIRegion } from "@/core/interfaces/IPreprocessingService";
export type { PHIRegion };

export type RedactionMethod = "redbox" | "blackbox" | "pixelate";

/**
 * Redact PHI regions in an image using the specified method.
 *
 * @param imageBlob - Source image as Blob
 * @param regions - PHI regions to redact
 * @param method - Redaction method (redbox, blackbox, pixelate)
 * @param padding - Extra pixels around each region (default 2)
 * @returns New Blob with regions redacted
 */
export async function redactImage(
  imageBlob: Blob,
  regions: PHIRegion[],
  method: RedactionMethod = "redbox",
  padding: number = 2,
): Promise<Blob> {
  if (regions.length === 0) {
    return imageBlob;
  }

  const bitmap = await createImageBitmap(imageBlob);
  const { width, height } = bitmap;

  const canvas = new OffscreenCanvas(width, height);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error(`Failed to get 2D context for ${width}x${height} OffscreenCanvas`);

  // Draw original image
  ctx.drawImage(bitmap, 0, 0);
  bitmap.close();

  for (const region of regions) {
    const rx = Math.max(0, region.x - padding);
    const ry = Math.max(0, region.y - padding);
    const rw = Math.min(width - rx, region.w + 2 * padding);
    const rh = Math.min(height - ry, region.h + 2 * padding);

    switch (method) {
      case "redbox":
        ctx.fillStyle = "red";
        ctx.fillRect(rx, ry, rw, rh);
        break;
      case "blackbox":
        ctx.fillStyle = "black";
        ctx.fillRect(rx, ry, rw, rh);
        break;
      case "pixelate": {
        // Extract region, scale down to ~10%, scale back up with no smoothing
        const regionData = ctx.getImageData(rx, ry, rw, rh);
        const pixelSize = Math.max(1, Math.ceil(Math.min(rw, rh) / 10));

        // Create tiny canvas
        const tinyW = Math.max(1, Math.ceil(rw / pixelSize));
        const tinyH = Math.max(1, Math.ceil(rh / pixelSize));
        const tinyCanvas = new OffscreenCanvas(tinyW, tinyH);
        const tinyCtx = tinyCanvas.getContext("2d");
        if (!tinyCtx) {
          // Fall back to solid fill — never leave PHI unredacted
          ctx.fillStyle = "black";
          ctx.fillRect(rx, ry, rw, rh);
          break;
        }

        // Draw region scaled down
        const tempCanvas = new OffscreenCanvas(rw, rh);
        const tempCtx = tempCanvas.getContext("2d");
        if (!tempCtx) {
          ctx.fillStyle = "black";
          ctx.fillRect(rx, ry, rw, rh);
          break;
        }
        tempCtx.putImageData(regionData, 0, 0);

        tinyCtx.drawImage(tempCanvas, 0, 0, tinyW, tinyH);

        // Draw back scaled up with no smoothing
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(tinyCanvas, 0, 0, tinyW, tinyH, rx, ry, rw, rh);
        ctx.imageSmoothingEnabled = true;
        break;
      }
    }
  }

  return canvas.convertToBlob({ type: "image/png" });
}
