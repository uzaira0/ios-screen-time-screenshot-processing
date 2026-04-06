from __future__ import annotations

import datetime
from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator
from screenshot_processor.core.generated_constants import EXPORT_CSV_HEADERS

# Import enums from models (single source of truth)
from .models import (
    AnnotationStatus as AnnotationStatusEnum,
)
from .models import (
    ProcessingMethod as ProcessingMethodEnum,
)
from .models import (
    ProcessingStatus as ProcessingStatusEnum,
)
from .models import (
    QueueStateStatus as QueueStateStatusEnum,
)
from .models import (
    SubmissionStatus as SubmissionStatusEnum,
)
from .models import (
    UserRole as UserRoleEnum,
)

# =============================================================================
# Shared Types - Used across multiple schemas
# =============================================================================


class Point(BaseModel):
    """A 2D point with x, y coordinates (pixel positions)."""

    x: int = Field(..., ge=0)
    y: int = Field(..., ge=0)


# Type aliases using model enums (single source of truth)
# These can be used in Pydantic models with the enum values
ImageType = Literal["battery", "screen_time"]
ProcessingStatus = ProcessingStatusEnum
AnnotationStatus = AnnotationStatusEnum
ProcessingMethod = ProcessingMethodEnum
UserRole = UserRoleEnum
SubmissionStatus = SubmissionStatusEnum
QueueStateStatus = QueueStateStatusEnum


class IssueSeverity(StrEnum):
    """Issue severity levels"""

    BLOCKING = "blocking"
    NON_BLOCKING = "non_blocking"


class IssueType(StrEnum):
    """Processing issue types"""

    GRID_DETECTION_FAILED = "grid_detection_failed"
    OCR_EXTRACTION_FAILED = "ocr_extraction_failed"
    ALIGNMENT_WARNING = "alignment_warning"
    CONFIDENCE_LOW = "confidence_low"
    MISSING_DATA = "missing_data"
    VALIDATION_ERROR = "validation_error"
    PROCESSING_ERROR = "ProcessingError"
    GRID_DETECTION_ISSUE = "GridDetectionIssue"


# =============================================================================
# Processing Issue Schema
# =============================================================================


class ProcessingIssue(BaseModel):
    """A processing issue encountered during OCR/grid detection."""

    issue_type: str  # Keep as str to allow unknown issue types from backend
    severity: IssueSeverity
    description: str
    message: str | None = None


class ProcessingIssueCreate(BaseModel):
    """Create a processing issue."""

    issue_type: str
    severity: IssueSeverity
    description: str
    annotation_id: int


class ProcessingIssueRead(BaseModel):
    """A processing issue with database fields."""

    id: int
    annotation_id: int
    issue_type: str
    severity: str  # Keep as str for DB compatibility
    description: str
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# User Schemas
# =============================================================================


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)


class UserCreate(UserBase):
    role: UserRole = Field(default="annotator")


