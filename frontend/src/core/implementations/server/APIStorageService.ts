import type {
  Screenshot,
  Annotation,
  ScreenshotListResponse,
  NavigationResponse,
} from "../../models";
import type {
  IStorageService,
  PaginationParams,
  NavigationQueryParams,
} from "../../interfaces";

export class APIStorageService implements IStorageService {
  async saveScreenshot(_screenshot: Screenshot): Promise<number> {
    throw new Error(
      "APIStorageService.saveScreenshot is not used in server mode",
    );
  }

  async getScreenshot(_id: number): Promise<Screenshot | null> {
    throw new Error(
      "APIStorageService.getScreenshot is not used in server mode",
    );
  }

  async getAllScreenshots(_filter?: {
    annotation_status?: string;
    group_id?: string;
    processing_status?: string;
  }): Promise<Screenshot[]> {
    throw new Error(
      "APIStorageService.getAllScreenshots is not used in server mode",
    );
  }

  async updateScreenshot(
    _id: number,
    _data: Partial<Screenshot>,
  ): Promise<void> {
    throw new Error(
      "APIStorageService.updateScreenshot is not used in server mode",
    );
  }

  async deleteScreenshot(_id: number): Promise<void> {
    throw new Error(
      "APIStorageService.deleteScreenshot is not used in server mode",
    );
  }

  async saveAnnotation(_annotation: Annotation): Promise<number> {
    throw new Error(
      "APIStorageService.saveAnnotation is not used in server mode",
    );
  }

  async getAnnotation(_id: number): Promise<Annotation | null> {
    throw new Error(
      "APIStorageService.getAnnotation is not used in server mode",
    );
  }

  async getAnnotationsByScreenshot(
    _screenshotId: number,
  ): Promise<Annotation[]> {
    throw new Error(
      "APIStorageService.getAnnotationsByScreenshot is not used in server mode",
    );
  }

  async deleteAnnotation(_id: number): Promise<void> {
    throw new Error(
      "APIStorageService.deleteAnnotation is not used in server mode",
    );
  }

  async saveImageBlob(_screenshotId: number, _blob: Blob): Promise<void> {
    throw new Error(
      "APIStorageService.saveImageBlob is not used in server mode",
    );
  }

  async getImageBlob(_screenshotId: number): Promise<Blob | null> {
    throw new Error(
      "APIStorageService.getImageBlob is not used in server mode",
    );
  }

  async saveStageBlob(_screenshotId: number, _stage: string, _blob: Blob): Promise<void> {
    throw new Error(
      "APIStorageService.saveStageBlob is not used in server mode",
    );
  }

  async getStageBlob(_screenshotId: number, _stage: string): Promise<Blob | null> {
    throw new Error(
      "APIStorageService.getStageBlob is not used in server mode",
    );
  }

  async deleteScreenshotsByGroup(_groupId: string): Promise<{ screenshots_deleted: number; annotations_deleted: number }> {
    throw new Error(
      "APIStorageService.deleteScreenshotsByGroup is not used in server mode",
    );
  }

  async clearAll(): Promise<void> {
    throw new Error("APIStorageService.clearAll is not used in server mode");
  }

  async getScreenshotsPaginated(
    _params: PaginationParams,
  ): Promise<ScreenshotListResponse> {
    throw new Error(
      "APIStorageService.getScreenshotsPaginated is not used in server mode",
    );
  }

  async navigateScreenshots(
    _currentId: number,
    _params: NavigationQueryParams,
  ): Promise<NavigationResponse> {
    throw new Error(
      "APIStorageService.navigateScreenshots is not used in server mode",
    );
  }
}
