import { TOKENS, type AppFeatures } from "./tokens";
import type { AppConfig } from "../config";
import type { ServiceContainer } from "./Container";
import { bootstrapWasmServices } from "./bootstrapWasm";
import { TauriProcessingService } from "../implementations/tauri/TauriProcessingService";

/**
 * Bootstrap services for Tauri (desktop) mode.
 *
 * Reuses WASM bootstrap for storage/annotations/consensus, but swaps in
 * TauriProcessingService (Rust-native) instead of WASMProcessingService.
 * Tauri ships native leptess so PHI detection stays available — re-enable
 * the flag that the WASM bootstrap turned off.
 */
export function bootstrapTauriServices(config: AppConfig): ServiceContainer {
  const container = bootstrapWasmServices(config);

  // Override the processing service with Rust-native implementation
  container.registerSingleton(
    TOKENS.PROCESSING_SERVICE,
    () => new TauriProcessingService(),
  );

  // Tauri has native leptess + libtesseract — turn PHI back on.
  const wasmFeatures = container.resolve<AppFeatures>(TOKENS.FEATURES);
  container.register(TOKENS.FEATURES, { ...wasmFeatures, phiDetection: true });

  return container;
}
