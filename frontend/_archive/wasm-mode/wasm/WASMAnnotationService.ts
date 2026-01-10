import type { Annotation, AnnotationCreate } from "../../models";
import type { IAnnotationService } from "../../interfaces";
import type { IStorageService } from "../../interfaces";

export class WASMAnnotationService implements IAnnotationService {
  private storageService: IStorageService;

  constructor(storageService: IStorageService) {
    this.storageService = storageService;
  }

  async create(data: AnnotationCreate): Promise<Annotation> {
    // AnnotationCreate uses grid_upper_left/grid_lower_right + hourly_values
    const annotation: Annotation = {
      id: Date.now(),
      screenshot_id: data.screenshot_id,
      user_id: 1,
      grid_upper_left: data.grid_upper_left ?? null,
      grid_lower_right: data.grid_lower_right ?? null,
      hourly_values: data.hourly_values,
      notes: data.notes ?? null,
      status: "completed",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    } as Annotation;

    const id = await this.storageService.saveAnnotation(annotation);
    annotation.id = id;

    await this.storageService.updateScreenshot(data.screenshot_id, {
      annotation_status: "annotated",
      current_annotation_count: 1,
    });

    return annotation;
  }

  async update(
    _id: number,
    _data: Partial<AnnotationCreate>,
  ): Promise<Annotation> {
    throw new Error("WASMAnnotationService.update: Not implemented yet");
  }

  async getByScreenshot(screenshotId: number): Promise<Annotation[]> {
    const result =
      await this.storageService.getAnnotationsByScreenshot(screenshotId);
    return Array.isArray(result) ? result : [];
  }

  async getHistory(skip = 0, limit = 50): Promise<Annotation[]> {
    const screenshotsResult = await this.storageService.getAllScreenshots({
      annotation_status: "annotated",
    });
    const screenshots = Array.isArray(screenshotsResult)
      ? screenshotsResult
      : [];
    const allAnnotations: Annotation[] = [];

    for (const screenshot of screenshots) {
      const annotationsResult =
        await this.storageService.getAnnotationsByScreenshot(screenshot.id);
      const annotations = Array.isArray(annotationsResult)
        ? annotationsResult
        : [];
      allAnnotations.push(...annotations);
    }

    allAnnotations.sort((a, b) => {
      return (
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
    });

    return allAnnotations.slice(skip, skip + limit);
  }

  async delete(id: number): Promise<void> {
    await this.storageService.deleteAnnotation(id);
  }
}
