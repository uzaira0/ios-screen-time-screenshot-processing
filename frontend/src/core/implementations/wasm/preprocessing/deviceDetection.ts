/**
 * iOS Device Detection - TypeScript port of the Python ios-device-detector package.
 *
 * Detects iPhone and iPad models from screenshot pixel dimensions.
 * iPad profiles include crop coordinates from the ipad-screenshot-cropper package.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type DeviceCategory = "iphone" | "ipad" | "unknown";

export interface DeviceProfile {
  profileId: string;
  modelName: string;
  displayName: string;
  category: DeviceCategory;
  family: string;
  /** Screenshot width in pixels (points * scaleFactor). */
  width: number;
  /** Screenshot height in pixels (points * scaleFactor). */
  height: number;
  scaleFactor: number;
  /** Crop X offset for iPad sidebar removal. */
  cropX?: number;
  /** Crop Y offset (typically 0). */
  cropY?: number;
  /** Cropped region width. */
  cropWidth?: number;
  /** Cropped region height. */
  cropHeight?: number;
}

export interface DetectionResult {
  detected: boolean;
  model?: string;
  family?: string;
  category: DeviceCategory;
  confidence: number;
  dimensions: { width: number; height: number };
  needsCropping?: boolean;
}

// ---------------------------------------------------------------------------
// Device Profiles
// ---------------------------------------------------------------------------

/**
 * All known iOS device profiles.
 *
 * iPhone profiles are de-duplicated by unique pixel dimensions (many models
 * share identical screen sizes). iPad profiles are kept separately because
 * each has distinct crop coordinates.
 */