class UserLogin(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str | None = Field(
        default=None,
        description="Shared access password. Required if ACCESS_PASSWORD is set in server config.",
    )


class PasswordRequiredResponse(BaseModel):
    password_required: bool = Field(..., description="Whether password is required for login")


class UserUpdate(BaseModel):
    email: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None


class UserRead(UserBase):
    id: int
    email: str | None = None
    role: str  # Keep as str for DB compatibility
    is_active: bool
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None
    user_id: int | None = None


# =============================================================================
# Screenshot Schemas
# =============================================================================


class ScreenshotBase(BaseModel):
    file_path: str = Field(..., max_length=500)
    image_type: ImageType


class ScreenshotCreate(ScreenshotBase):
    target_annotations: int = Field(default=1, ge=1)


class ScreenshotUpdate(BaseModel):
    annotation_status: AnnotationStatus | None = None
    target_annotations: int | None = Field(None, ge=1)
    extracted_title: str | None = None
    extracted_hourly_data: dict[str, int | float] | None = None


class ScreenshotRead(ScreenshotBase):
    id: int
    annotation_status: str  # Keep as str for DB compatibility
    target_annotations: int
    current_annotation_count: int
    has_consensus: bool | None
    uploaded_at: datetime.datetime
    uploaded_by_id: int | None
    processed_at: datetime.datetime | None = None
    processing_status: ProcessingStatus = "pending"
    extracted_title: str | None = None
    extracted_total: str | None = None
    extracted_hourly_data: dict[str, int | float] | None = None
    title_y_position: int | None = None
    # Grid coordinates as flat fields (consistent with DB model)
    grid_upper_left_x: int | None = None
    grid_upper_left_y: int | None = None
    grid_lower_right_x: int | None = None
    grid_lower_right_y: int | None = None
    processing_issues: list[ProcessingIssue] | None = None
    has_blocking_issues: bool = False
    alignment_score: float | None = None
    processing_method: ProcessingMethod | None = None
    grid_detection_confidence: float | None = None
    # API upload metadata
    participant_id: str | None = None
    group_id: str | None = None
    source_id: str | None = None
    device_type: str | None = None
    original_filepath: str | None = None
    screenshot_date: date | None = None
    # User verification tracking
    verified_by_user_ids: list[int] | None = None
    verified_by_usernames: list[str] | None = None  # Populated by API, not from DB
    # Dispute resolution fields
    resolved_hourly_data: dict[str, int | float] | None = None
    resolved_title: str | None = None
    resolved_total: str | None = None
    resolved_at: datetime.datetime | None = None
    resolved_by_user_id: int | None = None
    # Potential duplicate detection (same participant + date + title + total)
    potential_duplicate_of: int | None = None  # ID of the other screenshot
    duplicate_status: str | None = None  # processing_status of the duplicate (completed, skipped, etc.)
    # Processing metadata (preprocessing results, callback URLs, etc.)
    processing_metadata: dict | None = None
    content_hash: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def processing_time_seconds(self) -> float | None:
        """
        Time in seconds related to processing:
        - For PENDING screenshots: seconds since upload (waiting time)
        - For COMPLETED/FAILED screenshots: time between upload and processing completion
        - For other statuses: None
        """

        # Helper to ensure datetime is timezone-aware (SQLite may return naive datetimes)
        def ensure_tz_aware(dt: datetime.datetime) -> datetime.datetime:
            if dt.tzinfo is None:
                return dt.replace(tzinfo=datetime.timezone.utc)
            return dt

        if self.processing_status == "pending":
            # Waiting time - how long since upload
            now = datetime.datetime.now(datetime.timezone.utc)
            return (now - ensure_tz_aware(self.uploaded_at)).total_seconds()
        elif self.processed_at is not None:
            # Processing complete - show total duration
            return (ensure_tz_aware(self.processed_at) - ensure_tz_aware(self.uploaded_at)).total_seconds()
        return None

    @computed_field
    @property
    def alignment_score_status(self) -> dict | None:
        """
        Provides human-readable diagnostics for the alignment score.
        Returns a dict with status (good/warning/poor) and description.
        """
        if self.alignment_score is None:
            return None

        score = self.alignment_score
        if score >= 0.85:
            return {
                "status": "good",
                "description": "Excellent alignment - grid boundaries match well with the bar graph.",
                "action": None,
            }
        elif score >= 0.7:
            return {
                "status": "acceptable",
                "description": "Acceptable alignment - minor discrepancies that likely won't affect accuracy.",
                "action": "Consider reviewing the extracted values if results seem off.",
            }
        elif score >= 0.5:
            return {
                "status": "warning",
                "description": "Potential misalignment detected - grid boundaries may be slightly off.",
                "action": "Try adjusting the grid by dragging the boundary handles to better align with the bar graph.",
            }
        else:
            return {
                "status": "poor",
                "description": "Significant misalignment - grid boundaries do not match the bar graph.",
                "action": "Manually adjust the grid boundaries to align with the hourly bars. The bars should fit within the grid with correct hour alignment.",
            }


class ScreenshotDetail(ScreenshotRead):
    annotations_count: int = 0
    needs_annotations: int = 0


# =============================================================================
# Annotation Schemas
# =============================================================================


class AnnotationBase(BaseModel):
    """Base annotation with hourly values and grid coordinates."""

    hourly_values: dict[str, int | float] = Field(
        ..., description="Dictionary of hour (0-23) -> minutes (0-60, may be fractional)"
    )
    extracted_title: str | None = None
    extracted_total: str | None = None
    # Grid coordinates as nested Point objects
    grid_upper_left: Point | None = None
    grid_lower_right: Point | None = None
    time_spent_seconds: float | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=2000)

    @field_validator("hourly_values")
    @classmethod
    def validate_hourly_values(cls, v: dict[str, int | float]) -> dict[str, int | float]:
        """Light validation — reject clearly invalid data while accepting pipeline output.

        Pipeline can produce fractional values and slight > 60 overshoot, so bounds
        are generous. Only reject truly absurd values that indicate corruption.
        """
        for hour_key, minutes in v.items():
            try:
                hour = int(hour_key)
                if not 0 <= hour <= 23:
                    raise ValueError(f"Hour key '{hour_key}' must be between 0 and 23")
            except ValueError as e:
                if "must be between" in str(e):
                    raise
                raise ValueError(f"Hour key '{hour_key}' must be an integer")
            # Generous bounds — pipeline can overshoot slightly but reject absurd values
            if isinstance(minutes, (int, float)):
                if minutes < 0 or minutes > 120:
                    raise ValueError(f"Minutes value for hour {hour_key} out of bounds: {minutes}")
        return v

    @model_validator(mode="after")
    def validate_grid_coordinates(self) -> "AnnotationBase":
        """Validate grid coordinates are logically consistent."""
        if self.grid_upper_left is not None and self.grid_lower_right is not None:
            # Upper left should be above and to the left of lower right
            if self.grid_upper_left.x >= self.grid_lower_right.x:
                raise ValueError(
                    f"Grid upper_left.x ({self.grid_upper_left.x}) must be less than "
                    f"lower_right.x ({self.grid_lower_right.x})"
                )
            if self.grid_upper_left.y >= self.grid_lower_right.y:
                raise ValueError(
                    f"Grid upper_left.y ({self.grid_upper_left.y}) must be less than "
                    f"lower_right.y ({self.grid_lower_right.y})"
                )

            # Sanity check: grid shouldn't be too small (less than 10px on any dimension)
            min_grid_size = 10
            if (self.grid_lower_right.x - self.grid_upper_left.x) < min_grid_size:
                raise ValueError(
                    f"Grid width ({self.grid_lower_right.x - self.grid_upper_left.x}px) is too small, "
                    f"minimum is {min_grid_size}px"
                )
            if (self.grid_lower_right.y - self.grid_upper_left.y) < min_grid_size:
                raise ValueError(
                    f"Grid height ({self.grid_lower_right.y - self.grid_upper_left.y}px) is too small, "
                    f"minimum is {min_grid_size}px"
                )

        return self


