import type { Annotation, AnnotationCreate } from "@/types";
import type { IAnnotationService } from "@/core/interfaces";
import type { IStorageService } from "@/core/interfaces";
import { db } from "./storage/database";
import { useAuthStore } from "@/store/authStore";

export class WASMAnnotationService implements IAnnotationService {
  private storageService: IStorageService;

  constructor(storageService: IStorageService) {
    this.storageService = storageService;
  }

  async create(data: AnnotationCreate): Promise<Annotation> {
    // Build annotation without id — let IndexedDB auto-increment assign it
    const now = new Date().toISOString();
    const annotation = {
      screenshot_id: data.screenshot_id,
      user_id: useAuthStore.getState().userId ?? 1,
      grid_upper_left: data.grid_upper_left ?? null,
      grid_lower_right: data.grid_lower_right ?? null,
      hourly_values: data.hourly_values,
      extracted_title: data.extracted_title ?? null,
      extracted_total: data.extracted_total ?? null,
      notes: data.notes ?? null,
      status: "completed",
      created_at: now,
      updated_at: now,
    } as Annotation;

    const id = await this.storageService.saveAnnotation(annotation);
    annotation.id = id;

    await this.storageService.updateScreenshot(data.screenshot_id, {
      annotation_status: "annotated",
    });

    return annotation;
  }

  async update(
    id: number,
    data: Partial<AnnotationCreate>,
  ): Promise<Annotation> {
    const updates = {
      ...data,
      updated_at: new Date().toISOString(),
    };

    const updated = await db.annotations.update(id, updates);
    if (updated === 0) {
      throw new Error(`Annotation with ID ${id} not found`);
    }

    // Fetch the updated record to return the full annotation
    const annotation = await db.annotations.get(id);
    return annotation!;
  }

  async getByScreenshot(screenshotId: number): Promise<Annotation[]> {
    const result =
      await this.storageService.getAnnotationsByScreenshot(screenshotId);
    return Array.isArray(result) ? result : [];
  }

  async getHistory(skip = 0, limit = 50): Promise<Annotation[]> {
    // Query annotations directly, sorted by created_at descending, with pagination
    const allAnnotations = await db.annotations
      .orderBy("created_at")
      .reverse()
      .offset(skip)
      .limit(limit)
      .toArray();

    return allAnnotations;
  }

  async delete(id: number): Promise<void> {
    await this.storageService.deleteAnnotation(id);
  }
}
