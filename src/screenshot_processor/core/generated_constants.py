"""
AUTO-GENERATED from shared/*.json — do not edit manually.
Hash: 63aa46172e6b1efe
Regenerate: python scripts/generate-shared-constants.py
"""

from __future__ import annotations

RESOLUTION_LOOKUP_TABLE: dict[str, dict[str, int]] = {
    "640x1136": {"x": 30, "y": 270, "width": 510, "height": 180},
    "750x1334": {"x": 60, "y": 670, "width": 560, "height": 180},
    "750x1624": {"x": 60, "y": 450, "width": 560, "height": 180},
    "828x1792": {"x": 70, "y": 450, "width": 620, "height": 180},
    "848x2266": {"x": 70, "y": 390, "width": 640, "height": 180},
    "858x2160": {"x": 70, "y": 390, "width": 640, "height": 180},
    "896x2048": {"x": 70, "y": 500, "width": 670, "height": 180},
    "906x2160": {"x": 70, "y": 390, "width": 690, "height": 180},
    "960x2079": {"x": 80, "y": 620, "width": 720, "height": 270},
    "980x2160": {"x": 80, "y": 390, "width": 730, "height": 180},
    "990x2160": {"x": 80, "y": 390, "width": 740, "height": 180},
    "1000x2360": {"x": 80, "y": 420, "width": 790, "height": 180},
    "1028x2224": {"x": 80, "y": 400, "width": 820, "height": 180},
    "1028x2388": {"x": 80, "y": 400, "width": 820, "height": 180},
    "1170x2532": {"x": 90, "y": 640, "width": 880, "height": 270},
    "1258x2732": {"x": 80, "y": 450, "width": 1020, "height": 180},
}

DAILY_PAGE_MARKERS: list[str] = ["WEEK", "DAY", "MOST", "USED", "CATEGORIES", "TODAY", "SHOW", "ENTERTAINMENT", "EDUCATION", "INFORMATION", "READING"]
APP_PAGE_MARKERS: list[str] = ["INFO", "DEVELOPER", "RATING", "LIMIT", "AGE", "DAILY", "AVERAGE"]

NUM_SLICES: int = 24
MAX_Y: int = 60
LOWER_GRID_BUFFER: int = 2
SCALE_AMOUNT: int = 4
DARK_MODE_THRESHOLD: int = 100
DARKEN_NON_WHITE_LUMA_THRESHOLD: int = 240
DARKEN_NON_WHITE_LUMA_COEFFS: tuple[int, int, int] = (77, 150, 29)
DARKEN_NON_WHITE_LUMA_SHIFT: int = 8

H_GRAY_MIN: int = 195
H_GRAY_MAX: int = 210
H_MIN_WIDTH_PCT: float = 0.35
H_MIN_LINES: int = 4
H_MAX_LINES: int = 8
H_MAX_SPACING_DEVIATION: int = 10

V_GRAY_MIN: int = 190
V_GRAY_MAX: int = 215
V_MIN_HEIGHT_PCT: float = 0.4
V_EXPECTED_LINES: list[int] = [3, 4, 5]
V_SPACING_TOLERANCE: float = 0.25

EDGE_GRAY_MIN: int = 190
EDGE_GRAY_MAX: int = 220
EDGE_MIN_COVERAGE: float = 0.3

BLUE_HUE_MIN: int = 100
BLUE_HUE_MAX: int = 130
CYAN_HUE_MIN: int = 80
CYAN_HUE_MAX: int = 100
COLOR_MIN_SATURATION: int = 50
COLOR_MIN_VALUE: int = 50
MIN_BLUE_RATIO: float = 0.5

# OCR test vectors for cross-implementation parity testing
OCR_NORMALIZE_TEST_VECTORS: list[tuple[str, str]] = [["Ih 3Om", "1h 30m"], ["I2", "12"], ["3I h", "31 h"], ["O h", "0 h"], ["1O h", "10 h"], ["O5", "05"], ["1O2", "102"], ["S h", "5 h"], ["3S h", "35 h"], ["A h", "4 h"], ["1A h", "14 h"], ["hello world", "hello world"], ["3h 45m", "3h 45m"]]
OCR_EXTRACT_TIME_TEST_VECTORS: list[tuple[str, str]] = [["4h 36m", "4h 36m"], ["12h 5m", "12h 5m"], ["some text 2h 30m more text", "2h 30m"], ["4h 36", "4h 36m"], ["45m 30s", "45m 30s"], ["5m Os", "5m 0s"], ["3h", "3h"], ["45m", "45m"], ["30s", "30s"], ["no time here", ""], ["", ""], ["Ih 3Om", "1h 30m"]]

EXPORT_CSV_HEADERS: list[str] = ["Screenshot ID", "Filename", "Original Filepath", "Group ID", "Participant ID", "Image Type", "Screenshot Date", "Uploaded At", "Processing Status", "Is Verified", "Verified By Count", "Annotation Count", "Has Consensus", "Title", "OCR Total", "Computed Total", "Disagreement Count", "Hour 0", "Hour 1", "Hour 2", "Hour 3", "Hour 4", "Hour 5", "Hour 6", "Hour 7", "Hour 8", "Hour 9", "Hour 10", "Hour 11", "Hour 12", "Hour 13", "Hour 14", "Hour 15", "Hour 16", "Hour 17", "Hour 18", "Hour 19", "Hour 20", "Hour 21", "Hour 22", "Hour 23"]

# Shared enum values — single source of truth (shared/enums.json)
PREPROCESSING_STAGES: list[str] = ["device_detection", "cropping", "phi_detection", "phi_redaction", "ocr"]
PROCESSING_STATUSES: list[str] = ["pending", "processing", "completed", "failed", "skipped", "deleted"]
ANNOTATION_STATUSES: list[str] = ["pending", "annotated", "verified", "skipped"]
STAGE_STATUSES: list[str] = ["pending", "running", "completed", "skipped", "failed", "invalidated", "cancelled"]
PHI_REDACTION_METHODS: list[str] = ["redbox", "blackbox", "pixelate"]
GRID_DETECTION_METHODS: list[str] = ["line_based", "ocr_anchored"]
IMAGE_TYPES: list[str] = ["screen_time", "battery"]
USER_ROLES: list[str] = ["admin", "annotator"]
WEBSOCKET_EVENTS: list[str] = ["annotation_submitted", "screenshot_completed", "consensus_disputed", "user_joined", "user_left"]

SHARED_CONSTANTS_HASH: str = "63aa46172e6b1efe"
