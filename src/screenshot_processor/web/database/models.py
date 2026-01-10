from __future__ import annotations

import datetime
from enum import Enum

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class AnnotationStatus(str, Enum):
    """User annotation workflow status"""

    PENDING = "pending"  # Needs annotation
    ANNOTATED = "annotated"  # Has 1+ annotations
    VERIFIED = "verified"  # Manually verified correct
    SKIPPED = "skipped"  # User intentionally skipped


class ProcessingStatus(str, Enum):
    """OCR/auto-processing status"""

    PENDING = "pending"  # Waiting for processing
    PROCESSING = "processing"  # Currently being processed
    COMPLETED = "completed"  # Successfully processed
    FAILED = "failed"  # Processing error
    SKIPPED = "skipped"  # Skipped (e.g., Daily Total detected, or user skipped)
    DELETED = "deleted"  # Soft-deleted (can be restored)


class ProcessingMethod(str, Enum):
    """Method used to detect grid coordinates in the web/API pipeline.

    NOTE: This is distinct from core.queue_models.ProcessingMethod, which
    defines methods for the CLI/GUI pipeline (FIXED_GRID, ANCHOR_DETECTION, MANUAL).
    The web pipeline uses OCR_ANCHORED and LINE_BASED, which map to the DI-based
    ScreenshotProcessingService in core/screenshot_processing.py.
    Do not attempt to unify these two enums — they serve different pipelines.
    """

    OCR_ANCHORED = "ocr_anchored"  # Uses "12 AM" and "60" text markers
    LINE_BASED = "line_based"  # Uses visual line patterns (no OCR)
    MANUAL = "manual"  # User-provided grid coordinates


# Re-export from canonical definition in core to avoid duplication
from screenshot_processor.core.ocr_factory import OCREngineType  # noqa: F401, E402


