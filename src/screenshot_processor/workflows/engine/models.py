"""SQLAlchemy models for workflow engine persistence.

These tables replace the processing_metadata JSON blob with durable state
that survives worker restarts and supports the Temporal migration.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from screenshot_processor.web.database.models import Base


class WorkflowExecution(Base):
    __tablename__ = "workflow_execution"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    screenshot_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    workflow_type: Mapped[str] = mapped_column(String(64), nullable=False, default="preprocessing")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    current_activity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    activities: Mapped[list[ActivityExecution]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan", order_by="ActivityExecution.id"
    )
    signals: Mapped[list[WorkflowSignal]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(
            "uq_workflow_screenshot_type",
            "screenshot_id",
            "workflow_type",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
    )


class ActivityExecution(Base):
    __tablename__ = "activity_execution"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow_execution.id", ondelete="CASCADE"), nullable=False
    )
    activity_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)
    is_blocking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_class: Mapped[str | None] = mapped_column(String(20), nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workflow: Mapped[WorkflowExecution] = relationship(back_populates="activities")

    __table_args__ = (
        Index("ix_activity_workflow", "workflow_id"),
    )


class WorkflowSignal(Base):
    __tablename__ = "workflow_signal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow_execution.id", ondelete="CASCADE"), nullable=False
    )
    signal_name: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    consumed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    workflow: Mapped[WorkflowExecution] = relationship(back_populates="signals")

    __table_args__ = (
        Index("ix_signal_pending", "workflow_id", "consumed"),
    )


class WorkflowAuditEntry(Base):
    """Append-only audit log for workflow/activity state changes."""

    __tablename__ = "workflow_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow_execution.id", ondelete="CASCADE"), nullable=False
    )
    activity_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("ix_workflow_audit_workflow", "workflow_id"),
    )
