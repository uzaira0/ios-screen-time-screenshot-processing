/**
 * Image Processor Worker - Canvas 2D API Implementation
 *
 * This is a drop-in replacement for imageProcessor.worker.ts that uses
 * Canvas 2D API instead of OpenCV.js.
 *
 * ELIMINATES: 11MB OpenCV.js dependency and fetch+eval hack
 * USES: Pure Canvas 2D API implementations
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

import { imageDataToMat, convertDarkMode } from "../imageUtils.canvas";
import { findScreenshotTitle, findScreenshotTotalUsage, recognizeFullImage } from "../ocr.canvas";
import { extractHourlyData, computeBarAlignmentScore } from "../barExtraction.canvas";
import { extractROI } from "../canvasImageUtils";
import { detectGrid } from "../gridDetection.canvas";
import { detectGridLineBased } from "../lineBasedDetection.canvas";
import { optimizeBoundaries } from "../boundaryOptimizer.canvas";

let tesseractWorker: TesseractWorker | null = null;
let initialized = false;
let initializationPromise: Promise<void> | null = null;
// Track the current message id so progress messages can be correlated
let currentMessageId: string | undefined;

async function initialize(): Promise<void> {
  console.log("[Worker.initialize] Starting initialization");

  if (initialized) {
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

async function initializeInternal(): Promise<void> {
  try {
    postProgress("loading", 50, "Loading Tesseract.js...");
    console.log("[Worker.initialize] Loading Tesseract.js...");

    tesseractWorker = await createTesseractWorker("eng", 1, {
      workerPath: new URL("/tesseract-worker.min.js", self.location.origin).href,
      corePath: new URL("/", self.location.origin).href,
      langPath: new URL("/", self.location.origin).href,
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
    console.log(
      "[Worker.initialize] Initialization complete - Tesseract ready (NO OPENCV!)",
    );

    postProgress("complete", 100, "Initialization complete");
  } catch (error) {
    initializationPromise = null;
    console.error("[Worker.initializeInternal] Initialization failed:", error);
    throw error;
  }
}

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
    id: currentMessageId,
    payload: {
      stage,
      progress,
      message,
    },
  });
}

self.onmessage = async (e: MessageEvent<WorkerMessage>) => {
  const { type, id, payload } = e.data;
  // Track current message id so postProgress can include it
  currentMessageId = id;
  console.log("[Worker.onmessage] Received message:", {
    type,
    id,
    hasPayload: !!payload,
  });

  try {
    // Auto-initialize Tesseract for messages that need OCR.
    // Skip for INITIALIZE (handled explicitly) and line_based DETECT_GRID (no OCR needed).
    const isLineBased = type === "DETECT_GRID" && (payload as DetectGridMessage["payload"])?.method === "line_based";
    if (!initialized && type !== "INITIALIZE" && !isLineBased) {
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

  const t0 = performance.now();

  postProgress("preprocessing", 10, "Preprocessing image...");

  const mat = imageDataToMat(payload.imageData);
  const darkModeConverted = convertDarkMode(mat);
  const t1 = performance.now();
  console.log(`[BENCH] Preprocessing (mat + dark mode): ${(t1 - t0).toFixed(0)}ms`);

  let gridCoordinates = payload.gridCoordinates;

  if (!gridCoordinates) {
    postProgress("preprocessing", 30, "Detecting grid...");
    const tGrid0 = performance.now();
    const detectedGrid = await detectGrid(
      tesseractWorker,
      darkModeConverted,
    );
    console.log(`[BENCH] Grid detection: ${(performance.now() - tGrid0).toFixed(0)}ms`);

    if (!detectedGrid) {
      throw new Error("Failed to detect grid automatically");
    }

    gridCoordinates = detectedGrid;
  }

  // Run OCR on header area (above the grid) once and share the result.
  postProgress("ocr_title", 40, "Running OCR...");
  const gridUpperY = gridCoordinates.upper_left.y;
  const imgW = darkModeConverted.width;
  const cropH = Math.min(gridUpperY + 20, darkModeConverted.height);
  console.log(`[BENCH] Header OCR region: ${imgW}x${cropH} = ${(imgW * cropH / 1000000).toFixed(2)}M pixels`);

  const t2 = performance.now();
  const fullOCR = await recognizeFullImage(tesseractWorker, darkModeConverted, gridUpperY);
  const t3 = performance.now();
  console.log(`[BENCH] recognizeFullImage: ${(t3 - t2).toFixed(0)}ms (found ${fullOCR.words.length} words, isDaily=${fullOCR.isDaily})`);

  const t4 = performance.now();
  const { title } = await findScreenshotTitle(
    tesseractWorker,
    darkModeConverted,
    fullOCR,
  );
  const t5 = performance.now();
  console.log(`[BENCH] findScreenshotTitle: ${(t5 - t4).toFixed(0)}ms (title="${title}")`);

  postProgress("ocr_total", 60, "Extracting total usage...");
  const t6 = performance.now();
  const total = await findScreenshotTotalUsage(
    tesseractWorker,
    darkModeConverted,
    fullOCR,
  );
  const t7 = performance.now();
  console.log(`[BENCH] findScreenshotTotalUsage: ${(t7 - t6).toFixed(0)}ms (total="${total}")`);

  postProgress("ocr_hourly", 80, "Extracting hourly data...");
  const t8 = performance.now();

  const maxShift = payload.maxShift ?? 0;
  let hourlyData;
  let correctedTotal = total;

  if (maxShift > 0 && total) {
    const optResult = optimizeBoundaries(
      darkModeConverted,
      gridCoordinates,
      total,
      maxShift,
      payload.imageType === "battery",
    );
    hourlyData = optResult.hourlyData;
    gridCoordinates = optResult.bounds;
    // Use the 7→1 corrected total if it better matches the bar total
    correctedTotal = optResult.correctedTotal;
  } else {
    hourlyData = extractHourlyData(
      darkModeConverted,
      gridCoordinates,
      payload.imageType === "battery",
    );
  }

  // Compute bar alignment score (HSV-based, matches server's compute_bar_alignment_score)
  const roiRect = {
    x: gridCoordinates.upper_left.x,
    y: gridCoordinates.upper_left.y,
    width: gridCoordinates.lower_right.x - gridCoordinates.upper_left.x,
    height: gridCoordinates.lower_right.y - gridCoordinates.upper_left.y,
  };
  const roi = extractROI(darkModeConverted, roiRect);
  const alignmentScore = computeBarAlignmentScore(roi, hourlyData);

  const t9 = performance.now();
  console.log(`[BENCH] Hourly data extraction + alignment: ${(t9 - t8).toFixed(0)}ms`);
  console.log(`[BENCH] TOTAL processImage: ${(t9 - t0).toFixed(0)}ms`);

  postProgress("complete", 100, "Processing complete");

  const response: WorkerResponse = {
    type: "PROCESS_IMAGE_COMPLETE",
    id,
    payload: {
      hourlyData,
      title,
      total: correctedTotal,
      gridCoordinates,
      alignmentScore,
    },
  };

  console.log("[Worker.handleProcessImage] Sending response");
  self.postMessage(response);
  console.log("[Worker.handleProcessImage] Response sent");
}

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

async function handleExtractHourlyData(
  id: string,
  payload: ExtractHourlyDataMessage["payload"],
): Promise<void> {
  if (!tesseractWorker) {
    throw new Error("Worker not initialized - Tesseract not available");
  }

  const mat = imageDataToMat(payload.imageData);
  const darkModeConverted = convertDarkMode(mat);

  const hourlyData = extractHourlyData(
    darkModeConverted,
    payload.gridCoordinates,
    payload.imageType === "battery",
  );

  const response: WorkerResponse = {
    type: "EXTRACT_HOURLY_DATA_COMPLETE",
    id,
    payload: { hourlyData },
  };

  self.postMessage(response);
}

async function handleDetectGrid(
  id: string,
  payload: DetectGridMessage["payload"],
): Promise<void> {
  const mat = imageDataToMat(payload.imageData);
  const darkModeConverted = convertDarkMode(mat);

  let gridCoordinates;

  if (payload.method === "line_based") {
    // Line-based detection — no OCR required
    const result = detectGridLineBased(darkModeConverted);
    gridCoordinates = result.gridCoordinates;
    console.log("[Worker.handleDetectGrid] Line-based result:", {
      found: !!gridCoordinates,
      confidence: result.confidence,
      diagnostics: result.diagnostics,
    });
  } else {
    // OCR-anchored detection (default)
    if (!tesseractWorker) {
      throw new Error("Worker not initialized - Tesseract not available");
    }
    gridCoordinates = await detectGrid(tesseractWorker, darkModeConverted);
  }

  const response: WorkerResponse = {
    type: "DETECT_GRID_COMPLETE",
    id,
    payload: { gridCoordinates },
  };

  self.postMessage(response);
}

export {};
