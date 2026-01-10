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
import { findScreenshotTitle, findScreenshotTotalUsage } from "../ocr.canvas";
import { extractHourlyData } from "../barExtraction.canvas";
import { detectGrid } from "../gridDetection.canvas";

let tesseractWorker: TesseractWorker | null = null;
let initialized = false;
let initializationPromise: Promise<void> | null = null;

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
    payload: {
      stage,
      progress,
      message,
    },
  });
}

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

  postProgress("preprocessing", 10, "Preprocessing image...");
  console.log("[Worker.handleProcessImage] Converting to CanvasMat");

  const mat = imageDataToMat(payload.imageData);
  const darkModeConverted = convertDarkMode(mat);
  console.log("[Worker.handleProcessImage] Dark mode conversion complete");

  let gridCoordinates = payload.gridCoordinates;

  if (!gridCoordinates) {
    postProgress("preprocessing", 30, "Detecting grid...");
    console.log("[Worker.handleProcessImage] No grid provided, detecting...");
    const detectedGrid = await detectGrid(
      tesseractWorker,
      darkModeConverted,
    );

    if (!detectedGrid) {
      throw new Error("Failed to detect grid automatically");
    }

    gridCoordinates = detectedGrid;
    console.log("[Worker.handleProcessImage] Grid detected:", gridCoordinates);
  } else {
    console.log(
      "[Worker.handleProcessImage] Using provided grid:",
      gridCoordinates,
    );
  }

  postProgress("ocr_title", 40, "Extracting title...");
  console.log("[Worker.handleProcessImage] Extracting title...");
  const { title } = await findScreenshotTitle(
    tesseractWorker,
    darkModeConverted,
  );
  console.log("[Worker.handleProcessImage] Title extracted:", title);

  postProgress("ocr_total", 60, "Extracting total usage...");
  console.log("[Worker.handleProcessImage] Extracting total...");
  const total = await findScreenshotTotalUsage(
    tesseractWorker,
    darkModeConverted,
  );
  console.log("[Worker.handleProcessImage] Total extracted:", total);

  postProgress("ocr_hourly", 80, "Extracting hourly data...");
  console.log("[Worker.handleProcessImage] Extracting hourly data...");
  const hourlyData = extractHourlyData(
    darkModeConverted,
    gridCoordinates,
    payload.imageType === "battery",
  );
  console.log("[Worker.handleProcessImage] Hourly data extracted:", hourlyData);

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
  if (!tesseractWorker) {
    throw new Error("Worker not initialized - Tesseract not available");
  }

  const mat = imageDataToMat(payload.imageData);
  const darkModeConverted = convertDarkMode(mat);

  const gridCoordinates = await detectGrid(
    tesseractWorker,
    darkModeConverted,
  );

  const response: WorkerResponse = {
    type: "DETECT_GRID_COMPLETE",
    id,
    payload: { gridCoordinates },
  };

  self.postMessage(response);
}

export {};
