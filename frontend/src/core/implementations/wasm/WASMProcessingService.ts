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

/**
 * One worker slot in the pool. Each slot holds its own Web Worker,
 * which in turn holds its own LepTess instance + tessdata mount in
 * Emscripten heap. The slot tracks how many messages are currently
 * in-flight so we can route new work to whichever worker is least
 * loaded.
 */
interface WorkerSlot {
  worker: Worker;
  inFlight: number;
}

/** Hard floor of 2, cap of 8. The pool is bounded by per-worker memory
 *  cost (~22 MB tessdata + ~15 MB WASM module = ~40 MB per worker), so
 *  going wider than 8 wastes RAM without buying throughput on most
 *  client hardware. */
function poolSize(): number {
  const cores = typeof navigator !== "undefined" && navigator.hardwareConcurrency
    ? navigator.hardwareConcurrency
    : 4;
  // Leave half the cores for the main thread + decoders + canvas.
  const target = Math.max(2, Math.min(8, Math.floor(cores / 2)));
  return target;
}

export class WASMProcessingService implements IProcessingService {
  private workers: WorkerSlot[] = [];
  private initialized = false;
  private initializationPromise: Promise<void> | null = null;
  private messageIdCounter = 0;
  /** Maps message id → the slot it was dispatched to + handlers. We
   *  need to know the slot to decrement inFlight when the message
   *  completes (success, error, or timeout). */
  private pendingRequests = new Map<
    string,
    {
      slot: WorkerSlot;
      resolve: (value: unknown) => void;
      reject: (error: Error) => void;
      onProgress?: ProcessingProgressCallback | undefined;
    }
  >();

  constructor() {
    this.spawnPool();
  }

  /** Number of workers in the pool. Used by the preprocessing service
   *  to size its OCR concurrency exactly to the pool. */
  getPoolSize(): number {
    return this.workers.length;
  }

  private spawnPool(): void {
    // Rust+leptess pipeline (wasm32-unknown-emscripten). Each worker
    // dynamically imports the Emscripten-compiled IosScreenTimePipeline.wasm
    // and mounts its own copy of eng.traineddata via the JS loader in
    // pipelineLoader.ts. Workers don't share LepTess state, which is
    // exactly what we want — Tesseract isn't reentrant.
    const n = poolSize();
    for (let i = 0; i < n; i++) {
      const worker = new Worker(
        new URL(
          "./processing/workers/imageProcessor.worker.emscripten.ts",
          import.meta.url,
        ),
        { type: "module" },
      );
      const slot: WorkerSlot = { worker, inFlight: 0 };
      worker.onmessage = (e: MessageEvent<WorkerResponse>) => this.onWorkerMessage(slot, e);
      worker.onerror = (error) => this.onWorkerError(slot, error);
      this.workers.push(slot);
    }
  }

  private onWorkerMessage(slot: WorkerSlot, e: MessageEvent<WorkerResponse>): void {
    const { type, id, payload, error } = e.data;

    if (type === "PROGRESS") {
      const progressData = payload as ProgressUpdate["payload"];
      const request = this.pendingRequests.get(id);
      if (request?.onProgress) {
        request.onProgress(progressData);
      }
      return;
    }

    const request = this.pendingRequests.get(id);
    if (!request) {
      console.warn(
        "[WASMProcessingService] No pending request for id:", id,
      );
      return;
    }

    // Defensive: the slot we matched the message to should be the same
    // one we dispatched to. Log if it isn't — that points at a routing
    // bug.
    if (request.slot !== slot) {
      console.warn(
        "[WASMProcessingService] Response from unexpected worker; routing the result anyway.",
      );
    }

    if (type === "ERROR") {
      console.error("[WASMProcessingService] Worker returned error:", error);
      request.reject(new Error(error || "Unknown error in worker"));
    } else {
      request.resolve(payload);
    }

    request.slot.inFlight = Math.max(0, request.slot.inFlight - 1);
    this.pendingRequests.delete(id);
  }

  private onWorkerError(slot: WorkerSlot, error: ErrorEvent): void {
    console.error("[WASMProcessingService] Worker error:", error);
    // Reject every request that was routed to this slot. Other slots
    // are unaffected.
    for (const [id, request] of this.pendingRequests.entries()) {
      if (request.slot === slot) {
        request.reject(new Error("Worker error: " + error.message));
        this.pendingRequests.delete(id);
      }
    }
    slot.inFlight = 0;
    // Don't recreate the dead worker yet — terminate() handles full
    // pool replacement; a single dead worker just shrinks effective
    // concurrency until then. This avoids surprise re-fetching of
    // tessdata on the hot path.
    this.initialized = false;
  }

