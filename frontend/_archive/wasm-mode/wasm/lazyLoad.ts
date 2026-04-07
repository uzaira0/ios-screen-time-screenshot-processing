/**
 * Lazy Loading for WASM Modules
 *
 * OpenCV has been REMOVED - only Tesseract.js is loaded now.
 */

import toast from "react-hot-toast";

type TesseractType = any;
type TesseractWorkerType = any;

let tesseractInstance: TesseractType | null = null;
let tesseractLoading: Promise<TesseractType> | null = null;
let tesseractWorker: TesseractWorkerType | null = null;
let workerInitializing: Promise<TesseractWorkerType> | null = null;

/**
 * Load Tesseract.js
 */
export async function loadTesseract(
  onProgress?: (progress: number) => void,
): Promise<TesseractType> {
  if (tesseractInstance) {
    return tesseractInstance;
  }

  if (tesseractLoading) {
    return tesseractLoading;
  }

  tesseractLoading = (async () => {
    try {
      const loadingToast = toast.loading("Loading Tesseract.js...");

      onProgress?.(10);

      const Tesseract = await import("tesseract.js");
      onProgress?.(100);

      tesseractInstance = Tesseract;

      toast.success("Tesseract.js loaded successfully", {
        id: loadingToast,
      });

      return Tesseract;
    } catch (error) {
      toast.error("Failed to load Tesseract.js");
      throw new Error(`Failed to load Tesseract.js: ${error}`);
    } finally {
      tesseractLoading = null;
    }
  })();

  return tesseractLoading;
}

/**
 * Preload Tesseract during app initialization
 *
 * This loads and initializes a Tesseract worker during app startup,
 * eliminating the 2-5 second delay on first processing operation.
 * The worker is cached and reused for all subsequent operations.
 *
 * @param onProgress - Callback for loading progress (0-100)
 */
export async function preloadTesseract(
  onProgress?: (progress: number, message: string) => void,
): Promise<void> {
  if (tesseractWorker) {
    onProgress?.(100, "Tesseract already initialized");
    return;
  }

  if (workerInitializing) {
    return workerInitializing.then(() => {});
  }

  workerInitializing = (async () => {
    try {
      onProgress?.(0, "Loading Tesseract.js library...");

      // Load Tesseract library
      const Tesseract = await loadTesseract((libProgress) => {
        // Map library loading to first 30% of total progress
        onProgress?.(libProgress * 0.3, "Loading Tesseract.js library...");
      });

      onProgress?.(30, "Creating OCR worker...");

      // Create and initialize worker
      const worker = await Tesseract.createWorker("eng", 1, {
        logger: (m: { status?: string; progress?: number }) => {
          // Map worker initialization progress (30-100%)
          if (m.status === "loading tesseract core") {
            onProgress?.(40, "Loading Tesseract core...");
          } else if (m.status === "initializing tesseract") {
            onProgress?.(60, "Initializing Tesseract...");
          } else if (m.status === "loading language traineddata") {
            onProgress?.(70, "Loading language data...");
          } else if (m.status === "initializing api") {
            onProgress?.(90, "Initializing API...");
          }

          // Progress updates during loading
          if (m.progress !== undefined && m.progress > 0) {
            const baseProgress =
              m.status === "loading language traineddata" ? 70 : 40;
            const progressRange =
              m.status === "loading language traineddata" ? 20 : 20;
            onProgress?.(
              baseProgress + m.progress * progressRange,
              m.status || "Initializing...",
            );
          }
        },
      });

      tesseractWorker = worker;

      onProgress?.(100, "Tesseract ready!");

      return worker;
    } catch (error) {
      workerInitializing = null;
      throw new Error(`Failed to preload Tesseract: ${error}`);
    } finally {
      workerInitializing = null;
    }
  })();

  return workerInitializing.then(() => {});
}

/**
 * Get the preloaded Tesseract worker (if available)
 *
 * Returns the cached worker instance that was preloaded during app initialization.
 * This allows immediate processing without waiting for initialization.
 */
export function getPreloadedTesseractWorker(): TesseractWorkerType | null {
  return tesseractWorker;
}

/**
 * Check if Tesseract worker is preloaded and ready
 */
export function isTesseractWorkerReady(): boolean {
  return tesseractWorker !== null;
}

export async function getTesseract(): Promise<TesseractType> {
  if (tesseractInstance) {
    return tesseractInstance;
  }
  return loadTesseract();
}

export function isTesseractLoaded(): boolean {
  return tesseractInstance !== null;
}

export function unloadTesseract(): void {
  tesseractInstance = null;
  tesseractLoading = null;
}

export async function preloadWASMModules(
  onProgress?: (module: string, progress: number) => void,
): Promise<void> {
  await loadTesseract((progress) => onProgress?.("Tesseract", progress));
}

export interface WASMLoadingStatus {
  tesseract: {
    loaded: boolean;
    loading: boolean;
  };
}

export function getWASMLoadingStatus(): WASMLoadingStatus {
  return {
    tesseract: {
      loaded: tesseractInstance !== null,
      loading: tesseractLoading !== null,
    },
  };
}

// Legacy compatibility - these no-op functions prevent breaking existing code
export async function loadOpenCV(): Promise<any> {
  console.warn("OpenCV has been removed - using Canvas 2D API instead");
  return null;
}

export async function getOpenCV(): Promise<any> {
  console.warn("OpenCV has been removed - using Canvas 2D API instead");
  return null;
}

export function isOpenCVLoaded(): boolean {
  return false;
}

export function unloadOpenCV(): void {
  // No-op
}
