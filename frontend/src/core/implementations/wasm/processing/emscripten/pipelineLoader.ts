/**
 * Loader for the Emscripten-compiled pipeline (Path B).
 *
 * The emscripten build produces IosScreenTimePipeline.js + .wasm which are
 * placed in /pipeline-em/ at build time (see scripts/build-wasm-emscripten.sh).
 *
 * This module handles:
 *  1. Dynamically importing the Emscripten JS glue
 *  2. Fetching + mounting eng.traineddata into the Emscripten virtual FS
 *  3. Providing typed wrappers around the raw C-ABI exports
 */

export interface EmPipelineResult {
  success: boolean;
  hourly_values?: number[];
  total?: number;
  alignment_score?: number;
  title?: string | null;
  total_text?: string | null;
  is_daily_total?: boolean;
  grid_bounds?: {
    upper_left_x: number;
    upper_left_y: number;
    lower_right_x: number;
    lower_right_y: number;
  };
  grid_confidence?: number;
  error?: string;
  ocr_error?: string | null;
}

export interface EmGridResult {
  success: boolean;
  bounds?: {
    upper_left_x: number;
    upper_left_y: number;
    lower_right_x: number;
    lower_right_y: number;
  } | null;
  confidence: number;
  method: string;
  error?: string;
}

export interface EmOcrResult {
  title?: string | null;
  total_text?: string | null;
  is_daily_total?: boolean;
  ocr_error?: string | null;
  error?: string;
}

/** Per-word OCR result for PHI detection. `char_start`/`char_end` are
 *  offsets into the joined `full_text` (space-separated), so JS can map
 *  regex/NER matches back to image bboxes without re-tokenizing. */
export interface EmPhiWord {
  text: string;
  x: number;
  y: number;
  w: number;
  h: number;
  conf: number;
  char_start: number;
  char_end: number;
}

