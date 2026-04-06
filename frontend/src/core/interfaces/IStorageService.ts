import type {
  Screenshot,
  Annotation,
  ScreenshotListResponse,
  NavigationResponse,
} from "@/types";

export interface PaginationParams {
  group_id?: string;
  processing_status?: string;
  verified_by_me?: boolean;
  verified_by_others?: boolean;
  search?: string;
  sort_by?: string;
  sort_order?: "asc" | "desc";
  page?: number;
  page_size?: number;
}

export interface NavigationQueryParams {
  group_id?: string;
  processing_status?: string;
  verified_by_me?: boolean;
  verified_by_others?: boolean;
  direction?: "prev" | "next" | "current";
}

export interface IStorageService {
  saveScreenshot(screenshot: Screenshot): Promise<number>;

  getScreenshot(id: number): Promise<Screenshot | null>;

  getAllScreenshots(filter?: {
    annotation_status?: string;
    group_id?: string;
    processing_status?: string;
  }): Promise<Screenshot[]>;

  updateScreenshot(id: number, data: Partial<Screenshot>): Promise<void>;

  deleteScreenshot(id: number): Promise<void>;

  saveAnnotation(annotation: Annotation): Promise<number>;

  getAnnotation(id: number): Promise<Annotation | null>;

  getAnnotationsByScreenshot(screenshotId: number): Promise<Annotation[]>;

  deleteAnnotation(id: number): Promise<void>;

  saveImageBlob(screenshotId: number, blob: Blob): Promise<void>;

  getImageBlob(screenshotId: number): Promise<Blob | null>;

  /** Save a blob for a specific pipeline stage (e.g., "original", "cropping"). */
  saveStageBlob(screenshotId: number, stage: string, blob: Blob): Promise<void>;

  /** Retrieve a blob for a specific pipeline stage. */
  getStageBlob(screenshotId: number, stage: string): Promise<Blob | null>;

  deleteScreenshotsByGroup(groupId: string): Promise<{ screenshots_deleted: number; annotations_deleted: number }>;

  clearAll(): Promise<void>;

  /**
   * Efficient paginated query that only loads the requested page.
   * Uses IndexedDB indexes for filtering and sorting.
   */
  getScreenshotsPaginated(
    params: PaginationParams,
  ): Promise<ScreenshotListResponse>;

  /**
   * Efficient navigation that finds next/prev screenshot without loading all.
   * Uses cursor-based navigation on indexed fields.
   */
  navigateScreenshots(
    currentId: number,
    params: NavigationQueryParams,
  ): Promise<NavigationResponse>;

  /** Estimate storage usage via navigator.storage.estimate(). Returns null if unsupported. */
  getStorageEstimate?(): Promise<{ usage: number; quota: number; percentUsed: number } | null>;
}
