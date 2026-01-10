/**
 * OCR Utilities - Canvas 2D API Implementation
 *
 * This is a DROP-IN REPLACEMENT for ocr.ts that uses Canvas 2D API
 * instead of OpenCV.js. All function signatures and behaviors are identical.
 *
 * ZERO OpenCV dependencies - pure Canvas 2D API.
 */

import type { Worker as TesseractWorker } from "tesseract.js";
import type { CanvasMat, Rect } from "./canvasImageUtils";
import { matToImageData, imageDataToCanvas } from "./canvasImageUtils";
import { adjustContrastBrightness, extractRegion } from "./imageUtils.canvas";

const PAGE_MARKER_WORDS_DAILY = [
  "WEEK",
  "DAY",
  "MOST",
  "USED",
  "CATEGORIES",
  "TODAY",
  "SHOW",
  "ENTERTAINMENT",
  "EDUCATION",
  "INFORMATION",
  "READING",
];

const PAGE_MARKER_WORDS_APP = [
  "INFO",
  "DEVELOPER",
  "RATING",
  "LIMIT",
  "AGE",
  "DAILY",
  "AVERAGE",
];

/**
 * Determines if screenshot is a daily total page.
 *
 * Identical to OpenCV version.
 *
 * @param worker - Tesseract worker
 * @param imageMat - Source image
 * @returns True if daily total page
 */
export async function isDailyTotalPage(
  worker: TesseractWorker,
  imageMat: CanvasMat,
): Promise<boolean> {
  const imageData = matToImageData(imageMat);

  const { data } = await worker.recognize(imageDataToCanvas(imageData));

  const text = data.text.toUpperCase();

  let dailyCount = 0;
  let appCount = 0;

  for (const marker of PAGE_MARKER_WORDS_DAILY) {
    if (text.includes(marker)) {
      dailyCount++;
    }
  }

  for (const marker of PAGE_MARKER_WORDS_APP) {
    if (text.includes(marker)) {
      appCount++;
    }
  }

  return dailyCount > appCount;
}

/**
 * Finds screenshot title (app name or "Daily Total").
 *
 * Identical to OpenCV version.
 *
 * @param worker - Tesseract worker
 * @param imageMat - Source image
 * @returns Title and Y position
 */
export async function findScreenshotTitle(
  worker: TesseractWorker,
  imageMat: CanvasMat,
): Promise<{ title: string; titleYPosition: number | null }> {
  const imageData = matToImageData(imageMat);

  const { data } = await worker.recognize(imageDataToCanvas(imageData));

  const isDaily = await isDailyTotalPage(worker, imageMat);

  if (isDaily) {
    return { title: "Daily Total", titleYPosition: null };
  }

  let infoRect: Rect = { x: 40, y: 300, width: 120, height: 2000 };
  let foundInfo = false;

  if (data.words) {
    for (const word of data.words) {
      if (word.text && word.text.toUpperCase().includes("INFO") && word.bbox) {
        infoRect = {
          x: word.bbox.x0,
          y: word.bbox.y0,
          width: word.bbox.x1 - word.bbox.x0,
          height: word.bbox.y1 - word.bbox.y0,
        };
        foundInfo = true;
        break;
      }
    }
  }

  let titleYPosition: number | null = null;
  let appExtractRect: Rect;

  if (foundInfo) {
    const appHeight = infoRect.height * 7;
    const titleOriginY = infoRect.y + infoRect.height;
    const xOrigin = infoRect.x + Math.floor(1.5 * infoRect.width);
    const xWidth = xOrigin + Math.floor(infoRect.width * 12);

    appExtractRect = {
      x: xOrigin,
      y: titleOriginY,
      width: Math.min(xWidth - xOrigin, imageMat.width - xOrigin),
      height: Math.min(appHeight, imageMat.height - titleOriginY),
    };

    titleYPosition = titleOriginY + appHeight;
  } else {
    appExtractRect = infoRect;
  }

  const appExtract = extractRegion(imageMat, appExtractRect);

  const appExtractImageData = matToImageData(appExtract);
  const { data: titleData } = await worker.recognize(imageDataToCanvas(appExtractImageData));

  let title = "";
  if (titleData.text) {
    title = titleData.text.replace(/\|/g, "").trim();
  }

  return { title, titleYPosition };
}

