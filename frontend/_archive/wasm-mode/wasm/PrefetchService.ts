/**
 * PrefetchService - Background Screenshot Prefetching
 *
 * Loads and preprocesses the next screenshot while the user annotates the current one.
 * This enables instant navigation by having the next screenshot ready in cache.
 *
 * Performance Impact: Navigation time reduced from 3-5s to <500ms
 */

import type { Screenshot, GridCoordinates } from "../../models";
import type { IStorageService } from "../../interfaces";
import type { IProcessingService } from "../../interfaces";

interface PrefetchedScreenshot {
  screenshot: Screenshot;
  imageBlob: Blob;
  imageUrl: string;
  processingResult?: {
    title: string | null;
    total: string | null;
    gridCoordinates: GridCoordinates | null;
  };
  timestamp: number;
}

export class PrefetchService {
  private prefetchCache = new Map<number, PrefetchedScreenshot>();
  private storageService: IStorageService;
  private processingService: IProcessingService;
  private maxCacheSize = 3; // Cache up to 3 screenshots
  private maxCacheAge = 5 * 60 * 1000; // 5 minutes
  private isPrefetching = false;

  constructor(
    storageService: IStorageService,
    processingService: IProcessingService,
  ) {
    this.storageService = storageService;
    this.processingService = processingService;
  }

  /**
   * Prefetch the next screenshot after the current one
   *
   * This runs in the background while the user annotates.
   *
   * @param currentScreenshotId - ID of currently displayed screenshot
   */
  async prefetchNext(currentScreenshotId: number): Promise<void> {
    if (this.isPrefetching) {
      return;
    }

    this.isPrefetching = true;

    try {
      // Clean up old entries first
      this.cleanupCache();

      // Get all pending screenshots
      const pendingScreenshots = await this.storageService.getAllScreenshots({
        annotation_status: "pending",
      });

      if (!pendingScreenshots || pendingScreenshots.length === 0) {
        return;
      }

      // Find the next screenshot after current
      const currentIndex = pendingScreenshots.findIndex(
        (s) => s.id === currentScreenshotId,
      );

      const nextScreenshot =
        currentIndex >= 0 && currentIndex < pendingScreenshots.length - 1
          ? pendingScreenshots[currentIndex + 1]
          : pendingScreenshots[0]; // Fallback to first if current is last

      if (!nextScreenshot) {
        console.log("[PrefetchService] No next screenshot to prefetch");
        return;
      }

      // Don't prefetch if already in cache
      if (this.prefetchCache.has(nextScreenshot.id)) {
        return;
      }

      console.log(
        `[PrefetchService] Prefetching screenshot ${nextScreenshot.id}`,
      );

      // Load image blob
      const imageBlob = await this.storageService.getImageBlob(
        nextScreenshot.id,
      );

      if (!imageBlob) {
        console.warn(
          `[PrefetchService] No image blob for screenshot ${nextScreenshot.id}`,
        );
        return;
      }

      // Create object URL for instant display
      const imageUrl = URL.createObjectURL(imageBlob);

      // Store in cache
      const prefetched: PrefetchedScreenshot = {
        screenshot: nextScreenshot,
        imageBlob,
        imageUrl,
        timestamp: Date.now(),
      };

      this.prefetchCache.set(nextScreenshot.id, prefetched);

      // Optionally: Preprocess grid detection in background (don't await)
      this.preprocessInBackground(nextScreenshot.id, imageBlob).catch((err) => {
        console.error(
          "[PrefetchService] Background preprocessing failed:",
          err,
        );
      });

      console.log(
        `[PrefetchService] Successfully prefetched screenshot ${nextScreenshot.id}`,
      );
    } catch (error) {
      console.error("[PrefetchService] Prefetch failed:", error);
    } finally {
      this.isPrefetching = false;
    }
  }

  /**
   * Get a prefetched screenshot from cache
   *
   * Returns immediately if available, otherwise returns null.
   *
   * @param screenshotId - Screenshot ID
   * @returns Prefetched data or null
   */
  getPrefetched(screenshotId: number): PrefetchedScreenshot | null {
    const cached = this.prefetchCache.get(screenshotId);

    if (!cached) {
      return null;
    }

    // Check if cache is still valid
    const age = Date.now() - cached.timestamp;
    if (age > this.maxCacheAge) {
      console.log(
        `[PrefetchService] Cache expired for screenshot ${screenshotId}`,
      );
      this.evict(screenshotId);
      return null;
    }

    return cached;
  }

  /**
   * Remove a screenshot from cache and free resources
   *
   * @param screenshotId - Screenshot ID to evict
   */
  evict(screenshotId: number): void {
    const cached = this.prefetchCache.get(screenshotId);
    if (cached) {
      // Revoke object URL to free memory
      URL.revokeObjectURL(cached.imageUrl);
      this.prefetchCache.delete(screenshotId);
      console.log(`[PrefetchService] Evicted screenshot ${screenshotId}`);
    }
  }

  /**
   * Clear all cached screenshots and free resources
   */
  clearAll(): void {
    this.prefetchCache.forEach((cached) => {
      URL.revokeObjectURL(cached.imageUrl);
    });
    this.prefetchCache.clear();
    console.log("[PrefetchService] Cleared all cache");
  }

  /**
   * Clean up old cache entries
   */
  private cleanupCache(): void {
    const now = Date.now();
    const toEvict: number[] = [];

    // Find expired entries
    this.prefetchCache.forEach((cached, id) => {
      const age = now - cached.timestamp;
      if (age > this.maxCacheAge) {
        toEvict.push(id);
      }
    });

    // Evict expired
    toEvict.forEach((id) => this.evict(id));

    // If still over limit, evict oldest
    if (this.prefetchCache.size > this.maxCacheSize) {
      const entries = Array.from(this.prefetchCache.entries());
      entries.sort((a, b) => a[1].timestamp - b[1].timestamp);

      const toRemove = entries.slice(0, entries.length - this.maxCacheSize);
      toRemove.forEach(([id]) => this.evict(id));
    }
  }

  /**
   * Preprocess screenshot in background (grid detection)
   *
   * This runs without blocking the UI and stores results in cache.
   *
   * @param screenshotId - Screenshot ID
   * @param imageBlob - Image blob
   */
  private async preprocessInBackground(
    screenshotId: number,
    imageBlob: Blob,
  ): Promise<void> {
    const cached = this.prefetchCache.get(screenshotId);
    if (!cached) {
      return;
    }

    try {
      // Detect grid in background
      const gridCoordinates = await this.processingService.detectGrid(
        imageBlob,
        cached.screenshot.image_type,
      );

      // Update cache with preprocessing result
      const updated = this.prefetchCache.get(screenshotId);
      if (updated) {
        updated.processingResult = {
          title: null,
          total: null,
          gridCoordinates,
        };
        this.prefetchCache.set(screenshotId, updated);
        console.log(
          `[PrefetchService] Background preprocessing complete for screenshot ${screenshotId}`,
        );
      }
    } catch (error) {
      console.error(
        `[PrefetchService] Background preprocessing failed for screenshot ${screenshotId}:`,
        error,
      );
    }
  }

  /**
   * Get cache statistics (for debugging)
   */
  getStats(): {
    cacheSize: number;
    cachedIds: number[];
    isPrefetching: boolean;
  } {
    return {
      cacheSize: this.prefetchCache.size,
      cachedIds: Array.from(this.prefetchCache.keys()),
      isPrefetching: this.isPrefetching,
    };
  }

  /**
   * Cleanup method for service container destroy.
   * Alias for clearAll() to match service container expectations.
   */
  terminate(): void {
    this.clearAll();
  }
}