class AnnotationCreate(AnnotationBase):
    screenshot_id: int


class AnnotationUpdate(BaseModel):
    hourly_values: dict[str, int | float] | None = None
    extracted_title: str | None = None
    extracted_total: str | None = None
    grid_upper_left: Point | None = None
    grid_lower_right: Point | None = None
    time_spent_seconds: float | None = None
    notes: str | None = None
    status: AnnotationStatus | None = None


class AnnotationRead(AnnotationBase):
    id: int
    screenshot_id: int
    user_id: int
    status: str  # Keep as str for DB compatibility
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class AnnotationUpsert(AnnotationBase):
    """Schema for create-or-update annotation endpoint."""

    screenshot_id: int


class AnnotationWithIssues(AnnotationRead):
    issues: list[ProcessingIssueRead] = []


# =============================================================================
# Queue State Schemas
# =============================================================================


class UserQueueStateBase(BaseModel):
    status: str


class UserQueueStateCreate(UserQueueStateBase):
    user_id: int
    screenshot_id: int


class UserQueueStateRead(UserQueueStateBase):
    id: int
    user_id: int
    screenshot_id: int
    last_accessed: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Consensus Schemas
# =============================================================================


class DisagreementDetail(BaseModel):
    hour: str
    values: list[float]
    median: float
    has_disagreement: bool
    max_difference: float


class ConsensusResultBase(BaseModel):
    has_consensus: bool
    disagreement_details: list[DisagreementDetail] | None = None
    consensus_values: dict[str, float] | None = None


class ConsensusResultCreate(ConsensusResultBase):
    screenshot_id: int


class ConsensusResultRead(ConsensusResultBase):
    id: int
    screenshot_id: int
    calculated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class ConsensusAnalysis(BaseModel):
    screenshot_id: int
    has_consensus: bool
    total_annotations: int
    disagreements: list[DisagreementDetail]
    consensus_hourly_values: dict[str, float] | None = None
    calculated_at: datetime.datetime


# =============================================================================
# Stats Schemas
# =============================================================================


class StatsResponse(BaseModel):
    total_screenshots: int
    pending_screenshots: int
    completed_screenshots: int
    total_annotations: int
    screenshots_with_consensus: int
    screenshots_with_disagreements: int
    average_annotations_per_screenshot: float
    users_active: int
    auto_processed: int = 0
    pending: int = 0
    failed: int = 0
    skipped: int = 0
    deleted: int = 0


# =============================================================================
# Processing Schemas
# =============================================================================


