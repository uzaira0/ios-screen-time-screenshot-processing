import { useContext, useMemo } from "react";
import { ServiceContext } from "./ServiceProvider";
import { TOKENS, type AppFeatures, getActiveStages } from "../di/tokens";
import type { PreprocessingStages } from "@/core/generated/constants";
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

/**
 * Ordered list of preprocessing stages active in the current mode.
 * Use this — never the raw PREPROCESSING_STAGES constant — when computing
 * prerequisites, rendering wizard tabs, or validating deep-links.
 *
 * In WASM mode this returns ["device_detection", "cropping", "ocr"].
 * In server/Tauri mode it returns the full 5-stage list.
 */
export function useActiveStages(): readonly PreprocessingStages[] {
  const features = useFeatures();
  return useMemo(() => getActiveStages(features), [features]);
}
