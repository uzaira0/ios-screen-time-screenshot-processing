import type {
  Screenshot,
  GridCoordinates,
  ProcessingResult,
  QueueStats,
  ProcessingStatus,
  ScreenshotListResponse,
  ScreenshotListParams,
  NavigationResponse,
  NavigationParams,
} from "../../models";
import type { ImageType } from "@/types";
import type { IScreenshotService } from "../../interfaces";
import type { IStorageService } from "../../interfaces";
import type { IProcessingService, ProcessingProgress } from "../../interfaces";

export class WASMScreenshotService implements IScreenshotService {
  private storageService: IStorageService;
  private processingService: IProcessingService;

  constructor(
    storageService: IStorageService,
    processingService: IProcessingService,
  ) {
    this.storageService = storageService;
    this.processingService = processingService;
  }

  async getNext(
    groupId?: string,
    processingStatus?: string,
  ): Promise<Screenshot | null> {
    const filter: {
      annotation_status: string;
      group_id?: string;
      processing_status?: string;
    } = {
      annotation_status: "pending",
    };

    if (groupId) {
      filter.group_id = groupId;
    }

    if (processingStatus) {
      filter.processing_status = processingStatus;
    }

    const screenshots = await this.storageService.getAllScreenshots(filter);

    if (screenshots.length === 0) {
      return null;
    }

    return screenshots[0] || null;
  }

  async getById(id: number): Promise<Screenshot> {
    const screenshot = await this.storageService.getScreenshot(id);

    if (!screenshot) {
      throw new Error(`Screenshot with ID ${id} not found`);
    }

    return screenshot;
  }

  async getAll(status?: string, skip = 0, limit = 50): Promise<Screenshot[]> {
    const filter = status ? { annotation_status: status } : undefined;
    const allScreenshots = await this.storageService.getAllScreenshots(filter);

    // Ensure we always return an array, even if storage returns null/undefined
    const screenshots = Array.isArray(allScreenshots) ? allScreenshots : [];
    return screenshots.slice(skip, skip + limit);
  }

  async upload(file: File, imageType: ImageType): Promise<Screenshot> {
    const blob = new Blob([file], { type: file.type });
    const uploadedAt = new Date().toISOString();

    // Create screenshot record without ID (let IndexedDB auto-increment)
    // Omit id by using Partial and type assertion
    const screenshotData: Omit<Screenshot, "id"> & { id?: number } = {
      file_path: file.name,
      image_type: imageType,
      uploaded_at: uploadedAt,
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
      // API upload metadata
      participant_id: null,
      group_id: null,
      source_id: null,
      device_type: null,
      verified_by_user_ids: null,
      // Computed readonly properties (provided as null for WASM mode)
      processing_time_seconds: null,
      alignment_score_status: null,
    };

    // Save to IndexedDB - this will assign a unique auto-incremented ID
    const id = await this.storageService.saveScreenshot(
      screenshotData as Screenshot,
    );
    await this.storageService.saveImageBlob(id, blob);

    const screenshot: Screenshot = { ...screenshotData, id };

    // Auto-process in background (don't await to avoid blocking)
    this.autoProcess(screenshot).catch((error) => {
      console.error("Auto-processing failed:", error);
    });

    return screenshot;
  }

  async getImageUrl(screenshotId: number): Promise<string> {
    const imageBlob = await this.storageService.getImageBlob(screenshotId);

    if (!imageBlob) {
      throw new Error(`Image blob not found for screenshot ${screenshotId}`);
    }

    // Create a blob URL that can be used in img tags
    return URL.createObjectURL(imageBlob);
  }

  async getProcessingResult(screenshotId: number): Promise<ProcessingResult> {
    const screenshot = await this.getById(screenshotId);

    return {
      success: screenshot.processing_status === "completed",
      processing_status: screenshot.processing_status,
      skipped: screenshot.processing_status === "skipped",
      extracted_title: screenshot.extracted_title,
      extracted_total: screenshot.extracted_total,
      extracted_hourly_data: screenshot.extracted_hourly_data,
      issues: screenshot.processing_issues || [],
      has_blocking_issues: screenshot.has_blocking_issues,
      is_daily_total: false,
    };
  }

