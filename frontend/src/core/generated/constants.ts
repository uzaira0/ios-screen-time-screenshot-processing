/**
 * AUTO-GENERATED from shared/*.json — do not edit manually.
 * Hash: 63aa46172e6b1efe
 * Regenerate: python scripts/generate-shared-constants.py
 */

export const RESOLUTION_LOOKUP_TABLE: Record<string, { x: number; y: number; width: number; height: number }> = {
  "640x1136": { x: 30, y: 270, width: 510, height: 180 },
  "750x1334": { x: 60, y: 670, width: 560, height: 180 },
  "750x1624": { x: 60, y: 450, width: 560, height: 180 },
  "828x1792": { x: 70, y: 450, width: 620, height: 180 },
  "848x2266": { x: 70, y: 390, width: 640, height: 180 },
  "858x2160": { x: 70, y: 390, width: 640, height: 180 },
  "896x2048": { x: 70, y: 500, width: 670, height: 180 },
  "906x2160": { x: 70, y: 390, width: 690, height: 180 },
  "960x2079": { x: 80, y: 620, width: 720, height: 270 },
  "980x2160": { x: 80, y: 390, width: 730, height: 180 },
  "990x2160": { x: 80, y: 390, width: 740, height: 180 },
  "1000x2360": { x: 80, y: 420, width: 790, height: 180 },
  "1028x2224": { x: 80, y: 400, width: 820, height: 180 },
  "1028x2388": { x: 80, y: 400, width: 820, height: 180 },
  "1170x2532": { x: 90, y: 640, width: 880, height: 270 },
  "1258x2732": { x: 80, y: 450, width: 1020, height: 180 },
};

export const DAILY_PAGE_MARKERS: readonly string[] = ["WEEK", "DAY", "MOST", "USED", "CATEGORIES", "TODAY", "SHOW", "ENTERTAINMENT", "EDUCATION", "INFORMATION", "READING"] as const;
export const APP_PAGE_MARKERS: readonly string[] = ["INFO", "DEVELOPER", "RATING", "LIMIT", "AGE", "DAILY", "AVERAGE"] as const;

export const NUM_SLICES = 24;
export const MAX_Y = 60;
export const LOWER_GRID_BUFFER = 2;
export const SCALE_AMOUNT = 4;
export const DARK_MODE_THRESHOLD = 100;
export const DARKEN_NON_WHITE_LUMA_THRESHOLD = 240;
export const DARKEN_NON_WHITE_LUMA_COEFFS = [77, 150, 29] as const;
export const DARKEN_NON_WHITE_LUMA_SHIFT = 8;

export const H_GRAY_MIN = 195;
export const H_GRAY_MAX = 210;
export const H_MIN_WIDTH_PCT = 0.35;
export const V_GRAY_MIN = 190;
export const V_GRAY_MAX = 215;
export const V_MIN_HEIGHT_PCT = 0.4;
export const EDGE_GRAY_MIN = 190;
export const EDGE_GRAY_MAX = 220;

export const BLUE_HUE_MIN = 100;
export const BLUE_HUE_MAX = 130;
export const CYAN_HUE_MIN = 80;
export const CYAN_HUE_MAX = 100;
export const COLOR_MIN_SATURATION = 50;
export const COLOR_MIN_VALUE = 50;
export const MIN_BLUE_RATIO = 0.5;

export const EXPORT_CSV_HEADERS: readonly string[] = ["Screenshot ID", "Filename", "Original Filepath", "Group ID", "Participant ID", "Image Type", "Screenshot Date", "Uploaded At", "Processing Status", "Is Verified", "Verified By Count", "Annotation Count", "Has Consensus", "Title", "OCR Total", "Computed Total", "Disagreement Count", "Hour 0", "Hour 1", "Hour 2", "Hour 3", "Hour 4", "Hour 5", "Hour 6", "Hour 7", "Hour 8", "Hour 9", "Hour 10", "Hour 11", "Hour 12", "Hour 13", "Hour 14", "Hour 15", "Hour 16", "Hour 17", "Hour 18", "Hour 19", "Hour 20", "Hour 21", "Hour 22", "Hour 23"] as const;

// Shared enum values — single source of truth (shared/enums.json)
export const PREPROCESSING_STAGES = ["device_detection", "cropping", "phi_detection", "phi_redaction", "ocr"] as const;
export type PreprocessingStages = (typeof PREPROCESSING_STAGES)[number];
export const PROCESSING_STATUSES = ["pending", "processing", "completed", "failed", "skipped", "deleted"] as const;
export type ProcessingStatuses = (typeof PROCESSING_STATUSES)[number];
export const ProcessingStatus = { PENDING: "pending" as const, PROCESSING: "processing" as const, COMPLETED: "completed" as const, FAILED: "failed" as const, SKIPPED: "skipped" as const, DELETED: "deleted" as const };
export const ANNOTATION_STATUSES = ["pending", "annotated", "verified", "skipped"] as const;
export type AnnotationStatuses = (typeof ANNOTATION_STATUSES)[number];
export const AnnotationStatus = { PENDING: "pending" as const, ANNOTATED: "annotated" as const, VERIFIED: "verified" as const, SKIPPED: "skipped" as const };
export const STAGE_STATUSES = ["pending", "running", "completed", "skipped", "failed", "invalidated", "cancelled"] as const;
export type StageStatuses = (typeof STAGE_STATUSES)[number];
export const StageStatus = { PENDING: "pending" as const, RUNNING: "running" as const, COMPLETED: "completed" as const, SKIPPED: "skipped" as const, FAILED: "failed" as const, INVALIDATED: "invalidated" as const, CANCELLED: "cancelled" as const };
export const PHI_REDACTION_METHODS = ["redbox", "blackbox", "pixelate"] as const;
export type PhiRedactionMethods = (typeof PHI_REDACTION_METHODS)[number];
export const PhiRedactionMethod = { REDBOX: "redbox" as const, BLACKBOX: "blackbox" as const, PIXELATE: "pixelate" as const };
export const GRID_DETECTION_METHODS = ["line_based", "ocr_anchored"] as const;
export type GridDetectionMethods = (typeof GRID_DETECTION_METHODS)[number];
export const GridDetectionMethod = { LINE_BASED: "line_based" as const, OCR_ANCHORED: "ocr_anchored" as const };
export const IMAGE_TYPES = ["screen_time", "battery"] as const;
export type ImageTypes = (typeof IMAGE_TYPES)[number];
export const USER_ROLES = ["admin", "annotator"] as const;
export type UserRoles = (typeof USER_ROLES)[number];
export const UserRole = { ADMIN: "admin" as const, ANNOTATOR: "annotator" as const };
export const WEBSOCKET_EVENTS = ["annotation_submitted", "screenshot_completed", "consensus_disputed", "user_joined", "user_left"] as const;
export type WebsocketEvents = (typeof WEBSOCKET_EVENTS)[number];

export const SHARED_CONSTANTS_HASH = "63aa46172e6b1efe";
