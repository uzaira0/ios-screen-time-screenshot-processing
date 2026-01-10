"""Add dispute resolution fields to screenshots

Revision ID: g5h6i7j8k9l0
Revises: f4g5h6i7j8k9
Create Date: 2025-12-27 10:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "g5h6i7j8k9l0"
down_revision: str | None = "f4g5h6i7j8k9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add dispute resolution fields to screenshots table
    # These store resolved values separately from original annotations
    op.add_column("screenshots", sa.Column("resolved_hourly_data", sa.JSON(), nullable=True))
    op.add_column("screenshots", sa.Column("resolved_title", sa.String(500), nullable=True))
    op.add_column("screenshots", sa.Column("resolved_total", sa.String(100), nullable=True))
    op.add_column("screenshots", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "screenshots",
        sa.Column("resolved_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("screenshots", "resolved_by_user_id")
    op.drop_column("screenshots", "resolved_at")
    op.drop_column("screenshots", "resolved_total")
    op.drop_column("screenshots", "resolved_title")
    op.drop_column("screenshots", "resolved_hourly_data")
