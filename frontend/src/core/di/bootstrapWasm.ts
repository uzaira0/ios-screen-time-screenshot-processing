import { ServiceContainer } from "./Container";
import { TOKENS, type AppFeatures } from "./tokens";
import type { AppConfig } from "../config";
import { config as runtimeConfig } from "@/config";

import { IndexedDBStorageService } from "../implementations/wasm/storage/IndexedDBStorageService";
import { WASMScreenshotService } from "../implementations/wasm/WASMScreenshotService";
import { WASMAnnotationService } from "../implementations/wasm/WASMAnnotationService";
import { WASMConsensusService } from "../implementations/wasm/WASMConsensusService";
import { WASMProcessingService } from "../implementations/wasm/WASMProcessingService";
import { WASMPreprocessingService } from "../implementations/wasm/preprocessing/WASMPreprocessingService";

/**
 * Bootstrap services for WASM (local-first) mode.
 * All processing happens client-side with IndexedDB storage.
 */
export function bootstrapWasmServices(_config: AppConfig): ServiceContainer {
  const container = new ServiceContainer();

  if (runtimeConfig.isDev) {
    console.log("[Bootstrap] Registering WASM services (local-first mode)");
  }

  // Storage is the foundation - everything depends on it
  container.registerSingleton(
    TOKENS.STORAGE_SERVICE,
    () => new IndexedDBStorageService(),
  );

  // Processing service handles OCR via Tesseract.js Web Worker
  container.registerSingleton(
    TOKENS.PROCESSING_SERVICE,
    () => new WASMProcessingService(),
  );

  // Screenshot service orchestrates storage + processing
  container.registerSingleton(TOKENS.SCREENSHOT_SERVICE, () => {
    const storage = container.resolve<IndexedDBStorageService>(TOKENS.STORAGE_SERVICE);
    const processing = container.resolve<WASMProcessingService>(TOKENS.PROCESSING_SERVICE);
    return new WASMScreenshotService(storage, processing);
  });

  container.registerSingleton(TOKENS.ANNOTATION_SERVICE, () => {
    const storage = container.resolve<IndexedDBStorageService>(TOKENS.STORAGE_SERVICE);
    return new WASMAnnotationService(storage);
  });

  container.registerSingleton(TOKENS.CONSENSUS_SERVICE, () => {
    const storage = container.resolve<IndexedDBStorageService>(TOKENS.STORAGE_SERVICE);
    return new WASMConsensusService(storage);
  });

  container.registerSingleton(TOKENS.PREPROCESSING_PIPELINE_SERVICE, () => {
    const storage = container.resolve<IndexedDBStorageService>(TOKENS.STORAGE_SERVICE);
    const processing = container.resolve<WASMProcessingService>(TOKENS.PROCESSING_SERVICE);
    return new WASMPreprocessingService(storage, processing);
  });

  // WASM mode: local processing via Tesseract.js + IndexedDB.
  // Server-only features: cross-rater comparison, admin.
  const features: AppFeatures = {
    groups: true,
    consensusComparison: false,
    admin: false,
    preprocessing: true,
  };
  container.register(TOKENS.FEATURES, features);

  if (runtimeConfig.isDev) {
    console.log("[Bootstrap] WASM services registered.");
  }

  return container;
}
