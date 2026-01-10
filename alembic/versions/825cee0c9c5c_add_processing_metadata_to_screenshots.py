"""Add processing_metadata to screenshots

Revision ID: 825cee0c9c5c
Revises: c211dfc3aaff
Create Date: 2025-11-22 16:23:30.184165

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "825cee0c9c5c"
down_revision: Union[str, None] = "c211dfc3aaff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add processing_metadata JSON column to screenshots table.

    This column stores the ProcessingMetadata for each screenshot, including:
    - Processing method used (fixed_grid, anchor_detection, manual)
    - Tags tracking processing history
    - Queue assignment
    - Accuracy metrics (OCR total vs extracted total)
    - Timestamps
    - Schema version for future migrations
    """
    # Add processing_metadata column as JSON
    op.add_column("screenshots", sa.Column("processing_metadata", sa.JSON(), nullable=True))

    print("[OK] Added processing_metadata column to screenshots table")


def downgrade() -> None:
    """Remove processing_metadata column from screenshots table."""
    op.drop_column("screenshots", "processing_metadata")
    print("[DOWN] Removed processing_metadata column from screenshots table")