  private generateMessageId(): string {
    return `msg_${++this.messageIdCounter}_${Date.now()}`;
  }

  /** Pick the worker with the fewest in-flight messages. Round-robin
   *  is fine for uniform jobs but OCR-heavy stages have a long tail,
   *  and least-loaded keeps the pool draining evenly. */
  private pickSlot(): WorkerSlot {
    let best = this.workers[0]!;
    for (let i = 1; i < this.workers.length; i++) {
      if (this.workers[i]!.inFlight < best.inFlight) {
        best = this.workers[i]!;
      }
    }
    return best;
  }

  /** Send a message to a SPECIFIC slot. Used by initialize() to fan
   *  out an INITIALIZE to every worker so they all load tessdata
   *  before the first PROCESS_IMAGE arrives. */
  private async sendMessageTo<T>(
    slot: WorkerSlot,
    message: Omit<WorkerMessage, "id">,
    onProgress?: ProcessingProgressCallback,
  ): Promise<T> {
    const id = this.generateMessageId();

    return new Promise<T>((resolve, reject) => {
      const timeoutMs = message.type === "INITIALIZE" ? 120000 : 60000;
      const timeout = setTimeout(() => {
        const pending = this.pendingRequests.get(id);
        if (pending) {
          pending.slot.inFlight = Math.max(0, pending.slot.inFlight - 1);
          this.pendingRequests.delete(id);
        }
        reject(
          new Error(
            `Worker message ${message.type} timed out after ${timeoutMs / 1000} seconds`,
          ),
        );
      }, timeoutMs);

      this.pendingRequests.set(id, {
        slot,
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
      slot.inFlight++;

      const fullMessage: WorkerMessage = { ...message, id };

      // Collect transferable ArrayBuffers from ImageData payloads for zero-copy transfer.
      const transferables: Transferable[] = [];
      const payload = fullMessage.payload as Record<string, unknown> | undefined;
      if (payload?.imageData && (payload.imageData as ImageData).data?.buffer) {
        transferables.push((payload.imageData as ImageData).data.buffer);
      }
      slot.worker.postMessage(fullMessage, transferables);
    });
  }

  /** Send a message to whichever worker is least busy. Used for the
   *  ordinary processImage / detectGrid / extract* calls. */
  private async sendMessage<T>(
    message: Omit<WorkerMessage, "id">,
    onProgress?: ProcessingProgressCallback,
  ): Promise<T> {
    if (this.workers.length === 0) {
      throw new Error("Worker pool not initialized");
    }
    return this.sendMessageTo<T>(this.pickSlot(), message, onProgress);
  }

  async initialize(): Promise<void> {
    if (this.initialized) return;

    if (this.initializationPromise) {
      return this.initializationPromise;
    }

    this.initializationPromise = (async () => {
      try {
        // Fan out INITIALIZE to every worker in parallel so they all
        // mount tessdata before the first real PROCESS_IMAGE lands.
        // The browser's HTTP cache + service worker dedupe the
        // eng.traineddata fetch across workers, so the first one pays
        // the network cost and the rest hit cache.
        await Promise.all(
          this.workers.map((slot) =>
            this.sendMessageTo(slot, { type: "INITIALIZE", payload: {} }),
          ),
        );
        this.initialized = true;
      } catch (error) {
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
    if (!this.initialized) {
      await this.initialize();
    }

    const imgData =
      imageData instanceof Blob
        ? await smartConvertBlobToImageData(imageData)
        : imageData;

    return await this.sendMessage<ProcessImageResponse["payload"]>(
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
    const imgData = await this.ensureReadyAndConvert(imageData);
    const result = await this.sendMessage<{
      gridCoordinates: GridCoordinates | null;
    }>({
      type: "DETECT_GRID",
      payload: { imageData: imgData, imageType, method },
    });
    return result.gridCoordinates;
  }

  terminate(): void {
    for (const slot of this.workers) {
      slot.worker.terminate();
    }
    this.workers = [];
    this.initialized = false;
    this.initializationPromise = null;
    for (const request of this.pendingRequests.values()) {
      request.reject(new Error("Worker pool terminated"));
    }
    this.pendingRequests.clear();
    // Recreate the pool so the service can be used again
    this.spawnPool();
  }
}
