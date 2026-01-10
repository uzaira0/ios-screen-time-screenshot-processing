import type { HourlyData, GridCoordinates } from '../../models';
import type { ImageType } from '@/types';
import type {
  IProcessingService,
  ProcessingConfig,
  ProcessingProgressCallback,
} from '../../interfaces';

export class WASMProcessingService implements IProcessingService {
  private initialized = false;

  async initialize(): Promise<void> {
    throw new Error('WASMProcessingService.initialize: Not implemented yet. Phase 2-3 will implement OpenCV.js and Tesseract.js initialization.');
  }

  isInitialized(): boolean {
    return this.initialized;
  }

  async processImage(
    _imageData: ImageData | Blob,
    _config: ProcessingConfig,
    _onProgress?: ProcessingProgressCallback
  ): Promise<{
    hourlyData: HourlyData;
    title: string | null;
    total: string | null;
    gridCoordinates?: GridCoordinates;
  }> {
    throw new Error('WASMProcessingService.processImage: Not implemented yet. Phase 3 will implement this using OpenCV.js for image processing and Tesseract.js for OCR.');
  }

  async extractTitle(_imageData: ImageData | Blob): Promise<string | null> {
    throw new Error('WASMProcessingService.extractTitle: Not implemented yet. Phase 3 will implement OCR extraction using Tesseract.js.');
  }

  async extractTotal(_imageData: ImageData | Blob): Promise<string | null> {
    throw new Error('WASMProcessingService.extractTotal: Not implemented yet. Phase 3 will implement OCR extraction using Tesseract.js.');
  }

  async extractHourlyData(
    _imageData: ImageData | Blob,
    _gridCoordinates: GridCoordinates,
    _imageType: ImageType
  ): Promise<HourlyData> {
    throw new Error('WASMProcessingService.extractHourlyData: Not implemented yet. Phase 3 will implement grid-based OCR extraction.');
  }

  async detectGrid(
    _imageData: ImageData | Blob,
    _imageType: ImageType
  ): Promise<GridCoordinates | null> {
    throw new Error('WASMProcessingService.detectGrid: Not implemented yet. Phase 3 will implement automatic grid detection using OpenCV.js.');
  }
}
