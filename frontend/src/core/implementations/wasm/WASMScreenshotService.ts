import type {
  Screenshot,
  Group,
  GridCoordinates,
  ProcessingResult,
  QueueStats,
  ProcessingStatus,
  ScreenshotListResponse,
  ScreenshotListParams,
  NavigationResponse,
  NavigationParams,
} from "@/types";
import type { ImageType } from "@/types";
import type { IScreenshotService } from "@/core/interfaces";
import type { IStorageService } from "@/core/interfaces";
import { extractGridCoords } from "@/store/slices/helpers";
import type { IProcessingService, ProcessingProgress } from "@/core/interfaces";
import { db } from "./storage/database";
import { createObjectURL } from "./storage/opfsBlobStorage";
import { computeContentHash } from "./utils/contentHash";
import { useAuthStore } from "@/store/authStore";
import { DuplicateScreenshotError } from "@/core/errors";

export class WASMScreenshotService implements IScreenshotService {
  private storageService: IStorageService;
  private processingService: IProcessingService;
  private processingInProgress = new Set<number>();
  // Guards against concurrent uploads of the same content hash
  private uploadingHashes = new Set<string>();

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

  async addScreenshots(
    file: File,
    imageType: ImageType,
    options?: {
      groupId?: string;
      participantId?: string;
      screenshotDate?: string;
      originalFilepath?: string;
    },
  ): Promise<Screenshot> {
    // File extends Blob — no need to copy
    const uploadedAt = new Date().toISOString();

    // Content-hash dedup: compute SHA-256 and check for existing screenshot
    // Returns null in non-secure contexts where crypto.subtle is unavailable
    const contentHash = await computeContentHash(file);
    if (contentHash !== null) {
      // Check-and-add atomically (synchronous) to guard against concurrent batch uploads.
      // Must happen before the IndexedDB await to prevent the TOCTOU race.
      if (this.uploadingHashes.has(contentHash)) {
        throw new DuplicateScreenshotError(0);
      }
      this.uploadingHashes.add(contentHash);

      const existing = await db.screenshots
        .where("content_hash")
        .equals(contentHash)
        .first();
      if (existing) {
        this.uploadingHashes.delete(contentHash);
        throw new DuplicateScreenshotError(existing.id!);
      }
    }

    try {
      // Create screenshot record without ID (let IndexedDB auto-increment)
      // Omit id by using Partial and type assertion
      const screenshotData: Omit<Screenshot, "id"> & { id?: number; content_hash?: string | null } = {
        file_path: options?.originalFilepath || file.name,
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
        // Folder structure metadata
        participant_id: options?.participantId ?? null,
        group_id: options?.groupId ?? null,
        screenshot_date: options?.screenshotDate ?? null,
        source_id: null,
        device_type: null,
        verified_by_user_ids: null,
        // Computed readonly properties (provided as null for WASM mode)
        processing_time_seconds: null,
        alignment_score_status: null,
        // Content hash for dedup (null when crypto.subtle unavailable)
        content_hash: contentHash ?? null,
      };

      // Save to IndexedDB - this will assign a unique auto-incremented ID
      const id = await this.storageService.saveScreenshot(
        screenshotData as Screenshot,
      );
      try {
        await this.storageService.saveImageBlob(id, file);
      } catch (blobErr) {
        // Roll back metadata to prevent orphaned records with no image blob
        await this.storageService.deleteScreenshot(id).catch(() => { /* best-effort rollback cleanup */ });
        throw blobErr;
      }

      const screenshot: Screenshot = { ...screenshotData, id };

      // Auto-process if enabled in settings (fire-and-forget)
      try {
        const { autoProcessOnUpload } = await import("@/store/settingsStore").then(m => m.useSettingsStore.getState());
        if (autoProcessOnUpload) {
          this.processIfNeeded(screenshot).catch((err) =>
            console.warn("[WASMScreenshotService] Auto-process failed:", err)
          );
        }
      } catch {
        // Settings store not available — skip auto-process
      }

      return screenshot;
    } finally {
      if (contentHash) {
        this.uploadingHashes.delete(contentHash);
      }
    }
  }

