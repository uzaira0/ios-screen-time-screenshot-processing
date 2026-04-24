/**
 * OCR Utilities - Canvas 2D API Implementation
 *
 * Port of the server's ocr.py to Canvas 2D API + Tesseract.js.
 * Follows the same flow: 1 full-image OCR (cached) + 1 small title crop OCR
 * + 1 small total crop OCR = 3 recognize() calls total.
 *
 * ZERO OpenCV dependencies - pure Canvas 2D API.
 */

import type { Worker as TesseractWorker, Page } from "tesseract.js";
import type { CanvasMat, Rect } from "./canvasImageUtils";
import { matToImageData, imageDataToCanvas } from "./canvasImageUtils";
import { adjustContrastBrightness, extractRegion } from "./imageUtils.canvas";

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

/** Cached full-image OCR result — equivalent to server's _full_image_ocr_data() */
interface FullImageOCR {
  text: string;
  words: ReturnType<typeof getWordsFromPage>;
  isDaily: boolean;
}

/**
 * Run OCR on the header portion of the image and cache the result.
 *
 * Equivalent to server's `_full_image_ocr_data(img)` which runs
 * `pytesseract.image_to_data(img, config="--psm 3")` once on the full image.
 *
 * We crop to just above the grid (when coords provided) since all text anchors
 * ("INFO", "SCREEN", daily markers) are above the bar chart. Contrast is applied
 * to strip visual noise, matching the server's preprocessing.
 */
export async function recognizeFullImage(
  worker: TesseractWorker,
  imageMat: CanvasMat,
  gridUpperY?: number,
): Promise<FullImageOCR> {
  const _t0 = performance.now();
  // Server's _full_image_ocr_data() runs pytesseract.image_to_data(img, config="--psm 3")
  // on the FULL image with NO contrast. We match that: no contrast here — contrast is
  // only applied in extractAllText() for the small title/total crop regions.
  // We still crop to the header region since all text anchors (INFO, SCREEN, etc.)
  // are above the bar chart.
  const cropHeight = gridUpperY
    ? Math.min(gridUpperY + 20, imageMat.height)
    : Math.ceil(imageMat.height * 0.45);
  const cropped = extractRegion(imageMat, { x: 0, y: 0, width: imageMat.width, height: cropHeight });

  const imageData = matToImageData(cropped);
  const _t1 = performance.now();
  console.log(`[BENCH] recognizeFullImage prep (crop+toImageData): ${(_t1 - _t0).toFixed(0)}ms`);

  const canvas = imageDataToCanvas(imageData);
  const _t2 = performance.now();
  console.log(`[BENCH] recognizeFullImage imageDataToCanvas: ${(_t2 - _t1).toFixed(0)}ms`);

  const { data } = await worker.recognize(canvas, {}, { blocks: true });
  const _t3 = performance.now();
  console.log(`[BENCH] recognizeFullImage worker.recognize(): ${(_t3 - _t2).toFixed(0)}ms`);

  const text = data.text;
  const words = getWordsFromPage(data);

  const { isDaily } = classifyPageWords(words);

  return { text, words, isDaily };
}

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
 * Pure helper: count daily-vs-app page markers across OCR words.
 * Each word contributes at most 1 count per category (break after first match)
 * to prevent double-counting when one word contains multiple markers.
 * Equivalent to Rust is_daily_total_page() marker counting.
 */
export function classifyPageWords(
  words: ReadonlyArray<{ text: string }>,
): { dailyCount: number; appCount: number; isDaily: boolean } {
  let dailyCount = 0;
  let appCount = 0;
  for (const word of words) {
    const upper = word.text.toUpperCase();
    for (const marker of PAGE_MARKER_WORDS_DAILY) {
      if (upper.includes(marker)) { dailyCount++; break; }
    }
    for (const marker of PAGE_MARKER_WORDS_APP) {
      if (upper.includes(marker)) { appCount++; break; }
    }
  }
  return { dailyCount, appCount, isDaily: dailyCount > appCount };
}

/**
 * Determines if screenshot is a daily total page.
 * Equivalent to server's is_daily_total_page().
 */
export async function isDailyTotalPage(
  worker: TesseractWorker,
  imageMat: CanvasMat,
  cachedOCR?: FullImageOCR,
): Promise<boolean> {
  if (cachedOCR) return cachedOCR.isDaily;

  const ocr = await recognizeFullImage(worker, imageMat);
  return ocr.isDaily;
}

