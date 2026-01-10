"""Queue and tagging system models for screenshot processing.

This module defines the data models for the multi-stage processing pipeline,
including tags, queues, and processing metadata that track the complete
processing history of each screenshot.

These models are designed to work across:
- PyQt6 GUI (Python)
- CLI tool (Python)
- Web application (TypeScript/React)
- WASM application (TypeScript/Pyodide)
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic.dataclasses import dataclass as pydantic_dataclass


class ProcessingMethod(StrEnum):
    """Processing method used for grid detection in the CLI/GUI pipeline.

    NOTE: This is distinct from web.database.models.ProcessingMethod, which
    defines methods for the web/API pipeline (OCR_ANCHORED, LINE_BASED, MANUAL).
    The CLI pipeline uses FIXED_GRID (hardcoded coordinates) and ANCHOR_DETECTION
    (OCR-based "12AM"/"60" search), which are legacy concepts not used by the web app.
    Do not attempt to unify these two enums — they serve different pipelines.
    """

    FIXED_GRID = "fixed_grid"
    ANCHOR_DETECTION = "anchor_detection"
    MANUAL = "manual"


class ProcessingTag(StrEnum):
    """All possible processing tags.

    Uses StrEnum for JSON serialization compatibility across platforms.
    Tags are additive - a screenshot can have multiple tags throughout its lifecycle.
    """

    # Detection tags
    DAILY_SCREENSHOT = "daily_screenshot"
    TOTAL_DETECTED = "total_detected"
    TOTAL_NOT_FOUND = "total_not_found"

    # Method tags
    FIXED_GRID_SUCCESS = "fixed_grid_success"
    ANCHOR_METHOD_SUCCESS = "anchor_method_success"
    ANCHOR_METHOD_CLOSE = "anchor_method_close"
    ANCHOR_METHOD_FAILED = "anchor_method_failed"
    EXTRACTION_FAILED = "extraction_failed"

    # Accuracy tags
    EXACT_MATCH = "exact_match"
    CLOSE_MATCH = "close_match"
    POOR_MATCH = "poor_match"
    BARS_NOT_DETECTED = "bars_not_detected"

    # State tags
    AUTO_PROCESSED = "auto_processed"
    NEEDS_VALIDATION = "needs_validation"
    NEEDS_MANUAL = "needs_manual"
    USER_VALIDATED = "user_validated"
    USER_CORRECTED = "user_corrected"

    # Title tags
    TITLE_NOT_FOUND = "title_not_found"

    # User action tags
    MANUAL_GRID_ADJUSTMENT = "manual_grid_adjustment"
    MANUAL_TITLE_ENTRY = "manual_title_entry"
    APPROVED_AS_IS = "approved_as_is"
    REJECTED_SCREENSHOT = "rejected_screenshot"

    # Y-shift tags (for fixed grid method)
    Y_SHIFT_MINUS_2 = "y_shift_minus_2"
    Y_SHIFT_MINUS_1 = "y_shift_minus_1"
    Y_SHIFT_ZERO = "y_shift_zero"
    Y_SHIFT_PLUS_1 = "y_shift_plus_1"
    Y_SHIFT_PLUS_2 = "y_shift_plus_2"


class ScreenshotQueue(StrEnum):
    """All possible queues for organizing screenshots.

    Queues are mutually exclusive - a screenshot belongs to exactly one queue at a time.
    Queue is automatically determined from the screenshot's tags.
    """

    UNPROCESSED = "unprocessed"
    DAILY = "daily_screenshots"
    AUTO_FIXED = "auto_processed_fixed_grid"
    AUTO_ANCHOR = "auto_processed_anchor_method"
    NEEDS_REVIEW_CLOSE = "needs_review_close_match"
    NEEDS_REVIEW_POOR = "needs_review_poor_match"
    FAILED_EXTRACTION = "failed_extraction_error"
    FAILED_NO_TOTAL = "failed_no_total_detected"
    VALIDATED = "validated"
    REJECTED = "rejected"


@pydantic_dataclass(frozen=True, config={"arbitrary_types_allowed": True})
class ProcessingMetadata:
    """Immutable metadata for screenshot processing results.

    Design principles:
    - Frozen for thread safety and hashability
    - Uses frozenset for tags (immutable, hashable)
    - Validates tag combinations on creation
    - Auto-determines queue from tags (single source of truth)
    - JSON-serializable for cross-platform use

    Example:
        >>> metadata = ProcessingMetadata(
        ...     method=ProcessingMethod.FIXED_GRID,
        ...     tags={ProcessingTag.FIXED_GRID_SUCCESS, ProcessingTag.EXACT_MATCH},
        ...     y_shift=0,
        ...     ocr_total_minutes=45.0,
        ...     extracted_total_minutes=45.0,
        ... )
        >>> metadata.queue
        <ScreenshotQueue.AUTO_FIXED: 'auto_processed_fixed_grid'>
    """

    # Core fields
    method: ProcessingMethod | None = None
    tags: frozenset[str] = Field(default_factory=frozenset)
    queue: ScreenshotQueue = ScreenshotQueue.UNPROCESSED

    # Processing details
    y_shift: int | None = Field(default=None, ge=-2, le=2)
    ocr_total_minutes: float | None = Field(default=None, ge=0)
    extracted_total_minutes: float | None = Field(default=None, ge=0)
    accuracy_diff_minutes: float | None = None
    accuracy_diff_percent: float | None = None

    # Timestamps (ISO 8601 format strings for cross-platform compatibility)
    processed_at: str | None = None
    validated_at: str | None = None

    # Schema version for future migrations
    schema_version: int = 1

    @field_validator("tags", mode="before")
    @classmethod
    def convert_tags_to_frozenset(cls, v: Any) -> frozenset[str]:
        """Convert any iterable to frozenset of strings."""
        if isinstance(v, frozenset):
            return v
        if isinstance(v, (set, list, tuple)):
            # Convert ProcessingTag enums to strings
            return frozenset(tag.value if isinstance(tag, ProcessingTag) else str(tag) for tag in v)
        return frozenset()

    @model_validator(mode="after")
    def validate_tag_combinations(self) -> ProcessingMetadata:
        """Validate mutually exclusive tag groups."""
        tags_str = {str(tag) for tag in self.tags}

        # Define mutually exclusive groups
        mutually_exclusive = [
            {ProcessingTag.EXACT_MATCH.value, ProcessingTag.CLOSE_MATCH.value, ProcessingTag.POOR_MATCH.value},
            {
                ProcessingTag.FIXED_GRID_SUCCESS.value,
                ProcessingTag.ANCHOR_METHOD_SUCCESS.value,
                ProcessingTag.ANCHOR_METHOD_CLOSE.value,
                ProcessingTag.ANCHOR_METHOD_FAILED.value,
            },
            {ProcessingTag.TOTAL_DETECTED.value, ProcessingTag.TOTAL_NOT_FOUND.value},
            {
                ProcessingTag.AUTO_PROCESSED.value,
                ProcessingTag.NEEDS_VALIDATION.value,
                ProcessingTag.NEEDS_MANUAL.value,
            },
        ]

        for group in mutually_exclusive:
            present = tags_str & group
            if len(present) > 1:
                raise ValueError(f"Tags {present} are mutually exclusive")

        return self

    @model_validator(mode="after")
    def auto_determine_queue(self) -> ProcessingMetadata:
        """Automatically assign queue based on tags.

        Queue is derived from tags (single source of truth).
        Priority order (first match wins):
        1. Daily screenshots
        2. Rejected screenshots
        3. User validated
        4. Auto-processed (fixed grid or anchor method)
        5. Needs review (close or poor match)
        6. Failed (no total or extraction error)
        7. Unprocessed (default)
        """
        tags_str = {str(tag) for tag in self.tags}

        # Use object.__setattr__ to modify frozen dataclass
        if ProcessingTag.DAILY_SCREENSHOT.value in tags_str:
            object.__setattr__(self, "queue", ScreenshotQueue.DAILY)
        elif ProcessingTag.REJECTED_SCREENSHOT.value in tags_str:
            object.__setattr__(self, "queue", ScreenshotQueue.REJECTED)
        elif ProcessingTag.USER_VALIDATED.value in tags_str:
            object.__setattr__(self, "queue", ScreenshotQueue.VALIDATED)
        elif ProcessingTag.FIXED_GRID_SUCCESS.value in tags_str and ProcessingTag.EXACT_MATCH.value in tags_str:
            object.__setattr__(self, "queue", ScreenshotQueue.AUTO_FIXED)
        elif ProcessingTag.ANCHOR_METHOD_SUCCESS.value in tags_str and ProcessingTag.EXACT_MATCH.value in tags_str:
            object.__setattr__(self, "queue", ScreenshotQueue.AUTO_ANCHOR)
        elif ProcessingTag.CLOSE_MATCH.value in tags_str:
            object.__setattr__(self, "queue", ScreenshotQueue.NEEDS_REVIEW_CLOSE)
        elif ProcessingTag.POOR_MATCH.value in tags_str:
            object.__setattr__(self, "queue", ScreenshotQueue.NEEDS_REVIEW_POOR)
        elif ProcessingTag.TOTAL_NOT_FOUND.value in tags_str:
            object.__setattr__(self, "queue", ScreenshotQueue.FAILED_NO_TOTAL)
        elif ProcessingTag.BARS_NOT_DETECTED.value in tags_str or ProcessingTag.EXTRACTION_FAILED.value in tags_str:
            object.__setattr__(self, "queue", ScreenshotQueue.FAILED_EXTRACTION)

        return self

    def with_additional_tags(self, *new_tags: ProcessingTag) -> ProcessingMetadata:
        """Create new metadata with additional tags (immutable pattern).

        Args:
            *new_tags: Tags to add to the existing tag set

        Returns:
            New ProcessingMetadata instance with combined tags and updated queue

        Example:
            >>> original = ProcessingMetadata(tags={ProcessingTag.TOTAL_DETECTED})
            >>> validated = original.with_additional_tags(ProcessingTag.USER_VALIDATED)
            >>> ProcessingTag.USER_VALIDATED.value in validated.tags
            True
            >>> validated.queue
            <ScreenshotQueue.VALIDATED: 'validated'>
        """
        combined_tags = self.tags | frozenset(tag.value for tag in new_tags)

        # Create new instance - validators will run automatically
        return ProcessingMetadata(
            method=self.method,
            tags=combined_tags,
            queue=self.queue,  # Will be auto-updated by validator
            y_shift=self.y_shift,
            ocr_total_minutes=self.ocr_total_minutes,
            extracted_total_minutes=self.extracted_total_minutes,
            accuracy_diff_minutes=self.accuracy_diff_minutes,
            accuracy_diff_percent=self.accuracy_diff_percent,
            processed_at=self.processed_at,
            validated_at=self.validated_at,
            schema_version=self.schema_version,
        )

    def with_validation(self, validated_at: str | None = None) -> ProcessingMetadata:
        """Create new metadata with validation timestamp.

        Args:
            validated_at: ISO 8601 timestamp string. If None, uses current time.

        Returns:
            New ProcessingMetadata instance with USER_VALIDATED tag and timestamp
        """
        if validated_at is None:
            validated_at = datetime.utcnow().isoformat()

        return self.with_additional_tags(ProcessingTag.USER_VALIDATED).with_timestamp(validated_at=validated_at)

    def with_timestamp(self, **kwargs: str | None) -> ProcessingMetadata:
        """Create new metadata with updated timestamp fields.

        Args:
            **kwargs: Timestamp fields to update (processed_at, validated_at)

        Returns:
            New ProcessingMetadata instance with updated timestamps
        """
        return ProcessingMetadata(
            method=self.method,
            tags=self.tags,
            queue=self.queue,
            y_shift=self.y_shift,
            ocr_total_minutes=self.ocr_total_minutes,
            extracted_total_minutes=self.extracted_total_minutes,
            accuracy_diff_minutes=self.accuracy_diff_minutes,
            accuracy_diff_percent=self.accuracy_diff_percent,
            processed_at=kwargs.get("processed_at", self.processed_at),
            validated_at=kwargs.get("validated_at", self.validated_at),
            schema_version=self.schema_version,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation with tags as list of strings
        """
        return {
            "method": self.method.value if self.method else None,
            "tags": sorted(self.tags),  # Sort for consistent serialization
            "queue": self.queue.value,
            "y_shift": self.y_shift,
            "ocr_total_minutes": self.ocr_total_minutes,
            "extracted_total_minutes": self.extracted_total_minutes,
            "accuracy_diff_minutes": self.accuracy_diff_minutes,
            "accuracy_diff_percent": self.accuracy_diff_percent,
            "processed_at": self.processed_at,
            "validated_at": self.validated_at,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProcessingMetadata:
        """Create ProcessingMetadata from dictionary.

        Args:
            data: Dictionary with metadata fields

        Returns:
            ProcessingMetadata instance
        """
        # Convert method string to enum
        method = ProcessingMethod(data["method"]) if data.get("method") else None

        return cls(
            method=method,
            tags=data.get("tags", []),
            queue=ScreenshotQueue(data["queue"]) if "queue" in data else ScreenshotQueue.UNPROCESSED,
            y_shift=data.get("y_shift"),
            ocr_total_minutes=data.get("ocr_total_minutes"),
            extracted_total_minutes=data.get("extracted_total_minutes"),
            accuracy_diff_minutes=data.get("accuracy_diff_minutes"),
            accuracy_diff_percent=data.get("accuracy_diff_percent"),
            processed_at=data.get("processed_at"),
            validated_at=data.get("validated_at"),
            schema_version=data.get("schema_version", 1),
        )