  async reprocess(
    screenshotId: number,
    coords: GridCoordinates,
    onProgress?: (progress: ProcessingProgress) => void,
    _maxShift?: number, // Ignored in WASM mode - optimization is server-side only
  ): Promise<ProcessingResult> {
    const screenshot = await this.getById(screenshotId);
    const imageBlob = await this.storageService.getImageBlob(screenshotId);

    if (!imageBlob) {
      throw new Error("Image blob not found for screenshot " + screenshotId);
    }

    // OPTIMIZATION: When grid is provided (user adjusting), only extract hourly data
    // Title and total don't change with grid position - skip expensive OCR calls
    // This reduces processing from ~4.8s to ~230ms
    if (onProgress) {
      onProgress({
        stage: "ocr_hourly",
        progress: 50,
        message: "Extracting hourly data...",
      });
    }

    const hourlyData = await this.processingService.extractHourlyData(
      imageBlob,
      coords,
      screenshot.image_type,
    );

    if (onProgress) {
      onProgress({
        stage: "complete",
        progress: 100,
        message: "Processing complete",
      });
    }

    const processingStatus: ProcessingStatus = hourlyData
      ? "completed"
      : "failed";

    // Keep existing title/total, only update grid and hourly data
    await this.storageService.updateScreenshot(screenshotId, {
      extracted_hourly_data: hourlyData,
      grid_upper_left_x: coords.upper_left.x,
      grid_upper_left_y: coords.upper_left.y,
      grid_lower_right_x: coords.lower_right.x,
      grid_lower_right_y: coords.lower_right.y,
      processing_status: processingStatus,
      processed_at: new Date().toISOString(),
    });

    return {
      success: processingStatus === "completed",
      processing_status: processingStatus,
      skipped: false,
      extracted_title: screenshot.extracted_title, // Preserve existing
      extracted_total: screenshot.extracted_total, // Preserve existing
      extracted_hourly_data: hourlyData,
      issues: [],
      has_blocking_issues: false,
      is_daily_total: false,
    };
  }

  async reprocessWithMethod(
    screenshotId: number,
    method: "ocr_anchored" | "line_based",
    _onProgress?: (progress: ProcessingProgress) => void,
    _maxShift?: number, // Ignored in WASM mode - optimization is server-side only
  ): Promise<ProcessingResult> {
    // WASM mode doesn't support line-based detection (requires server-side processing)
    if (method === "line_based") {
      return {
        success: false,
        processing_status: "failed",
        skipped: false,
        extracted_title: null,
        extracted_total: null,
        extracted_hourly_data: null,
        issues: [
          {
            issue_type: "UnsupportedMethod",
            severity: "blocking" as const,
            description:
              "Line-based detection is not available in offline mode. Please use server mode or select grid manually.",
          },
        ],
        has_blocking_issues: true,
        is_daily_total: false,
      };
    }

    // For ocr_anchored, just do a full reprocess without grid coords
    const screenshot = await this.getById(screenshotId);
    const imageBlob = await this.storageService.getImageBlob(screenshotId);

    if (!imageBlob) {
      throw new Error("Image blob not found for screenshot " + screenshotId);
    }

    const result = await this.processingService.processImage(imageBlob, {
      imageType: screenshot.image_type,
    });

    if (result) {
      // Check if grid detection specifically failed
      const gridFailed = result.gridDetectionFailed === true;
      const hasHourlyData = result.hourlyData && Object.keys(result.hourlyData).length > 0;
      const processingStatus = hasHourlyData ? "completed" : "failed";

      // Build issues list with proper typing
      const issues: Array<{ issue_type: string; description: string; severity: "blocking" | "non_blocking" }> = [];
      if (gridFailed) {
        issues.push({
          issue_type: "grid_detection_failed",
          description: result.gridDetectionError || "Could not automatically detect the graph grid. Please manually select the grid area.",
          severity: "blocking",
        });
      }

      await this.storageService.updateScreenshot(screenshotId, {
        extracted_title: result.title || null,
        extracted_total: result.total || null,
        extracted_hourly_data: result.hourlyData || null,
        grid_upper_left_x: result.gridCoordinates?.upper_left?.x || null,
        grid_upper_left_y: result.gridCoordinates?.upper_left?.y || null,
        grid_lower_right_x: result.gridCoordinates?.lower_right?.x || null,
        grid_lower_right_y: result.gridCoordinates?.lower_right?.y || null,
        processing_status: processingStatus,
        processed_at: new Date().toISOString(),
      });

      return {
        success: processingStatus === "completed" && !gridFailed,
        processing_status: processingStatus,
        skipped: false,
        extracted_title: result.title || null,
        extracted_total: result.total || null,
        extracted_hourly_data: result.hourlyData || null,
        issues: issues,
        has_blocking_issues: gridFailed,
        is_daily_total: false,
      };
    }

    return {
      success: false,
      processing_status: "failed",
      skipped: false,
      extracted_title: null,
      extracted_total: null,
      extracted_hourly_data: null,
      issues: [],
      has_blocking_issues: true,
      is_daily_total: false,
    };
  }