/**
 * Finds total usage time from screenshot.
 *
 * Identical to OpenCV version.
 *
 * @param worker - Tesseract worker
 * @param imageMat - Source image
 * @returns Total usage string (e.g., "2h 30m")
 */
export async function findScreenshotTotalUsage(
  worker: TesseractWorker,
  imageMat: CanvasMat,
): Promise<string> {
  const imageData = matToImageData(imageMat);

  const { data } = await worker.recognize(imageDataToCanvas(imageData));

  const isDaily = await isDailyTotalPage(worker, imageMat);

  let totalRect: Rect | null = null;

  if (data.words) {
    for (const word of data.words) {
      if (
        word.text &&
        word.text.toUpperCase().includes("SCREEN") &&
        word.bbox
      ) {
        totalRect = {
          x: word.bbox.x0,
          y: word.bbox.y0,
          width: word.bbox.x1 - word.bbox.x0,
          height: word.bbox.y1 - word.bbox.y0,
        };
        break;
      }
    }
  }

  let totalExtractRect: Rect;

  if (totalRect) {
    if (isDaily) {
      const yOrigin = totalRect.y + totalRect.height + 95;
      const height = Math.floor(totalRect.height * 5);
      const xOrigin = totalRect.x - 50;
      const width = Math.floor(totalRect.width * 4);

      totalExtractRect = {
        x: Math.max(0, xOrigin),
        y: Math.max(0, yOrigin),
        width: Math.min(width, imageMat.width - xOrigin),
        height: Math.min(height, imageMat.height - yOrigin),
      };
    } else {
      const height = Math.floor(totalRect.height * 6);
      const yOrigin = totalRect.y + totalRect.height + 50;
      const xOrigin = totalRect.x - 50;
      const width = Math.floor(totalRect.width * 4);

      totalExtractRect = {
        x: Math.max(0, xOrigin),
        y: Math.max(0, yOrigin),
        width: Math.min(width, imageMat.width - xOrigin),
        height: Math.min(height, imageMat.height - yOrigin),
      };
    }
  } else if (isDaily) {
    totalExtractRect = { x: 325, y: 30, width: 100, height: 420 };
  } else {
    totalExtractRect = { x: 250, y: 30, width: 100, height: 420 };
  }

  const totalExtract = extractRegion(imageMat, totalExtractRect);

  const contrastAdjusted = adjustContrastBrightness(totalExtract, 2.0, 0);

  const totalExtractImageData = matToImageData(contrastAdjusted);
  const { data: totalData } = await worker.recognize(imageDataToCanvas(totalExtractImageData));

  let total = "";
  if (totalData.text) {
    total = totalData.text.replace(/Os/g, "0s").replace(/\|/g, "").trim();
  }

  if (!total || !/\d+\s*[hms]/.test(total)) {
    const regexTotal = await findScreenshotTotalUsageRegex(worker, imageMat);
    if (regexTotal) {
      return regexTotal;
    }
  }

  return total;
}

/**
 * Finds total usage using regex fallback.
 *
 * Identical to OpenCV version.
 *
 * @param worker - Tesseract worker
 * @param imageMat - Source image
 * @returns Total usage string
 */
async function findScreenshotTotalUsageRegex(
  worker: TesseractWorker,
  imageMat: CanvasMat,
): Promise<string> {
  const imageData = matToImageData(imageMat);

  const { data } = await worker.recognize(imageDataToCanvas(imageData));

  const fullImageText = data.text.replace(/Os/g, "0s");

  const hourMinPattern = /(\d{1,2})\s*h\s+(\d{1,2})\s*m/;
  const minSecPattern = /(\d{1,2})\s*m\s+([0O]|\d{1,2})\s*s/;
  const minOnlyPattern = /(\d{1,2})\s*m\b/;
  const hoursOnlyPattern = /(\d{1,2})\s*h\b/;
  const secOnlyPattern = /([0O]|\d{1,2})\s*s\b/;

  let match = fullImageText.match(hourMinPattern);
  if (match && match[1] && match[2]) {
    return `${match[1]}h ${match[2]}m`;
  }

  match = fullImageText.match(minSecPattern);
  if (match && match[1] && match[2]) {
    const seconds = match[2].replace(/O/g, "0");
    return `${match[1]}m ${seconds}s`;
  }

  match = fullImageText.match(hoursOnlyPattern);
  if (match && match[1]) {
    return `${match[1]}h`;
  }

  match = fullImageText.match(minOnlyPattern);
  if (match && match[1]) {
    return `${match[1]}m`;
  }

  match = fullImageText.match(secOnlyPattern);
  if (match && match[1]) {
    const seconds = match[1].replace(/O/g, "0");
    return `${seconds}s`;
  }

  return "";
}