  async getImageUrl(screenshotId: number): Promise<string> {
    const imageBlob = await this.storageService.getImageBlob(screenshotId);

    if (!imageBlob) {
      throw new Error(`Image blob not found for screenshot ${screenshotId}`);
    }

    // Use LRU-cached blob URLs to avoid leaking memory
    const url = await createObjectURL(screenshotId, imageBlob);
    if (!url) {
      throw new Error(`Failed to create object URL for screenshot ${screenshotId}`);
    }
    return url;
  }

  async getProcessingResult(screenshotId: number): Promise<ProcessingResult> {
    const screenshot = await this.getById(screenshotId);

    return {
      success: screenshot.processing_status === "completed",
      processing_status: screenshot.processing_status,
      skipped: screenshot.processing_status === "skipped",
      extracted_title: screenshot.extracted_title ?? null,
      extracted_total: screenshot.extracted_total ?? null,
      extracted_hourly_data: screenshot.extracted_hourly_data ?? null,
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
      extracted_title: screenshot.extracted_title ?? null, // Preserve existing
      extracted_total: screenshot.extracted_total ?? null, // Preserve existing
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
    maxShift?: number,
  ): Promise<ProcessingResult> {
    const screenshot = await this.getById(screenshotId);
    const imageBlob = await this.storageService.getImageBlob(screenshotId);

    if (!imageBlob) {
      throw new Error("Image blob not found for screenshot " + screenshotId);
    }

    // Detect grid with the requested method, then fall back to the other if it fails
    let gridCoordinates: GridCoordinates | undefined;
    const fallbackMethod = method === "line_based" ? "ocr_anchored" : "line_based";
    const detected = await this.processingService.detectGrid(imageBlob, screenshot.image_type, method);
    if (detected) {
      gridCoordinates = detected;
    } else {
      const fallback = await this.processingService.detectGrid(imageBlob, screenshot.image_type, fallbackMethod);
      if (fallback) {
        gridCoordinates = fallback;
      }
    }

    const processConfig: { imageType: typeof screenshot.image_type; gridCoordinates?: GridCoordinates; maxShift?: number } = {
      imageType: screenshot.image_type,
    };
    if (gridCoordinates) {
      processConfig.gridCoordinates = gridCoordinates;
    }
    if (maxShift && maxShift > 0) {
      processConfig.maxShift = maxShift;
    }

    const result = await this.processingService.processImage(imageBlob, processConfig);

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
        grid_upper_left_x: result.gridCoordinates?.upper_left?.x ?? null,
        grid_upper_left_y: result.gridCoordinates?.upper_left?.y ?? null,
        grid_lower_right_x: result.gridCoordinates?.lower_right?.x ?? null,
        grid_lower_right_y: result.gridCoordinates?.lower_right?.y ?? null,
        alignment_score: result.alignmentScore ?? null,
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
        alignment_score: result.alignmentScore ?? null,
        processing_method: method,
        grid_detection_confidence: null,
        grid_upper_left_x: result.gridCoordinates?.upper_left?.x ?? null,
        grid_upper_left_y: result.gridCoordinates?.upper_left?.y ?? null,
        grid_lower_right_x: result.gridCoordinates?.lower_right?.x ?? null,
        grid_lower_right_y: result.gridCoordinates?.lower_right?.y ?? null,
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

  async skip(screenshotId: number, reason?: string): Promise<void> {
    const update: Record<string, unknown> = {
      annotation_status: "skipped",
      processing_status: "skipped",
    };
    if (reason) {
      const screenshot = await this.getById(screenshotId);
      const meta = (screenshot.processing_metadata ?? {}) as Record<string, unknown>;
      update.processing_metadata = { ...meta, skip_reason: reason };
    }
    await this.storageService.updateScreenshot(screenshotId, update);
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
    // Skip if already being processed
    if (this.processingInProgress.has(screenshot.id)) {
      console.log(
        `[WASMScreenshotService.processIfNeeded] Screenshot ${screenshot.id} already being processed, returning as-is`,
      );
      return screenshot;
    }

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

    // Skip re-processing if we already have hourly data (the expensive part).
    // Title/total may be null if OCR missed them — that's OK, the user can see the data.
    const needsProcessing = !screenshot.extracted_hourly_data;

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

    this.processingInProgress.add(screenshot.id);
    try {
      const imageBlob = await this.storageService.getImageBlob(screenshot.id);

      if (!imageBlob) {
        console.warn(
          `[WASMScreenshotService.processIfNeeded] No image blob for screenshot ${screenshot.id}, marking as failed`,
        );
        await this.storageService.updateScreenshot(screenshot.id, {
          processing_status: "failed",
          processed_at: new Date().toISOString(),
        });
        return { ...screenshot, processing_status: "failed" };
      }

      // Determine grid coordinates to use (priority: locked > existing > auto-detect)
      let gridCoordsToUse = undefined;
      
      // Priority 1: Check if there's a locked grid saved in localStorage
      const lockEnabled = localStorage.getItem("gridLockEnabled") === "true";
      if (lockEnabled) {
        const savedGrid = localStorage.getItem("lastGridPosition");
        if (savedGrid) {
          try {
            const parsed = JSON.parse(savedGrid);
            // Validate shape before using — malformed JSON would crash the worker
            if (
              parsed?.upper_left?.x !== undefined &&
              parsed?.upper_left?.y !== undefined &&
              parsed?.lower_right?.x !== undefined &&
              parsed?.lower_right?.y !== undefined
            ) {
              gridCoordsToUse = parsed;
              console.log(
                `[WASMScreenshotService.processIfNeeded] Using locked grid from localStorage:`,
                gridCoordsToUse,
              );
            } else {
              console.warn(
                `[WASMScreenshotService.processIfNeeded] Invalid grid shape in localStorage, ignoring:`,
                parsed,
              );
            }
          } catch (e) {
            console.warn(
              `[WASMScreenshotService.processIfNeeded] Failed to parse saved grid position, clearing corrupted data:`,
              savedGrid, e,
            );
            localStorage.removeItem("lastGridPosition");
          }
        }
      }
      
      // Priority 2: Use existing screenshot grid coordinates if available
      if (!gridCoordsToUse) {
        gridCoordsToUse = extractGridCoords(screenshot);
        if (gridCoordsToUse) {
          console.log(
            `[WASMScreenshotService.processIfNeeded] Using existing grid from screenshot:`,
            gridCoordsToUse,
          );
        }
      }

      // Priority 3: Detect grid with both methods before calling processImage
      // This prevents the worker from throwing "Failed to detect grid automatically"
      if (!gridCoordsToUse) {
        console.log(
          `[WASMScreenshotService.processIfNeeded] No grid coords, trying line_based then ocr_anchored detection`,
        );
        gridCoordsToUse = await this.processingService.detectGrid(imageBlob, screenshot.image_type, "line_based")
          ?? await this.processingService.detectGrid(imageBlob, screenshot.image_type, "ocr_anchored")
          ?? undefined;
        if (gridCoordsToUse) {
          console.log(
            `[WASMScreenshotService.processIfNeeded] Detected grid:`,
            gridCoordsToUse,
          );
        } else {
          console.warn(
            `[WASMScreenshotService.processIfNeeded] Grid detection failed for screenshot ${screenshot.id}`,
          );
        }
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
            screenshot.grid_upper_left_x ?? null,
          grid_upper_left_y:
            result.gridCoordinates?.upper_left?.y ??
            screenshot.grid_upper_left_y ?? null,
          grid_lower_right_x:
            result.gridCoordinates?.lower_right?.x ??
            screenshot.grid_lower_right_x ?? null,
          grid_lower_right_y:
            result.gridCoordinates?.lower_right?.y ??
            screenshot.grid_lower_right_y ?? null,
          alignment_score: result.alignmentScore ?? null,
          processing_status: processingStatus,
          processed_at: new Date().toISOString(),
        };

        await this.storageService.updateScreenshot(screenshot.id, updates);

        // Return updated screenshot
        return { ...screenshot, ...updates };
      }

      // processImage returned null — mark as failed to prevent infinite reprocess loop
      await this.storageService.updateScreenshot(screenshot.id, {
        processing_status: "failed",
        processed_at: new Date().toISOString(),
      });
      return { ...screenshot, processing_status: "failed" };
    } catch (error) {
      console.error(
        `[WASMScreenshotService.processIfNeeded] Failed for screenshot ${screenshot.id}:`,
        error,
      );
      try {
        await this.storageService.updateScreenshot(screenshot.id, {
          processing_status: "failed",
        });
        return { ...screenshot, processing_status: "failed" };
      } catch (updateError) {
        console.error(
          `[WASMScreenshotService.processIfNeeded] Failed to update status:`,
          updateError,
        );
        return { ...screenshot, processing_status: "failed" };
      }
    } finally {
      this.processingInProgress.delete(screenshot.id);
    }
  }

  async getStats(): Promise<QueueStats> {
    // Use indexed counts instead of loading entire table into memory
    const [
      totalScreenshots,
      pendingAnnotation,
      annotatedAnnotation,
      verifiedAnnotation,
      processingCompleted,
      processingPending,
      processingFailed,
      processingSkipped,
      processingDeleted,
      totalAnnotations,
    ] = await Promise.all([
      db.screenshots.count(),
      db.screenshots.where("annotation_status").equals("pending").count(),
      db.screenshots.where("annotation_status").equals("annotated").count(),
      db.screenshots.where("annotation_status").equals("verified").count(),
      db.screenshots.where("processing_status").equals("completed").count(),
      db.screenshots.where("processing_status").equals("pending").count(),
      db.screenshots.where("processing_status").equals("failed").count(),
      db.screenshots.where("processing_status").equals("skipped").count(),
      db.screenshots.where("processing_status").equals("deleted").count(),
      db.annotations.count(),
    ]);

    const completedScreenshots = annotatedAnnotation + verifiedAnnotation;
    const averageAnnotations =
      totalScreenshots > 0 ? totalAnnotations / totalScreenshots : 0;

    return {
      total_screenshots: totalScreenshots,
      pending_screenshots: pendingAnnotation,
      completed_screenshots: completedScreenshots,
      total_annotations: totalAnnotations,
      screenshots_with_consensus: 0,
      screenshots_with_disagreements: 0,
      average_annotations_per_screenshot:
        Math.round(averageAnnotations * 100) / 100,
      users_active: 1,
      auto_processed: processingCompleted,
      pending: processingPending,
      failed: processingFailed,
      skipped: processingSkipped,
      deleted: processingDeleted,
    };
  }

  async getList(params: ScreenshotListParams): Promise<ScreenshotListResponse> {
    // Use optimized query that only fetches the page we need
    const page = params.page || 1;
    const pageSize = params.page_size || 50;
    const sortBy = params.sort_by || "id";
    const sortOrder = params.sort_order || "asc";

    // Build the query using Dexie's efficient indexed queries
    const result = await this.storageService.getScreenshotsPaginated({
      ...(params.group_id != null && { group_id: params.group_id }),
      ...(params.processing_status != null && { processing_status: params.processing_status }),
      ...(params.verified_by_me != null && { verified_by_me: params.verified_by_me }),
      ...(params.verified_by_others != null && { verified_by_others: params.verified_by_others }),
      ...(params.search != null && { search: params.search }),
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
      ...(params.group_id != null && { group_id: params.group_id }),
      ...(params.processing_status != null && { processing_status: params.processing_status }),
      ...(params.verified_by_me != null && { verified_by_me: params.verified_by_me }),
      ...(params.verified_by_others != null && { verified_by_others: params.verified_by_others }),
      ...(params.direction != null && { direction: params.direction }),
    });

    return result;
  }

  async verify(
    screenshotId: number,
    gridCoords?: GridCoordinates,
  ): Promise<Screenshot> {
    const screenshot = await this.getById(screenshotId);
    const verifiedIds = screenshot.verified_by_user_ids || [];
    const verifiedUsernames = screenshot.verified_by_usernames || [];

    const updates: Partial<Screenshot> = {};

    // Use local user ID and username for WASM mode
    const userId = useAuthStore.getState().userId ?? 1;
    const username = useAuthStore.getState().username ?? "local";

    if (!verifiedIds.includes(userId)) {
      verifiedIds.push(userId);
      updates.verified_by_user_ids = verifiedIds;
    }
    if (!verifiedUsernames.includes(username)) {
      verifiedUsernames.push(username);
      updates.verified_by_usernames = verifiedUsernames;
    }

    // Mark as verified
    updates.annotation_status = "verified";

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
      verified_by_usernames: verifiedUsernames,
    };
  }

