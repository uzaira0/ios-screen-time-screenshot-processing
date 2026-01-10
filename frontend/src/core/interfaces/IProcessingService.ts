import type { HourlyData, GridCoordinates, ImageType } from '@/types';

export interface ProcessingConfig {
  imageType: ImageType;
  gridCoordinates?: GridCoordinates;
  /** Max pixels to shift grid for optimization (0 = disabled) */
  maxShift?: number;
}

/**
 * Processing progress with specific stage types for the processing pipeline.
 * This extends the general ProcessingProgress with more specific stage values.
 */
export interface ProcessingProgress {
  stage: 'loading' | 'preprocessing' | 'ocr_title' | 'ocr_total' | 'ocr_hourly' | 'complete' | string;
  progress: number;
  message?: string;
}

export type ProcessingProgressCallback = (progress: ProcessingProgress) => void;

export interface IProcessingService {
  processImage(
    imageData: ImageData | Blob,
    config: ProcessingConfig,
    onProgress?: ProcessingProgressCallback
  ): Promise<{
    hourlyData: HourlyData;
    title: string | null;
    total: string | null;
    gridCoordinates?: GridCoordinates;
    gridDetectionFailed?: boolean;
    gridDetectionError?: string;
    alignmentScore?: number | null;
  }>;

  extractTitle(imageData: ImageData | Blob): Promise<string | null>;

  extractTotal(imageData: ImageData | Blob): Promise<string | null>;

  extractHourlyData(
    imageData: ImageData | Blob,
    gridCoordinates: GridCoordinates,
    imageType: ImageType
  ): Promise<HourlyData>;

  detectGrid(imageData: ImageData | Blob, imageType: ImageType, method?: "ocr_anchored" | "line_based"): Promise<GridCoordinates | null>;

  initialize(): Promise<void>;

  isInitialized(): boolean;

  /** Terminate the processing worker. It will be lazily recreated on next use. */
  terminate(): void;
}
