# Chapter 02: WASM Processing

## Decision Framework

Not everything belongs in a Web Worker, and not everything needs Rust-to-WASM compilation. Use this table to decide:

| Factor | JS/TS Web Worker | Rust to WASM |
|--------|-----------------|--------------|
| **Build complexity** | None -- Vite handles Worker bundling natively via `new Worker(new URL(...), { type: "module" })` | Requires `wasm-pack`, `wasm-bindgen`, cargo build step, WASM binary in `public/` |
| **Performance** | Sufficient for I/O-bound work, image manipulation via Canvas API, OCR orchestration | 2-10x faster for CPU-bound loops: pixel iteration, matrix math, compression |
| **Ecosystem access** | Full npm ecosystem (Tesseract.js, Dexie, etc.) | Rust crate ecosystem (image, tesseract-rs), but no DOM or Web API access without `wasm-bindgen` |
| **Debugging** | Standard browser DevTools, source maps, breakpoints | `console_error_panic_hook` + limited WASM debugging in Chrome DevTools |
| **Bundle size** | Only the JS you import | Base WASM overhead ~50-100KB + your code. Tesseract WASM core alone is ~3MB |
| **Memory model** | GC-managed, SharedArrayBuffer for cross-thread | Manual (Rust ownership) or `wasm-bindgen` bridging. Must manage linear memory carefully |
| **Hiring/maintenance** | Any TypeScript developer | Requires Rust competence on the team |

**Rule of thumb**: Use JS/TS Workers unless the operation is CPU-bound and already has a Rust implementation you are porting. The debugging and maintenance costs of Rust-to-WASM are significant.

In this codebase, all WASM-mode processing uses JS/TS Workers. Tesseract.js itself is a pre-compiled C++-to-WASM binary consumed as an npm package -- you do not compile it. The grid detection, bar extraction, and image preprocessing are TypeScript running in a Worker thread using `OffscreenCanvas`.

---

## JS/TS Web Worker Pattern

### Message Protocol

All Worker communication uses a typed message protocol with request-response correlation:

```typescript
// frontend/src/core/implementations/wasm/processing/workers/types.ts

export interface WorkerMessage {
  type: string;
  id: string;
  payload: WorkerMessagePayload;
}

export interface WorkerResponse {
  type: string;
  id: string;
  payload?: WorkerResponsePayload;
  error?: string;
}
```

Every message has three fields:
- `type`: Discriminator for the operation (`"INITIALIZE"`, `"PROCESS_IMAGE"`, `"DETECT_GRID"`, etc.)
- `id`: Unique correlation ID (format: `msg_{counter}_{timestamp}`) so responses can be matched to requests
- `payload`: Operation-specific data

### Message Types

Request payloads are discriminated unions:

```typescript
export type WorkerMessagePayload =
  | InitializePayload
  | ProcessImagePayload
  | ExtractTitlePayload
  | ExtractTotalPayload
  | ExtractHourlyDataPayload
  | DetectGridPayload;

export interface InitializePayload {}

export interface ProcessImagePayload {
  imageData: ImageData;
  imageType: ImageType;
  gridCoordinates?: GridCoordinates;
  maxShift?: number;
}

export interface DetectGridPayload {
  imageData: ImageData;
  imageType: ImageType;
  method?: "ocr_anchored" | "line_based";
}
```

Response payloads are similarly typed:

```typescript
export type WorkerResponsePayload =
  | ProcessImageResponsePayload
  | ProgressPayload
  | InitializeCompletePayload
  | ExtractTitleResponsePayload
  | ExtractTotalResponsePayload
  | ExtractHourlyDataResponsePayload
  | DetectGridResponsePayload;

export interface ProcessImageResponsePayload {
  hourlyData: HourlyData;
  title: string | null;
  total: string | null;
  gridCoordinates?: GridCoordinates;
  gridDetectionFailed?: boolean;
  gridDetectionError?: string;
  alignmentScore?: number | null;
}

export interface ProgressPayload {
  stage: "loading" | "preprocessing" | "ocr_title" | "ocr_total"
       | "ocr_hourly" | "complete";
  progress: number;
  message?: string;
}
```

