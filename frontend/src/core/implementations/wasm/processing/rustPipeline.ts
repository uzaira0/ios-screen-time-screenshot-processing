/**
 * TypeScript wrapper around the Rust WASM processing pipeline (Tier 1).
 *
 * The Rust crate `ios-screen-time-image-pipeline` is compiled to
 * wasm32-unknown-unknown via wasm-pack (scripts/build-wasm-bindgen.sh) and
 * exposes the pixel-analysis parts of the pipeline: grid detection
 * (line-based), bar extraction + alignment, OCR-word parsing, and text
 * normalization.
 *
 * OCR itself is still run by Tesseract.js on the JS side; the raw word list
 * is passed into `parseOcrResult` for the Rust-native spatial filtering that
 * produces `title`, `title_y`, `total_text`, and the daily-total flag.
 *
 * Tier 2 will replace Tesseract.js with leptess-via-Emscripten and this
 * module will be superseded by `rustPipelineEm.ts`.
 */

import init, {
  check_is_daily_total,
  detect_grid,
  extract_bars,
  normalize_ocr_text,
  parse_ocr_result,
} from "@/wasm/pkg/ios_screen_time_image_pipeline";
import type { GridCoordinates } from "@/types";

// ── Types ────────────────────────────────────────────────────────────────────

/** Rust-side grid bounds shape (snake_case, flat i32 fields). */
export interface GridBoundsRust {
  upper_left_x: number;
  upper_left_y: number;
  lower_right_x: number;
  lower_right_y: number;
}

/** Result shape returned by Rust's `detect_grid`. */
export interface DetectGridResult {
  success: boolean;
  bounds: GridBoundsRust | null;
  confidence: number;
  method: string;
  error: string | null;
}

/** Result shape returned by Rust's `extract_bars`. */
export interface ExtractBarsResult {
  hourly_values: number[];
  total: number;
  alignment_score: number;
}

/** Minimal OCR word shape consumed by `parseOcrResult`. */
export interface OcrWord {
  text: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Result shape returned by Rust's `parse_ocr_result`. */
export interface ParseOcrResult {
  title: string;
  title_y: number;
  total_text: string;
  is_daily_total: boolean;
}

// ── Initialization ───────────────────────────────────────────────────────────

let initPromise: Promise<void> | null = null;

/**
 * Lazily instantiate the WASM module. Safe to call concurrently — all callers
 * await the same in-flight promise. First call triggers the ~1.2 MB fetch.
 */
export function initRustPipeline(): Promise<void> {
  if (!initPromise) {
    initPromise = init().then(() => undefined);
  }
  return initPromise;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Zero-copy view of `ImageData.data` as a Uint8Array. The underlying buffer is
 * shared; wasm-bindgen will copy into WASM linear memory on the call boundary,
 * but we avoid a premature JS-side copy here.
 */
function rgbaView(imageData: ImageData): Uint8Array {
  return new Uint8Array(
    imageData.data.buffer,
    imageData.data.byteOffset,
    imageData.data.byteLength,
  );
}

/** Rust {upper_left_x,…} → TS {upper_left: {x, y}, lower_right: {x, y}}. */
export function gridBoundsRustToCoordinates(
  bounds: GridBoundsRust,
): GridCoordinates {
  return {
    upper_left: { x: bounds.upper_left_x, y: bounds.upper_left_y },
    lower_right: { x: bounds.lower_right_x, y: bounds.lower_right_y },
  };
}

/** TS {upper_left: {x, y}, lower_right: {x, y}} → Rust flat GridBounds. */
export function gridCoordinatesToRustBounds(
  coords: GridCoordinates,
): GridBoundsRust {
  return {
    upper_left_x: coords.upper_left.x,
    upper_left_y: coords.upper_left.y,
    lower_right_x: coords.lower_right.x,
    lower_right_y: coords.lower_right.y,
  };
}

// ── Exported API ─────────────────────────────────────────────────────────────

/**
 * Line-based grid detection. No OCR required.
 *
 * Dark-mode conversion is applied internally by the Rust side, so callers pass
 * the raw ImageData without pre-processing.
 *
 * Returns `null` bounds on failure (still check `success`).
 */
export async function detectGridLineBased(
  imageData: ImageData,
): Promise<DetectGridResult> {
  await initRustPipeline();
  return detect_grid(
    rgbaView(imageData),
    imageData.width,
    imageData.height,
  ) as DetectGridResult;
}

/**
 * Extract 24 hourly bar values and compute the alignment score.
 * `imageType` is "screen_time" or "battery".
 */
export async function extractBars(
  imageData: ImageData,
  grid: GridCoordinates,
  imageType: "screen_time" | "battery",
): Promise<ExtractBarsResult> {
  await initRustPipeline();
  const boundsJson = JSON.stringify(gridCoordinatesToRustBounds(grid));
  return extract_bars(
    rgbaView(imageData),
    imageData.width,
    imageData.height,
    boundsJson,
    imageType,
  ) as ExtractBarsResult;
}

/**
 * Parse a Tesseract.js word list and extract `title`, `title_y`, `total_text`,
 * and `is_daily_total`. Tesseract.js provides raw OCR; Rust does the spatial
 * filtering that used to live in `ocr.canvas.ts::classifyPageWords` + friends.
 */
export async function parseOcrResult(
  words: OcrWord[],
  imgWidth: number,
  imgHeight: number,
): Promise<ParseOcrResult> {
  await initRustPipeline();
  return parse_ocr_result(
    JSON.stringify(words),
    imgWidth,
    imgHeight,
  ) as ParseOcrResult;
}

/**
 * Normalize OCR digit confusions (I→1, O→0, S→5) in time-string contexts.
 * Use on raw Tesseract.js text before display.
 */
export async function normalizeOcrText(text: string): Promise<string> {
  await initRustPipeline();
  return normalize_ocr_text(text);
}

/**
 * Detect Daily Total / weekly summary page from the full OCR word list.
 * Convenience wrapper; `parseOcrResult` also returns `is_daily_total`.
 */
export async function isDailyTotalPage(texts: string[]): Promise<boolean> {
  await initRustPipeline();
  return check_is_daily_total(JSON.stringify(texts));
}
