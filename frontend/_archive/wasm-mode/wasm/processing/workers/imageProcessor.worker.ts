/**
 * Image Processor Worker - Canvas 2D API Implementation
 *
 * ZERO OpenCV dependencies - uses pure Canvas 2D API for all image processing.
 *
 * This worker handles:
 * - Image preprocessing (dark mode conversion, contrast adjustment)
 * - OCR (Tesseract.js for text extraction)
 * - Grid detection (finding 24-hour graph boundaries)
 * - Hourly data extraction (analyzing bar heights)
 */

import { createWorker as createTesseractWorker, PSM } from "tesseract.js";
import type { Worker as TesseractWorker } from "tesseract.js";
import type {
  WorkerMessage,
  ProcessImageMessage,
  ExtractTitleMessage,
  ExtractTotalMessage,
  ExtractHourlyDataMessage,
  DetectGridMessage,
  WorkerResponse,
} from "./types";

// Canvas API implementations (NO OpenCV!)
import { imageDataToMat, convertDarkMode } from "../imageUtils.canvas";
import { findScreenshotTitle, findScreenshotTotalUsage } from "../ocr.canvas";
import { extractHourlyData } from "../barExtraction.canvas";
import { detectGrid } from "../gridDetection.canvas";

let tesseractWorker: TesseractWorker | null = null;
let initialized = false;
let initializationPromise: Promise<void> | null = null;
let initializationError: Error | null = null;

// Constants
const MAX_INIT_RETRIES = 3;
const INIT_RETRY_DELAY_MS = 1000;

/**
 * Initialize the worker (Tesseract only - NO OpenCV!)
 * Includes retry logic for transient failures.
 */
async function initialize(): Promise<void> {
  console.log("[Worker.initialize] Starting initialization");

  // If we already failed initialization, throw the cached error
  if (initializationError) {
    throw initializationError;
  }

  if (initialized && tesseractWorker) {
    console.log("[Worker.initialize] Already initialized");
    return;
  }

  if (initializationPromise) {
    console.log(
      "[Worker.initialize] Initialization already in progress, waiting...",
    );
    return initializationPromise;
  }

  initializationPromise = initializeInternal();
  return initializationPromise;
}

/**
 * Internal initialization - loads Tesseract only with retry logic
 */
async function initializeInternal(): Promise<void> {
  let lastError: Error | null = null;

  for (let attempt = 1; attempt <= MAX_INIT_RETRIES; attempt++) {
    try {
      postProgress(
        "loading",
        50,
        `Loading Tesseract.js (attempt ${attempt}/${MAX_INIT_RETRIES})...`,
      );
      console.log(
        `[Worker.initialize] Loading Tesseract.js (attempt ${attempt}/${MAX_INIT_RETRIES})...`,
      );

      tesseractWorker = await createTesseractWorker("eng", 1, {
        logger: (m) => {
          if (m.status === "recognizing text") {
            postProgress(
              "ocr_title",
              m.progress * 100,
              `OCR Progress: ${Math.round(m.progress * 100)}%`,
            );
          }
        },
      });
      console.log("[Worker.initialize] Tesseract.js loaded");

      console.log("[Worker.initialize] Setting Tesseract parameters...");
      await tesseractWorker.setParameters({
        tessedit_char_whitelist:
          "0123456789hmHM: ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
        tessedit_pageseg_mode: PSM.SINGLE_BLOCK,
      });

      initialized = true;
      initializationError = null;
      console.log(
        "[Worker.initialize] Initialization complete - Tesseract ready",
      );

      postProgress("complete", 100, "Initialization complete");
      return;
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));
      console.error(
        `[Worker.initializeInternal] Attempt ${attempt} failed:`,
        error,
      );

      // Clean up failed worker
      if (tesseractWorker) {
        try {
          await tesseractWorker.terminate();
        } catch {
          // Ignore cleanup errors
        }
        tesseractWorker = null;
      }

      // Wait before retry (except on last attempt)
      if (attempt < MAX_INIT_RETRIES) {
        console.log(
          `[Worker.initialize] Retrying in ${INIT_RETRY_DELAY_MS}ms...`,
        );
        await new Promise((resolve) =>
          setTimeout(resolve, INIT_RETRY_DELAY_MS),
        );
      }
    }
  }

  // All retries failed
  initializationPromise = null;
  initializationError =
    lastError || new Error("Tesseract initialization failed after all retries");
  console.error(
    "[Worker.initializeInternal] All initialization attempts failed:",
    initializationError,
  );
  throw initializationError;
}

