/**
 * Grid Detection - Canvas 2D API Implementation
 *
 * This is a DROP-IN REPLACEMENT for gridDetection.ts that uses Canvas 2D API
 * instead of OpenCV.js. All function signatures and behaviors are identical.
 *
 * ZERO OpenCV dependencies - pure Canvas 2D API.
 */

import type { Worker as TesseractWorker, Page } from "tesseract.js";

/** Extract all words from Tesseract v7 Page (blocks→paragraphs→lines→words) */
function getWordsFromPage(page: Page) {
  const words: Array<{ text: string; bbox: { x0: number; y0: number; x1: number; y1: number } }> = [];
  if (page.blocks) {
    for (const block of page.blocks) {
      for (const para of block.paragraphs) {
        for (const line of para.lines) {
          for (const word of line.words) {
            words.push(word);
          }
        }
      }
    }
  }
  return words;
}
import type { GridCoordinates } from "@/types";
import type { CanvasMat } from "./canvasImageUtils";
import {
  extractROI,
  matToImageData,
  setPixel,
  imageDataToCanvas,
} from "./canvasImageUtils";
import { adjustContrastBrightness } from "./imageUtils.canvas";
import {
  bitwiseNot,
  calculateMean,
  cvtColorToGray,
  createCanvasMat,
} from "./canvasImageUtils";
import { extractLine, LineExtractionMode } from "./barExtraction.canvas";

const BUFFER = 25;
const MAXIMUM_OFFSET = 100;

interface OCRData {
  text: string[];
  left: number[];
  top: number[];
  width: number[];
  height: number[];
}

/**
 * Detects grid coordinates automatically using OCR anchor points.
 *
 * Identical to OpenCV version.
 *
 * Algorithm:
 * 1. Adjust contrast to make grid visible
 * 2. Split image into left and right chunks
 * 3. Perform OCR to find anchor points ("12 AM" on left, "60" on right)
 * 4. Extract grid lines from anchors
 * 5. Calculate ROI (region of interest) bounding box
 *
 * @param worker - Tesseract worker
 * @param imageMat - Source image
 * @returns Grid coordinates or null if detection fails
 */
export async function detectGrid(
  worker: TesseractWorker,
  imageMat: CanvasMat,
  originalMat?: CanvasMat,
): Promise<GridCoordinates | null> {
  const adjustedImg = adjustContrastBrightness(imageMat, 2.0, -220);

  const { imgLeft, imgRight, rightOffset } = prepareImageChunks(adjustedImg);

  const dLeft = await performOCR(worker, imgLeft);
  const dRight = await performOCR(worker, imgRight);

  adjustAnchorOffsets(dRight, rightOffset);

  const gridCoords = await findGridAnchorsAndCalculateROI(
    dLeft,
    dRight,
    adjustedImg,
  );

  if (gridCoords) return gridCoords;

  // Dark mode fallback: standard preprocessing destroys faint text contrast.
  // Use adaptive thresholding which preserves text for Tesseract.
  const source = originalMat ?? imageMat;
  const mean = calculateMean(source);
  const avgBrightness = (mean[0] + mean[1] + mean[2]) / 3;
  if (avgBrightness < 100) {
    const ocrImg = convertDarkModeForOcr(source);
    const ocrAdjusted = adjustContrastBrightness(ocrImg, 2.0, -220);
    const { imgLeft: ocrLeft, imgRight: ocrRight, rightOffset: ocrOffset } = prepareImageChunks(ocrAdjusted);
    const dLeftRetry = await performOCR(worker, ocrLeft);
    const dRightRetry = await performOCR(worker, ocrRight);
    adjustAnchorOffsets(dRightRetry, ocrOffset);
    return findGridAnchorsAndCalculateROI(dLeftRetry, dRightRetry, adjustedImg);
  }

  return null;
}

/**
 * Splits image into left and right chunks for anchor detection.
 *
 * Identical to OpenCV version.
 *
 * @param img - Source image
 * @returns Left chunk, right chunk, and right offset
 */