### Progress Reporting

The Worker sends `PROGRESS` messages mid-operation. These are not request-response -- they are fire-and-forget notifications correlated by the same `id` as the original request:

```typescript
// Inside the Worker
self.postMessage({
  type: "PROGRESS",
  id: requestId,
  payload: {
    stage: "ocr_title",
    progress: 0.4,
    message: "Extracting title text...",
  },
});
```

The service wrapper routes these to a callback without resolving the pending promise:

```typescript
// In WASMProcessingService.worker.onmessage handler
if (type === "PROGRESS") {
  const progressData = payload as ProgressUpdate["payload"];
  const request = this.pendingRequests.get(id);
  if (request && request.onProgress) {
    request.onProgress(progressData);
  }
  return; // Do not resolve/reject -- the operation is still running
}
```

---

## Processing Service Wrapper

`WASMProcessingService` wraps the raw Worker with a promise-based RPC layer. Every public method sends a typed message and returns a promise that resolves when the Worker responds.

### Initialization

```typescript
export class WASMProcessingService implements IProcessingService {
  private worker: Worker | null = null;
  private initialized = false;
  private initializationPromise: Promise<void> | null = null;
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
    this.worker = new Worker(
      new URL(
        "./processing/workers/imageProcessor.worker.canvas.ts",
        import.meta.url,
      ),
      { type: "module" },
    );

    this.worker.onmessage = (e: MessageEvent<WorkerResponse>) => {
      // ... message routing (see below)
    };

    this.worker.onerror = (error) => {
      this.initialized = false;
      this.pendingRequests.forEach((request) => {
        request.reject(new Error("Worker error: " + error.message));
      });
      this.pendingRequests.clear();
    };
  }
}
```

The Worker is created in the constructor using Vite's Worker URL pattern (`new URL("...", import.meta.url)`). Vite transforms this at build time into a separate chunk. The `{ type: "module" }` flag enables ES module imports inside the Worker.

### Message Correlation and Timeouts

```typescript
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

  return new Promise<T>((resolve, reject) => {
    // INITIALIZE downloads ~15MB of Tesseract WASM + trained data
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

    // Zero-copy transfer for ImageData buffers
    const transferables: Transferable[] = [];
    const payload = message.payload as Record<string, unknown> | undefined;
    if (payload?.imageData && (payload.imageData as ImageData).data?.buffer) {
      transferables.push((payload.imageData as ImageData).data.buffer);
    }
    this.worker!.postMessage({ ...message, id }, transferables);
  });
}
```

Key design decisions:

| Aspect | Implementation | Rationale |
|--------|---------------|-----------|
| **Timeout: 120s for INITIALIZE** | `message.type === "INITIALIZE" ? 120000 : 60000` | First init downloads ~15MB of Tesseract WASM + trained language data. On slow connections this takes 30-60s. |
| **Timeout: 60s for messages** | Default timeout | Processing a single image with OCR can take 10-20s. 60s provides headroom for large/complex images. |
| **Pending request map** | `Map<string, { resolve, reject, onProgress }>` | Multiple operations can be in-flight simultaneously (e.g., detect grid while extracting title). Each is correlated by ID. |
| **Transferable objects** | `transferables.push(payload.imageData.data.buffer)` | `ImageData.data` is a `Uint8ClampedArray` backed by an `ArrayBuffer`. Transferring it moves ownership to the Worker thread with zero memory copy. The main thread's reference becomes detached (unusable). |

### Initialization Guard

```typescript
async initialize(): Promise<void> {
  if (this.initialized) return;

  // If initialization is in progress, wait for it (prevents race condition)
  if (this.initializationPromise) return this.initializationPromise;

  this.initializationPromise = (async () => {
    try {
      await this.sendMessage({ type: "INITIALIZE", payload: {} });
      this.initialized = true;
    } catch (error) {
      this.initializationPromise = null; // Allow retry on failure
      throw error;
    }
  })();

  return this.initializationPromise;
}
```