/**
 * Post progress update to main thread
 */
function postProgress(
  stage:
    | "loading"
    | "preprocessing"
    | "ocr_title"
    | "ocr_total"
    | "ocr_hourly"
    | "complete",
  progress: number,
  message?: string,
): void {
  self.postMessage({
    type: "PROGRESS",
    payload: {
      stage,
      progress,
      message,
    },
  });
}

/**
 * Main message handler
 */
self.onmessage = async (e: MessageEvent<WorkerMessage>) => {
  const { type, id, payload } = e.data;
  console.log("[Worker.onmessage] Received message:", {
    type,
    id,
    hasPayload: !!payload,
  });

  try {
    if (!initialized && type !== "INITIALIZE") {
      console.log("[Worker.onmessage] Not initialized, calling initialize()");
      await initialize();
      console.log("[Worker.onmessage] Initialize complete");
    }

    switch (type) {
      case "INITIALIZE":
        console.log("[Worker.onmessage] Handling INITIALIZE");
        await handleInitialize(id);
        break;

      case "PROCESS_IMAGE":
        console.log("[Worker.onmessage] Handling PROCESS_IMAGE");
        await handleProcessImage(id, payload as ProcessImageMessage["payload"]);
        break;

      case "EXTRACT_TITLE":
        console.log("[Worker.onmessage] Handling EXTRACT_TITLE");
        await handleExtractTitle(id, payload as ExtractTitleMessage["payload"]);
        break;

      case "EXTRACT_TOTAL":
        console.log("[Worker.onmessage] Handling EXTRACT_TOTAL");
        await handleExtractTotal(id, payload as ExtractTotalMessage["payload"]);
        break;

      case "EXTRACT_HOURLY_DATA":
        console.log("[Worker.onmessage] Handling EXTRACT_HOURLY_DATA");
        await handleExtractHourlyData(
          id,
          payload as ExtractHourlyDataMessage["payload"],
        );
        break;

      case "DETECT_GRID":
        console.log("[Worker.onmessage] Handling DETECT_GRID");
        await handleDetectGrid(id, payload as DetectGridMessage["payload"]);
        break;

      default:
        throw new Error(`Unknown message type: ${type}`);
    }
  } catch (error) {
    console.error("[Worker.onmessage] Error processing message:", error);
    const response: WorkerResponse = {
      type: "ERROR",
      id,
      error: error instanceof Error ? error.message : String(error),
    };
    self.postMessage(response);
  }
};

/**
 * Handle INITIALIZE message
 */
async function handleInitialize(id: string): Promise<void> {
  console.log("[Worker.handleInitialize] Starting");
  await initialize();
  console.log(
    "[Worker.handleInitialize] Initialize complete, sending response",
  );

  const response: WorkerResponse = {
    type: "INITIALIZE_COMPLETE",
    id,
    payload: { initialized: true },
  };

  self.postMessage(response);
  console.log("[Worker.handleInitialize] Response sent");
}

/**
 * Handle PROCESS_IMAGE message (full pipeline)
 */
