import type {
  Screenshot,
  Annotation,
  ScreenshotListResponse,
  NavigationResponse,
} from "@/types";
import type {
  IStorageService,
  PaginationParams,
  NavigationQueryParams,
} from "@/core/interfaces";
import { db } from "./database";
import {
  storeImageBlob,
  retrieveImageBlob,
  deleteAllBlobsForScreenshot,
  clearAllOpfsBlobs,
  getTotalBlobSize,
  storeStageBlob,
  retrieveStageBlob,
} from "./opfsBlobStorage";

import type { Collection, IndexableType } from "dexie";
import { useAuthStore } from "@/store/authStore";

/** Get the current user's ID from the auth store, defaulting to 1 for WASM mode. */
function getCurrentUserId(): number {
  return useAuthStore.getState().userId ?? 1;
}

/** Apply verified_by_me / verified_by_others filters to a Dexie collection. */
function applyVerificationFilter<TKey extends IndexableType>(
  collection: Collection<Screenshot, TKey>,
  params: { verified_by_me?: boolean; verified_by_others?: boolean },
): Collection<Screenshot, TKey> {
  const userId = getCurrentUserId();
  if (params.verified_by_others === true) {
    return collection.filter(
      (s): boolean =>
        !!(
          s.verified_by_user_ids &&
          s.verified_by_user_ids.length > 0 &&
          !s.verified_by_user_ids.includes(userId)
        ),
    );
  }
  if (params.verified_by_me === true) {
    return collection.filter(
      (s): boolean =>
        !!(s.verified_by_user_ids && s.verified_by_user_ids.includes(userId)),
    );
  }
  if (params.verified_by_me === false) {
    return collection.filter(
      (s): boolean =>
        !s.verified_by_user_ids || !s.verified_by_user_ids.includes(userId),
    );
  }
  return collection;
}

export class IndexedDBStorageService implements IStorageService {
  private persistenceRequested = false;
  private dbReady: Promise<void>;
  private dbOpenFailed = false;

  constructor() {
    this.dbReady = this.initializeDb();
    this.requestPersistentStorage();
  }

  private async initializeDb(): Promise<void> {
    try {
      await this.maybeBackupBeforeMigration();
      await db.open();
    } catch (error) {
      this.dbOpenFailed = true;
      console.error("Failed to open IndexedDB:", error);
      throw new Error(
        `IndexedDB unavailable: ${error instanceof Error ? error.message : String(error)}. ` +
          "Local storage mode requires IndexedDB. Check that you are not in private browsing mode.",
      );
    }
  }

  private async maybeBackupBeforeMigration(): Promise<void> {
    let currentVersion: number;
    try {
      currentVersion = await new Promise<number>((resolve, reject) => {
        let resolved = false;
        const req = indexedDB.open("ScreenshotProcessorDB");
        req.onupgradeneeded = () => {
          // DB doesn't exist yet — abort to avoid creating it, resolve as 0
          req.transaction?.abort();
          resolved = true;
          resolve(0);
        };
        req.onsuccess = () => {
          if (!resolved) {
            resolve(req.result.version);
            req.result.close();
          }
        };
        req.onerror = () => {
          // onerror fires after onupgradeneeded abort — ignore if already resolved
          if (!resolved) reject(req.error);
        };
      });
    } catch (err) {
      console.error("[Migration] Failed to probe DB version:", err);
      return;
    }

    const targetVersion = db.verno;
    if (currentVersion > 0 && currentVersion < targetVersion) {
      try {
        const { createPreMigrationBackup } = await import(
          "./database/preMigrationBackup"
        );
        await createPreMigrationBackup("ScreenshotProcessorDB");
      } catch (err) {
        console.warn("[Migration] Pre-migration backup failed (continuing):", err);
      }
    }
  }

  /** Ensure the database is open before performing operations. */
  private async ensureDB(): Promise<void> {
    if (this.dbOpenFailed) {
      throw new Error(
        "IndexedDB is not available. Local storage mode cannot function without it.",
      );
    }
    await this.dbReady;
  }

  /**
   * Request persistent storage to prevent browser from automatically
   * evicting IndexedDB data under storage pressure.
   */
  private async requestPersistentStorage(): Promise<void> {
    if (this.persistenceRequested) return;
    this.persistenceRequested = true;

    try {
      if (navigator.storage && navigator.storage.persist) {
        const isPersisted = await navigator.storage.persisted();
        if (isPersisted) {
          console.log(
            "[IndexedDBStorageService] Storage is already persistent",
          );
          return;
        }

        const granted = await navigator.storage.persist();
        if (granted) {
          console.log("[IndexedDBStorageService] Persistent storage granted");
        } else {
          console.warn(
            "[IndexedDBStorageService] Persistent storage denied - data may be evicted under storage pressure",
          );
        }
      } else {
        console.warn(
          "[IndexedDBStorageService] Storage persistence API not available",
        );
      }
    } catch (error) {
      console.error(
        "[IndexedDBStorageService] Failed to request persistent storage:",
        error,
      );
    }
  }