class ProcessingResultResponse(BaseModel):
    """Result of processing/reprocessing a screenshot.

    Contains all data needed by the frontend to display results:
    - Extracted data (title, total, hourly values)
    - Grid coordinates (for drawing the overlay)
    - Processing metadata (method, confidence, issues)
    """

    success: bool
    processing_status: ProcessingStatus
    # Skipped processing (e.g., verified screenshots)
    skipped: bool = False
    skip_reason: str | None = None
    message: str | None = None
    extracted_title: str | None = None
    extracted_total: str | None = None
    extracted_hourly_data: dict[str, int | float] | None = None
    issues: list[ProcessingIssue] = []
    has_blocking_issues: bool = False
    is_daily_total: bool = False
    alignment_score: float | None = None
    processing_method: ProcessingMethod | None = None
    grid_detection_confidence: float | None = None
    # Grid coordinates as flat fields (matches ScreenshotRead)
    grid_upper_left_x: int | None = None
    grid_upper_left_y: int | None = None
    grid_lower_right_x: int | None = None
    grid_lower_right_y: int | None = None


class ReprocessRequest(BaseModel):
    """Request to reprocess a screenshot with optional grid override."""

    grid_upper_left_x: int | None = None
    grid_upper_left_y: int | None = None
    grid_lower_right_x: int | None = None
    grid_lower_right_y: int | None = None
    processing_method: ProcessingMethod | None = Field(
        None,
        description="Processing method to use: 'ocr_anchored' (default) or 'line_based'",
    )
    max_shift: int = Field(
        default=5,
        ge=0,
        le=10,
        description="Max pixels to shift grid boundaries for optimization (0=disabled, higher=slower)",
    )


# =============================================================================
# Preprocessing Schemas
# =============================================================================


class PreprocessRequest(BaseModel):
    """Request to run preprocessing on a single screenshot."""

    phi_pipeline_preset: str = Field(
        default="screen_time",
        description="PHI detection pipeline preset: fast, balanced, hipaa_compliant, thorough, screen_time",
    )
    phi_redaction_method: str = Field(
        default="redbox",
        description="PHI redaction method: redbox, blackbox, pixelate",
    )
    phi_detection_enabled: bool = Field(
        default=True,
        description="Whether to run PHI detection/redaction",
    )
    phi_ocr_engine: Literal["pytesseract", "leptess"] = Field(
        default="pytesseract",
        description="OCR engine for PHI text extraction: pytesseract (default), leptess (faster C API)",
    )
    phi_ner_detector: Literal["presidio", "gliner"] = Field(
        default="presidio",
        description="NER detector: presidio (fast, 6ms), gliner (accurate, F1=0.98, 112ms)",
    )
    run_ocr_after: bool = Field(
        default=True,
        description="Whether to chain OCR processing after preprocessing",
    )


class BatchPreprocessRequest(BaseModel):
    """Request to run preprocessing on multiple screenshots in a group."""

    group_id: str = Field(..., min_length=1, max_length=100)
    screenshot_ids: list[int] | None = Field(
        default=None,
        description="Specific screenshot IDs to preprocess. If None, all screenshots in the group are processed.",
    )
    phi_pipeline_preset: str = Field(default="screen_time")
    phi_redaction_method: str = Field(default="redbox")
    phi_detection_enabled: bool = Field(default=True)
    phi_ocr_engine: Literal["pytesseract", "leptess"] = Field(default="pytesseract")
    phi_ner_detector: Literal["presidio", "gliner"] = Field(default="presidio")
    run_ocr_after: bool = Field(default=True)


class BatchPreprocessResponse(BaseModel):
    """Response from batch preprocessing request."""

    queued_count: int
    screenshot_ids: list[int]
    message: str


class PreprocessingDetailsResponse(BaseModel):
    """Typed view of preprocessing results from processing_metadata."""

    has_preprocessing: bool = False
    device_detection: dict | None = None
    cropping: dict | None = None
    phi_detection: dict | None = None
    phi_redaction: dict | None = None
    preprocessing_timestamp: str | None = None
    original_file_path: str | None = None
    preprocessed_file_path: str | None = None
    skip_reason: str | None = None


# --- Composable pipeline schemas (event log architecture) ---


class StagePreprocessRequest(BaseModel):
    """Request to run a single preprocessing stage on a batch."""

    screenshot_ids: list[int] | None = Field(
        default=None,
        description="Specific screenshot IDs. If None, all eligible in group.",
    )
    group_id: str | None = Field(
        default=None,
        description="Required if screenshot_ids is None.",
    )
    stage: str | None = Field(
        default=None,
        description="Stage name (used by reset endpoint).",
    )
    task_ids: list[str] = Field(
        default_factory=list,
        description="Celery task IDs to cancel (used by cancel endpoint).",
    )


class PHIDetectionStageRequest(StagePreprocessRequest):
    """PHI detection stage with preset."""

    phi_pipeline_preset: str = Field(default="screen_time")
    phi_ocr_engine: Literal["pytesseract", "leptess"] = Field(default="pytesseract", description="OCR engine: pytesseract, leptess")
    phi_ner_detector: Literal["presidio", "gliner"] = Field(default="presidio", description="NER detector: presidio, gliner")
    llm_endpoint: str | None = Field(default=None, description="LLM API endpoint for assisted detection")
    llm_model: str | None = Field(default=None, description="LLM model name (e.g. openai/gpt-oss-20b)")
    llm_api_key: str | None = Field(default=None, description="API key for the LLM endpoint")