async function handleProcessImage(
  id: string,
  payload: ProcessImageMessage["payload"],
): Promise<void> {
  console.log(
    "[Worker.handleProcessImage] Starting, imageType:",
    payload.imageType,
    "hasGridCoords:",
    !!payload.gridCoordinates,
  );

  if (!tesseractWorker) {
    throw new Error("Worker not initialized - Tesseract not available");
  }

  // Benchmarking
  const benchmarks: Record<string, number> = {};
  let startTime = performance.now();

  postProgress("preprocessing", 10, "Preprocessing image...");
  console.log("[Worker.handleProcessImage] Converting to CanvasMat");

  const mat = imageDataToMat(payload.imageData);
  benchmarks["imageDataToMat"] = performance.now() - startTime;
  startTime = performance.now();

  const darkModeConverted = convertDarkMode(mat);
  benchmarks["convertDarkMode"] = performance.now() - startTime;
  console.log("[Worker.handleProcessImage] Dark mode conversion complete");

  // Extract title and total FIRST - these use anchor-based OCR and don't need grid
  postProgress("ocr_title", 20, "Extracting title...");
  console.log("[Worker.handleProcessImage] Extracting title...");
  startTime = performance.now();
  const { title } = await findScreenshotTitle(
    tesseractWorker,
    darkModeConverted,
  );
  benchmarks["findScreenshotTitle"] = performance.now() - startTime;
  console.log("[Worker.handleProcessImage] Title extracted:", title);

  postProgress("ocr_total", 40, "Extracting total usage...");
  console.log("[Worker.handleProcessImage] Extracting total...");
  startTime = performance.now();
  const total = await findScreenshotTotalUsage(
    tesseractWorker,
    darkModeConverted,
  );
  benchmarks["findScreenshotTotalUsage"] = performance.now() - startTime;
  console.log("[Worker.handleProcessImage] Total extracted:", total);

  // Now detect grid if not provided
  let gridCoordinates = payload.gridCoordinates;

  if (!gridCoordinates) {
    postProgress("preprocessing", 60, "Detecting grid...");
    console.log("[Worker.handleProcessImage] No grid provided, detecting...");
    startTime = performance.now();
    const detectedGrid = await detectGrid(tesseractWorker, darkModeConverted);
    benchmarks["detectGrid"] = performance.now() - startTime;

    if (!detectedGrid) {
      // Grid detection failed - return error with partial data
      console.warn(
        "[Worker.handleProcessImage] Grid detection failed",
      );

      const response: WorkerResponse = {
        type: "PROCESS_IMAGE_COMPLETE",
        id,
        payload: {
          hourlyData: {},
          title,
          total,
          gridCoordinates: undefined,
          gridDetectionFailed: true,
          gridDetectionError: "Could not automatically detect the graph grid. Please manually select the grid area by clicking and dragging on the screenshot.",
        },
      };
      self.postMessage(response);
      return;
    }

    gridCoordinates = detectedGrid;
    console.log("[Worker.handleProcessImage] Grid detected:", gridCoordinates);
  } else {
    console.log(
      "[Worker.handleProcessImage] Using provided grid:",
      gridCoordinates,
    );
  }

  postProgress("ocr_hourly", 80, "Extracting hourly data...");
  console.log("[Worker.handleProcessImage] Extracting hourly data...");
  startTime = performance.now();
  const hourlyData = extractHourlyData(
    darkModeConverted,
    gridCoordinates,
    payload.imageType === "battery",
  );
  benchmarks["extractHourlyData"] = performance.now() - startTime;
  console.log("[Worker.handleProcessImage] Hourly data extracted:", hourlyData);

  // Log benchmarks
  console.log("[Worker.handleProcessImage] === BENCHMARKS ===");
  let totalTime = 0;
  for (const [key, value] of Object.entries(benchmarks)) {
    console.log(`  ${key}: ${value.toFixed(2)}ms`);
    totalTime += value;
  }
  console.log(`  TOTAL: ${totalTime.toFixed(2)}ms`);
  console.log("[Worker.handleProcessImage] ==================");

  postProgress("complete", 100, "Processing complete");

  const response: WorkerResponse = {
    type: "PROCESS_IMAGE_COMPLETE",
    id,
    payload: {
      hourlyData,
      title,
      total,
      gridCoordinates,
    },
  };

  console.log("[Worker.handleProcessImage] Sending response");
  self.postMessage(response);
  console.log("[Worker.handleProcessImage] Response sent");
}

