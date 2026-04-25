import type { HourlyData, GridCoordinates } from "@/types";
import type { ImageType } from "@/types";
import type {
  IProcessingService,
  ProcessingConfig,
  ProcessingProgressCallback,
} from "@/core/interfaces";
import type {
  WorkerMessage,
  WorkerResponse,
  ProcessImageResponse,
  ProgressUpdate,
} from "./processing/workers/types";
import { smartConvertBlobToImageData } from "./imageConversion";

export class WASMProcessingService implements IProcessingService {
  private worker: Worker | null = null;
  private initialized = false;
  private initializationPromise: Promise<void> | null = null; // Prevents race conditions
  private messageIdCounter = 0;
  private pendingRequests = new Map<
    string,
    {
      resolve: (value: unknown) => void;
      reject: (error: Error) => void;
      onProgress?: ProcessingProgressCallback | undefined;
    }
  >();

  constructor() {
    this.initializeWorker();
  }

  private initializeWorker(): void {
    // Rust+leptess pipeline (wasm32-unknown-emscripten). The worker dynamically
    // imports the Emscripten-compiled IosScreenTimePipeline.wasm produced by
    // scripts/build-wasm-emscripten.sh and staged into
    // frontend/public/pipeline-em/. Grid detection, OCR (leptess →
    // libtesseract), bar extraction, and boundary optimization all run in
    // Rust — no Tesseract.js, no TS canvas ports.
    this.worker = new Worker(
      new URL("./processing/workers/imageProcessor.worker.emscripten.ts", import.meta.url),
      { type: "module" },
    );

    this.worker.onmessage = (e: MessageEvent<WorkerResponse>) => {
      const { type, id, payload, error } = e.data;
      console.log(
        "[WASMProcessingService.worker.onmessage] Received message:",
        { type, id, hasPayload: !!payload, error },
      );

      if (type === "PROGRESS") {
        const progressData = payload as ProgressUpdate["payload"];
        const request = this.pendingRequests.get(id);
        if (request && request.onProgress) {
          request.onProgress(progressData);
        }
        return;
      }

      const request = this.pendingRequests.get(id);
      if (!request) {
        console.warn(
          "[WASMProcessingService.worker.onmessage] No pending request found for id:",
          id,
        );
        return;
      }

      if (type === "ERROR") {
        console.error(
          "[WASMProcessingService.worker.onmessage] Worker returned error:",
          error,
        );
        request.reject(new Error(error || "Unknown error in worker"));
      } else {
        console.log(
          "[WASMProcessingService.worker.onmessage] Resolving request with payload",
        );
        request.resolve(payload);
      }

      this.pendingRequests.delete(id);
    };

    this.worker.onerror = (error) => {
      console.error("Worker error:", error);
      this.initialized = false;
      this.pendingRequests.forEach((request) => {
        request.reject(new Error("Worker error: " + error.message));
      });
      this.pendingRequests.clear();
    };
  }

  private generateMessageId(): string {
    return `msg_${++this.messageIdCounter}_${Date.now()}`;
  }

  private async sendMessage<T>(
    message: Omit<WorkerMessage, "id">,
    onProgress?: ProcessingProgressCallback,
  ): Promise<T> {
    if (!this.worker) {
      throw new Error("Worker not initialized");
    }

    const id = this.generateMessageId();
    console.log(
      "[WASMProcessingService.sendMessage] Sending message type:",
      message.type,
      "with id:",
      id,
    );

    return new Promise<T>((resolve, reject) => {
      // INITIALIZE downloads ~15MB of Tesseract WASM + trained data — needs longer timeout.
      // Regular messages use 60s (processing a single image with OCR can take 10-20s).
      const timeoutMs = message.type === "INITIALIZE" ? 120000 : 60000;
      const timeout = setTimeout(() => {
        this.pendingRequests.delete(id);
        reject(
          new Error(
            `Worker message ${message.type} timed out after ${timeoutMs / 1000} seconds`,
          ),
        );
      }, timeoutMs);

      this.pendingRequests.set(id, {
        resolve: (value: unknown) => {
          clearTimeout(timeout);
          resolve(value as T);
        },
        reject: (error: Error) => {
          clearTimeout(timeout);
          reject(error);
        },
        onProgress,
      });

      const fullMessage: WorkerMessage = {
        ...message,
        id,
      };

      console.log(
        "[WASMProcessingService.sendMessage] Posted message to worker:",
        fullMessage.type,
      );

      // Collect transferable ArrayBuffers from ImageData payloads for zero-copy transfer
      const transferables: Transferable[] = [];
      const payload = fullMessage.payload as Record<string, unknown> | undefined;
      if (payload?.imageData && (payload.imageData as ImageData).data?.buffer) {
        transferables.push((payload.imageData as ImageData).data.buffer);
      }
      this.worker!.postMessage(fullMessage, transferables);
    });
  }