  async skip(screenshotId: number): Promise<void> {
    await this.storageService.updateScreenshot(screenshotId, {
      annotation_status: "skipped",
      processing_status: "skipped",
    });
  }

  async updateTitle(screenshotId: number, title: string): Promise<void> {
    await this.storageService.updateScreenshot(screenshotId, {
      extracted_title: title,
    });
  }

  async updateHourlyData(
    screenshotId: number,
    hourlyData: Record<string, number>,
  ): Promise<void> {
    await this.storageService.updateScreenshot(screenshotId, {
      extracted_hourly_data: hourlyData,
    });
  }

  async processIfNeeded(screenshot: Screenshot): Promise<Screenshot> {
    // IMPORTANT: Never reprocess verified screenshots - they are frozen
    const isVerified =
      screenshot.verified_by_user_ids &&
      screenshot.verified_by_user_ids.length > 0;

    if (isVerified) {
      console.log(
        `[WASMScreenshotService.processIfNeeded] Screenshot ${screenshot.id} is verified, skipping processing`,
      );
      return screenshot;
    }

    // If already has title and total (for screen_time) or hourly data, no need to process
    const needsProcessing =
      screenshot.image_type === "screen_time"
        ? !screenshot.extracted_title || !screenshot.extracted_total
        : !screenshot.extracted_hourly_data;

    console.log(
      `[WASMScreenshotService.processIfNeeded] Screenshot ${screenshot.id}: type=${screenshot.image_type}, title=${screenshot.extracted_title}, total=${screenshot.extracted_total}, needsProcessing=${needsProcessing}`,
    );

    if (!needsProcessing) {
      console.log(
        `[WASMScreenshotService.processIfNeeded] Screenshot ${screenshot.id} already processed, skipping`,
      );
      return screenshot;
    }

    console.log(
      `[WASMScreenshotService.processIfNeeded] Processing screenshot ${screenshot.id}`,
    );

    try {
      const imageBlob = await this.storageService.getImageBlob(screenshot.id);

      if (!imageBlob) {
        console.warn(
          `[WASMScreenshotService.processIfNeeded] No image blob for screenshot ${screenshot.id}`,
        );
        return screenshot;
      }

      // Determine grid coordinates to use (priority: locked > existing > auto-detect)
      let gridCoordsToUse = undefined;
      
      // Priority 1: Check if there's a locked grid saved in localStorage
      const lockEnabled = localStorage.getItem("gridLockEnabled") === "true";
      if (lockEnabled) {
        const savedGrid = localStorage.getItem("lastGridPosition");
        if (savedGrid) {
          try {
            gridCoordsToUse = JSON.parse(savedGrid);
            console.log(
              `[WASMScreenshotService.processIfNeeded] Using locked grid from localStorage:`,
              gridCoordsToUse,
            );
          } catch (e) {
            console.warn(
              `[WASMScreenshotService.processIfNeeded] Failed to parse saved grid position`,
            );
          }
        }
      }
      
      // Priority 2: Use existing screenshot grid coordinates if available
      if (
        !gridCoordsToUse &&
        screenshot.grid_upper_left_x != null &&
        screenshot.grid_lower_right_x != null
      ) {
        gridCoordsToUse = {
          upper_left: {
            x: screenshot.grid_upper_left_x,
            y: screenshot.grid_upper_left_y ?? 0,
          },
          lower_right: {
            x: screenshot.grid_lower_right_x,
            y: screenshot.grid_lower_right_y ?? 0,
          },
        };
        console.log(
          `[WASMScreenshotService.processIfNeeded] Using existing grid from screenshot:`,
          gridCoordsToUse,
        );
      }

      // Use full processImage to get title, total, grid, and hourly data
      const result = await this.processingService.processImage(imageBlob, {
        imageType: screenshot.image_type,
        gridCoordinates: gridCoordsToUse,
      });

      if (result) {
        const processingStatus = result.hourlyData ? "completed" : "failed";

        const updates: Partial<Screenshot> = {
          extracted_title: result.title || screenshot.extracted_title || null,
          extracted_total: result.total || screenshot.extracted_total || null,
          extracted_hourly_data:
            result.hourlyData || screenshot.extracted_hourly_data || null,
          grid_upper_left_x:
            result.gridCoordinates?.upper_left?.x ??
            screenshot.grid_upper_left_x,
          grid_upper_left_y:
            result.gridCoordinates?.upper_left?.y ??
            screenshot.grid_upper_left_y,
          grid_lower_right_x:
            result.gridCoordinates?.lower_right?.x ??
            screenshot.grid_lower_right_x,
          grid_lower_right_y:
            result.gridCoordinates?.lower_right?.y ??
            screenshot.grid_lower_right_y,
          processing_status: processingStatus,
          processed_at: new Date().toISOString(),
        };

        await this.storageService.updateScreenshot(screenshot.id, updates);

        // Return updated screenshot
        return { ...screenshot, ...updates };
      }
    } catch (error) {
      console.error(
        `[WASMScreenshotService.processIfNeeded] Failed for screenshot ${screenshot.id}:`,
        error,
      );
    }

    return screenshot;
  }