/**
 * OCR a small image region with contrast preprocessing.
 * Equivalent to server's extract_all_text() which applies
 * adjust_contrast_brightness(2.0, 0) then runs image_to_data().
 */
async function extractAllText(
  worker: TesseractWorker,
  region: CanvasMat,
  label?: string,
): Promise<string> {
  const _et0 = performance.now();
  const contrasted = adjustContrastBrightness(region, 2.0, 0);
  const imageData = matToImageData(contrasted);
  const _et1 = performance.now();
  const { data } = await worker.recognize(imageDataToCanvas(imageData));
  const _et2 = performance.now();
  console.log(`[BENCH] extractAllText(${label ?? "?"}): prep=${(_et1 - _et0).toFixed(0)}ms, recognize=${(_et2 - _et1).toFixed(0)}ms, region=${region.width}x${region.height}`);

  let text = "";
  if (data.text) {
    for (const piece of data.text.split(/\s+/)) {
      if (piece.length > 0) {
        text = text + " " + piece;
      }
    }
    text = text.replace(/\|/g, "").trim();
  }
  return text;
}

/**
 * Finds screenshot title (app name or "Daily Total").
 *
 * Matches server's find_screenshot_title():
 * 1. Use cached full-image OCR words to find "INFO" anchor
 * 2. Compute title crop region relative to INFO
 * 3. Run extractAllText() on the small crop
 */
