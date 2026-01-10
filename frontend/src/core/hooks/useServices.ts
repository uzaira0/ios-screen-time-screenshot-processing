import { useContext } from "react";
import { ServiceContext } from "./ServiceProvider";
import { TOKENS, type AppFeatures } from "../di/tokens";
import type {
  IScreenshotService,
  IAnnotationService,
  IConsensusService,
  IStorageService,
  IProcessingService,
  IPreprocessingService,
} from "../interfaces";

function useServiceContainer() {
  const container = useContext(ServiceContext);

  if (!container) {
    throw new Error(
      "useServiceContainer must be used within a ServiceProvider",
    );
  }

  return container;
}

export function useScreenshotService(): IScreenshotService {
  const container = useServiceContainer();
  return container.resolve<IScreenshotService>(TOKENS.SCREENSHOT_SERVICE);
}

export function useAnnotationService(): IAnnotationService {
  const container = useServiceContainer();
  return container.resolve<IAnnotationService>(TOKENS.ANNOTATION_SERVICE);
}

export function useConsensusService(): IConsensusService {
  const container = useServiceContainer();
  return container.resolve<IConsensusService>(TOKENS.CONSENSUS_SERVICE);
}

export function useStorageService(): IStorageService {
  const container = useServiceContainer();
  return container.resolve<IStorageService>(TOKENS.STORAGE_SERVICE);
}

/**
 * Returns the processing service if registered (WASM mode), or null (server mode).
 */
export function useProcessingService(): IProcessingService | null {
  const container = useServiceContainer();
  if (container.has(TOKENS.PROCESSING_SERVICE)) {
    return container.resolve<IProcessingService>(TOKENS.PROCESSING_SERVICE);
  }
  return null;
}

export function usePreprocessingPipelineService(): IPreprocessingService {
  const container = useServiceContainer();
  return container.resolve<IPreprocessingService>(TOKENS.PREPROCESSING_PIPELINE_SERVICE);
}

/**
 * Returns the feature flags for the current mode.
 * Components use this to check what capabilities are available
 * instead of checking config.isLocalMode directly.
 */
export function useFeatures(): AppFeatures {
  const container = useServiceContainer();
  return container.resolve<AppFeatures>(TOKENS.FEATURES);
}
