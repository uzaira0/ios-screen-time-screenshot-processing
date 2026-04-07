import type { Annotation, AnnotationCreate } from '@/types';

export interface IAnnotationService {
  create(data: AnnotationCreate): Promise<Annotation>;

  update(id: number, data: Partial<AnnotationCreate>): Promise<Annotation>;

  getByScreenshot(screenshotId: number): Promise<Annotation[]>;

  getHistory(skip?: number, limit?: number): Promise<Annotation[]>;

  delete(id: number): Promise<void>;
}