  async saveScreenshot(screenshot: Screenshot): Promise<number> {
    await this.ensureDB();
    try {
      const id = await db.screenshots.add(screenshot);
      return id;
    } catch (error) {
      console.error("Failed to save screenshot:", error);
      throw error;
    }
  }

  async getScreenshot(id: number): Promise<Screenshot | null> {
    await this.ensureDB();
    try {
      const screenshot = await db.screenshots.get(id);
      return screenshot || null;
    } catch (error) {
      console.error("Failed to get screenshot:", error);
      throw error;
    }
  }

  async getAllScreenshots(filter?: {
    annotation_status?: string;
    group_id?: string;
    processing_status?: string;
  }): Promise<Screenshot[]> {
    await this.ensureDB();
    try {
      // Start with the most selective indexed filter, then apply remaining as .filter()
      let collection;

      if (filter?.annotation_status && filter?.group_id) {
        collection = db.screenshots
          .where("[group_id+annotation_status]")
          .equals([filter.group_id, filter.annotation_status]);
      } else if (filter?.group_id) {
        collection = db.screenshots
          .where("group_id")
          .equals(filter.group_id);
      } else if (filter?.annotation_status) {
        collection = db.screenshots
          .where("annotation_status")
          .equals(filter.annotation_status);
      } else if (filter?.processing_status) {
        // Only use processing_status index when no other filters
        return await db.screenshots
          .where("processing_status")
          .equals(filter.processing_status)
          .toArray();
      } else {
        return await db.screenshots.toArray();
      }

      // Apply processing_status as a post-filter if it wasn't used as the primary index
      if (filter?.processing_status) {
        collection = collection.filter(
          (s) => s.processing_status === filter.processing_status,
        );
      }

      return await collection.toArray();
    } catch (error) {
      console.error("Failed to get all screenshots:", error);
      throw error;
    }
  }

  async updateScreenshot(id: number, data: Partial<Screenshot>): Promise<void> {
    await this.ensureDB();
    try {
      const updated = await db.screenshots.update(id, data);
      if (updated === 0) {
        throw new Error(`Screenshot with ID ${id} not found`);
      }
    } catch (error) {
      console.error("Failed to update screenshot:", error);
      throw error;
    }
  }

  async deleteScreenshot(id: number): Promise<void> {
    await this.ensureDB();
    try {
      // Delete IndexedDB records atomically, then clean up OPFS blobs separately
      // (OPFS is outside IndexedDB transaction scope)
      await db.transaction(
        "rw",
        db.screenshots,
        db.annotations,
        db.imageBlobs,
        async () => {
          await db.screenshots.delete(id);
          await db.annotations.where("screenshot_id").equals(id).delete();
          await db.imageBlobs.delete(id);
        },
      );
      // Delete OPFS blobs (main + stage) outside transaction — best-effort cleanup
      await deleteAllBlobsForScreenshot(id);
    } catch (error) {
      console.error("Failed to delete screenshot:", error);
      throw error;
    }
  }

  async saveAnnotation(annotation: Annotation): Promise<number> {
    await this.ensureDB();
    try {
      const id = await db.transaction(
        "rw",
        db.annotations,
        db.screenshots,
        async () => {
          // Check for existing annotation for this screenshot by this user
          // In WASM mode, we use a simple approach: one annotation per screenshot
          const existing = await db.annotations
            .where("screenshot_id")
            .equals(annotation.screenshot_id)
            .first();

          let annotationId: number;

          if (existing) {
            // UPDATE existing annotation (upsert)
            await db.annotations.update(existing.id!, {
              ...annotation,
              id: existing.id,
              updated_at: new Date().toISOString(),
            });
            annotationId = existing.id!;
          } else {
            // CREATE new annotation
            annotationId = await db.annotations.add({
              ...annotation,
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            });

            // Only increment count for NEW annotations
            const screenshot = await db.screenshots.get(
              annotation.screenshot_id,
            );

            if (screenshot) {
              const currentCount = screenshot.current_annotation_count || 0;

              await db.screenshots.update(annotation.screenshot_id, {
                current_annotation_count: currentCount + 1,
              });
            }
          }

          return annotationId;
        },
      );

      return id;
    } catch (error) {
      console.error("Failed to save annotation:", error);
      throw error;
    }
  }

