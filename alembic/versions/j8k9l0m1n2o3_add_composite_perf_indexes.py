"""Add composite indexes for stats and dedup query performance

Revision ID: j8k9l0m1n2o3
Revises: 3613c2977638
Create Date: 2026-03-15 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "j8k9l0m1n2o3"
down_revision: Union[str, None] = "8d2e3be6f7de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_screenshots_status_annotation",
        "screenshots",
        ["processing_status", "annotation_status"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_screenshots_dedup",
        "screenshots",
        ["participant_id", "screenshot_date", "extracted_title", "extracted_total"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_screenshots_dedup", table_name="screenshots")
    op.drop_index("ix_screenshots_status_annotation", table_name="screenshots")