function prepareImageChunks(img: CanvasMat): {
  imgLeft: CanvasMat;
  imgRight: CanvasMat;
  rightOffset: number;
} {
  const imgChunkNum = 3;
  const imgWidth = img.width;
  const imgHeight = img.height;
  const topRemoval = Math.floor(imgHeight * 0.05);

  const leftWidth = Math.floor(imgWidth / imgChunkNum);
  const rightWidth = Math.floor(imgWidth / imgChunkNum);
  const rightOffset = imgWidth - rightWidth;

  const imgLeft = extractROI(img, {
    x: 0,
    y: 0,
    width: leftWidth,
    height: imgHeight,
  });
  const imgRight = extractROI(img, {
    x: rightOffset,
    y: 0,
    width: rightWidth,
    height: imgHeight,
  });

  // Blank out top portion (remove title/header noise)
  for (let y = 0; y < topRemoval; y++) {
    for (let x = 0; x < imgLeft.width; x++) {
      setPixel(imgLeft, y, x, 0, 255); // R
      setPixel(imgLeft, y, x, 1, 255); // G
      setPixel(imgLeft, y, x, 2, 255); // B
    }
  }

  for (let y = 0; y < topRemoval; y++) {
    for (let x = 0; x < imgRight.width; x++) {
      setPixel(imgRight, y, x, 0, 255); // R
      setPixel(imgRight, y, x, 1, 255); // G
      setPixel(imgRight, y, x, 2, 255); // B
    }
  }

  return { imgLeft, imgRight, rightOffset };
}

/**
 * Performs OCR on image chunk.
 *
 * Identical to OpenCV version.
 *
 * @param worker - Tesseract worker
 * @param img - Image chunk
 * @returns OCR data with text and bounding boxes
 */
async function performOCR(
  worker: TesseractWorker,
  img: CanvasMat,
): Promise<OCRData> {
  const imageData = matToImageData(img);

  // Tesseract needs a canvas element in worker context, not raw ImageData
  const canvas = imageDataToCanvas(imageData);

  const { data } = await worker.recognize(canvas, {}, { blocks: true });

  const ocrData: OCRData = {
    text: [],
    left: [],
    top: [],
    width: [],
    height: [],
  };

  const words = getWordsFromPage(data);
  for (const word of words) {
    if (word.text && word.bbox) {
      ocrData.text.push(word.text);
      ocrData.left.push(word.bbox.x0);
      ocrData.top.push(word.bbox.y0);
      ocrData.width.push(word.bbox.x1 - word.bbox.x0);
      ocrData.height.push(word.bbox.y1 - word.bbox.y0);
    }
  }

  return ocrData;
}

/**
 * Adjusts left coordinates by offset (for right chunk).
 *
 * Identical to OpenCV version.
 *
 * @param data - OCR data
 * @param offset - Offset to add to left coordinates
 */
function adjustAnchorOffsets(data: OCRData, offset: number): void {
  for (let i = 0; i < data.left.length; i++) {
    const currentLeft = data.left[i];
    if (currentLeft !== undefined) {
      data.left[i] = currentLeft + offset;
    }
  }
}

/**
 * Finds grid anchors and calculates ROI.
 *
 * Identical to OpenCV version.
 *
 * @param dLeft - OCR data from left chunk
 * @param dRight - OCR data from right chunk
 * @param img - Source image
 * @returns Grid coordinates or null
 */
async function findGridAnchorsAndCalculateROI(
  dLeft: OCRData,
  dRight: OCRData,
  img: CanvasMat,
): Promise<GridCoordinates | null> {
  for (let skipValue = 0; skipValue < 4; skipValue++) {
    const leftAnchor = findLeftAnchor(dLeft, img, skipValue);
    const rightAnchor = findRightAnchor(dRight, img);

    if (leftAnchor.found && rightAnchor.found) {
      const lowerLeftX = leftAnchor.x;
      const lowerLeftY = leftAnchor.y;
      const upperRightX = rightAnchor.x;
      const upperRightY = rightAnchor.y;

      const roi = calculateROI(
        lowerLeftX,
        upperRightY,
        upperRightX - lowerLeftX,
        lowerLeftY - upperRightY,
        img,
      );

      if (roi) {
        return {
          upper_left: { x: roi.x, y: roi.y },
          lower_right: { x: roi.x + roi.width, y: roi.y + roi.height },
        };
      }
    }
  }

  return null;
}

