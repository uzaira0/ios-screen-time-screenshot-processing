import { detectDevice, DEVICE_PROFILES } from "./deviceDetection";

export interface CropResult {
  croppedBlob: Blob;
  wasCropped: boolean;
  originalDimensions: { width: number; height: number };
  croppedDimensions: { width: number; height: number };
  deviceModel?: string | undefined;
}

/**
 * Check if an image needs cropping based on its dimensions.
 * Returns true for iPad screenshots that have a sidebar to remove.
 */
export function shouldCrop(width: number, height: number): boolean {
  const result = detectDevice(width, height);
  return result.detected && result.needsCropping === true;
}

/**
 * Find the device profile matching the given dimensions within tolerance.
 * Returns the profile's crop coordinates, or null if no match.
 */
function findProfileCropCoords(
  width: number,
  height: number,
  tolerance: number = 10,
): {
  cropX: number;
  cropY: number;
  cropWidth: number;
  cropHeight: number;
} | null {
  // Ensure portrait orientation for matching
  const w = Math.min(width, height);
  const h = Math.max(width, height);

  for (const profile of DEVICE_PROFILES) {
    if (
      profile.category !== "ipad" ||
      profile.cropX === undefined ||
      profile.cropWidth === undefined ||
      profile.cropY === undefined ||
      profile.cropHeight === undefined
    ) {
      continue;
    }

    const pW = Math.min(profile.width, profile.height);
    const pH = Math.max(profile.width, profile.height);

    if (Math.abs(w - pW) <= tolerance && Math.abs(h - pH) <= tolerance) {
      return {
        cropX: profile.cropX,
        cropY: profile.cropY,
        cropWidth: profile.cropWidth,
        cropHeight: profile.cropHeight,
      };
    }
  }
  return null;
}

/**
 * Crop an iPad screenshot by removing the left sidebar.
 * Uses Canvas API for the crop operation.
 */
export async function cropScreenshot(imageBlob: Blob): Promise<CropResult> {
  // 1. Create ImageBitmap from blob
  const bitmap = await createImageBitmap(imageBlob);
  const { width, height } = bitmap;

  // 2. Detect device to determine if cropping is needed
  const detection = detectDevice(width, height);

  if (!detection.detected || !detection.needsCropping) {
    bitmap.close();
    return {
      croppedBlob: imageBlob,
      wasCropped: false,
      originalDimensions: { width, height },
      croppedDimensions: { width, height },
      deviceModel: detection.model,
    };
  }

  // 3. Find the matching profile to get crop coordinates
  const cropCoords = findProfileCropCoords(width, height);

  if (!cropCoords) {
    // Detection said it needs cropping but no profile matched — tolerance mismatch.
    console.warn(`[cropping] Device detection indicated cropping needed but no crop profile found for ${width}x${height}`);
    bitmap.close();
    return {
      croppedBlob: imageBlob,
      wasCropped: false,
      originalDimensions: { width, height },
      croppedDimensions: { width, height },
      deviceModel: detection.model,
    };
  }

  const { cropX, cropY, cropWidth, cropHeight } = cropCoords;

  // 4. Create canvas with crop dimensions
  const canvas = new OffscreenCanvas(cropWidth, cropHeight);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error(`Failed to get 2D context for ${cropWidth}x${cropHeight} OffscreenCanvas`);

  // 5. Draw cropped region
  ctx.drawImage(
    bitmap,
    cropX,
    cropY,
    cropWidth,
    cropHeight,
    0,
    0,
    cropWidth,
    cropHeight
  );
  bitmap.close();

  // 6. Convert to blob — JPEG is ~10x faster to encode than PNG for screenshots
  const croppedBlob = await canvas.convertToBlob({ type: "image/jpeg", quality: 0.92 });

  return {
    croppedBlob,
    wasCropped: true,
    originalDimensions: { width, height },
    croppedDimensions: { width: cropWidth, height: cropHeight },
    deviceModel: detection.model,
  };
}