  async unverify(screenshotId: number): Promise<Screenshot> {
    const screenshot = await this.getById(screenshotId);
    const userId = useAuthStore.getState().userId ?? 1;
    const username = useAuthStore.getState().username ?? "local";

    let verifiedIds = screenshot.verified_by_user_ids || [];
    let verifiedUsernames = screenshot.verified_by_usernames || [];

    verifiedIds = verifiedIds.filter((id) => id !== userId);
    verifiedUsernames = verifiedUsernames.filter((u) => u !== username);

    const hasVerifiers = verifiedIds.length > 0;
    await this.storageService.updateScreenshot(screenshotId, {
      verified_by_user_ids: hasVerifiers ? verifiedIds : null,
      verified_by_usernames: hasVerifiers ? verifiedUsernames : null,
      // Revert to "annotated" if no verifiers remain
      annotation_status: hasVerifiers ? "verified" : "annotated",
    });

    return {
      ...screenshot,
      verified_by_user_ids: hasVerifiers ? verifiedIds : null,
      verified_by_usernames: hasVerifiers ? verifiedUsernames : null,
      annotation_status: hasVerifiers ? "verified" : "annotated",
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

  async getGroups(): Promise<Group[]> {
    // Use cursor-based iteration to avoid loading all screenshots into memory at once
    const groupMap = new Map<
      string,
      {
        count: number;
        image_type: string;
        created_at: string;
        processing_pending: number;
        processing_completed: number;
        processing_failed: number;
        processing_skipped: number;
        processing_deleted: number;
      }
    >();

    await db.screenshots.each((s) => {
      const gid = s.group_id || "ungrouped";
      const existing = groupMap.get(gid) || {
        count: 0,
        image_type: s.image_type || "screen_time",
        created_at: s.uploaded_at || new Date().toISOString(),
        processing_pending: 0,
        processing_completed: 0,
        processing_failed: 0,
        processing_skipped: 0,
        processing_deleted: 0,
      };

      existing.count++;
      const ps = s.processing_status || "pending";
      if (ps === "pending" || ps === "processing")
        existing.processing_pending++;
      else if (ps === "completed") existing.processing_completed++;
      else if (ps === "failed") existing.processing_failed++;
      else if (ps === "skipped") existing.processing_skipped++;
      else if (ps === "deleted") existing.processing_deleted++;

      if (s.uploaded_at && s.uploaded_at < existing.created_at) {
        existing.created_at = s.uploaded_at;
      }

      groupMap.set(gid, existing);
    });

    return Array.from(groupMap.entries()).map(([id, data]) => ({
      id,
      name: id === "ungrouped" ? "Ungrouped" : id,
      image_type: data.image_type as "battery" | "screen_time",
      created_at: data.created_at,
      screenshot_count: data.count,
      processing_pending: data.processing_pending,
      processing_completed: data.processing_completed,
      processing_failed: data.processing_failed,
      processing_skipped: data.processing_skipped,
      processing_deleted: data.processing_deleted,
      totals_mismatch_count: 0,
    }));
  }

  async deleteGroup(groupId: string): Promise<{ screenshots_deleted: number; annotations_deleted: number }> {
    return this.storageService.deleteScreenshotsByGroup(groupId);
  }

  async updateGridCoords(screenshotId: number, coords: GridCoordinates | null): Promise<void> {
    if (coords) {
      await this.storageService.updateScreenshot(screenshotId, {
        grid_upper_left_x: coords.upper_left.x,
        grid_upper_left_y: coords.upper_left.y,
        grid_lower_right_x: coords.lower_right.x,
        grid_lower_right_y: coords.lower_right.y,
      });
    } else {
      await this.storageService.updateScreenshot(screenshotId, {
        grid_upper_left_x: null,
        grid_upper_left_y: null,
        grid_lower_right_x: null,
        grid_lower_right_y: null,
      });
    }
  }

  async exportCSV(): Promise<string> {
    const allScreenshots = await db.screenshots.toArray();

    // Import column headers from generated constants (single source of truth: shared/export_columns.json)
    const { EXPORT_CSV_HEADERS } = await import("@/core/generated/constants");
    const headers = EXPORT_CSV_HEADERS;

    const rows = allScreenshots.map((s) => {
      const hourlyData = (s as Record<string, unknown>).extracted_hourly_data as Record<string, number> | null;
      const hourlyValues: string[] = Array(24).fill("");
      let totalMinutes = 0;
      if (hourlyData) {
        for (const [key, val] of Object.entries(hourlyData)) {
          const idx = parseInt(key, 10);
          if (idx >= 0 && idx < 24 && val != null) {
            hourlyValues[idx] = String(val);
            totalMinutes += Number(val) || 0;
          }
        }
      }
      const hours = Math.floor(totalMinutes / 60);
      const mins = Math.round(totalMinutes % 60);
      const computedTotal = totalMinutes > 0 ? (hours > 0 ? `${hours}h ${mins}m` : `${mins}m`) : "";
      const verifiedIds = ((s as Record<string, unknown>).verified_by_user_ids as number[] | null) || [];

      return [
        s.id ?? "",
        (s.file_path ?? "").split("/").pop() || "",
        (s as Record<string, unknown>).original_filepath ?? "",
        s.group_id ?? "",
        s.participant_id ?? "",
        (s as Record<string, unknown>).image_type ?? "screen_time",
        (s as Record<string, unknown>).screenshot_date ?? "",
        (s as Record<string, unknown>).uploaded_at ?? "",
        (s as Record<string, unknown>).processing_status ?? "",
        verifiedIds.length > 0 ? "Yes" : "No",
        verifiedIds.length,
        (s as Record<string, unknown>).current_annotation_count ?? 0,
        (s as Record<string, unknown>).has_consensus ? "Yes" : "No",
        s.extracted_title ?? "",
        s.extracted_total ?? "",
        computedTotal,
        0, // Disagreement count not available in WASM mode
        ...hourlyValues,
      ];
    });

    // CSV escaping: handle commas, quotes, AND newlines
    const escapeCell = (v: unknown): string => {
      const s = String(v ?? "");
      return s.includes(",") || s.includes('"') || s.includes("\n")
        ? `"${s.replace(/"/g, '""')}"`
        : s;
    };

    // UTF-8 BOM for Excel compatibility
    const csvLines = [
      "\ufeff" + headers.map(escapeCell).join(","),
      ...rows.map((r) => r.map(escapeCell).join(",")),
    ];

    return csvLines.join("\n");
  }
}