  async getStats(): Promise<QueueStats> {
    const allScreenshots = await this.storageService.getAllScreenshots();

    const totalScreenshots = allScreenshots.length;
    const pendingScreenshots = allScreenshots.filter(
      (s) => s.annotation_status === "pending",
    ).length;
    const completedScreenshots = allScreenshots.filter(
      (s) =>
        s.annotation_status === "annotated" ||
        s.annotation_status === "verified",
    ).length;
    const skipped = allScreenshots.filter(
      (s) => s.annotation_status === "skipped",
    ).length;

    // Count all annotations across all screenshots
    let totalAnnotations = 0;
    for (const screenshot of allScreenshots) {
      const annotations = await this.storageService.getAnnotationsByScreenshot(
        screenshot.id,
      );
      totalAnnotations += annotations.length;
    }

    const averageAnnotations =
      totalScreenshots > 0 ? totalAnnotations / totalScreenshots : 0;

    return {
      total_screenshots: totalScreenshots,
      pending_screenshots: pendingScreenshots,
      completed_screenshots: completedScreenshots,
      total_annotations: totalAnnotations,
      screenshots_with_consensus: 0,
      screenshots_with_disagreements: 0,
      average_annotations_per_screenshot:
        Math.round(averageAnnotations * 100) / 100,
      users_active: 1,
      auto_processed: allScreenshots.filter(
        (s) => s.processing_status === "completed",
      ).length,
      pending: allScreenshots.filter((s) => s.processing_status === "pending")
        .length,
      failed: allScreenshots.filter((s) => s.processing_status === "failed")
        .length,
      skipped,
      deleted: allScreenshots.filter((s) => s.processing_status === "deleted")
        .length,
    };
  }