/**
 * Finds left anchor point ("12 AM" text).
 *
 * Identical to OpenCV version.
 *
 * @param ocrData - OCR data
 * @param img - Source image
 * @param detectionsToSkip - Number of detections to skip (for retries)
 * @returns Anchor position
 */
function findLeftAnchor(
  ocrData: OCRData,
  img: CanvasMat,
  detectionsToSkip: number = 0,
): { found: boolean; x: number; y: number } {
  const keyList = ["2A", "12", "AM"];
  let detectionCount = 0;

  for (let i = 0; i < ocrData.text.length; i++) {
    const text = ocrData.text[i];

    if (text && keyList.some((key) => text.includes(key))) {
      detectionCount++;

      if (detectionCount <= detectionsToSkip) {
        continue;
      }

      const x = ocrData.left[i];
      const y = ocrData.top[i];
      const w = ocrData.width[i];
      const h = ocrData.height[i];

      if (x === undefined || y === undefined || w === undefined || h === undefined) {
        continue;
      }

      // Parity: Rust find_left_anchor uses nested loops — only search for the
      // vertical line if a horizontal line was found first. When neither loop
      // finds a line the fallbacks match Rust's explicit return values:
      //   horizontal found, vertical not → x - BUFFER  (Rust line 117)
      //   no horizontal at all           → y + h       (Rust line 122)
      let lineRow: number | null = null;
      let movingIndex = 0;
      while (lineRow === null && movingIndex < MAXIMUM_OFFSET) {
        const extractedLine = extractLine(
          img,
          x - BUFFER,
          x + w + BUFFER,
          y - movingIndex - BUFFER,
          y - movingIndex + BUFFER,
          LineExtractionMode.HORIZONTAL,
        );
        if (extractedLine !== 0) {
          lineRow = extractedLine;
        }
        movingIndex++;
      }

      if (lineRow !== null) {
        const lowerLeftY = y - BUFFER + lineRow - movingIndex + 1;

        let lineCol: number | null = null;
        let vMovingIndex = 0;
        while (lineCol === null && vMovingIndex < MAXIMUM_OFFSET) {
          const extractedLine = extractLine(
            img,
            x - vMovingIndex - BUFFER,
            x - vMovingIndex + BUFFER,
            y - BUFFER,
            y,
            LineExtractionMode.VERTICAL,
          );
          if (extractedLine !== 0) {
            lineCol = extractedLine;
          }
          vMovingIndex++;
        }

        const lowerLeftX =
          lineCol !== null ? x - BUFFER + lineCol - vMovingIndex + 1 : x - BUFFER;

        return { found: true, x: lowerLeftX, y: lowerLeftY };
      }

      // Fallback: no horizontal grid line found — approximate from text position.
      return { found: true, x: x - BUFFER, y: y + h };
    }
  }

  return { found: false, x: -1, y: -1 };
}

/**
 * Finds right anchor point ("60" text).
 *
 * Identical to OpenCV version.
 *
 * @param ocrData - OCR data
 * @param img - Source image
 * @returns Anchor position
 */
