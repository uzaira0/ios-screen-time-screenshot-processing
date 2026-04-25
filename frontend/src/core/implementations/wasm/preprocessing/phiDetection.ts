/**
 * Client-side PHI detection using the Rust+leptess OCR (via Emscripten WASM)
 * + Transformers.js NER + regex patterns.
 *
 * Replicates the server's Presidio + regex pipeline:
 * 1. OCR with `pipeline_phi_words` (Rust + libtesseract) → words with bboxes
 * 2. NER with BERT (via Web Worker) → PERSON, ORG, LOC, MISC entities
 * 3. Regex patterns → email, phone, SSN, MRN, etc.
 * 4. Allow-list filtering → remove known false positives (app names, UI labels)
 * 5. Map matches back to image coordinates via OCR word bboxes
 */

import type { PHIRegion } from "@/core/interfaces/IPreprocessingService";
import { emPhiWords } from "@/core/implementations/wasm/processing/emscripten/pipelineLoader";
export type { PHIRegion };

export interface PHIDetectionResult {
  regions: PHIRegion[];
  ocrText: string;
  ocrConfidence: number;
  /** Indicates whether the NER engine ran successfully. "skipped" means only regex ran. */
  nerStatus: "success" | "failed" | "timeout" | "skipped";
}

// Word with bounding box from Tesseract.js
interface OCRWord {
  text: string;
  bbox: { x0: number; y0: number; x1: number; y1: number };
  confidence: number;
  charStart: number; // offset into full text
  charEnd: number;
}

// NER entity from worker
interface NEREntity {
  entity_group: string;
  word: string;
  start: number;
  end: number;
  score: number;
}

// ---------------------------------------------------------------------------
// Regex patterns (ported from Python phi-detector-remover/core/detectors/regex.py)
// ---------------------------------------------------------------------------