  async initialize(): Promise<void> {
    console.log("[WASMProcessingService.initialize] Starting initialization");

    // If already initialized, return immediately
    if (this.initialized) {
      console.log("[WASMProcessingService.initialize] Already initialized");
      return;
    }

    // If initialization is in progress, wait for it to complete (prevents race condition)
    if (this.initializationPromise) {
      console.log(
        "[WASMProcessingService.initialize] Initialization already in progress, waiting...",
      );
      return this.initializationPromise;
    }

    // Start new initialization and cache the promise
    this.initializationPromise = (async () => {
      try {
        console.log(
          "[WASMProcessingService.initialize] Sending INITIALIZE message to worker",
        );
        await this.sendMessage({
          type: "INITIALIZE",
          payload: {},
        });

        this.initialized = true;
        console.log(
          "[WASMProcessingService.initialize] Initialization complete",
        );
      } catch (error) {
        // Clear the promise on error so retry is possible
        this.initializationPromise = null;
        throw error;
      }
    })();

    return this.initializationPromise;
  }

  isInitialized(): boolean {
    return this.initialized;
  }

  async processImage(
    imageData: ImageData | Blob,
    config: ProcessingConfig,
    onProgress?: ProcessingProgressCallback,
  ): Promise<{
    hourlyData: HourlyData;
    title: string | null;
    total: string | null;
    gridCoordinates?: GridCoordinates;
    gridDetectionFailed?: boolean;
    gridDetectionError?: string;
    alignmentScore?: number | null;
  }> {
    console.log(
      "[WASMProcessingService.processImage] Starting, initialized:",
      this.initialized,
    );

    if (!this.initialized) {
      console.log(
        "[WASMProcessingService.processImage] Not initialized, calling initialize()",
      );
      await this.initialize();
      console.log("[WASMProcessingService.processImage] Initialize complete");
    }

    const _blobT0 = performance.now();
    const imgData =
      imageData instanceof Blob
        ? await smartConvertBlobToImageData(imageData)
        : imageData;
    console.log(`[BENCH] processImage blob→ImageData: ${(performance.now() - _blobT0).toFixed(0)}ms (${imgData.width}x${imgData.height})`);

    const _workerT0 = performance.now();
    const result = await this.sendMessage<ProcessImageResponse["payload"]>(
      {
        type: "PROCESS_IMAGE",
        payload: {
          imageData: imgData,
          imageType: config.imageType,
          gridCoordinates: config.gridCoordinates,
          maxShift: config.maxShift,
        },
      },
      onProgress,
    );
    console.log(`[BENCH] processImage worker round-trip: ${(performance.now() - _workerT0).toFixed(0)}ms`);

    return result;
  }

  private async ensureReadyAndConvert(imageData: ImageData | Blob): Promise<ImageData> {
    if (!this.initialized) {
      await this.initialize();
    }
    return imageData instanceof Blob
      ? await smartConvertBlobToImageData(imageData)
      : imageData;
  }

  async extractTitle(imageData: ImageData | Blob): Promise<string | null> {
    const imgData = await this.ensureReadyAndConvert(imageData);
    const result = await this.sendMessage<{ title: string | null }>({
      type: "EXTRACT_TITLE",
      payload: { imageData: imgData },
    });
    return result.title;
  }

  async extractTotal(imageData: ImageData | Blob): Promise<string | null> {
    const imgData = await this.ensureReadyAndConvert(imageData);
    const result = await this.sendMessage<{ total: string | null }>({
      type: "EXTRACT_TOTAL",
      payload: { imageData: imgData },
    });
    return result.total;
  }

  async extractHourlyData(
    imageData: ImageData | Blob,
    gridCoordinates: GridCoordinates,
    imageType: ImageType,
  ): Promise<HourlyData> {
    const imgData = await this.ensureReadyAndConvert(imageData);
    const result = await this.sendMessage<{ hourlyData: HourlyData }>({
      type: "EXTRACT_HOURLY_DATA",
      payload: { imageData: imgData, gridCoordinates, imageType },
    });
    return result.hourlyData;
  }

  async detectGrid(
    imageData: ImageData | Blob,
    imageType: ImageType,
    method?: "ocr_anchored" | "line_based",
  ): Promise<GridCoordinates | null> {
    const _dgT0 = performance.now();
    const imgData = await this.ensureReadyAndConvert(imageData);
    console.log(`[BENCH] detectGrid blob→ImageData: ${(performance.now() - _dgT0).toFixed(0)}ms`);
    const _dgT1 = performance.now();
    const result = await this.sendMessage<{
      gridCoordinates: GridCoordinates | null;
    }>({
      type: "DETECT_GRID",
      payload: { imageData: imgData, imageType, method },
    });
    console.log(`[BENCH] detectGrid worker round-trip (${method}): ${(performance.now() - _dgT1).toFixed(0)}ms`);
    return result.gridCoordinates;
  }

  terminate(): void {
    if (this.worker) {
      this.worker.terminate();
      this.worker = null;
      this.initialized = false;
      this.initializationPromise = null;
      for (const request of this.pendingRequests.values()) {
        request.reject(new Error("Worker terminated"));
      }
      this.pendingRequests.clear();
    }
    // Recreate the worker so the service can be used again
    this.initializeWorker();
  }
}
