import { create } from "zustand";
import { PHI_REDACTION_METHODS, GRID_DETECTION_METHODS } from "@/core/generated/constants";

export interface ProcessingSettings {
  /** Auto-skip daily total screenshots during preprocessing */
  skipDailyTotals: boolean;
  /** Default grid detection method */
  gridDetectionMethod: "line_based" | "ocr_anchored";
  /** Boundary optimizer max pixel shift (0 = disabled) */
  maxShift: number;
  /** Auto-run OCR processing when screenshots are uploaded */
  autoProcessOnUpload: boolean;
  /** NER detector for PHI detection: presidio (fast) or gliner (accurate) */
  phiNerDetector: "presidio" | "gliner";
  /** PHI redaction method */
  phiRedactionMethod: "redbox" | "blackbox" | "pixelate";
  /** Auto-advance to next screenshot after verifying */
  autoAdvanceAfterVerify: boolean;
}

const STORAGE_KEY = "processing-settings";

const DEFAULTS: ProcessingSettings = {
  skipDailyTotals: false,
  gridDetectionMethod: "line_based",
  maxShift: 5,
  autoProcessOnUpload: false,
  phiNerDetector: "presidio",
  phiRedactionMethod: "redbox",
  autoAdvanceAfterVerify: true,
};

function loadFromStorage(): ProcessingSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw);
    const merged = { ...DEFAULTS, ...parsed };
    // Sanitize fields that could be corrupted to invalid types
    const shift = Number(merged.maxShift);
    merged.maxShift = Number.isFinite(shift) ? Math.max(0, Math.min(10, shift)) : DEFAULTS.maxShift;
    if (!(GRID_DETECTION_METHODS as readonly string[]).includes(merged.gridDetectionMethod)) {
      merged.gridDetectionMethod = DEFAULTS.gridDetectionMethod;
    }
    if (!["presidio", "gliner"].includes(merged.phiNerDetector)) {
      merged.phiNerDetector = DEFAULTS.phiNerDetector;
    }
    if (!(PHI_REDACTION_METHODS as readonly string[]).includes(merged.phiRedactionMethod)) {
      merged.phiRedactionMethod = DEFAULTS.phiRedactionMethod;
    }
    return merged;
  } catch {
    return DEFAULTS;
  }
}

function saveToStorage(settings: ProcessingSettings) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

interface SettingsState extends ProcessingSettings {
  set: <K extends keyof ProcessingSettings>(key: K, value: ProcessingSettings[K]) => void;
  reset: () => void;
}

export const useSettingsStore = create<SettingsState>((set) => ({
  ...loadFromStorage(),
  set: (key, value) =>
    set((state) => {
      const updated = { ...state, [key]: value };
      saveToStorage({
        skipDailyTotals: updated.skipDailyTotals,
        gridDetectionMethod: updated.gridDetectionMethod,
        maxShift: updated.maxShift,
        autoProcessOnUpload: updated.autoProcessOnUpload,
        phiNerDetector: updated.phiNerDetector,
        phiRedactionMethod: updated.phiRedactionMethod,
        autoAdvanceAfterVerify: updated.autoAdvanceAfterVerify,
      });
      return { [key]: value };
    }),
  reset: () => {
    saveToStorage(DEFAULTS);
    set(DEFAULTS);
  },
}));