const REGEX_PATTERNS: Array<{ label: string; pattern: RegExp }> = [
  { label: "email", pattern: /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g },
  { label: "phone", pattern: /(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}/g },
  // SSN with IRS validation: exclude 000/666/9xx area numbers, 00 group, 0000 serial
  { label: "ssn", pattern: /\b(?!000|666|9\d{2})\d{3}[-.]?(?!00)\d{2}[-.]?(?!0000)\d{4}\b/g },
  { label: "mrn", pattern: /(?:MRN|Medical Record|Record #)[:\s]*(\d{6,10})/gi },
  { label: "study_id", pattern: /(?:EXAMPLE_STUDY|STUDY)[_-]?\d{4}(?:[_-]\d+)?/gi },
  { label: "zip", pattern: /\b\d{5}(?:-\d{4})?\b/g },
  { label: "url", pattern: /https?:\/\/[^\s]+/g },
  { label: "ip_address", pattern: /\b(?:\d{1,3}\.){3}\d{1,3}\b/g },
  { label: "credit_card", pattern: /\b(?:\d{4}[-\s]?){3}\d{4}\b/g },
  // Apple device serial (12 alphanumeric chars)
  { label: "device_serial", pattern: /\b[A-Z0-9]{12}\b/g },
  // IMEI (15 digits)
  { label: "imei", pattern: /\b\d{15}\b/g },
  // UUID
  { label: "uuid", pattern: /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi },
];

// ---------------------------------------------------------------------------
// Allow-list — matching server Presidio config
// Terms that should never be flagged as PHI in iOS Screen Time screenshots
// ---------------------------------------------------------------------------

const ALLOW_LIST = new Set([
  // Wi-Fi variations
  "Wi-Fi", "WiFi", "wi",
  // App names commonly flagged as PERSON/ORG
  "Disney", "Disney+", "Lingokids", "Photo Booth",
  "Screen Time", "App Store", "Control Center", "Bluetooth",
  "YT Kids", "YT", "YouTube", "YouTube Kids",
  "TikTok", "Instagram", "Safari", "Netflix",
  "Roblox", "Minecraft", "Fortnite",
  "PBS Kids", "Nick Jr",
  // UI labels
  "Daily Average", "Pickups", "Notifications",
  "Most Used", "Show More", "Show Less",
  "Settings", "General", "Privacy",
  // Time strings (common OCR noise)
  "12 AM", "12AM", "AM", "PM",
]);

// Case-insensitive version for comparison
const ALLOW_LIST_LOWER = new Set([...ALLOW_LIST].map((s) => s.toLowerCase()));

// Entity types to exclude (matching server Presidio config — too many false positives)
const EXCLUDED_ENTITY_TYPES = new Set(["DATE_TIME", "LOCATION", "LOC"]);

// Min bounding box area to consider a valid detection
const MIN_BBOX_AREA = 100;

// ---------------------------------------------------------------------------
// NER Worker management
// ---------------------------------------------------------------------------

let nerWorker: Worker | null = null;
let nerRequestId = 0;
const pendingNER = new Map<number, {
  resolve: (result: NERResult) => void;
  reject: (err: Error) => void;
}>();

interface NERResult {
  entities: NEREntity[];
  status: "success" | "failed" | "timeout" | "skipped";
}

function getNERWorker(): Worker {
  if (!nerWorker) {
    nerWorker = new Worker(
      new URL("./nerWorker.ts", import.meta.url),
      { type: "module" },
    );
    nerWorker.onmessage = (e: MessageEvent) => {
      const { id, entities, error } = e.data;
      if (e.data.type === "ready" || e.data.type === "error") return;
      const pending = pendingNER.get(id);
      if (pending) {
        pendingNER.delete(id);
        if (error) {
          console.warn(`[phiDetection] NER failed for request ${id}: ${error} — falling back to regex-only`);
          pending.resolve({ entities: [], status: "failed" });
        } else {
          pending.resolve({ entities, status: "success" });
        }
      }
    };
    nerWorker.onerror = (e: ErrorEvent) => {
      console.error("[phiDetection] NER worker error:", e.message);
      // Reject all pending requests
      for (const [id, pending] of pendingNER) {
        pending.resolve({ entities: [], status: "failed" });
        pendingNER.delete(id);
      }
      // Worker is broken — reset so it gets recreated on next call
      nerWorker = null;
    };
    // Pre-initialize the pipeline
    nerWorker.postMessage({ type: "init" });
  }
  return nerWorker;
}

async function runNER(text: string): Promise<NERResult> {
  if (!text.trim()) return { entities: [], status: "skipped" };

  const worker = getNERWorker();
  const id = ++nerRequestId;

  return new Promise((resolve) => {
    pendingNER.set(id, { resolve, reject: () => resolve({ entities: [], status: "failed" }) });
    worker.postMessage({ text, id });

    // Timeout after 60s (model download on first run can exceed 30s)
    setTimeout(() => {
      if (pendingNER.has(id)) {
        pendingNER.delete(id);
        console.warn(`[phiDetection] NER timed out after 60s for request ${id} — falling back to regex-only`);
        resolve({ entities: [], status: "timeout" });
      }
    }, 60_000);
  });
}

/**
 * No-op kept for backwards compatibility with WASMPreprocessingService —
 * the OCR engine is now the shared Emscripten pipeline module which has its
 * own (singleton) lifecycle. No Tesseract.js worker to tear down.
 */
export function terminateTesseractWorker(): void {}

// ---------------------------------------------------------------------------
// OCR helper — full-page Rust OCR via the Emscripten pipeline.
//
// Replaces Tesseract.js. The Rust side returns word-level boxes with
// confidence and pre-computed char offsets into a joined `full_text`,
// matching the contract that NER/regex/allow-list code below already uses.
// ---------------------------------------------------------------------------

async function blobToImageData(imageBlob: Blob): Promise<ImageData> {
  const imageBitmap = await createImageBitmap(imageBlob);
  try {
    const canvas = new OffscreenCanvas(imageBitmap.width, imageBitmap.height);
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      throw new Error(
        `Failed to get 2D context for ${imageBitmap.width}x${imageBitmap.height} OffscreenCanvas`,
      );
    }
    ctx.drawImage(imageBitmap, 0, 0);
    return ctx.getImageData(0, 0, imageBitmap.width, imageBitmap.height);
  } finally {
    imageBitmap.close();
  }
}

async function ocrWithBboxes(imageBlob: Blob): Promise<{
  words: OCRWord[];
  fullText: string;
  confidence: number;
}> {
  const imageData = await blobToImageData(imageBlob);
  const result = await emPhiWords(imageData);

  if (!result.success || !result.words) {
    throw new Error(`PHI OCR failed: ${result.error ?? "unknown"}`);
  }

  const words: OCRWord[] = result.words.map((w) => ({
    text: w.text,
    bbox: { x0: w.x, y0: w.y, x1: w.x + w.w, y1: w.y + w.h },
    confidence: w.conf,
    charStart: w.char_start,
    charEnd: w.char_end,
  }));

  return {
    words,
    fullText: result.full_text ?? "",
    // Tesseract conf is 0–100; downstream consumers don't care about scale,
    // but keep it as a number.
    confidence: result.avg_confidence ?? 0,
  };
}

// ---------------------------------------------------------------------------
// Map text offsets back to image bounding boxes
// ---------------------------------------------------------------------------

function offsetToRegion(
  start: number,
  end: number,
  words: OCRWord[],
): { x: number; y: number; w: number; h: number } | null {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  let found = false;

  for (const word of words) {
    // Check if word overlaps with the match range
    if (word.charEnd > start && word.charStart < end) {
      found = true;
      minX = Math.min(minX, word.bbox.x0);
      minY = Math.min(minY, word.bbox.y0);
      maxX = Math.max(maxX, word.bbox.x1);
      maxY = Math.max(maxY, word.bbox.y1);
    }
  }

  if (!found) return null;

  return {
    x: minX,
    y: minY,
    w: maxX - minX,
    h: maxY - minY,
  };
}

// ---------------------------------------------------------------------------
// Check if a detected text is in the allow list
// ---------------------------------------------------------------------------

function isAllowListed(text: string): boolean {
  const trimmed = text.trim();
  if (ALLOW_LIST.has(trimmed)) return true;
  const trimmedLower = trimmed.toLowerCase();
  if (ALLOW_LIST_LOWER.has(trimmedLower)) return true;

  // Check if the text is a substring of an allow-listed term
  if (trimmed.length >= 3) {
    for (const allowedLower of ALLOW_LIST_LOWER) {
      if (allowedLower.includes(trimmedLower)) return true;
    }
  }
  return false;
}

// ---------------------------------------------------------------------------
// Main detection function
// ---------------------------------------------------------------------------

export interface DetectPHIOptions {
  llmEndpoint?: string | undefined;
  llmModel?: string | undefined;
  llmApiKey?: string | undefined;
}

export async function detectPHI(imageBlob: Blob, options?: DetectPHIOptions): Promise<PHIDetectionResult> {
  // Step 1: OCR with bounding boxes
  const { words, fullText, confidence } = await ocrWithBboxes(imageBlob);

  if (!fullText.trim()) {
    return { regions: [], ocrText: "", ocrConfidence: 0, nerStatus: "skipped" };
  }

  // Step 2 & 3: Run NER, regex, and optionally LLM in parallel
  const tasks: [Promise<NERResult>, Promise<RegexMatch[]>, Promise<LLMEntity[]>] = [
    runNER(fullText),
    Promise.resolve(findRegexMatches(fullText)),
    options?.llmEndpoint && options?.llmModel
      ? runLLMDetection(fullText, options.llmEndpoint, options.llmModel, options.llmApiKey)
      : Promise.resolve([]),
  ];

  const [nerResult, regexMatches, llmEntities] = await Promise.all(tasks);

  const nerEntities = nerResult.entities;

  const regions: PHIRegion[] = [];

  // Step 4: Process NER results
  for (const entity of nerEntities) {
    if (EXCLUDED_ENTITY_TYPES.has(entity.entity_group)) continue;
    if (isAllowListed(entity.word)) continue;

    const bbox = offsetToRegion(entity.start, entity.end, words);
    if (!bbox) continue;
    if (bbox.w * bbox.h < MIN_BBOX_AREA) continue;

    regions.push({
      ...bbox,
      label: entity.entity_group,
      source: "ner",
      confidence: entity.score,
      text: entity.word,
    });
  }

  // Step 5: Process regex matches
  for (const match of regexMatches) {
    if (isAllowListed(match.text)) continue;

    const bbox = offsetToRegion(match.start, match.end, words);
    if (!bbox) continue;
    if (bbox.w * bbox.h < MIN_BBOX_AREA) continue;

    if (isDuplicateRegion(regions, bbox)) continue;

    regions.push({
      ...bbox,
      label: match.label,
      source: "regex",
      confidence: 0.85,
      text: match.text,
    });
  }

  // Step 6: Process LLM results
  for (const entity of llmEntities) {
    if (isAllowListed(entity.text)) continue;

    const bbox = offsetToRegion(entity.start, entity.end, words);
    if (!bbox) continue;
    if (bbox.w * bbox.h < MIN_BBOX_AREA) continue;

    if (isDuplicateRegion(regions, bbox)) continue;

    regions.push({
      ...bbox,
      label: entity.label,
      source: `llm:${options?.llmModel ?? "unknown"}`,
      confidence: entity.confidence,
      text: entity.text,
    });
  }

  return {
    regions,
    ocrText: fullText,
    ocrConfidence: confidence,
    nerStatus: nerResult.status,
  };
}

function isDuplicateRegion(
  existing: PHIRegion[],
  bbox: { x: number; y: number; w: number; h: number },
): boolean {
  return existing.some(
    (r) =>
      Math.abs(r.x - bbox.x) < 5 &&
      Math.abs(r.y - bbox.y) < 5 &&
      Math.abs(r.w - bbox.w) < 10 &&
      Math.abs(r.h - bbox.h) < 10,
  );
}

// ---------------------------------------------------------------------------
// LLM-assisted detection — calls an OpenAI-compatible chat/completions endpoint
// ---------------------------------------------------------------------------

interface LLMEntity {
  label: string;
  text: string;
  start: number;
  end: number;
  confidence: number;
}

const LLM_SYSTEM_PROMPT = `You are a PHI (Protected Health Information) detector for iOS Screen Time screenshots.
Given OCR-extracted text, identify ALL personally identifiable information.

Return ONLY a JSON array of objects with these fields:
- "label": entity type (PERSON, PHONE, EMAIL, SSN, MRN, ADDRESS, DATE_OF_BIRTH, MEDICAL_RECORD, DEVICE_ID)
- "text": the exact text matched (must appear verbatim in the input)
- "confidence": 0.0-1.0

Example: [{"label":"PERSON","text":"John Smith","confidence":0.95}]

If no PHI is found, return an empty array: []
Do NOT include app names, UI labels, or time strings. Only real PHI.`;

async function runLLMDetection(
  fullText: string,
  endpoint: string,
  model: string,
  apiKey?: string,
): Promise<LLMEntity[]> {
  try {
    const url = `${endpoint.replace(/\/+$/, "")}/chat/completions`;
    console.log(`[phiDetection] Querying LLM at ${url} with model ${model}`);

    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (apiKey) {
      headers["Authorization"] = `Bearer ${apiKey}`;
    }

    const response = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify({
        model,
        messages: [
          { role: "system", content: LLM_SYSTEM_PROMPT },
          { role: "user", content: `Analyze this OCR text for PHI:\n\n${fullText}` },
        ],
        temperature: 0.1,
        max_tokens: 2048,
      }),
    });

    if (!response.ok) {
      console.error(`[phiDetection] LLM request failed: ${response.status} ${response.statusText}`);
      return [];
    }

    const data = await response.json();
    const content = data?.choices?.[0]?.message?.content ?? "";

    // Parse JSON from response (may be wrapped in ```json ... ```)
    const jsonMatch = content.match(/\[[\s\S]*\]/);
    if (!jsonMatch) {
      console.warn("[phiDetection] LLM returned no JSON array:", content.slice(0, 200));
      return [];
    }

    const parsed: Array<{ label: string; text: string; confidence: number }> = JSON.parse(jsonMatch[0]);
    if (!Array.isArray(parsed)) return [];

    // Map LLM entities back to text offsets
    const entities: LLMEntity[] = [];
    const textLower = fullText.toLowerCase();
    for (const item of parsed) {
      if (!item.text || !item.label) continue;
      const idx = textLower.indexOf(item.text.toLowerCase());
      if (idx === -1) continue;
      entities.push({
        label: item.label,
        text: item.text,
        start: idx,
        end: idx + item.text.length,
        confidence: item.confidence ?? 0.8,
      });
    }

    console.log(`[phiDetection] LLM found ${entities.length} entities`);
    return entities;
  } catch (err) {
    console.error("[phiDetection] LLM detection failed:", err);
    return [];
  }
}

// ---------------------------------------------------------------------------
// Regex matching helper
// ---------------------------------------------------------------------------

interface RegexMatch {
  label: string;
  text: string;
  start: number;
  end: number;
}

function findRegexMatches(text: string): RegexMatch[] {
  const matches: RegexMatch[] = [];

  for (const { label, pattern } of REGEX_PATTERNS) {
    // Reset regex state (lastIndex)
    const re = new RegExp(pattern.source, pattern.flags);
    let match: RegExpExecArray | null;

    while ((match = re.exec(text)) !== null) {
      matches.push({
        label,
        text: match[0],
        start: match.index,
        end: match.index + match[0].length,
      });
    }
  }

  return matches;
}

/**
 * Terminate the NER worker to free resources.
 * Call when preprocessing is complete or component unmounts.
 */
export function terminateNERWorker(): void {
  if (nerWorker) {
    nerWorker.terminate();
    nerWorker = null;
    pendingNER.clear();
  }
}
