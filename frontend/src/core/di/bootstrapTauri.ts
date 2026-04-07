import { TOKENS } from "./tokens";
import type { AppConfig } from "../config";
import type { ServiceContainer } from "./Container";
import { bootstrapWasmServices } from "./bootstrapWasm";
import { TauriProcessingService } from "../implementations/tauri/TauriProcessingService";

/**
 * Bootstrap services for Tauri (desktop) mode.
 *
 * Reuses WASM bootstrap for storage/annotations/consensus, but swaps in
 * TauriProcessingService (Rust-native) instead of WASMProcessingService (Tesseract.js).
 */
export function bootstrapTauriServices(config: AppConfig): ServiceContainer {
  const container = bootstrapWasmServices(config);

  // Override the processing service with Rust-native implementation
  container.registerSingleton(
    TOKENS.PROCESSING_SERVICE,
    () => new TauriProcessingService(),
  );

  return container;
}
