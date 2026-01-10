"""Add processing_started_at to screenshots for timing metrics

Revision ID: i7j8k9l0m1n2
Revises: h6i7j8k9l0m1
Create Date: 2026-01-10 23:30:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "i7j8k9l0m1n2"
down_revision: str | None = "1dc90afb6cac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add processing_started_at column to track when processing actually begins
    # This enables computing actual processing time (processed_at - processing_started_at)
    # separate from queue wait time (processing_started_at - uploaded_at)
    op.add_column(
        "screenshots",
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("screenshots", "processing_started_at")