  async getAnnotation(id: number): Promise<Annotation | null> {
    await this.ensureDB();
    try {
      const annotation = await db.annotations.get(id);
      return annotation || null;
    } catch (error) {
      console.error("Failed to get annotation:", error);
      throw error;
    }
  }

  async getAnnotationsByScreenshot(
    screenshotId: number,
  ): Promise<Annotation[]> {
    await this.ensureDB();
    try {
      return await db.annotations
        .where("screenshot_id")
        .equals(screenshotId)
        .toArray();
    } catch (error) {
      console.error("Failed to get annotations by screenshot:", error);
      throw error;
    }
  }

  async deleteAnnotation(id: number): Promise<void> {
    await this.ensureDB();
    try {
      await db.transaction("rw", db.annotations, db.screenshots, async () => {
        const annotation = await db.annotations.get(id);

        if (annotation) {
          const screenshot = await db.screenshots.get(annotation.screenshot_id);

          if (screenshot) {
            const currentCount = screenshot.current_annotation_count || 0;

            await db.screenshots.update(annotation.screenshot_id, {
              current_annotation_count: Math.max(0, currentCount - 1),
            });
          }
        }

        await db.annotations.delete(id);
      });
    } catch (error) {
      console.error("Failed to delete annotation:", error);
      throw error;
    }
  }

  async saveImageBlob(screenshotId: number, blob: Blob): Promise<void> {
    await this.ensureDB();
    try {
      await storeImageBlob(screenshotId, blob);
    } catch (error) {
      console.error("Failed to save image blob:", error);
      throw error;
    }
  }

  async getImageBlob(screenshotId: number): Promise<Blob | null> {
    await this.ensureDB();
    try {
      return await retrieveImageBlob(screenshotId);
    } catch (error) {
      console.error("Failed to get image blob:", error);
      throw error;
    }
  }

  async saveStageBlob(screenshotId: number, stage: string, blob: Blob): Promise<void> {
    await this.ensureDB();
    try {
      await storeStageBlob(screenshotId, stage, blob);
    } catch (error) {
      console.error(`Failed to save stage blob for ${stage}:`, error);
      throw error;
    }
  }

  async getStageBlob(screenshotId: number, stage: string): Promise<Blob | null> {
    await this.ensureDB();
    try {
      return await retrieveStageBlob(screenshotId, stage);
    } catch (error) {
      console.error(`Failed to get stage blob for ${stage}:`, error);
      throw error;
    }
  }

  async deleteScreenshotsByGroup(groupId: string): Promise<{ screenshots_deleted: number; annotations_deleted: number }> {
    await this.ensureDB();
    try {
      const screenshots = await db.screenshots
        .where("group_id")
        .equals(groupId)
        .toArray();

      const screenshotIds = screenshots.map((s) => s.id!);
      if (screenshotIds.length === 0) {
        return { screenshots_deleted: 0, annotations_deleted: 0 };
      }

      // Delete records atomically, capturing annotation count from delete() return values
      let annotationsDeleted = 0;
      await db.transaction(
        "rw",
        db.screenshots,
        db.annotations,
        db.imageBlobs,
        async () => {
          await db.screenshots.bulkDelete(screenshotIds);
          for (const id of screenshotIds) {
            annotationsDeleted += await db.annotations.where("screenshot_id").equals(id).delete();
            await db.imageBlobs.delete(id);
          }
        },
      );

      // Delete OPFS blobs (main + stage) outside transaction — best-effort cleanup
      await Promise.allSettled(screenshotIds.map((id) => deleteAllBlobsForScreenshot(id)));

      return { screenshots_deleted: screenshotIds.length, annotations_deleted: annotationsDeleted };
    } catch (error) {
      console.error("Failed to delete screenshots by group:", error);
      throw error;
    }
  }

  async clearAll(): Promise<void> {
    try {
      // Clear OPFS blobs first (outside transaction since OPFS is not part of IndexedDB)
      await clearAllOpfsBlobs();

      await db.transaction(
        "rw",
        [db.screenshots, db.annotations, db.imageBlobs, db.processingQueue, db.syncRecords, db.settings],
        async () => {
          await Promise.all([
            db.screenshots.clear(),
            db.annotations.clear(),
            db.imageBlobs.clear(),
            db.processingQueue.clear(),
            db.syncRecords.clear(),
            db.settings.clear(),
          ]);
        },
      );
    } catch (error) {
      console.error("Failed to clear all data:", error);
      throw error;
    }
  }