export interface EmPhiWordsResult {
  success: boolean;
  words?: EmPhiWord[];
  full_text?: string;
  avg_confidence?: number;
  error?: string;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type EmscriptenModule = any;

let modulePromise: Promise<EmscriptenModule> | null = null;

// Resolve relative to the bundled chunk URL. Under GitHub Pages this becomes
// `https://<host>/<repo>/assets/<chunk>.js`, so `../pipeline-em/` lands at
// `<repo>/pipeline-em/`. An absolute `/pipeline-em/` would break the subpath.
const BASE = new URL("../pipeline-em/", import.meta.url).href;
const OUTPUT_BUFFER_SIZE = 65536; // 64 KB — enough for any JSON result

async function loadModule(): Promise<EmscriptenModule> {
  if (modulePromise) return modulePromise;

  modulePromise = (async () => {
    const scriptUrl = `${BASE}IosScreenTimePipeline.js`;

    let factory: (opts: object) => Promise<EmscriptenModule>;

    // Workers don't have `document` — use fetch + new Function instead of a script tag.
    if (typeof document === "undefined") {
      const src = await fetch(scriptUrl).then((r) => {
        if (!r.ok) throw new Error(`Failed to fetch ${scriptUrl}: ${r.status}`);
        return r.text();
      });
      // eslint-disable-next-line no-new-func
      factory = new Function(`${src}; return IosScreenTimePipeline;`)() as typeof factory;
    } else {
      await new Promise<void>((resolve, reject) => {
        const script = document.createElement("script");
        script.src = scriptUrl;
        script.onload = () => resolve();
        script.onerror = () => reject(new Error(`Failed to load ${scriptUrl}`));
        document.head.appendChild(script);
      });
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      factory = (globalThis as any).IosScreenTimePipeline as typeof factory; // ast-grep-ignore: no-as-any
    }

    if (typeof factory !== "function") {
      throw new Error("IosScreenTimePipeline factory not found");
    }

    const mod: EmscriptenModule = await factory({
      locateFile: (name: string) => `${BASE}${name}`,
    });

    // Mount eng.traineddata into the Emscripten virtual filesystem.
    const tessdata = await fetch(`${BASE}eng.traineddata`).then((r) => {
      if (!r.ok) throw new Error(`Failed to fetch eng.traineddata: ${r.status}`);
      return r.arrayBuffer();
    });

    mod.FS.mkdir("/tesseract");
    mod.FS.writeFile("/tesseract/eng.traineddata", new Uint8Array(tessdata));

    return mod;
  })();

  return modulePromise;
}

function encodeNullTerminated(str: string): Uint8Array {
  const enc = new TextEncoder();
  const bytes = enc.encode(str);
  const buf = new Uint8Array(bytes.length + 1);
  buf.set(bytes);
  buf[bytes.length] = 0;
  return buf;
}

/**
 * Run the full pipeline (OCR + grid + bars) on raw RGBA image data.
 */
export async function emPipelineProcess(
  imageData: ImageData,
  imageType: "screen_time" | "battery",
  options?: {
    maxShift?: number;
    gridCoordinates?: {
      upper_left: { x: number; y: number };
      lower_right: { x: number; y: number };
    };
  },
): Promise<EmPipelineResult> {
  const mod = await loadModule();

  const rgba = imageData.data as Uint8ClampedArray;
  const width = imageData.width;
  const height = imageData.height;

  const maxShift = options?.maxShift ?? 0;
  const gc = options?.gridCoordinates;
  const gridUlX = gc ? gc.upper_left.x : -1;
  const gridUlY = gc ? gc.upper_left.y : -1;
  const gridLrX = gc ? gc.lower_right.x : -1;
  const gridLrY = gc ? gc.lower_right.y : -1;

  const rgbaPtr = mod._pipeline_alloc(rgba.length);
  const outPtr = mod._pipeline_alloc(OUTPUT_BUFFER_SIZE);
  const imageTypeBytes = encodeNullTerminated(imageType);
  const imgTypePtr = mod._pipeline_alloc(imageTypeBytes.length);

  try {
    mod.HEAPU8.set(rgba, rgbaPtr);
    mod.HEAPU8.set(imageTypeBytes, imgTypePtr);

    const written: number = mod._pipeline_process(
      rgbaPtr,
      rgba.length,
      width,
      height,
      imgTypePtr,
      maxShift,
      gridUlX,
      gridUlY,
      gridLrX,
      gridLrY,
      outPtr,
      OUTPUT_BUFFER_SIZE,
    );

    if (written < 0) {
      return { success: false, error: "Output buffer too small" };
    }

    const json = new TextDecoder().decode(mod.HEAPU8.subarray(outPtr, outPtr + written));
    return JSON.parse(json) as EmPipelineResult;
  } finally {
    mod._pipeline_free(rgbaPtr, rgba.length);
    mod._pipeline_free(outPtr, OUTPUT_BUFFER_SIZE);
    mod._pipeline_free(imgTypePtr, imageTypeBytes.length);
  }
}

/**
 * Grid detection only.
 *
 * `options.method`: 0 = OcrAnchored with LineBased fallback (default, matches canvas),
 *                   1 = LineBased only (fast, no OCR).
 */
export async function emDetectGrid(
  imageData: ImageData,
  options?: { method?: 0 | 1 },
): Promise<EmGridResult> {
  const mod = await loadModule();

  const rgba = imageData.data as Uint8ClampedArray;
  const width = imageData.width;
  const height = imageData.height;
  const method = options?.method ?? 0;

  const rgbaPtr = mod._pipeline_alloc(rgba.length);
  const outPtr = mod._pipeline_alloc(OUTPUT_BUFFER_SIZE);

  try {
    mod.HEAPU8.set(rgba, rgbaPtr);

    const written: number = mod._pipeline_detect_grid(
      rgbaPtr,
      rgba.length,
      width,
      height,
      method,
      outPtr,
      OUTPUT_BUFFER_SIZE,
    );

    if (written < 0) {
      return { success: false, confidence: 0, method: "line_based", error: "Buffer too small" };
    }

    const json = new TextDecoder().decode(mod.HEAPU8.subarray(outPtr, outPtr + written));
    return JSON.parse(json) as EmGridResult;
  } finally {
    mod._pipeline_free(rgbaPtr, rgba.length);
    mod._pipeline_free(outPtr, OUTPUT_BUFFER_SIZE);
  }
}

/**
 * OCR-only extraction — no grid detection, no bar extraction.
 *
 * Crops to the top 45% of the image and runs Tesseract to extract title and
 * total usage text. Use for EXTRACT_TITLE / EXTRACT_TOTAL to avoid the cost
 * of full OcrAnchored grid detection.
 */
export async function emExtractOcr(imageData: ImageData): Promise<EmOcrResult> {
  const mod = await loadModule();

  const rgba = imageData.data as Uint8ClampedArray;
  const width = imageData.width;
  const height = imageData.height;

  const rgbaPtr = mod._pipeline_alloc(rgba.length);
  const outPtr = mod._pipeline_alloc(OUTPUT_BUFFER_SIZE);

  try {
    mod.HEAPU8.set(rgba, rgbaPtr);

    const written: number = mod._pipeline_extract_ocr(
      rgbaPtr,
      rgba.length,
      width,
      height,
      outPtr,
      OUTPUT_BUFFER_SIZE,
    );

    if (written < 0) {
      return { error: "Output buffer too small" };
    }

    const json = new TextDecoder().decode(mod.HEAPU8.subarray(outPtr, outPtr + written));
    return JSON.parse(json) as EmOcrResult;
  } finally {
    mod._pipeline_free(rgbaPtr, rgba.length);
    mod._pipeline_free(outPtr, OUTPUT_BUFFER_SIZE);
  }
}

/**
 * Full-page OCR for PHI detection. Returns every word with bbox + confidence
 * + character offsets into the joined `full_text`. Replaces Tesseract.js for
 * the PHI redaction pipeline.
 *
 * The output buffer is 1 MB rather than 64 KB because a long screenshot
 * (multi-app summary view) can have hundreds of words and the JSON balloons.
 */
const PHI_OUTPUT_BUFFER_SIZE = 1024 * 1024; // 1 MB

export async function emPhiWords(imageData: ImageData): Promise<EmPhiWordsResult> {
  const mod = await loadModule();

  const rgba = imageData.data as Uint8ClampedArray;
  const width = imageData.width;
  const height = imageData.height;

  const rgbaPtr = mod._pipeline_alloc(rgba.length);
  const outPtr = mod._pipeline_alloc(PHI_OUTPUT_BUFFER_SIZE);

  try {
    mod.HEAPU8.set(rgba, rgbaPtr);

    const written: number = mod._pipeline_phi_words(
      rgbaPtr,
      rgba.length,
      width,
      height,
      outPtr,
      PHI_OUTPUT_BUFFER_SIZE,
    );

    if (written < 0) {
      return { success: false, error: "Output buffer too small" };
    }

    const json = new TextDecoder().decode(mod.HEAPU8.subarray(outPtr, outPtr + written));
    return JSON.parse(json) as EmPhiWordsResult;
  } finally {
    mod._pipeline_free(rgbaPtr, rgba.length);
    mod._pipeline_free(outPtr, PHI_OUTPUT_BUFFER_SIZE);
  }
}
