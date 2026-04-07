"""Base model classes and mixins for SQLAlchemy."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models.

    Provides:
    - Automatic table naming from class name
    - Automatic __repr__ with primary key

    Example:
        class User(Base):
            __tablename__ = "users"

            id: Mapped[int] = mapped_column(primary_key=True)
            name: Mapped[str]
    """

    def __repr__(self) -> str:
        """Generate repr with class name and primary key."""
        pk_cols = [col.name for col in self.__table__.primary_key.columns]
        pk_vals = [getattr(self, col, None) for col in pk_cols]
        pk_str = ", ".join(f"{col}={val!r}" for col, val in zip(pk_cols, pk_vals))
        return f"<{self.__class__.__name__}({pk_str})>"


class TimestampMixin:
    """Mixin that adds created_at and updated_at columns.

    Example:
        class User(TimestampMixin, Base):
            __tablename__ = "users"
            id: Mapped[int] = mapped_column(primary_key=True)
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )


class SoftDeleteMixin:
    """Mixin that adds soft delete support.

    Instead of actually deleting rows, sets deleted_at timestamp.

    Example:
        class User(SoftDeleteMixin, Base):
            __tablename__ = "users"
            id: Mapped[int] = mapped_column(primary_key=True)

        # To soft delete:
        user.deleted_at = datetime.now(timezone.utc)

        # Query active only:
        select(User).where(User.deleted_at.is_(None))
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    @property
    def is_deleted(self) -> bool:
        """Check if this record has been soft deleted."""
        return self.deleted_at is not None
