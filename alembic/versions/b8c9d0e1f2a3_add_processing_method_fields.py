"""Add processing_method and grid_detection_confidence fields

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2025-12-10

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add processing_method and grid_detection_confidence columns.

    processing_method tracks which grid detection method was used:
    - 'ocr_anchored': Uses "12 AM" and "60" text markers (original method)
    - 'line_based': Uses visual line patterns without OCR
    - 'manual': User-provided grid coordinates

    grid_detection_confidence stores the confidence score from line-based detection.
    """
    op.add_column(
        "screenshots",
        sa.Column("processing_method", sa.String(20), nullable=True),
    )
    op.add_column(
        "screenshots",
        sa.Column("grid_detection_confidence", sa.Float(), nullable=True),
    )
    op.create_index(
        "ix_screenshots_processing_method",
        "screenshots",
        ["processing_method"],
        unique=False,
    )
    print("[OK] Added processing_method and grid_detection_confidence columns")


def downgrade() -> None:
    """Remove processing_method and grid_detection_confidence columns."""
    op.drop_index("ix_screenshots_processing_method", table_name="screenshots")
    op.drop_column("screenshots", "grid_detection_confidence")
    op.drop_column("screenshots", "processing_method")
    print("[DOWN] Removed processing_method and grid_detection_confidence columns")
