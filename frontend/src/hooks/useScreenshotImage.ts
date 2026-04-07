import { useEffect, useState } from "react";
import { useScreenshotService } from "@/core/hooks/useServices";

/**
 * Hook to get the image URL for a screenshot, handling both server and WASM modes.
 * Pass a refreshKey that changes when the image needs to be re-fetched
 * (e.g., after crop or redaction modifies the underlying file).
 */
export function useScreenshotImage(screenshotId: number, refreshKey?: number): string | null {
  const screenshotService = useScreenshotService();
  const [imageUrl, setImageUrl] = useState<string | null>(null);

  useEffect(() => {
    // Don't try to load if screenshotId is 0 or invalid
    if (!screenshotId) {
      setImageUrl(null);
      return;
    }

    // Clear stale URL immediately so components don't render with a revoked
    // blob URL during the async gap (e.g., after crop/redaction calls
    // storeImageBlob which revokes the old URL synchronously).
    setImageUrl(null);

    let cancelled = false;

    const loadImage = async () => {
      try {
        let resolvedUrl = await screenshotService.getImageUrl(screenshotId);
        // Bust browser cache when image has been modified (crop/redaction)
        if (refreshKey && !resolvedUrl.startsWith("blob:")) {
          const separator = resolvedUrl.includes("?") ? "&" : "?";
          resolvedUrl = `${resolvedUrl}${separator}_t=${refreshKey}`;
        }
        if (!cancelled) {
          setImageUrl(resolvedUrl);
        }
        // Note: blob URLs are managed by the opfsBlobStorage LRU cache.
        // Do NOT revoke them here — the cache shares URLs across components
        // and revokes them automatically on eviction.
      } catch (error) {
        if (!cancelled) {
          console.error(
            `Failed to load image for screenshot ${screenshotId}:`,
            error,
          );
          setImageUrl(null);
        }
      }
    };

    loadImage();

    return () => {
      cancelled = true;
    };
  }, [screenshotId, screenshotService, refreshKey]);

  return imageUrl;
}
