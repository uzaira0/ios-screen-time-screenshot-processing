import { ServiceContainer } from "./Container";
import { TOKENS, type AppFeatures } from "./tokens";
import type { AppConfig } from "../config";
import { config as runtimeConfig } from "@/config";

import { APIScreenshotService } from "../implementations/server/APIScreenshotService";
import { APIAnnotationService } from "../implementations/server/APIAnnotationService";
import { APIConsensusService } from "../implementations/server/APIConsensusService";
import { APIStorageService } from "../implementations/server/APIStorageService";
import { ServerPreprocessingService } from "../implementations/server/ServerPreprocessingService";

/**
 * Bootstrap services based on application mode.
 *
 * Uses dynamic import() for WASM/Tauri so their dependencies (Dexie,
 * Tesseract.js, Web Workers) are code-split from the server bundle.
 */
export async function bootstrapServices(
  config: AppConfig,
): Promise<ServiceContainer> {
  if (config.mode === "tauri") {
    const { bootstrapTauriServices } = await import("./bootstrapTauri");
    return bootstrapTauriServices(config);
  }

  if (config.mode === "wasm") {
    const { bootstrapWasmServices } = await import("./bootstrapWasm");
    return bootstrapWasmServices(config);
  }

  return bootstrapServerServices(config);
}

function bootstrapServerServices(config: AppConfig): ServiceContainer {
  const container = new ServiceContainer();
  const apiBaseUrl = config.apiBaseUrl || "/api/v1";

  if (runtimeConfig.isDev) {
    console.log(
      "[Bootstrap] Registering server services with apiBaseUrl:",
      apiBaseUrl,
    );
  }

  container.registerSingleton(
    TOKENS.SCREENSHOT_SERVICE,
    () => new APIScreenshotService(apiBaseUrl),
  );

  container.registerSingleton(
    TOKENS.ANNOTATION_SERVICE,
    () => new APIAnnotationService(apiBaseUrl),
  );

  container.registerSingleton(
    TOKENS.CONSENSUS_SERVICE,
    () => new APIConsensusService(apiBaseUrl),
  );

  container.registerSingleton(
    TOKENS.STORAGE_SERVICE,
    () => new APIStorageService(),
  );

  container.registerSingleton(
    TOKENS.PREPROCESSING_PIPELINE_SERVICE,
    () => new ServerPreprocessingService(),
  );

  // Server mode has all server-dependent features
  const features: AppFeatures = {
    groups: true,
    consensusComparison: true,
    admin: true,
    preprocessing: true,
    phiDetection: true,
  };
  container.register(TOKENS.FEATURES, features);

  if (runtimeConfig.isDev) {
    console.log(
      "[Bootstrap] Services registered. Container has SCREENSHOT_SERVICE:",
      container.has(TOKENS.SCREENSHOT_SERVICE),
    );
  }
  return container;
}
