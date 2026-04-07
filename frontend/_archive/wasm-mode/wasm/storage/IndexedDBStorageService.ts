import type {
  Screenshot,
  Annotation,
  ScreenshotListResponse,
  NavigationResponse,
} from "../../../models";
import type {
  IStorageService,
  PaginationParams,
  NavigationQueryParams,
} from "../../../interfaces";
import { db } from "./database";
import {
  storeImageBlob,
  retrieveImageBlob,
  deleteImageBlob,
} from "./blobStorage";

// Constants for WASM mode
const LOCAL_USER_ID = 1;

export class IndexedDBStorageService implements IStorageService {
  private persistenceRequested = false;

  constructor() {
    db.open().catch((error) => {
      console.error("Failed to open IndexedDB:", error);
    });

    // Request persistent storage to prevent browser from evicting data
    this.requestPersistentStorage();
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
    try {
      const id = await db.screenshots.add(screenshot);
      return id;
    } catch (error) {
      console.error("Failed to save screenshot:", error);
      throw error;
    }
  }

  async getScreenshot(id: number): Promise<Screenshot | null> {
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
    try {
      // Use compound index if both annotation_status and group_id are provided
      if (filter?.annotation_status && filter?.group_id) {
        return await db.screenshots
          .where("[group_id+annotation_status]")
          .equals([filter.group_id, filter.annotation_status])
          .toArray();
      }

      if (filter?.group_id) {
        return await db.screenshots
          .where("group_id")
          .equals(filter.group_id)
          .toArray();
      }

      if (filter?.annotation_status) {
        return await db.screenshots
          .where("annotation_status")
          .equals(filter.annotation_status)
          .toArray();
      }

      if (filter?.processing_status) {
        return await db.screenshots
          .where("processing_status")
          .equals(filter.processing_status)
          .toArray();
      }

      return await db.screenshots.toArray();
    } catch (error) {
      console.error("Failed to get all screenshots:", error);
      throw error;
    }
  }

  async updateScreenshot(id: number, data: Partial<Screenshot>): Promise<void> {
    try {
      const existing = await this.getScreenshot(id);

      if (!existing) {
        throw new Error(`Screenshot with ID ${id} not found`);
      }

      await db.screenshots.update(id, data);
    } catch (error) {
      console.error("Failed to update screenshot:", error);
      throw error;
    }
  }

  async deleteScreenshot(id: number): Promise<void> {
    try {
      await db.transaction(
        "rw",
        db.screenshots,
        db.annotations,
        db.imageBlobs,
        async () => {
          await db.screenshots.delete(id);

          await db.annotations.where("screenshot_id").equals(id).delete();

          await deleteImageBlob(id);
        },
      );
    } catch (error) {
      console.error("Failed to delete screenshot:", error);
      throw error;
    }
  }

  async saveAnnotation(annotation: Annotation): Promise<number> {
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
    try {
      await storeImageBlob(screenshotId, blob);
    } catch (error) {
      console.error("Failed to save image blob:", error);
      throw error;
    }
  }

  async getImageBlob(screenshotId: number): Promise<Blob | null> {
    try {
      return await retrieveImageBlob(screenshotId);
    } catch (error) {
      console.error("Failed to get image blob:", error);
      throw error;
    }
  }

  async clearAll(): Promise<void> {
    try {
      await db.transaction(
        "rw",
        db.screenshots,
        db.annotations,
        db.imageBlobs,
        db.processingQueue,
        async () => {
          await Promise.all([
            db.screenshots.clear(),
            db.annotations.clear(),
            db.imageBlobs.clear(),
            db.processingQueue.clear(),
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
      const [screenshotCount, annotationCount, blobCount, blobs] =
        await Promise.all([
          db.screenshots.count(),
          db.annotations.count(),
          db.imageBlobs.count(),
          db.imageBlobs.toArray(),
        ]);

      const totalSize = blobs.reduce(
        (sum, record) => sum + record.blob.size,
        0,
      );

      return {
        screenshotCount,
        annotationCount,
        blobCount,
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
            (s) => s.processing_status === "pending" || !s.has_blocking_issues,
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
      });

      return ids;
    } catch (error) {
      console.error("Failed to bulk save annotations:", error);
      throw error;
    }
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
        // Note: We'd need a compound index for this to be efficient
        // For now, use the most selective filter first
        collection = db.screenshots
          .where("group_id")
          .equals(params.group_id)
          .filter((s) => s.processing_status === params.processing_status);
      } else if (params.group_id) {
        collection = db.screenshots.where("group_id").equals(params.group_id);
      } else if (params.processing_status) {
        collection = db.screenshots
          .where("processing_status")
          .equals(params.processing_status);
      }

      // Apply additional filters that can't use indexes
      if (params.verified_by_me === true) {
        collection = collection.filter(
          (s): boolean =>
            !!(
              s.verified_by_user_ids &&
              s.verified_by_user_ids.includes(LOCAL_USER_ID)
            ),
        );
      } else if (params.verified_by_me === false) {
        collection = collection.filter(
          (s): boolean =>
            !s.verified_by_user_ids ||
            !s.verified_by_user_ids.includes(LOCAL_USER_ID),
        );
      }

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

      if (params.group_id) {
        baseQuery = db.screenshots.where("group_id").equals(params.group_id);
      }

      // Apply filters
      if (params.processing_status) {
        baseQuery = baseQuery.filter(
          (s) => s.processing_status === params.processing_status,
        );
      }

      if (params.verified_by_me === true) {
        baseQuery = baseQuery.filter(
          (s): boolean =>
            !!(
              s.verified_by_user_ids &&
              s.verified_by_user_ids.includes(LOCAL_USER_ID)
            ),
        );
      } else if (params.verified_by_me === false) {
        baseQuery = baseQuery.filter(
          (s): boolean =>
            !s.verified_by_user_ids ||
            !s.verified_by_user_ids.includes(LOCAL_USER_ID),
        );
      }

      // Get total count
      const total = await baseQuery.count();

      if (total === 0) {
        return {
          screenshot: null,
          current_index: 0,
          total_in_filter: 0,
          has_next: false,
          has_prev: false,
        };
      }

      // For navigation, we need to find position and adjacent items
      // Use sorted IDs for consistent ordering
      const sortedIds = await baseQuery.primaryKeys();
      sortedIds.sort((a, b) => a - b);

      const currentIdx = sortedIds.indexOf(currentId);

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
        if (currentIdx >= 0) {
          targetId = sortedIds[currentIdx] ?? null;
          targetIdx = currentIdx;
        }
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