function findRightAnchor(
  ocrData: OCRData,
  img: CanvasMat,
): { found: boolean; x: number; y: number } {
  const keyList = ["60"];

  for (let i = 0; i < ocrData.text.length; i++) {
    const text = ocrData.text[i];

    if (text && keyList.some((key) => text.includes(key))) {
      const x = ocrData.left[i];
      const y = ocrData.top[i];
      const h = ocrData.height[i];

      if (x === undefined || y === undefined || h === undefined) {
        continue;
      }

      let lineRow: number | null = null;
      let movingIndex = 0;
      while (lineRow === null && movingIndex < MAXIMUM_OFFSET) {
        const extractedLine = extractLine(
          img,
          x - BUFFER,
          x,
          y - movingIndex,
          y - movingIndex + h + BUFFER,
          LineExtractionMode.HORIZONTAL,
        );
        if (extractedLine !== 0) {
          lineRow = extractedLine;
        }
        movingIndex++;
      }

      if (lineRow !== null) {
        const upperRightY = y + lineRow - movingIndex + 1;

        let lineCol: number | null = null;
        let vMovingIndex = 0;
        while (lineCol === null && vMovingIndex < MAXIMUM_OFFSET) {
          const extractedLine = extractLine(
            img,
            x - BUFFER - vMovingIndex,
            x - vMovingIndex,
            y,
            y + h + BUFFER,
            LineExtractionMode.VERTICAL,
          );
          if (extractedLine !== 0) {
            lineCol = extractedLine;
          }
          vMovingIndex++;
        }

        const upperRightX =
          lineCol !== null
            ? x - BUFFER + lineCol - vMovingIndex + 1
            : x - BUFFER;
        return { found: true, x: upperRightX, y: upperRightY };
      }

      // Fallback: no horizontal grid line found — approximate from text position.
      return { found: true, x: x - BUFFER, y: y };
    }
  }

  return { found: false, x: -1, y: -1 };
}

/**
 * Calculates ROI bounding box.
 *
 * Identical to OpenCV version.
 *
 * @param lowerLeftX - Lower left X coordinate
 * @param upperRightY - Upper right Y coordinate
 * @param roiWidth - ROI width
 * @param roiHeight - ROI height
 * @param img - Source image
 * @returns ROI rectangle or null
 */
function calculateROI(
  lowerLeftX: number,
  upperRightY: number,
  roiWidth: number,
  roiHeight: number,
  img: CanvasMat,
): { x: number; y: number; width: number; height: number } | null {
  if (lowerLeftX < 0 || upperRightY < 0 || roiWidth <= 0 || roiHeight <= 0) {
    return null;
  }

  if (lowerLeftX >= img.width || upperRightY >= img.height) {
    return null;
  }

  if (
    lowerLeftX + roiWidth > img.width ||
    upperRightY + roiHeight > img.height
  ) {
    return null;
  }

  return {
    x: lowerLeftX,
    y: upperRightY,
    width: roiWidth,
    height: roiHeight,
  };
}

/**
 * Convert dark mode image using adaptive thresholding for OCR.
 *
 * The standard convertDarkMode uses contrast=3.0 which clips faint gray text
 * (e.g., "12 AM", "60" labels) to near-white, destroying contrast for Tesseract.
 * This uses adaptive thresholding to preserve text readability.
 */
function convertDarkModeForOcr(src: CanvasMat): CanvasMat {
  const inverted = bitwiseNot(src);
  const gray = cvtColorToGray(inverted);
  const grayData = gray.imageData.data;
  const { width, height } = gray;

  const blockSize = 31;
  const half = Math.floor(blockSize / 2);
  const cOffset = 10;

  // Build integral image for fast mean calculation
  const integral = new Float64Array((width + 1) * (height + 1));
  const iw = width + 1;
  for (let y = 0; y < height; y++) {
    let rowSum = 0;
    for (let x = 0; x < width; x++) {
      rowSum += grayData[(y * width + x) * 4]!;
      integral[(y + 1) * iw + (x + 1)] = rowSum + integral[y * iw + (x + 1)]!;
    }
  }

  // Apply adaptive threshold
  const result = new ImageData(width, height);
  const out = result.data;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const y0 = Math.max(0, y - half);
      const y1 = Math.min(height, y + half + 1);
      const x0 = Math.max(0, x - half);
      const x1 = Math.min(width, x + half + 1);
      const area = (y1 - y0) * (x1 - x0);
      const sum = integral[y1 * iw + x1]! - integral[y0 * iw + x1]!
        - integral[y1 * iw + x0]! + integral[y0 * iw + x0]!;
      const meanVal = sum / area;
      const threshold = meanVal - cOffset;
      const val = grayData[(y * width + x) * 4]! > threshold ? 255 : 0;
      const idx = (y * width + x) * 4;
      out[idx] = val;
      out[idx + 1] = val;
      out[idx + 2] = val;
      out[idx + 3] = 255;
    }
  }

  return createCanvasMat(result);
}
