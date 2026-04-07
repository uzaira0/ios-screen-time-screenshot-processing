import Dexie, { type Table } from "dexie";
import type { Screenshot, Annotation, Group } from "../../../../models";

export interface ImageBlob {
  screenshotId: number;
  blob: Blob;
  uploadedAt: string;
}

export interface Settings {
  id?: number;
  key: string;
  value: string | number | boolean | object | null;
  updatedAt: string;
}

export interface QueueItem {
  id?: number;
  screenshotId: number;
  priority: number;
  status: "pending" | "processing" | "completed" | "failed";
  createdAt: string;
  processedAt?: string;
}

export class ScreenshotDB extends Dexie {
  screenshots!: Table<Screenshot, number>;
  annotations!: Table<Annotation, number>;
  imageBlobs!: Table<ImageBlob, number>;
  settings!: Table<Settings, number>;
  processingQueue!: Table<QueueItem, number>;
  groups!: Table<Group, string>;

  constructor() {
    super("ScreenshotProcessorDB");

    this.version(1).stores({
      screenshots:
        "++id, status, image_type, uploaded_at, processing_status, has_blocking_issues",
      annotations: "++id, screenshot_id, created_at, status",
      imageBlobs: "screenshotId, uploadedAt",
      settings: "++id, &key",
      processingQueue: "++id, screenshotId, priority, status, createdAt",
    });

    this.version(2).stores({
      screenshots:
        "++id, status, image_type, uploaded_at, processing_status, has_blocking_issues, [status+processing_status]",
      annotations:
        "++id, screenshot_id, annotator_id, created_at, status, [screenshot_id+status]",
    });

    // Add group_id, participant_id indexes and groups table
    this.version(3).stores({
      screenshots:
        "++id, status, image_type, uploaded_at, processing_status, has_blocking_issues, [status+processing_status], group_id, participant_id, [group_id+status]",
      annotations:
        "++id, screenshot_id, annotator_id, created_at, status, [screenshot_id+status]",
      groups: "&id, name, created_at",
    });

    // Version 4: Add compound indexes for efficient pagination and filtering
    this.version(4).stores({
      screenshots:
        "++id, status, image_type, uploaded_at, processing_status, has_blocking_issues, " +
        "[status+processing_status], group_id, participant_id, [group_id+status], " +
        // New indexes for pagination efficiency
        "[group_id+processing_status], " + // Filter by group and processing status
        "[processing_status+id], " + // Sorted pagination by processing status
        "[group_id+id]", // Sorted pagination by group
      annotations:
        "++id, screenshot_id, annotator_id, created_at, status, [screenshot_id+status]",
      groups: "&id, name, created_at",
    });

    // Version 5: Rename status to annotation_status for clarity
    this.version(5)
      .stores({
        screenshots:
          "++id, annotation_status, image_type, uploaded_at, processing_status, has_blocking_issues, " +
          "[annotation_status+processing_status], group_id, participant_id, [group_id+annotation_status], " +
          "[group_id+processing_status], " +
          "[processing_status+id], " +
          "[group_id+id]",
        annotations:
          "++id, screenshot_id, annotator_id, created_at, status, [screenshot_id+status]",
        groups: "&id, name, created_at",
      })
      .upgrade((tx) => {
        // Migrate existing data: rename status to annotation_status
        return tx
          .table("screenshots")
          .toCollection()
          .modify((screenshot: Screenshot & { status?: string }) => {
            if (screenshot.status && !screenshot.annotation_status) {
              // Map old status values to new annotation_status values
              const statusMap: Record<string, string> = {
                pending: "pending",
                completed: "annotated",
                skipped: "skipped",
                in_progress: "pending",
              };
              screenshot.annotation_status =
                (statusMap[
                  screenshot.status
                ] as Screenshot["annotation_status"]) || "pending";
              delete screenshot.status;
            }
          });
      });
  }
}

export const db = new ScreenshotDB();