  async getStats(): Promise<{
    screenshotCount: number;
    annotationCount: number;
    blobCount: number;
    totalSize: number;
  }> {
    try {
      // Use screenshot count as blob count proxy (each screenshot has one blob)
      // and use getTotalBlobSize() which checks OPFS first, falling back to IndexedDB
      const [screenshotCount, annotationCount, totalSize] =
        await Promise.all([
          db.screenshots.count(),
          db.annotations.count(),
          getTotalBlobSize(),
        ]);

      return {
        screenshotCount,
        annotationCount,
        blobCount: screenshotCount,
        totalSize,
      };
    } catch (error) {
      console.error("Failed to get stats:", error);
      throw error;
    }
  }

  async getNextPendingScreenshot(): Promise<Screenshot | null> {
    try {
      return (
        (await db.screenshots
          .where("annotation_status")
          .equals("pending")
          .and(
            (s) => s.processing_status !== "failed" && !s.has_blocking_issues,
          )
          .first()) || null
      );
    } catch (error) {
      console.error("Failed to get next pending screenshot:", error);
      throw error;
    }
  }

  async bulkSaveScreenshots(screenshots: Screenshot[]): Promise<number[]> {
    try {
      const ids: number[] = [];

      await db.transaction("rw", db.screenshots, async () => {
        for (const screenshot of screenshots) {
          const id = await db.screenshots.add(screenshot);
          ids.push(id);
        }
      });

      return ids;
    } catch (error) {
      console.error("Failed to bulk save screenshots:", error);
      throw error;
    }
  }

  async bulkSaveAnnotations(annotations: Annotation[]): Promise<number[]> {
    try {
      const ids: number[] = [];

      await db.transaction("rw", db.annotations, db.screenshots, async () => {
        for (const annotation of annotations) {
          // Upsert: check for existing annotation for this screenshot (same as saveAnnotation)
          const existing = await db.annotations
            .where("screenshot_id")
            .equals(annotation.screenshot_id)
            .first();

          if (existing) {
            await db.annotations.update(existing.id!, {
              ...annotation,
              id: existing.id,
              updated_at: new Date().toISOString(),
            });
            ids.push(existing.id!);
          } else {
            const id = await db.annotations.add(annotation);
            ids.push(id);

            const screenshot = await db.screenshots.get(annotation.screenshot_id);
            if (screenshot) {
              const currentCount = screenshot.current_annotation_count || 0;
              await db.screenshots.update(annotation.screenshot_id, {
                current_annotation_count: currentCount + 1,
              });
            }
          }
        }
      });

      return ids;
    } catch (error) {
      console.error("Failed to bulk save annotations:", error);
      throw error;
    }
  }

  async getStorageEstimate(): Promise<{ usage: number; quota: number; percentUsed: number } | null> {
    if (!navigator.storage?.estimate) return null;
    const { usage, quota } = await navigator.storage.estimate();
    return {
      usage: usage ?? 0,
      quota: quota ?? 0,
      percentUsed: quota ? ((usage ?? 0) / quota) * 100 : 0,
    };
  }