/**
 * Handle EXTRACT_TITLE message
 */
async function handleExtractTitle(
  id: string,
  payload: ExtractTitleMessage["payload"],
): Promise<void> {
  if (!tesseractWorker) {
    throw new Error("Worker not initialized - Tesseract not available");
  }

  const mat = imageDataToMat(payload.imageData);
  const darkModeConverted = convertDarkMode(mat);

  const { title } = await findScreenshotTitle(
    tesseractWorker,
    darkModeConverted,
  );

  const response: WorkerResponse = {
    type: "EXTRACT_TITLE_COMPLETE",
    id,
    payload: { title },
  };

  self.postMessage(response);
}

/**
 * Handle EXTRACT_TOTAL message
 */
async function handleExtractTotal(
  id: string,
  payload: ExtractTotalMessage["payload"],
): Promise<void> {
  if (!tesseractWorker) {
    throw new Error("Worker not initialized - Tesseract not available");
  }

  const mat = imageDataToMat(payload.imageData);
  const darkModeConverted = convertDarkMode(mat);

  const total = await findScreenshotTotalUsage(
    tesseractWorker,
    darkModeConverted,
  );

  const response: WorkerResponse = {
    type: "EXTRACT_TOTAL_COMPLETE",
    id,
    payload: { total },
  };

  self.postMessage(response);
}

/**
 * Handle EXTRACT_HOURLY_DATA message
 */
async function handleExtractHourlyData(
  id: string,
  payload: ExtractHourlyDataMessage["payload"],
): Promise<void> {
  if (!tesseractWorker) {
    throw new Error("Worker not initialized - Tesseract not available");
  }

  // Benchmarking for grid adjustment (fast path - no OCR)
  const benchmarks: Record<string, number> = {};
  let startTime = performance.now();

  const mat = imageDataToMat(payload.imageData);
  benchmarks["imageDataToMat"] = performance.now() - startTime;
  startTime = performance.now();

  const darkModeConverted = convertDarkMode(mat);
  benchmarks["convertDarkMode"] = performance.now() - startTime;
  startTime = performance.now();

  const hourlyData = extractHourlyData(
    darkModeConverted,
    payload.gridCoordinates,
    payload.imageType === "battery",
  );
  benchmarks["extractHourlyData"] = performance.now() - startTime;

  // Log benchmarks for grid adjustment
  console.log(
    "[Worker.handleExtractHourlyData] === BENCHMARKS (Grid Adjustment - No OCR) ===",
  );
  let totalTime = 0;
  for (const [key, value] of Object.entries(benchmarks)) {
    console.log(`  ${key}: ${value.toFixed(2)}ms`);
    totalTime += value;
  }
  console.log(`  TOTAL: ${totalTime.toFixed(2)}ms`);
  console.log("[Worker.handleExtractHourlyData] ==================");

  const response: WorkerResponse = {
    type: "EXTRACT_HOURLY_DATA_COMPLETE",
    id,
    payload: { hourlyData },
  };

  self.postMessage(response);
}

/**
 * Handle DETECT_GRID message
 */
async function handleDetectGrid(
  id: string,
  payload: DetectGridMessage["payload"],
): Promise<void> {
  if (!tesseractWorker) {
    throw new Error("Worker not initialized - Tesseract not available");
  }

  const mat = imageDataToMat(payload.imageData);
  console.log("[handleDetectGrid] Created mat:", {
    width: mat.width,
    height: mat.height,
    channels: mat.channels,
  });

  const darkModeConverted = convertDarkMode(mat);
  console.log("[handleDetectGrid] Dark mode converted:", {
    width: darkModeConverted.width,
    height: darkModeConverted.height,
    channels: darkModeConverted.channels,
  });

  const gridCoordinates = await detectGrid(tesseractWorker, darkModeConverted);

  const response: WorkerResponse = {
    type: "DETECT_GRID_COMPLETE",
    id,
    payload: { gridCoordinates },
  };

  self.postMessage(response);
}

export {};