Three states:
1. `initialized === true`: Return immediately.
2. `initializationPromise !== null`: Another caller is already initializing. Await the same promise (no duplicate downloads).
3. Neither: Start initialization, cache the promise.

If initialization fails (network error downloading Tesseract data), the promise is cleared so the next call retries.

### Public API Methods

Each method follows the same pattern: ensure initialized, convert Blob to ImageData if needed, send typed message, return typed response:

```typescript
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
  if (!this.initialized) await this.initialize();

  const imgData = imageData instanceof Blob
    ? await smartConvertBlobToImageData(imageData)
    : imageData;

  return this.sendMessage<ProcessImageResponsePayload>(
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
```

The `smartConvertBlobToImageData` conversion happens on the main thread (it needs DOM access for `createImageBitmap`). The resulting `ImageData` is then transferred to the Worker.

### Termination and Recovery

```typescript
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
```

`terminate()` kills the Worker thread, rejects all pending promises, then immediately creates a fresh Worker. The next `processImage()` call will trigger `initialize()` again (downloading Tesseract data). This is used for:

- Canceling a stuck OCR operation
- `forceStop()` in the preprocessing pipeline
- Container cleanup on `beforeunload` (though in this case the tab is closing, so recreation is moot)

---

## Rust-to-WASM Pattern

This codebase does not currently use Rust-to-WASM, but the architecture supports it. Here is the integration pattern for when CPU-bound operations justify the build complexity.

### Build Setup

```bash
# Install wasm-pack
cargo install wasm-pack

# Build for browser target (generates ES module + WASM binary)
wasm-pack build --target web --out-dir frontend/src/wasm/pkg
```

The `--target web` flag generates:
- `pkg/your_crate_bg.wasm` -- the compiled WASM binary
- `pkg/your_crate.js` -- JS glue with `wasm-bindgen` bindings
- `pkg/your_crate.d.ts` -- TypeScript type definitions

### Rust Side

```rust
// src/lib.rs
use wasm_bindgen::prelude::*;

#[wasm_bindgen]
pub struct ImageProcessor {
    width: u32,
    height: u32,
}

#[wasm_bindgen]
impl ImageProcessor {
    #[wasm_bindgen(constructor)]
    pub fn new(width: u32, height: u32) -> Self {
        console_error_panic_hook::set_once();
        Self { width, height }
    }

    /// Process raw RGBA pixel data.
    #[wasm_bindgen]
    pub fn detect_grid(&self, pixels: &[u8]) -> JsValue {
        // CPU-intensive pixel analysis
        serde_wasm_bindgen::to_value(&result).unwrap()
    }
}
```

### TypeScript Side (Worker)

```typescript
// Inside the Web Worker
import init, { ImageProcessor } from "@/wasm/pkg/your_crate";

let processor: ImageProcessor | null = null;

async function initialize() {
  await init();
  processor = new ImageProcessor(0, 0);
}

function detectGrid(imageData: ImageData): GridCoordinates | null {
  if (!processor) throw new Error("WASM not initialized");
  const result = processor.detect_grid(imageData.data);
  return result as GridCoordinates | null;
}
```

### Comlink for Typed RPC (Alternative to Manual Messages)