  private async autoProcess(screenshot: Screenshot): Promise<void> {
    try {
      const imageBlob = await this.storageService.getImageBlob(screenshot.id);

      if (!imageBlob) {
        return;
      }

      // Use full processImage to get title, total, grid, and hourly data
      const result = await this.processingService.processImage(imageBlob, {
        imageType: screenshot.image_type,
      });

      if (result) {
        const processingStatus = result.hourlyData ? "completed" : "failed";

        await this.storageService.updateScreenshot(screenshot.id, {
          extracted_title: result.title || null,
          extracted_total: result.total || null,
          extracted_hourly_data: result.hourlyData || null,
          grid_upper_left_x: result.gridCoordinates?.upper_left?.x || null,
          grid_upper_left_y: result.gridCoordinates?.upper_left?.y || null,
          grid_lower_right_x: result.gridCoordinates?.lower_right?.x || null,
          grid_lower_right_y: result.gridCoordinates?.lower_right?.y || null,
          processing_status: processingStatus,
          processed_at: new Date().toISOString(),
        });
      }
    } catch (error) {
      console.error("Auto-processing failed:", error);
      await this.storageService.updateScreenshot(screenshot.id, {
        processing_status: "failed",
      });
    }
  }

  async getList(params: ScreenshotListParams): Promise<ScreenshotListResponse> {
    // Use optimized query that only fetches the page we need
    const page = params.page || 1;
    const pageSize = params.page_size || 50;
    const sortBy = params.sort_by || "id";
    const sortOrder = params.sort_order || "asc";

    // Build the query using Dexie's efficient indexed queries
    const result = await this.storageService.getScreenshotsPaginated({
      group_id: params.group_id,
      processing_status: params.processing_status,
      verified_by_me: params.verified_by_me,
      search: params.search,
      sort_by: sortBy,
      sort_order: sortOrder,
      page,
      page_size: pageSize,
    });

    return result;
  }

  async navigate(
    screenshotId: number,
    params: NavigationParams,
  ): Promise<NavigationResponse> {
    // Use optimized navigation that doesn't load all screenshots
    const result = await this.storageService.navigateScreenshots(screenshotId, {
      group_id: params.group_id,
      processing_status: params.processing_status,
      verified_by_me: params.verified_by_me,
      direction: params.direction,
    });

    return result;
  }

  async verify(
    screenshotId: number,
    gridCoords?: GridCoordinates,
  ): Promise<Screenshot> {
    const screenshot = await this.getById(screenshotId);
    const verifiedIds = screenshot.verified_by_user_ids || [];

    const updates: Partial<Screenshot> = {};

    // Use local user ID = 1 for WASM mode
    if (!verifiedIds.includes(1)) {
      verifiedIds.push(1);
      updates.verified_by_user_ids = verifiedIds;
    }

    // Save grid coordinates if provided (freeze grid at verification time)
    if (gridCoords) {
      updates.grid_upper_left_x = gridCoords.upper_left.x;
      updates.grid_upper_left_y = gridCoords.upper_left.y;
      updates.grid_lower_right_x = gridCoords.lower_right.x;
      updates.grid_lower_right_y = gridCoords.lower_right.y;
    }

    if (Object.keys(updates).length > 0) {
      await this.storageService.updateScreenshot(screenshotId, updates);
    }

    return {
      ...screenshot,
      ...updates,
      verified_by_user_ids: verifiedIds,
    };
  }

  async unverify(screenshotId: number): Promise<Screenshot> {
    const screenshot = await this.getById(screenshotId);
    let verifiedIds = screenshot.verified_by_user_ids || [];

    // Use local user ID = 1 for WASM mode
    verifiedIds = verifiedIds.filter((id) => id !== 1);
    await this.storageService.updateScreenshot(screenshotId, {
      verified_by_user_ids: verifiedIds.length > 0 ? verifiedIds : null,
    });

    return {
      ...screenshot,
      verified_by_user_ids: verifiedIds.length > 0 ? verifiedIds : null,
    };
  }

  async recalculateOcr(screenshotId: number): Promise<string | null> {
    const imageBlob = await this.storageService.getImageBlob(screenshotId);

    if (!imageBlob) {
      console.warn(
        `[WASMScreenshotService.recalculateOcr] No image blob for screenshot ${screenshotId}`,
      );
      return null;
    }

    try {
      // Use processing service to extract total
      const total = await this.processingService.extractTotal(imageBlob);

      if (total) {
        await this.storageService.updateScreenshot(screenshotId, {
          extracted_total: total,
        });
        return total;
      }
    } catch (error) {
      console.error(
        `[WASMScreenshotService.recalculateOcr] Failed for screenshot ${screenshotId}:`,
        error,
      );
    }

    return null;
  }

}