  /**
   * Efficient paginated query using IndexedDB indexes.
   * Only loads the requested page instead of all screenshots.
   */
  async getScreenshotsPaginated(
    params: PaginationParams,
  ): Promise<ScreenshotListResponse> {
    try {
      const page = params.page || 1;
      const pageSize = params.page_size || 50;
      const offset = (page - 1) * pageSize;

      // Build query based on available indexes
      let collection = db.screenshots.toCollection();

      // Use compound index if both group_id and processing_status provided
      if (params.group_id && params.processing_status) {
        collection = db.screenshots
          .where("[group_id+processing_status]")
          .equals([params.group_id, params.processing_status]);
      } else if (params.group_id) {
        collection = db.screenshots.where("group_id").equals(params.group_id);
      } else if (params.processing_status) {
        collection = db.screenshots
          .where("processing_status")
          .equals(params.processing_status);
      }

      // Apply verification filters
      collection = applyVerificationFilter(collection, params);

      if (params.search) {
        const searchLower = params.search.toLowerCase();
        collection = collection.filter(
          (s): boolean =>
            s.id.toString().includes(searchLower) ||
            !!(
              s.participant_id &&
              s.participant_id.toLowerCase().includes(searchLower)
            ) ||
            !!(
              s.extracted_title &&
              s.extracted_title.toLowerCase().includes(searchLower)
            ),
        );
      }

      // Get total count first (this still needs full scan for complex filters)
      const total = await collection.count();

      // Apply sorting
      const sortBy = params.sort_by || "id";
      const sortOrder = params.sort_order || "asc";

      // For simple ID sorting, use indexed access
      if (sortBy === "id") {
        if (sortOrder === "desc") {
          collection = collection.reverse();
        }
      } else {
        // For other fields, we need to sort in memory (less efficient)
        // But we still only load what we need
        const allForSort = await collection.toArray();
        allForSort.sort((a, b) => {
          let aVal: unknown = a[sortBy as keyof Screenshot];
          let bVal: unknown = b[sortBy as keyof Screenshot];
          if (typeof aVal === "string") aVal = aVal.toLowerCase();
          if (typeof bVal === "string") bVal = bVal.toLowerCase();
          if (aVal === null || aVal === undefined) return 1;
          if (bVal === null || bVal === undefined) return -1;
          if (aVal < bVal) return sortOrder === "asc" ? -1 : 1;
          if (aVal > bVal) return sortOrder === "asc" ? 1 : -1;
          return 0;
        });

        const items = allForSort.slice(offset, offset + pageSize);
        return {
          items,
          total,
          page,
          page_size: pageSize,
          pages: Math.ceil(total / pageSize),
          has_next: offset + items.length < total,
          has_prev: page > 1,
        };
      }

      // Use offset and limit for efficient pagination
      const items = await collection.offset(offset).limit(pageSize).toArray();

      return {
        items,
        total,
        page,
        page_size: pageSize,
        pages: Math.ceil(total / pageSize),
        has_next: offset + items.length < total,
        has_prev: page > 1,
      };
    } catch (error) {
      console.error("Failed to get paginated screenshots:", error);
      throw error;
    }
  }

  /**
   * Efficient cursor-based navigation.
   * Only fetches the target screenshot and counts, not the entire list.
   */
  async navigateScreenshots(
    currentId: number,
    params: NavigationQueryParams,
  ): Promise<NavigationResponse> {
    try {
      // Build base query
      let baseQuery = db.screenshots.toCollection();
      let hasJsFilter = false;

      if (params.group_id && params.processing_status) {
        // Use compound index when both filters are present
        baseQuery = db.screenshots
          .where("[group_id+processing_status]")
          .equals([params.group_id, params.processing_status]);
      } else if (params.group_id) {
        baseQuery = db.screenshots.where("group_id").equals(params.group_id);
      } else if (params.processing_status) {
        // Use processing_status index directly when no group_id
        baseQuery = db.screenshots.where("processing_status").equals(params.processing_status);
      }

      if (params.verified_by_me !== undefined || params.verified_by_others !== undefined) {
        hasJsFilter = true;
      }
      baseQuery = applyVerificationFilter(baseQuery, params);

      // primaryKeys() may not respect JS .filter() predicates — use each() to collect IDs when filters are present
      let sortedIds: number[];
      if (hasJsFilter) {
        const ids: number[] = [];
        await baseQuery.each((s) => { ids.push(s.id); });
        sortedIds = ids.sort((a, b) => a - b);
      } else {
        sortedIds = await baseQuery.primaryKeys();
        sortedIds.sort((a, b) => a - b);
      }
      const total = sortedIds.length;

      if (total === 0) {
        return {
          screenshot: null,
          current_index: 0,
          total_in_filter: 0,
          has_next: false,
          has_prev: false,
        };
      }

      let currentIdx = sortedIds.indexOf(currentId);

      // If currentId is not in the filtered set (e.g., status changed), fall back to first item
      if (currentIdx === -1) {
        currentIdx = 0;
      }

      let targetId: number | null = null;
      let targetIdx = currentIdx;

      if (params.direction === "next") {
        targetIdx = currentIdx + 1;
        if (targetIdx < sortedIds.length) {
          targetId = sortedIds[targetIdx] ?? null;
        }
      } else if (params.direction === "prev") {
        targetIdx = currentIdx - 1;
        if (targetIdx >= 0) {
          targetId = sortedIds[targetIdx] ?? null;
        }
      } else {
        // current
        targetId = sortedIds[currentIdx] ?? null;
        targetIdx = currentIdx;
      }

      // Fetch only the target screenshot
      let targetScreenshot: Screenshot | null = null;
      if (targetId !== null) {
        targetScreenshot = (await db.screenshots.get(targetId)) || null;
      }

      return {
        screenshot: targetScreenshot,
        current_index: targetScreenshot ? targetIdx + 1 : 0,
        total_in_filter: total,
        has_next: targetIdx < sortedIds.length - 1,
        has_prev: targetIdx > 0,
      };
    } catch (error) {
      console.error("Failed to navigate screenshots:", error);
      throw error;
    }
  }
}