/**
 * Extracts text from specific ROI coordinates.
 *
 * Identical to OpenCV version.
 *
 * @param worker - Tesseract worker
 * @param imageMat - Source image
 * @param roiX - ROI X coordinate
 * @param roiY - ROI Y coordinate
 * @param roiWidth - ROI width
 * @param roiHeight - ROI height
 * @returns Extracted text and PM flag
 */
export async function getText(
  worker: TesseractWorker,
  imageMat: CanvasMat,
  roiX: number,
  roiY: number,
  roiWidth: number,
  roiHeight: number,
): Promise<{ text1: string; text2: string; isPM: boolean }> {
  const textYStart = roiY + Math.floor(roiHeight * 1.23);
  const textYEnd = roiY + Math.floor(roiHeight * 1.46);
  const textXWidth = Math.floor(roiWidth / 8);

  const firstLocationRect: Rect = {
    x: roiX,
    y: textYStart,
    width: textXWidth,
    height: textYEnd - textYStart,
  };

  const secondLocationRect: Rect = {
    x: roiX + Math.floor(roiWidth / 2),
    y: textYStart,
    width: textXWidth,
    height: textYEnd - textYStart,
  };

  const firstLocation = extractRegion(imageMat, firstLocationRect);
  const secondLocation = extractRegion(imageMat, secondLocationRect);

  const firstImageData = matToImageData(firstLocation);
  const secondImageData = matToImageData(secondLocation);

  const { data: firstData } = await worker.recognize(imageDataToCanvas(firstImageData));
  const { data: secondData } = await worker.recognize(imageDataToCanvas(secondImageData));

  const firstDate = cleanDateString(firstData.text?.trim() || "");
  const secondDate = cleanDateString(secondData.text?.trim() || "");

  let isPM = false;
  let text1 = firstDate;

  try {
    text1 = getDayBefore(secondDate);
    isPM = true;
  } catch {
    isPM = false;
  }

  return { text1, text2: secondDate, isPM };
}

/**
 * Cleans date string.
 *
 * @param dateString - Raw date string
 * @returns Cleaned date string
 */
function cleanDateString(dateString: string | undefined): string {
  if (!dateString) return "";
  return dateString.replace(/[^a-zA-Z0-9\s]/g, "");
}

/**
 * Checks if string is a valid date.
 *
 * @param str - String to check
 * @returns True if valid date
 */
function isDate(str: string): boolean {
  const months = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ];
  const pattern = new RegExp(`^(${months.join("|")})\\s+\\d{1,2}$`);
  return pattern.test(str);
}

/**
 * Gets the day before a given date.
 *
 * @param dateString - Date string (e.g., "Jan 15")
 * @returns Previous day string
 */
function getDayBefore(dateString: string): string {
  if (!isDate(dateString)) {
    throw new Error("Invalid date string");
  }

  const parts = dateString.split(" ");
  const monthStr = parts[0];
  const dayStr = parts[1];

  if (!monthStr || !dayStr) {
    throw new Error("Invalid date format");
  }

  const months = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ];
  const monthIndex = months.indexOf(monthStr);

  if (monthIndex === -1) {
    throw new Error("Invalid month");
  }

  const currentYear = new Date().getFullYear();
  const date = new Date(currentYear, monthIndex, parseInt(dayStr, 10));

  date.setDate(date.getDate() - 1);

  const newMonthStr = months[date.getMonth()];
  const newDay = date.getDate();

  return `${newMonthStr} ${newDay}`;
}
