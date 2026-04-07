import { db } from "./database";
import type {
  Screenshot,
  Group,
  ScreenshotUploadRequest,
  ScreenshotUploadResponse,
} from "../../../models";

/**
 * Service to handle API uploads for WASM mode.
 * Processes incoming screenshot uploads and stores them in IndexedDB.
 */
export class UploadAPIService {
  /**
   * Process an upload request from the API.
   */
  async processUpload(
    request: ScreenshotUploadRequest,
  ): Promise<ScreenshotUploadResponse> {
    // Validate required fields
    if (!request.screenshot) {
      throw new Error("screenshot (base64) is required");
    }
    if (!request.participant_id) {
      throw new Error("participant_id is required");
    }
    if (!request.group_id) {
      throw new Error("group_id is required");
    }
    if (
      !request.image_type ||
      !["battery", "screen_time"].includes(request.image_type)
    ) {
      throw new Error('image_type must be "battery" or "screen_time"');
    }

    // Check if group exists, create if not
    const groupCreated = await this.ensureGroupExists(
      request.group_id,
      request.image_type,
    );

    // Convert base64 to Blob
    const blob = this.base64ToBlob(request.screenshot);

    // Detect device type from image dimensions if not provided
    let deviceType = request.device_type || null;
    if (!deviceType) {
      deviceType = await this.detectDeviceType(blob);
    }

    // Create screenshot record
    const now = new Date().toISOString();
    const screenshot: Omit<Screenshot, "id"> = {
      file_path: request.filename || `upload_${Date.now()}.png`,
      image_type: request.image_type,
      uploaded_at: now,
      uploaded_by_id: null,
      current_annotation_count: 0,
      target_annotations: 1,
      has_consensus: null,
      annotation_status: "pending",
      processed_at: null,
      processing_status: "pending",
      extracted_title: null,
      extracted_total: null,
      extracted_hourly_data: null,
      title_y_position: null,
      grid_upper_left_x: null,
      grid_upper_left_y: null,
      grid_lower_right_x: null,
      grid_lower_right_y: null,
      processing_issues: null,
      has_blocking_issues: false,
      alignment_score: null,
      // API metadata
      participant_id: request.participant_id,
      group_id: request.group_id,
      source_id: request.source_id || null,
      device_type: deviceType,
      // Verification tracking
      verified_by_user_ids: null,
      // Computed readonly properties (provided as null for WASM mode)
      processing_time_seconds: null,
      alignment_score_status: null,
    };

    // Store screenshot and image blob in transaction
    const screenshotId = await db.transaction(
      "rw",
      [db.screenshots, db.imageBlobs],
      async () => {
        const id = await db.screenshots.add(screenshot as Screenshot);
        await db.imageBlobs.add({
          screenshotId: id,
          blob,
          uploadedAt: now,
        });
        return id;
      },
    );

    // Update group counts
    await this.updateGroupCounts(request.group_id);

    return {
      success: true,
      screenshot_id: screenshotId,
      group_created: groupCreated,
      duplicate: false,
      processing_queued: false,
      preprocessing_queued: false,
    };
  }

  /**
   * Ensure a group exists, creating it if necessary.
   * Returns true if the group was created.
   */
  private async ensureGroupExists(
    groupId: string,
    imageType: "battery" | "screen_time" = "screen_time",
  ): Promise<boolean> {
    const existing = await db.groups.get(groupId);
    if (existing) {
      return false;
    }

    const group: Group = {
      id: groupId,
      name: groupId, // Use ID as name by default
      image_type: imageType,
      created_at: new Date().toISOString(),
      screenshot_count: 0,
      processing_pending: 0,
      processing_completed: 0,
      processing_failed: 0,
      processing_skipped: 0,
      processing_deleted: 0,
    };

    await db.groups.add(group);
    return true;
  }

  /**
   * Update group screenshot counts.
   */
  async updateGroupCounts(groupId: string): Promise<void> {
    const screenshots = await db.screenshots
      .where("group_id")
      .equals(groupId)
      .toArray();

    const counts = {
      screenshot_count: screenshots.length,
      processing_pending: screenshots.filter(
        (s) => s.processing_status === "pending",
      ).length,
      processing_completed: screenshots.filter(
        (s) => s.processing_status === "completed",
      ).length,
      processing_failed: screenshots.filter(
        (s) => s.processing_status === "failed",
      ).length,
      processing_skipped: screenshots.filter(
        (s) => s.processing_status === "skipped",
      ).length,
    };

    await db.groups.update(groupId, counts);
  }

  /**
   * Convert base64 string to Blob.
   */
  private base64ToBlob(base64: string): Blob {
    // Remove data URL prefix if present
    const base64Data = base64.replace(/^data:image\/\w+;base64,/, "");

    const byteCharacters = atob(base64Data);
    const byteNumbers = new Array(byteCharacters.length);

    for (let i = 0; i < byteCharacters.length; i++) {
      byteNumbers[i] = byteCharacters.charCodeAt(i);
    }

    const byteArray = new Uint8Array(byteNumbers);
    return new Blob([byteArray], { type: "image/png" });
  }

  /**
   * Detect device type from image dimensions.
   */
  private async detectDeviceType(blob: Blob): Promise<string | null> {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        const { width, height } = img;
        URL.revokeObjectURL(img.src);

        // Common iPhone resolutions (portrait)
        const iphoneResolutions = [
          { w: 1170, h: 2532 }, // iPhone 12/13/14
          { w: 1179, h: 2556 }, // iPhone 14 Pro
          { w: 1284, h: 2778 }, // iPhone 12/13/14 Pro Max
          { w: 1290, h: 2796 }, // iPhone 14 Pro Max
          { w: 1125, h: 2436 }, // iPhone X/XS/11 Pro
          { w: 1242, h: 2688 }, // iPhone XS Max/11 Pro Max
          { w: 750, h: 1334 }, // iPhone 6/7/8
          { w: 1080, h: 1920 }, // iPhone 6/7/8 Plus
        ];

        // Common iPad resolutions
        const ipadResolutions = [
          { w: 2048, h: 2732 }, // iPad Pro 12.9"
          { w: 1668, h: 2388 }, // iPad Pro 11"
          { w: 1620, h: 2160 }, // iPad 10.2"
          { w: 1536, h: 2048 }, // iPad Air/Mini
        ];

        // Check dimensions (consider both orientations)
        const dims = [
          { w: width, h: height },
          { w: height, h: width },
        ];

        for (const dim of dims) {
          if (iphoneResolutions.some((r) => r.w === dim.w && r.h === dim.h)) {
            resolve("iphone");
            return;
          }
          if (ipadResolutions.some((r) => r.w === dim.w && r.h === dim.h)) {
            resolve("ipad");
            return;
          }
        }

        // Fallback: guess based on aspect ratio
        const aspectRatio = Math.max(width, height) / Math.min(width, height);
        if (aspectRatio > 1.8) {
          resolve("iphone");
        } else if (aspectRatio < 1.5) {
          resolve("ipad");
        } else {
          resolve(null);
        }
      };

      img.onerror = () => {
        resolve(null);
      };

      img.src = URL.createObjectURL(blob);
    });
  }

  /**
   * Get all groups with counts.
   */
  async getGroups(): Promise<Group[]> {
    return db.groups.orderBy("created_at").reverse().toArray();
  }

  /**
   * Get screenshots for a specific group.
   */
  async getScreenshotsByGroup(groupId: string): Promise<Screenshot[]> {
    return db.screenshots.where("group_id").equals(groupId).toArray();
  }
}

// Singleton instance
export const uploadAPIService = new UploadAPIService();