class PHIRedactionStageRequest(StagePreprocessRequest):
    """PHI redaction stage with method."""

    phi_redaction_method: str = Field(default="redbox")


class OCRStageRequest(StagePreprocessRequest):
    """OCR batch processing stage with method selection."""

    ocr_method: str = Field(
        default="line_based",
        description="Grid detection method: 'line_based' (pixel analysis) or 'ocr_anchored' (text anchor detection)",
    )
    max_shift: int = Field(default=5, description="Max boundary shift for grid optimization")


class SkipStageRequest(StagePreprocessRequest):
    """Request to skip or unskip a preprocessing stage."""

    unskip: bool = Field(default=False, description="If true, revert skipped back to pending")


class StagePreprocessResponse(BaseModel):
    """Response from a stage preprocessing request."""

    queued_count: int
    screenshot_ids: list[int]
    stage: str
    message: str
    task_ids: list[str] = []


class InvalidateFromStageRequest(BaseModel):
    """Request to manually invalidate downstream stages."""

    stage: str = Field(
        ...,
        description="Stage to invalidate from (device_detection, cropping, phi_detection)",
    )


class PreprocessingEvent(BaseModel):
    """A single event in the preprocessing event log."""

    event_id: int
    stage: str
    timestamp: str
    source: str
    params: dict
    result: dict
    output_file: str | None = None
    input_file: str | None = None
    supersedes: int | None = None


class PreprocessingEventLog(BaseModel):
    """Full event log for a screenshot."""

    screenshot_id: int
    base_file_path: str
    stage_status: dict[str, str]
    current_events: dict[str, int | None]
    events: list[PreprocessingEvent]


class PreprocessingStageSummary(BaseModel):
    """Per-stage counts."""

    completed: int = 0
    pending: int = 0
    skipped: int = 0
    invalidated: int = 0
    running: int = 0
    failed: int = 0
    cancelled: int = 0
    exceptions: int = 0


class PreprocessingSummary(BaseModel):
    """Full summary across all stages."""

    total: int
    device_detection: PreprocessingStageSummary
    cropping: PreprocessingStageSummary
    phi_detection: PreprocessingStageSummary
    phi_redaction: PreprocessingStageSummary
    ocr: PreprocessingStageSummary


# =============================================================================
# Navigation Schemas
# =============================================================================


class NextScreenshotResponse(BaseModel):
    screenshot: ScreenshotRead | None
    queue_position: int
    total_remaining: int
    message: str | None = None


class NavigationResponse(BaseModel):
    """Response for screenshot navigation."""

    screenshot: ScreenshotRead | None = None
    current_index: int
    total_in_filter: int
    has_next: bool
    has_prev: bool


# =============================================================================
# Group Schemas
# =============================================================================