class StageStatus(str, Enum):
    """Preprocessing pipeline stage status.

    Used in JSON metadata, not a DB column -- no migration needed.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INVALIDATED = "invalidated"
    CANCELLED = "cancelled"


class UserRole(str, Enum):
    """User role for authorization"""

    ADMIN = "admin"
    ANNOTATOR = "annotator"


class SubmissionStatus(str, Enum):
    """Annotation submission status"""

    SUBMITTED = "submitted"  # Annotation has been submitted
    DRAFT = "draft"  # Work in progress (future use)


class QueueStateStatus(str, Enum):
    """User queue state status for tracking per-user screenshot progress"""

    PENDING = "pending"  # Screenshot is in user's queue
    SKIPPED = "skipped"  # User explicitly skipped this screenshot


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=UserRole.ANNOTATOR.value)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    annotations: Mapped[list["Annotation"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    queue_states: Mapped[list["UserQueueState"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    image_type: Mapped[str] = mapped_column(String(50), nullable=False, default="screen_time")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    screenshots: Mapped[list["Screenshot"]] = relationship(back_populates="group")


class Screenshot(Base):
    __tablename__ = "screenshots"
    __table_args__ = (
        Index("ix_screenshots_group_processing", "group_id", "processing_status"),
        Index("ix_screenshots_group_date", "group_id", "screenshot_date"),
        Index("ix_screenshots_group_id_asc", "group_id", "id"),
        # Composite indexes for stats/queue queries
        Index("ix_screenshots_status_annotation", "processing_status", "annotation_status"),
        Index("ix_screenshots_dedup", "participant_id", "screenshot_date", "extracted_title", "extracted_total"),
        # Unique partial index: prevent duplicate uploads by content hash
        Index("ix_screenshots_content_hash_unique", "content_hash", unique=True, postgresql_where=text("content_hash IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    file_path: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    image_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Annotation workflow status
    annotation_status: Mapped[AnnotationStatus] = mapped_column(
        SQLEnum(AnnotationStatus, native_enum=False), nullable=False, default=AnnotationStatus.PENDING, index=True
    )
    target_annotations: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_annotation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    has_consensus: Mapped[bool | None] = mapped_column(default=None, nullable=True)
    uploaded_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # API upload metadata
    participant_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    group_id: Mapped[str | None] = mapped_column(
        ForeignKey("groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    original_filepath: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    screenshot_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True, index=True)

    processed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # OCR processing status
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        SQLEnum(ProcessingStatus, native_enum=False), nullable=False, default=ProcessingStatus.PENDING, index=True
    )
    extracted_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extracted_total: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extracted_hourly_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    title_y_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grid_upper_left_x: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grid_upper_left_y: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grid_lower_right_x: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grid_lower_right_y: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processing_issues: Mapped[list | None] = mapped_column(JSON, nullable=True)
    has_blocking_issues: Mapped[bool] = mapped_column(default=False, nullable=False)
    processing_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    alignment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Grid detection method and confidence
    processing_method: Mapped[ProcessingMethod | None] = mapped_column(
        SQLEnum(ProcessingMethod, native_enum=False), nullable=True, index=True
    )
    grid_detection_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Content hash for dedup (blake2b, 32-byte digest → 64 hex chars)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # User verification tracking - stores list of user IDs who have verified this screenshot
    verified_by_user_ids: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

    # Dispute resolution fields - preserves original annotations, stores resolved values separately
    resolved_hourly_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resolved_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resolved_total: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    annotations: Mapped[list["Annotation"]] = relationship(back_populates="screenshot", cascade="all, delete-orphan")
    queue_states: Mapped[list["UserQueueState"]] = relationship(
        back_populates="screenshot", cascade="all, delete-orphan"
    )
    consensus_result: Mapped["ConsensusResult | None"] = relationship(
        back_populates="screenshot", uselist=False, cascade="all, delete-orphan"
    )
    uploaded_by: Mapped["User | None"] = relationship(foreign_keys=[uploaded_by_id])
    resolved_by: Mapped["User | None"] = relationship(foreign_keys=[resolved_by_user_id])
    group: Mapped["Group | None"] = relationship(back_populates="screenshots")


class Annotation(Base):
    __tablename__ = "annotations"

    # Ensure one annotation per user per screenshot at the database level
    __table_args__ = (
        UniqueConstraint("screenshot_id", "user_id", name="uq_annotation_screenshot_user"),
        Index("ix_annotations_user_created", "user_id", "created_at"),  # For history queries
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    screenshot_id: Mapped[int] = mapped_column(
        ForeignKey("screenshots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    hourly_values: Mapped[dict] = mapped_column(JSON, nullable=False)
    extracted_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extracted_total: Mapped[str | None] = mapped_column(String(100), nullable=True)
    grid_upper_left: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    grid_lower_right: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    time_spent_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=SubmissionStatus.SUBMITTED.value, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    screenshot: Mapped["Screenshot"] = relationship(back_populates="annotations")
    user: Mapped["User"] = relationship(back_populates="annotations")
    issues: Mapped[list["ProcessingIssue"]] = relationship(back_populates="annotation", cascade="all, delete-orphan")


class ProcessingIssue(Base):
    __tablename__ = "processing_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    annotation_id: Mapped[int] = mapped_column(
        ForeignKey("annotations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    issue_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    annotation: Mapped["Annotation"] = relationship(back_populates="issues")


class AnnotationAuditLog(Base):
    """Tracks changes to annotations for audit purposes."""

    __tablename__ = "annotation_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    annotation_id: Mapped[int] = mapped_column(
        ForeignKey("annotations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    screenshot_id: Mapped[int] = mapped_column(
        ForeignKey("screenshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # created, updated, deleted
    previous_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # JSON snapshot of old values
    new_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # JSON snapshot of new values
    changes_summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # Human-readable summary
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    annotation: Mapped["Annotation"] = relationship(foreign_keys=[annotation_id])
    user: Mapped["User | None"] = relationship(foreign_keys=[user_id])


class UserQueueState(Base):
    __tablename__ = "user_queue_states"
    __table_args__ = (UniqueConstraint("user_id", "screenshot_id", name="uq_user_queue_state_user_screenshot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    screenshot_id: Mapped[int] = mapped_column(
        ForeignKey("screenshots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=QueueStateStatus.PENDING.value, index=True)
    last_accessed: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="queue_states")
    screenshot: Mapped["Screenshot"] = relationship(back_populates="queue_states")


class ConsensusResult(Base):
    __tablename__ = "consensus_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    screenshot_id: Mapped[int] = mapped_column(
        ForeignKey("screenshots.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    has_consensus: Mapped[bool] = mapped_column(nullable=False, index=True)
    disagreement_details: Mapped[dict] = mapped_column(JSON, nullable=False)
    consensus_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    calculated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    screenshot: Mapped["Screenshot"] = relationship(back_populates="consensus_result")


class Session(Base):
    """Session storage for cookie-based site-wide authentication.

    Used by SessionAuthMiddleware to store session tokens.
    """

    __tablename__ = "sessions"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_activity: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