export const DEVICE_PROFILES: DeviceProfile[] = [
  // =========================================================================
  // iPhones (one representative per unique pixel dimension)
  // =========================================================================

  // 640x1136 - iPhone SE (1st generation) - 320*2 x 568*2
  {
    profileId: "iphone_se_1st",
    modelName: "iPhone SE (1st generation)",
    displayName: "iPhone SE",
    category: "iphone",
    family: "iphone_se",
    width: 640,
    height: 1136,
    scaleFactor: 2,
  },

  // 750x1334 - iPhone SE 2nd/3rd, 6, 7, 8 - 375*2 x 667*2
  {
    profileId: "iphone_se_2nd",
    modelName: "iPhone SE (2nd generation)",
    displayName: "iPhone SE (2020)",
    category: "iphone",
    family: "iphone_se",
    width: 750,
    height: 1334,
    scaleFactor: 2,
  },

  // 1242x2208 - iPhone 6/7/8 Plus - 414*3 x 736*3
  {
    profileId: "iphone_6_plus",
    modelName: "iPhone 6 Plus",
    displayName: "iPhone 6 Plus",
    category: "iphone",
    family: "iphone_plus",
    width: 1242,
    height: 2208,
    scaleFactor: 3,
  },

  // 1125x2436 - iPhone X, XS, 11 Pro, 12 mini, 13 mini - 375*3 x 812*3
  {
    profileId: "iphone_x",
    modelName: "iPhone X",
    displayName: "iPhone X",
    category: "iphone",
    family: "iphone_pro",
    width: 1125,
    height: 2436,
    scaleFactor: 3,
  },

  // 828x1792 - iPhone XR, 11 - 414*2 x 896*2
  {
    profileId: "iphone_xr",
    modelName: "iPhone XR",
    displayName: "iPhone XR",
    category: "iphone",
    family: "iphone_standard",
    width: 828,
    height: 1792,
    scaleFactor: 2,
  },

  // 1242x2688 - iPhone XS Max, 11 Pro Max - 414*3 x 896*3
  {
    profileId: "iphone_xs_max",
    modelName: "iPhone XS Max",
    displayName: "iPhone XS Max",
    category: "iphone",
    family: "iphone_pro_max",
    width: 1242,
    height: 2688,
    scaleFactor: 3,
  },

  // 1170x2532 - iPhone 12, 12 Pro, 13, 13 Pro, 14 - 390*3 x 844*3
  {
    profileId: "iphone_12",
    modelName: "iPhone 12",
    displayName: "iPhone 12",
    category: "iphone",
    family: "iphone_standard",
    width: 1170,
    height: 2532,
    scaleFactor: 3,
  },

  // 1284x2778 - iPhone 12 Pro Max, 13 Pro Max, 14 Plus - 428*3 x 926*3
  {
    profileId: "iphone_12_pro_max",
    modelName: "iPhone 12 Pro Max",
    displayName: "iPhone 12 Pro Max",
    category: "iphone",
    family: "iphone_pro_max",
    width: 1284,
    height: 2778,
    scaleFactor: 3,
  },

  // 1179x2556 - iPhone 14 Pro, 15, 15 Pro - 393*3 x 852*3
  {
    profileId: "iphone_14_pro",
    modelName: "iPhone 14 Pro",
    displayName: "iPhone 14 Pro",
    category: "iphone",
    family: "iphone_pro",
    width: 1179,
    height: 2556,
    scaleFactor: 3,
  },

  // 1290x2796 - iPhone 14 Pro Max, 15 Plus, 15 Pro Max - 430*3 x 932*3
  {
    profileId: "iphone_14_pro_max",
    modelName: "iPhone 14 Pro Max",
    displayName: "iPhone 14 Pro Max",
    category: "iphone",
    family: "iphone_pro_max",
    width: 1290,
    height: 2796,
    scaleFactor: 3,
  },

  // =========================================================================
  // iPads (each has unique crop coordinates)
  // =========================================================================

  // 1620x2160 - iPad 9th Gen - 810*2 x 1080*2
  {
    profileId: "ipad_9th",
    modelName: "iPad (9th generation)",
    displayName: "iPad 9th Gen",
    category: "ipad",
    family: "ipad_standard",
    width: 1620,
    height: 2160,
    scaleFactor: 2,
    cropX: 640,
    cropY: 0,
    cropWidth: 980,
    cropHeight: 2160,
  },

  // 1640x2360 - iPad 10th Gen / iPad Air 4th/5th - 820*2 x 1180*2
  {
    profileId: "ipad_10th",
    modelName: "iPad (10th generation)",
    displayName: "iPad 10th Gen",
    category: "ipad",
    family: "ipad_standard",
    width: 1640,
    height: 2360,
    scaleFactor: 2,
    cropX: 640,
    cropY: 0,
    cropWidth: 1000,
    cropHeight: 2360,
  },

  // 1536x2048 - iPad Mini 5th Gen - 768*2 x 1024*2
  {
    profileId: "ipad_mini_5th",
    modelName: "iPad mini (5th generation)",
    displayName: "iPad mini 5",
    category: "ipad",
    family: "ipad_mini",
    width: 1536,
    height: 2048,
    scaleFactor: 2,
    cropX: 640,
    cropY: 0,
    cropWidth: 896,
    cropHeight: 2048,
  },

  // 1488x2266 - iPad Mini 6th Gen - 744*2 x 1133*2
  {
    profileId: "ipad_mini_6th",
    modelName: "iPad mini (6th generation)",
    displayName: "iPad mini 6",
    category: "ipad",
    family: "ipad_mini",
    width: 1488,
    height: 2266,
    scaleFactor: 2,
    cropX: 640,
    cropY: 0,
    cropWidth: 848,
    cropHeight: 2266,
  },

  // 1668x2224 - iPad Air 3rd Gen - 834*2 x 1112*2
  {
    profileId: "ipad_air_3rd",
    modelName: "iPad Air (3rd generation)",
    displayName: "iPad Air 3",
    category: "ipad",
    family: "ipad_air",
    width: 1668,
    height: 2224,
    scaleFactor: 2,
    cropX: 640,
    cropY: 0,
    cropWidth: 1028,
    cropHeight: 2224,
  },

  // 1668x2388 - iPad Pro 11" (all generations) - 834*2 x 1194*2
  {
    profileId: "ipad_pro_11",
    modelName: 'iPad Pro 11-inch (1st generation)',
    displayName: 'iPad Pro 11"',
    category: "ipad",
    family: "ipad_pro_11",
    width: 1668,
    height: 2388,
    scaleFactor: 2,
    cropX: 640,
    cropY: 0,
    cropWidth: 1028,
    cropHeight: 2388,
  },

  // 2048x2732 - iPad Pro 12.9" (all generations) - 1024*2 x 1366*2
  {
    profileId: "ipad_pro_12_9",
    modelName: 'iPad Pro 12.9-inch (3rd generation)',
    displayName: 'iPad Pro 12.9"',
    category: "ipad",
    family: "ipad_pro_12_9",
    width: 2048,
    height: 2732,
    scaleFactor: 2,
    cropX: 790,
    cropY: 0,
    cropWidth: 1258,
    cropHeight: 2732,
  },
];