For simpler Worker APIs, [Comlink](https://github.com/GoogleChromeLabs/comlink) provides proxy-based RPC that eliminates manual message correlation:

```typescript
// worker.ts
import * as Comlink from "comlink";

const api = {
  async detectGrid(pixels: Uint8ClampedArray, width: number, height: number) {
    // ... processing
    return gridCoordinates;
  },
};

Comlink.expose(api);

// main thread
import * as Comlink from "comlink";

const worker = new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });
const api = Comlink.wrap<typeof import("./worker").api>(worker);

// Looks like a direct function call, but runs in the Worker
const grid = await api.detectGrid(imageData.data, width, height);
```

This codebase uses manual message correlation instead of Comlink because:
1. Progress reporting requires interleaved messages (Comlink does not handle this natively)
2. Transferable objects require explicit handling at the `postMessage` boundary
3. Timeout management per-message-type is not supported by Comlink's proxy model

### Zero-Copy Transfers with Rust-WASM

When passing large buffers (image pixels) between JS and WASM:

```rust
// Rust: Accept a reference (borrows from JS memory, zero-copy)
#[wasm_bindgen]
pub fn process(pixels: &[u8]) -> Vec<u8> { ... }

// Rust: Accept ownership (copies from JS to WASM linear memory)
#[wasm_bindgen]
pub fn process(pixels: Vec<u8>) -> Vec<u8> { ... }
```

Prefer `&[u8]` (borrow) when the Rust code only reads the data. Use `Vec<u8>` when the Rust code needs to own and modify the data. The return value (`Vec<u8>`) is always copied back to JS memory.

For truly zero-copy round-trips, operate directly on the WASM linear memory:

```typescript
// JS side
const ptr = processor.alloc(imageData.data.length);
const wasmMemory = new Uint8Array(processor.memory.buffer, ptr, imageData.data.length);
wasmMemory.set(imageData.data); // Write directly into WASM memory
processor.process_in_place(ptr, imageData.data.length);
// Read results back from the same memory region
const result = new Uint8ClampedArray(processor.memory.buffer, ptr, imageData.data.length);
processor.dealloc(ptr, imageData.data.length);
```

This avoids all copies but requires manual memory management. Only use this for performance-critical hot paths where profiling shows the copy overhead is significant.

---

## OffscreenCanvas

Workers cannot access the DOM. `OffscreenCanvas` provides Canvas 2D (and WebGL) rendering in Workers without DOM access.

### Usage in This Codebase

The image processing Worker uses `OffscreenCanvas` for:
- Decoding image blobs into pixel data
- Drawing cropped regions for OCR
- Color space conversion (dark mode detection)
- Bar graph pixel sampling

```typescript
// Inside the Worker (imageProcessor.worker.canvas.ts)
function imageDataFromPixels(
  width: number,
  height: number,
  pixels: Uint8ClampedArray,
): ImageData {
  return new ImageData(pixels, width, height);
}

function cropRegion(
  imageData: ImageData,
  x: number, y: number,
  width: number, height: number,
): ImageData {
  const canvas = new OffscreenCanvas(width, height);
  const ctx = canvas.getContext("2d")!;
  ctx.putImageData(imageData, -x, -y);
  return ctx.getImageData(0, 0, width, height);
}
```

### Platform Support

| Platform | OffscreenCanvas Support |
|----------|------------------------|
| Chrome 69+ | Full support |
| Firefox 105+ | Full support |
| Safari 16.4+ | Full support |
| Tauri (system webview) | Depends on OS webview version. macOS 13+ (WebKit), Windows (Edge/Chromium), Linux (WebKitGTK 2.40+) |

**Fallback strategy**: If `OffscreenCanvas` is unavailable (unlikely in 2024+ targets), fall back to main-thread Canvas rendering. This blocks the UI during processing but produces correct results:

```typescript
function getCanvas(width: number, height: number): OffscreenCanvas | HTMLCanvasElement {
  if (typeof OffscreenCanvas !== "undefined") {
    return new OffscreenCanvas(width, height);
  }
  // Fallback: create a hidden DOM canvas (main thread only)
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  return canvas;
}
```

---

## CSP Requirements

Web Workers and WASM require specific Content Security Policy directives.

### Required Directives

The `worker-src` directive must include `'self' blob:`:
- `'self'` allows Workers loaded from the same origin
- `blob:` is required because Vite may emit Workers as blob URLs during development (HMR)
- In production builds only `'self'` is needed, but including `blob:` prevents dev/prod CSP drift

The `script-src` directive must include the WASM instantiation permission (`wasm-unsafe-eval` -- note this is a CSP keyword, not actual code). This is the narrowest CSP directive that permits `WebAssembly.instantiate`. Do NOT use the broader `unsafe-eval` keyword, which also permits arbitrary string-to-code conversion that is unnecessary and dangerous.

### Nginx Configuration

```nginx
# docker/nginx/nginx.conf (relevant CSP header)
# The wasm-unsafe-eval keyword permits WebAssembly compilation only
add_header Content-Security-Policy
  "default-src 'self'; "
  "script-src 'self' 'wasm-unsafe-eval'; "
  "worker-src 'self' blob:; "
  "style-src 'self' 'unsafe-inline'; "
  "img-src 'self' blob: data:; "
  "connect-src 'self' ws: wss:; "
  always;
```

### Tauri CSP

Tauri v2 uses a capability-based security model. CSP is configured in `tauri.conf.json`. The same directives apply, with the addition of `asset:` and `https://asset.localhost` for Tauri's asset protocol (loading images from the app bundle or local filesystem).

### Common CSP Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `Refused to create a worker` | Missing `blob:` in `worker-src` | Add `blob:` to `worker-src` |
| `Refused to compile or instantiate WebAssembly module` | Missing WASM permission in `script-src` | Add the WASM CSP keyword to `script-src` |
| `Refused to load the script because it violates the CSP` | Worker script blocked by `script-src` | Ensure `worker-src` is set (it falls back to `script-src` if missing) |

---

## Note on OCR

Tesseract.js is the only viable browser-based OCR engine for this workload. It is a JavaScript/WASM port of the C++ Tesseract 5.x engine, maintained by the [naptha/tesseract.js](https://github.com/naptha/tesseract.js) project.

### What It Provides

- Pre-compiled WASM binary (~3MB) + trained language data (~15MB for English)
- JavaScript API that wraps the WASM module
- Worker-based execution (it creates its own Worker internally, but in this codebase we run it inside our Worker to control the lifecycle)
- Text extraction with bounding boxes (needed for grid anchor detection)

### What It Does Not Provide

- GPU acceleration (browser WASM does not expose GPU compute)
- Multi-language packs without additional downloads
- Vision-LLM quality (no contextual understanding, struggles with unusual fonts)
- Bounding box confidence scores comparable to PaddleOCR

### Server vs WASM OCR Quality

The server uses a three-engine fallback chain: HunyuanOCR (vision LLM) -> PaddleOCR (neural network) -> Tesseract (traditional). WASM mode only has Tesseract.

Impact on this project:

| OCR Task | Server Quality | WASM Quality | Degradation |
|----------|---------------|--------------|-------------|
| Grid anchor detection ("12 AM", "60") | High (PaddleOCR bboxes) | Moderate (Tesseract bboxes) | Occasional misalignment |
| Title extraction | High (Hunyuan LLM) | Low-moderate (Tesseract) | Misreads some app names |
| Total usage extraction | High (Hunyuan LLM) | Moderate (Tesseract) | "1h 23m" sometimes read as "1h 28m" |
| Daily page detection | High | Moderate | May miss some daily total pages |

**No pure-Rust browser OCR alternative exists** that matches Tesseract.js quality. PaddleOCR has an unofficial WASM port but it is unmaintained and 30MB+. The practical path to better WASM OCR is:

1. Ship with Tesseract.js (current state)
2. When Tauri mode is available, call server-side OCR engines via Tauri HTTP commands (best of both worlds: local-first with optional server-quality OCR)
3. Monitor the Rust OCR ecosystem for a `leptonica` + `tesseract` crate that compiles to WASM cleanly

### Tesseract.js Integration

The Worker initializes Tesseract with a pre-downloaded language data path:

```typescript
// Inside imageProcessor.worker.canvas.ts (simplified)
import { createWorker } from "tesseract.js";

let tesseractWorker: Tesseract.Worker | null = null;

async function initialize() {
  tesseractWorker = await createWorker("eng", 1, {
    workerPath: "/tesseract/worker.min.js",
    corePath: "/tesseract/tesseract-core-simd.wasm.js",
    langPath: "/tesseract/lang-data",
  });
}

async function extractText(imageData: ImageData): Promise<string> {
  if (!tesseractWorker) throw new Error("Tesseract not initialized");
  const { data } = await tesseractWorker.recognize(imageData);
  return data.text;
}
```

The language data files are served as static assets (placed in `public/tesseract/` at build time). This avoids CDN dependency and works fully offline.

---

## Processing Pipeline: Python to TypeScript Port

The WASM processing pipeline mirrors the Python server-side pipeline. Each Python module has a TypeScript counterpart:

| Python Module | TypeScript Port | Purpose |
|---------------|----------------|---------|
| `core/image_processor.py` (`slice_image`) | `processing/barExtraction.canvas.ts` | Extract 24 hourly bar heights from graph ROI |
| `core/grid_detectors.py` | `processing/gridDetection.canvas.ts` | Find grid boundaries using OCR anchors |
| `core/line_based_detection/` | `processing/lineBasedDetection.canvas.ts` | Alternative grid detection using visual line patterns |
| `core/bar_processor.py` | `processing/barExtraction.canvas.ts` | Bar height measurement from pixel colors |
| `core/ocr.py` | `processing/ocr.canvas.ts` | Title and total text extraction |
| `core/image_processor.py` (normalization) | `processing/imageUtils.canvas.ts` | Dark mode conversion, contrast adjustment |

### Porting Considerations

**Pixel coordinate systems**: Python uses (row, col) indexing with PIL/OpenCV. TypeScript Canvas uses (x, y). The mapping is `x = col`, `y = row`. Off-by-one errors in this mapping cause grid misalignment that is invisible in unit tests but produces wrong hourly values.

**Color space**: PIL's `getpixel()` returns (R, G, B, A) or (R, G, B). Canvas `getImageData()` returns a flat `Uint8ClampedArray` in RGBA order with stride `width * 4`. Accessing pixel (x, y):

```typescript
const idx = (y * width + x) * 4;
const r = data[idx];
const g = data[idx + 1];
const b = data[idx + 2];
const a = data[idx + 3];
```

**Numerical precision**: Python uses 64-bit floats by default. JavaScript also uses 64-bit floats (`Number`), so there is no precision loss. However, intermediate rounding in integer division can differ:

```python
# Python: integer division truncates toward zero
bar_height = pixel_count // column_width  # 7 // 2 = 3
```

```typescript
// TypeScript: must explicitly truncate
const barHeight = Math.trunc(pixelCount / columnWidth); // 7 / 2 = 3.5 -> 3
// NOT Math.floor(), which differs for negative numbers
```

**Image decoding**: Python decodes images with PIL (`Image.open()`). In the browser, use `createImageBitmap()` for async decoding, then draw to `OffscreenCanvas` to get `ImageData`:

```typescript
async function blobToImageData(blob: Blob): Promise<ImageData> {
  const bitmap = await createImageBitmap(blob);
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const ctx = canvas.getContext("2d")!;
  ctx.drawImage(bitmap, 0, 0);
  bitmap.close(); // Release bitmap memory
  return ctx.getImageData(0, 0, canvas.width, canvas.height);
}
```

### Regression Testing Strategy

When porting algorithms from Python to TypeScript, maintain a set of test images with known-good Python outputs:

1. Run the Python pipeline on each test image, save the output (grid coordinates, hourly values, title, total) as JSON
2. Run the TypeScript pipeline on the same images in a Playwright test
3. Compare outputs with tolerance thresholds:
   - Grid coordinates: exact match (pixel-level)
   - Hourly values: within +/- 1 minute (accounts for minor pixel-sampling differences)
   - Title/total: fuzzy string match (OCR quality will differ between engines)

Store test images in `tests/fixtures/` and reference them from both Python `pytest` tests and Playwright tests.