class GroupBase(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    image_type: ImageType = "screen_time"


class GroupCreate(GroupBase):
    pass


class GroupRead(GroupBase):
    created_at: datetime.datetime
    screenshot_count: int = 0
    processing_pending: int = 0
    processing_completed: int = 0
    processing_failed: int = 0
    processing_skipped: int = 0
    processing_deleted: int = 0
    totals_mismatch_count: int = 0
    # Processing time metrics (in seconds) - computed from screenshots
    total_processing_time_seconds: float | None = None
    avg_processing_time_seconds: float | None = None
    min_processing_time_seconds: float | None = None
    max_processing_time_seconds: float | None = None

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Upload Schemas
# =============================================================================

# 100 MB max image size -> ~140 MB as base64 (4/3 ratio)
MAX_SCREENSHOT_BASE64_LENGTH = 140 * 1024 * 1024  # ~140 MB


class ScreenshotUploadRequest(BaseModel):
    """Request schema for uploading a single screenshot.

    Supports idempotency keys for safe retries and SHA256 checksums for
    integrity verification. Callback URLs enable webhook notifications
    when processing completes.
    """

    screenshot: str = Field(
        ...,
        description="Base64 encoded image data (PNG or JPEG)",
        max_length=MAX_SCREENSHOT_BASE64_LENGTH,
    )
    participant_id: str = Field(..., min_length=1, max_length=100, pattern=r"^[\w\-. ]+$")
    group_id: str = Field(..., min_length=1, max_length=100, pattern=r"^[\w\-. ]+$")
    image_type: ImageType
    device_type: str | None = Field(None, max_length=50)
    source_id: str | None = Field(None, max_length=100)
    filename: str | None = Field(None, max_length=255)
    original_filepath: str | None = Field(
        None, max_length=1000, description="Original file path on source system for traceability"
    )
    screenshot_date: date | None = Field(None, description="Date the screenshot was taken (YYYY-MM-DD)")

    # New fields for improved reliability
    idempotency_key: str | None = Field(
        None,
        max_length=64,
        description="Unique key for idempotent uploads. If provided, duplicate requests return the original response.",
    )
    sha256: str | None = Field(
        None,
        min_length=64,
        max_length=64,
        pattern=r"^[a-fA-F0-9]{64}$",
        description="SHA256 hash of raw image bytes for integrity verification",
    )
    callback_url: str | None = Field(
        None,
        max_length=500,
        description="URL to POST processing results when complete",
    )
    preprocess: bool = Field(
        default=False,
        description="Run preprocessing pipeline (device detection, iPad cropping, PHI redaction) before OCR processing",
    )


class ScreenshotUploadResponse(BaseModel):
    """Response from screenshot upload with processing metadata.

    Includes detailed information useful for pipeline tracking and debugging.
    """

    success: bool
    screenshot_id: int
    group_created: bool = False
    message: str | None = None

    # Extended metadata for pipeline consumption
    duplicate: bool = False
    file_path: str | None = None
    file_size_bytes: int | None = None
    image_dimensions: tuple[int, int] | None = Field(None, description="(width, height) in pixels")
    device_type_detected: str | None = None
    processing_queued: bool = False
    preprocessing_queued: bool = False
    idempotency_key: str | None = None


class UploadErrorCode(StrEnum):
    """Structured error codes for upload failures."""

    INVALID_API_KEY = "invalid_api_key"
    INVALID_BASE64 = "invalid_base64"
    UNSUPPORTED_FORMAT = "unsupported_format"
    IMAGE_TOO_LARGE = "image_too_large"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    INVALID_CALLBACK_URL = "invalid_callback_url"
    BATCH_TOO_LARGE = "batch_too_large"
    RATE_LIMITED = "rate_limited"
    STORAGE_ERROR = "storage_error"
    DATABASE_ERROR = "database_error"


class UploadErrorResponse(BaseModel):
    """Structured error response for upload failures."""

    success: bool = False
    error_code: UploadErrorCode
    detail: str
    screenshot_index: int | None = Field(None, description="Index in batch where error occurred (for batch uploads)")


class BatchScreenshotItem(BaseModel):
    """Single item in a batch upload request."""

    screenshot: str = Field(
        ...,
        description="Base64 encoded image data",
        max_length=MAX_SCREENSHOT_BASE64_LENGTH,
    )
    participant_id: str = Field(..., min_length=1, max_length=100, pattern=r"^[\w\-. ]+$")
    filename: str | None = Field(None, max_length=255)
    original_filepath: str | None = Field(None, max_length=1000, description="Original file path on source system")
    screenshot_date: date | None = None
    source_id: str | None = Field(None, max_length=100)
    sha256: str | None = Field(
        None,
        min_length=64,
        max_length=64,
        pattern=r"^[a-fA-F0-9]{64}$",
    )


class BatchUploadRequest(BaseModel):
    """Request schema for batch uploading multiple screenshots.

    All screenshots in a batch share the same group_id and image_type.
    Max 60 images per batch.
    """

    group_id: str = Field(..., min_length=1, max_length=100, pattern=r"^[\w\-. ]+$")
    image_type: ImageType
    device_type: str | None = Field(None, max_length=50)
    screenshots: list[BatchScreenshotItem] = Field(
        ...,
        min_length=1,
        max_length=60,
        description="List of screenshots to upload (max 60)",
    )
    callback_url: str | None = Field(
        None,
        max_length=500,
        description="URL to POST batch results when all processing completes",
    )
    idempotency_key: str | None = Field(
        None,
        max_length=64,
        description="Unique key for idempotent batch uploads",
    )
    preprocess: bool = Field(
        default=False,
        description="Run preprocessing pipeline before OCR processing",
    )


class BatchItemResult(BaseModel):
    """Result for a single item in batch upload."""

    index: int
    success: bool
    screenshot_id: int | None = None
    duplicate: bool = False
    error_code: UploadErrorCode | None = None
    error_detail: str | None = None


class BatchUploadResponse(BaseModel):
    """Response from batch screenshot upload."""

    success: bool
    total_count: int
    successful_count: int
    failed_count: int
    duplicate_count: int
    group_created: bool = False
    results: list[BatchItemResult]
    idempotency_key: str | None = None


# =============================================================================
# Admin Schemas
# =============================================================================


class UserStatsRead(BaseModel):
    """User with annotation statistics for admin dashboard."""

    id: int
    username: str
    email: str | None = None
    role: str
    is_active: bool
    created_at: str  # ISO format
    annotations_count: int
    avg_time_spent_seconds: float


class UserUpdateResponse(BaseModel):
    """Response for user update operations."""

    id: int
    username: str
    email: str | None = None
    role: str
    is_active: bool


class ResetTestDataResponse(BaseModel):
    """Response for test data reset."""

    success: bool
    message: str


class ConsensusSummaryResponse(BaseModel):
    """Summary statistics for consensus analysis."""

    total_screenshots: int = 0
    screenshots_with_consensus: int = 0
    screenshots_with_disagreements: int = 0
    total_disagreements: int = 0
    avg_disagreements_per_screenshot: float = 0.0


# =============================================================================
# Verification Tier Schemas (Cross-Rater Consensus)
# =============================================================================


class VerificationTier(BaseModel):
    """Verification tier category."""

    tier: Literal["single_verified", "agreed", "disputed"]
    count: int
    color: str  # For UI: yellow, green, red


class GroupVerificationSummary(BaseModel):
    """Group with verification tier breakdown."""

    id: str
    name: str
    image_type: ImageType
    single_verified: int = 0  # Verified by exactly 1 user
    agreed: int = 0  # 2+ users verified, all values match exactly
    disputed: int = 0  # 2+ users verified, any difference exists
    total_verified: int = 0
    total_screenshots: int = 0


class VerifierAnnotation(BaseModel):
    """A single verifier's annotation data for comparison."""

    user_id: int
    username: str
    hourly_values: dict[str, int | float]
    extracted_title: str | None = None
    extracted_total: str | None = None
    verified_at: datetime.datetime


class FieldDifference(BaseModel):
    """Difference in a specific field between verifiers."""

    field: str  # "hourly_0", "hourly_1", ..., "title", "total"
    values: dict[str, str | int | float | None]  # user_id -> value


class ScreenshotComparison(BaseModel):
    """Comparison data for a screenshot with multiple verifiers."""

    screenshot_id: int
    file_path: str
    group_id: str | None
    participant_id: str | None
    screenshot_date: date | None
    tier: Literal["single_verified", "agreed", "disputed"]
    verifier_annotations: list[VerifierAnnotation]
    differences: list[FieldDifference]  # Empty for agreed, populated for disputed
    is_resolved: bool = False
    resolved_at: datetime.datetime | None = None
    resolved_by_user_id: int | None = None
    resolved_by_username: str | None = None
    # Resolved values (original annotations preserved separately)
    resolved_hourly_data: dict[str, int | float] | None = None
    resolved_title: str | None = None
    resolved_total: str | None = None


class ScreenshotTierItem(BaseModel):
    """Screenshot summary for tier list view."""

    id: int
    file_path: str
    participant_id: str | None
    screenshot_date: date | None
    verifier_count: int
    has_differences: bool
    extracted_title: str | None = None


class ResolveDisputeRequest(BaseModel):
    """Request to resolve a dispute with final values."""

    hourly_values: dict[str, int | float]
    extracted_title: str | None = None
    extracted_total: str | None = None
    resolution_notes: str | None = None


class ResolveDisputeResponse(BaseModel):
    """Response after resolving a dispute."""

    success: bool
    screenshot_id: int
    message: str
    resolved_at: datetime.datetime | None = None
    resolved_by_user_id: int | None = None
    resolved_by_username: str | None = None


class DeleteGroupResponse(BaseModel):
    """Response for group deletion."""

    success: bool
    group_id: str
    screenshots_deleted: int
    annotations_deleted: int
    message: str


class RecalculateOcrResponse(BaseModel):
    """Response for OCR recalculation. Response-only model, no DB column."""

    success: bool
    screenshot_id: int
    extracted_total: str | None = None
    message: str | None = None


class RecalculateOcrTotalResponse(BaseModel):
    """Response for OCR total recalculation."""

    success: bool
    extracted_total: str | None = None


# =============================================================================
# Export Schemas — SINGLE SOURCE OF TRUTH for CSV/JSON export columns
# =============================================================================


class ExportRow(BaseModel):
    """One row of export data. This schema defines the canonical export format.

    Both the server CSV export and the WASM client-side export MUST produce
    columns matching these field names exactly. The frontend imports column
    names from the generated OpenAPI types to stay in sync.
    """

    screenshot_id: int
    filename: str = ""
    original_filepath: str = ""
    group_id: str = ""
    participant_id: str = ""
    image_type: str = "screen_time"
    screenshot_date: str = ""
    uploaded_at: str = ""
    processing_status: str = ""
    is_verified: str = "No"
    verified_by_count: int = 0
    annotation_count: int = 0
    has_consensus: str = "No"
    title: str = ""
    ocr_total: str = ""
    computed_total: str = ""
    disagreement_count: int = 0
    hour_0: str = ""
    hour_1: str = ""
    hour_2: str = ""
    hour_3: str = ""
    hour_4: str = ""
    hour_5: str = ""
    hour_6: str = ""
    hour_7: str = ""
    hour_8: str = ""
    hour_9: str = ""
    hour_10: str = ""
    hour_11: str = ""
    hour_12: str = ""
    hour_13: str = ""
    hour_14: str = ""
    hour_15: str = ""
    hour_16: str = ""
    hour_17: str = ""
    hour_18: str = ""
    hour_19: str = ""
    hour_20: str = ""
    hour_21: str = ""
    hour_22: str = ""
    hour_23: str = ""


# EXPORT_CSV_HEADERS imported at top of file from generated_constants


# =============================================================================
# Health/Root Schemas
# =============================================================================


class RootResponse(BaseModel):
    """Root endpoint response."""

    message: str
    version: str
    docs: str
    redoc: str


class HealthCheckResponse(BaseModel):
    """Health check response."""

    status: str
    checks: dict[str, bool | str]  # Typed more specifically


# =============================================================================
# Browser Upload Schemas (Phase 2)
# =============================================================================


class BrowserUploadItem(BaseModel):
    """Per-file metadata for browser upload."""

    participant_id: str = Field(..., min_length=1, max_length=100)
    filename: str = Field(..., min_length=1, max_length=255)
    original_filepath: str | None = Field(None, max_length=1000)
    screenshot_date: date | None = None


class BrowserUploadRequest(BaseModel):
    """Metadata for browser-based multi-file upload."""

    group_id: str = Field(..., min_length=1, max_length=100, pattern=r"^[\w\-. ]+$")
    image_type: ImageType
    items: list[BrowserUploadItem] = Field(..., min_length=1, max_length=60)


class BrowserUploadItemResult(BaseModel):
    """Result for a single file in browser upload."""

    index: int
    success: bool
    screenshot_id: int | None = None
    error: str | None = None


class BrowserUploadResponse(BaseModel):
    """Response from browser-based upload."""

    total: int
    successful: int
    failed: int
    results: list[BrowserUploadItemResult]


# =============================================================================
# Manual Crop Schemas (Phase 3)
# =============================================================================


class ManualCropRequest(BaseModel):
    """Pixel coordinates for a manual crop rectangle."""

    left: int = Field(..., ge=0)
    top: int = Field(..., ge=0)
    right: int = Field(..., ge=0)
    bottom: int = Field(..., ge=0)

    @model_validator(mode="after")
    def validate_crop_coords(self) -> "ManualCropRequest":
        if self.right <= self.left:
            raise ValueError(f"right ({self.right}) must be greater than left ({self.left})")
        if self.bottom <= self.top:
            raise ValueError(f"bottom ({self.bottom}) must be greater than top ({self.top})")
        return self


class ManualCropResponse(BaseModel):
    """Response from manual crop operation."""

    success: bool
    event_id: int
    output_file: str
    width: int
    height: int
    message: str


# =============================================================================
# PHI Region Schemas (Phase 4)
# =============================================================================


class PHIRegionRect(BaseModel):
    """A single PHI region rectangle."""

    x: int = Field(..., ge=0)
    y: int = Field(..., ge=0)
    w: int = Field(..., ge=1)
    h: int = Field(..., ge=1)
    label: str = Field(default="OTHER", max_length=50)
    source: str = Field(default="manual", max_length=100)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    text: str = Field(default="", max_length=500)


class ManualPHIRegionsRequest(BaseModel):
    """Save manually-adjusted PHI regions."""

    regions: list[PHIRegionRect] = []
    preset: str = Field(default="manual")


class ManualPHIRegionsResponse(BaseModel):
    """Response from saving PHI regions."""

    success: bool
    event_id: int
    regions_count: int
    message: str


class ApplyPHIRedactionRequest(BaseModel):
    """Apply redaction to confirmed PHI regions."""

    regions: list[PHIRegionRect] = []
    redaction_method: str = Field(default="redbox")


class ApplyPHIRedactionResponse(BaseModel):
    """Response from applying PHI redaction."""

    success: bool
    event_id: int
    regions_redacted: int
    output_file: str
    message: str


class PHIRegionsResponse(BaseModel):
    """Current PHI regions for a screenshot."""

    regions: list[PHIRegionRect] = []
    source: str | None = None
    event_id: int | None = None