export async function findScreenshotTitle(
  worker: TesseractWorker,
  imageMat: CanvasMat,
  cachedOCR?: FullImageOCR,
): Promise<{ title: string; titleYPosition: number | null }> {
  const ocr = cachedOCR ?? await recognizeFullImage(worker, imageMat);

  if (ocr.isDaily) {
    return { title: "Daily Total", titleYPosition: null };
  }

  // Server: info_rect = [40, 300, 120, 2000] (left, top, width, height)
  // BUT the fallback uses numpy slicing: img[info_rect[0]:info_rect[2], info_rect[1]:info_rect[3]]
  // = img[40:120, 300:2000] = y: 40-120, x: 300-2000 (80px tall, 1700px wide horizontal strip)
  let infoLeft = 40, infoTop = 300, infoWidth = 120, infoHeight = 2000;
  let foundInfo = false;

  // Server: iterate all words, find last "INFO" match
  if (ocr.words.length > 0) {
    for (const word of ocr.words) {
      if (word.text && word.text.toUpperCase().includes("INFO") && word.bbox) {
        infoLeft = word.bbox.x0;
        infoTop = word.bbox.y0;
        infoWidth = word.bbox.x1 - word.bbox.x0;
        infoHeight = word.bbox.y1 - word.bbox.y0;
        foundInfo = true;
        // Server doesn't break — takes the last match
      }
    }
  }

  let titleYPosition: number | null = null;
  let appExtractRect: Rect;

  if (foundInfo) {
    // Parity: Rust uses info.h * 4 to avoid picking up text below the title.
    const appHeight = infoHeight * 4;
    const titleOriginY = infoTop + infoHeight;
    const xOrigin = infoLeft + Math.floor(1.5 * infoWidth);
    const xWidth = xOrigin + Math.floor(infoWidth * 12);

    appExtractRect = {
      x: xOrigin,
      y: titleOriginY,
      width: Math.min(xWidth - xOrigin, imageMat.width - xOrigin),
      height: Math.min(appHeight, imageMat.height - titleOriginY),
    };

    titleYPosition = titleOriginY + appHeight;
  } else {
    // Server fallback: img[info_rect[0]:info_rect[2], info_rect[1]:info_rect[3]]
    // With default [40, 300, 120, 2000]:
    // img[40:120, 300:2000] = numpy [rows, cols] = y: 40-120, x: 300-2000
    // = 80px tall horizontal strip near top, spanning most of the width
    appExtractRect = { x: 300, y: 40, width: 1700, height: 80 };
  }

  // Server: app_find = extract_all_text(app_extract, ocr_config)
  const appExtract = extractRegion(imageMat, appExtractRect);
  let title = await extractAllText(worker, appExtract, "title");

  // Server: title.strip("#_ ")
  title = title.replace(/^[#_ ]+|[#_ ]+$/g, "");

  // Server: MAX_TITLE_LENGTH = 50
  if (title.length > 50) {
    title = "";
  }

  return { title, titleYPosition };
}

/**
 * Finds total usage time from screenshot.
 *
 * Matches server's find_screenshot_total_usage():
 * 1. Use cached full-image OCR words to find "SCREEN" anchor
 * 2. Compute total crop region relative to SCREEN
 * 3. Run extractAllText() on the small crop
 * 4. Apply normalization and regex fallback
 */
export async function findScreenshotTotalUsage(
  worker: TesseractWorker,
  imageMat: CanvasMat,
  cachedOCR?: FullImageOCR,
): Promise<string> {
  const ocr = cachedOCR ?? await recognizeFullImage(worker, imageMat);

  let totalRect: Rect | null = null;

  // Server: iterate all words, find last "SCREEN" match
  if (ocr.words.length > 0) {
    for (const word of ocr.words) {
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
        // Server doesn't break — takes the last match
      }
    }
  }

  let totalExtractRect: Rect;

  if (totalRect) {
    if (ocr.isDaily) {
      // Server: daily page extraction
      const yOrigin = totalRect.y + totalRect.height + 95;
      const height = Math.floor(totalRect.height * 5);
      const xOrigin = totalRect.x - 50;
      const width = Math.floor(totalRect.width * 4);

      totalExtractRect = {
        x: Math.max(0, xOrigin),
        y: Math.max(0, yOrigin),
        width: Math.min(width, imageMat.width - Math.max(0, xOrigin)),
        height: Math.min(height, imageMat.height - Math.max(0, yOrigin)),
      };
    } else {
      // Server: app page extraction — narrow region on left side
      const height = Math.floor(totalRect.height * 6);
      const yOrigin = totalRect.y + totalRect.height + 50;
      const xOrigin = Math.max(0, totalRect.x - 20);
      const maxWidth = Math.floor(imageMat.width / 3);
      const width = Math.min(Math.floor(totalRect.width * 3), maxWidth);

      totalExtractRect = {
        x: xOrigin,
        y: Math.max(0, yOrigin),
        width: Math.min(width, imageMat.width - xOrigin),
        height: Math.min(height, imageMat.height - Math.max(0, yOrigin)),
      };
    }
  } else if (ocr.isDaily) {
    // Server fallback: img[325:425, 30:450]
    totalExtractRect = { x: 30, y: 325, width: 420, height: 100 };
  } else {
    // Server fallback: img[250:350, 30:450]
    totalExtractRect = { x: 30, y: 250, width: 420, height: 100 };
  }

  // Server: total_find = extract_all_text(total_extract, ocr_config)
  const totalExtract = extractRegion(imageMat, totalExtractRect);
  let total = await extractAllText(worker, totalExtract, "total");

  // Server: text_piece.replace("Os", "0s")
  total = total.replace(/Os/g, "0s");

  // Server: _normalize_ocr_digits(total) then _extract_time_from_text(total)
  total = normalizeOcrDigits(total);
  const extracted = extractTimeFromText(total);
  if (extracted) {
    total = extracted;
  }

  // Server: regex fallback if no time pattern found
  // Server does 3-tier fallback: left third → left half → full image
  // We simulate this by filtering cached OCR words by x-position
  if (!total || !/\d+\s*[hms]/.test(total)) {
    const imgWidth = imageMat.width;
    // Try left third first (avoids "Daily Average" on right side)
    const leftThirdText = ocr.words
      .filter(w => w.bbox && w.bbox.x1 <= imgWidth / 3)
      .map(w => w.text).join(" ").replace(/Os/g, "0s");
    let regexTotal = extractTimeFromText(normalizeOcrDigits(leftThirdText));
    if (!regexTotal) {
      // Try left half
      const leftHalfText = ocr.words
        .filter(w => w.bbox && w.bbox.x1 <= imgWidth / 2)
        .map(w => w.text).join(" ").replace(/Os/g, "0s");
      regexTotal = extractTimeFromText(normalizeOcrDigits(leftHalfText));
    }
    if (!regexTotal) {
      // Full image fallback
      regexTotal = findTotalUsageRegex(ocr.text);
    }
    if (regexTotal) {
      return regexTotal;
    }
  }

  return total;
}

/**
 * Normalize common OCR digit misreadings.
 * Port of server's _normalize_ocr_digits().
 */
function normalizeOcrDigits(text: string): string {
  let result = text;

  // I, l, | -> 1
  result = result.replace(/([Il|])(\s*[hm]\b)/g, "1$2");
  result = result.replace(/(\d)([Il|])(\s*[hms]\b)/g, "$11$3");
  result = result.replace(/([Il|])(\d)/g, "1$2");

  // O -> 0
  result = result.replace(/(O)(\s*[hms]\b)/g, "0$2");
  result = result.replace(/(\d)(O)(\s*[hms]\b)/g, "$10$3");
  result = result.replace(/(O)(\d)/g, "0$2");
  result = result.replace(/(\d)(O)(\d)/g, "$10$3");

  // A -> 4
  result = result.replace(/(A)(\s*[hm]\b)/g, "4$2");
  result = result.replace(/(\d)(A)(\s*[hms]\b)/g, "$14$3");

  // S -> 5 (not when it's the 's' seconds unit)
  result = result.replace(/(S)(\s*[hm]\b)/g, "5$2");
  result = result.replace(/(\d)(S)(\s*[hm]\b)/g, "$15$3");
  result = result.replace(/(S)(\d)/g, "5$2");

  // G, b -> 6
  result = result.replace(/([Gb])(\s*[hms]\b)/g, "6$2");
  result = result.replace(/(\d)([Gb])(\s*[hms]\b)/g, "$16$3");

  // B -> 8
  result = result.replace(/(B)(\s*[hms]\b)/g, "8$2");
  result = result.replace(/(\d)(B)(\s*[hms]\b)/g, "$18$3");

  // g, q -> 9
  result = result.replace(/([gq])(\s*[hms]\b)/g, "9$2");
  result = result.replace(/(\d)([gq])(\s*[hms]\b)/g, "$19$3");

  // Z -> 2
  result = result.replace(/(Z)(\s*[hms]\b)/g, "2$2");
  result = result.replace(/(\d)(Z)(\s*[hms]\b)/g, "$12$3");

  // T -> 7
  result = result.replace(/(T)(\s*[hms]\b)/g, "7$2");
  result = result.replace(/(\d)(T)(\s*[hms]\b)/g, "$17$3");

  return result;
}

/**
 * Extract time duration from text.
 * Port of server's _extract_time_from_text().
 */
function extractTimeFromText(rawText: string): string {
  const text = normalizeOcrDigits(rawText);

  let match = text.match(/(\d{1,2})\s*h\s*(\d{1,2})\s*m/);
  if (match && match[1] && match[2]) {
    return `${match[1]}h ${match[2]}m`;
  }

  // Fallback: "Xh YY" where OCR missed the 'm'
  match = text.match(/(\d{1,2})\s*h\s+(\d{1,2})(?!\s*[hms])/);
  if (match && match[1] && match[2]) {
    return `${match[1]}h ${match[2]}m`;
  }

  match = text.match(/(\d{1,2})\s*m\s*([0O]|\d{1,2})\s*s/);
  if (match && match[1] && match[2]) {
    const seconds = match[2].replace(/O/g, "0");
    return `${match[1]}m ${seconds}s`;
  }

  match = text.match(/(\d{1,2})\s*h\b/);
  if (match && match[1]) {
    return `${match[1]}h`;
  }

  match = text.match(/(\d{1,2})\s*m\b/);
  if (match && match[1]) {
    return `${match[1]}m`;
  }

  match = text.match(/([0O]|\d{1,2})\s*s\b/);
  if (match && match[1]) {
    const seconds = match[1].replace(/O/g, "0");
    return `${seconds}s`;
  }

  return "";
}

/** Extract a time duration from text using regex patterns (no OCR call). */
function findTotalUsageRegex(rawText: string): string {
  const text = rawText.replace(/Os/g, "0s");
  return extractTimeFromText(text);
}

/**
 * Extracts text from specific ROI coordinates.
 * Port of server's get_text().
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

function cleanDateString(dateString: string | undefined): string {
  if (!dateString) return "";
  return dateString.replace(/[^a-zA-Z0-9\s]/g, "");
}

function isDate(str: string): boolean {
  const months = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  const pattern = new RegExp(`^(${months.join("|")})\\s+\\d{1,2}$`);
  return pattern.test(str);
}

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
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
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
