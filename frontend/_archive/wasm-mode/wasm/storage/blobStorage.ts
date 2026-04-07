import { db } from "./database";

// LRU cache for object URLs with automatic eviction
const MAX_CACHE_SIZE = 50; // Maximum number of cached URLs
const objectURLCache = new Map<number, string>();
const cacheAccessOrder: number[] = []; // Track LRU order

/**
 * Evict oldest entries from cache if over limit
 */
function evictOldEntries(): void {
  while (cacheAccessOrder.length > MAX_CACHE_SIZE) {
    const oldestId = cacheAccessOrder.shift();
    if (oldestId !== undefined) {
      const url = objectURLCache.get(oldestId);
      if (url) {
        URL.revokeObjectURL(url);
        objectURLCache.delete(oldestId);
        console.log(
          `[blobStorage] Evicted cached URL for screenshot ${oldestId}`,
        );
      }
    }
  }
}

/**
 * Update LRU access order
 */
function touchCache(screenshotId: number): void {
  const index = cacheAccessOrder.indexOf(screenshotId);
  if (index > -1) {
    cacheAccessOrder.splice(index, 1);
  }
  cacheAccessOrder.push(screenshotId);
}

export async function storeImageBlob(
  screenshotId: number,
  blob: Blob,
): Promise<void> {
  await db.imageBlobs.put(
    {
      screenshotId,
      blob,
      uploadedAt: new Date().toISOString(),
    },
    screenshotId,
  );
}

export async function retrieveImageBlob(
  screenshotId: number,
): Promise<Blob | null> {
  const record = await db.imageBlobs.get(screenshotId);
  return record?.blob || null;
}

export async function deleteImageBlob(screenshotId: number): Promise<void> {
  revokeObjectURL(screenshotId);
  await db.imageBlobs.delete(screenshotId);
}

export async function createObjectURL(
  screenshotId: number,
): Promise<string | null> {
  if (objectURLCache.has(screenshotId)) {
    // Update LRU order on cache hit
    touchCache(screenshotId);
    return objectURLCache.get(screenshotId)!;
  }

  const blob = await retrieveImageBlob(screenshotId);

  if (!blob) {
    return null;
  }

  const url = URL.createObjectURL(blob);
  objectURLCache.set(screenshotId, url);
  touchCache(screenshotId);

  // Evict old entries if cache is too large
  evictOldEntries();

  return url;
}

export function revokeObjectURL(screenshotId: number): void {
  const url = objectURLCache.get(screenshotId);

  if (url) {
    URL.revokeObjectURL(url);
    objectURLCache.delete(screenshotId);
    // Remove from LRU order
    const index = cacheAccessOrder.indexOf(screenshotId);
    if (index > -1) {
      cacheAccessOrder.splice(index, 1);
    }
  }
}

export function revokeAllObjectURLs(): void {
  for (const [, url] of objectURLCache.entries()) {
    URL.revokeObjectURL(url);
  }
  objectURLCache.clear();
  cacheAccessOrder.length = 0; // Clear the LRU order array
}

export async function getImageBlobInfo(screenshotId: number): Promise<{
  size: number;
  type: string;
  uploadedAt: string;
} | null> {
  const record = await db.imageBlobs.get(screenshotId);

  if (!record) {
    return null;
  }

  return {
    size: record.blob.size,
    type: record.blob.type,
    uploadedAt: record.uploadedAt,
  };
}

export async function getTotalBlobSize(): Promise<number> {
  const allBlobs = await db.imageBlobs.toArray();
  return allBlobs.reduce((total, record) => total + record.blob.size, 0);
}

export async function checkStorageQuota(): Promise<{
  usage: number;
  quota: number;
  percentUsed: number;
  available: number;
}> {
  if (!navigator.storage || !navigator.storage.estimate) {
    return {
      usage: 0,
      quota: 0,
      percentUsed: 0,
      available: 0,
    };
  }

  const estimate = await navigator.storage.estimate();
  const usage = estimate.usage || 0;
  const quota = estimate.quota || 0;
  const percentUsed = quota > 0 ? (usage / quota) * 100 : 0;
  const available = quota - usage;

  return {
    usage,
    quota,
    percentUsed,
    available,
  };
}

export async function canStoreBlob(blob: Blob): Promise<boolean> {
  const quota = await checkStorageQuota();
  const blobSize = blob.size;

  const SAFETY_MARGIN = 10 * 1024 * 1024;

  return quota.available > blobSize + SAFETY_MARGIN;
}

export async function compressImage(
  blob: Blob,
  maxWidth = 1920,
  quality = 0.9,
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");

    if (!ctx) {
      reject(new Error("Could not get canvas context"));
      return;
    }

    img.onload = () => {
      let width = img.width;
      let height = img.height;

      if (width > maxWidth) {
        height = (height * maxWidth) / width;
        width = maxWidth;
      }

      canvas.width = width;
      canvas.height = height;
      ctx.drawImage(img, 0, 0, width, height);

      canvas.toBlob(
        (compressedBlob) => {
          if (compressedBlob) {
            resolve(compressedBlob);
          } else {
            reject(new Error("Failed to compress image"));
          }
        },
        "image/jpeg",
        quality,
      );
    };

    img.onerror = () => {
      reject(new Error("Failed to load image for compression"));
    };

    img.src = URL.createObjectURL(blob);
  });
}