// ---------------------------------------------------------------------------
// Detection
// ---------------------------------------------------------------------------

/**
 * Detect iOS device from screenshot pixel dimensions.
 *
 * Matching strategy (highest confidence first):
 *  1. Exact match (portrait or landscape) -> 1.0
 *  2. Within +/- tolerance              -> 0.8 - 0.99
 *  3. Width matches, height partially cropped (>50%) -> 0.7 - 0.85
 *  4. Aspect-ratio only (ratio_diff < 0.05)          -> 0.5 - 0.6
 *  5. No match                                       -> 0.0
 */
export function detectDevice(
  width: number,
  height: number,
  tolerance: number = 5,
): DetectionResult {
  // Ensure portrait orientation for comparison
  const inputW = Math.min(width, height);
  const inputH = Math.max(width, height);

  let bestProfile: DeviceProfile | null = null;
  let bestConfidence = 0;

  for (const profile of DEVICE_PROFILES) {
    const profW = Math.min(profile.width, profile.height);
    const profH = Math.max(profile.width, profile.height);

    // --- 1. Exact match ---
    if (inputW === profW && inputH === profH) {
      bestProfile = profile;
      bestConfidence = 1.0;
      break; // Can't beat exact
    }

    // --- 2. Within tolerance ---
    const wDiff = Math.abs(inputW - profW);
    const hDiff = Math.abs(inputH - profH);

    if (wDiff <= tolerance && hDiff <= tolerance) {
      const maxDiff = Math.max(wDiff, hDiff);
      const confidence = Math.max(0.8, 1.0 - (maxDiff / tolerance) * 0.2);
      if (confidence > bestConfidence) {
        bestConfidence = confidence;
        bestProfile = profile;
      }
      continue;
    }

    // --- 3. Partially cropped (width matches, height shorter but >50%) ---
    if (wDiff <= tolerance && inputH < profH && inputH > profH * 0.5) {
      const heightRatio = inputH / profH;
      const confidence = Math.max(0.7, 0.85 * heightRatio);
      if (confidence > bestConfidence) {
        bestConfidence = confidence;
        bestProfile = profile;
      }
      continue;
    }

    // --- 4. Aspect ratio only ---
    const inputRatio = inputH / inputW;
    const profRatio = profH / profW;
    const ratioDiff = Math.abs(inputRatio - profRatio);

    if (ratioDiff < 0.05) {
      const confidence = Math.max(0.5, 0.6 - ratioDiff * 2);
      if (confidence > bestConfidence) {
        bestConfidence = confidence;
        bestProfile = profile;
      }
    }
  }

  // --- No match ---
  if (!bestProfile || bestConfidence < 0.5) {
    return {
      detected: false,
      category: "unknown",
      confidence: 0,
      dimensions: { width, height },
    };
  }

  // Determine if this iPad needs cropping (crop region differs from full width)
  const needsCropping =
    bestProfile.category === "ipad" &&
    bestProfile.cropX !== undefined &&
    bestProfile.cropWidth !== undefined &&
    bestProfile.cropWidth !== bestProfile.width;

  return {
    detected: true,
    model: bestProfile.modelName,
    family: bestProfile.family,
    category: bestProfile.category,
    confidence: bestConfidence,
    dimensions: { width, height },
    needsCropping,
  };
}
