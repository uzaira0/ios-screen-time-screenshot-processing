"""Add annotation audit log table

Revision ID: e3f4g5h6i7j8
Revises: d2e3f4g5h6i7
Create Date: 2024-12-18

This migration adds the annotation_audit_logs table to track changes
to annotations for audit purposes.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e3f4g5h6i7j8"
down_revision: Union[str, None] = "d2e3f4g5h6i7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create annotation_audit_logs table."""
    op.create_table(
        "annotation_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "annotation_id",
            sa.Integer(),
            sa.ForeignKey("annotations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "screenshot_id",
            sa.Integer(),
            sa.ForeignKey("screenshots.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("action", sa.String(50), nullable=False, index=True),
        sa.Column("previous_values", sa.JSON(), nullable=True),
        sa.Column("new_values", sa.JSON(), nullable=True),
        sa.Column("changes_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Drop annotation_audit_logs table."""
    op.drop_table("annotation_audit_logs")
