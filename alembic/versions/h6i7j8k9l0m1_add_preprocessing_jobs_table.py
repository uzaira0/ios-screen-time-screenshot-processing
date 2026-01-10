"""Add preprocessing_jobs table for ZIP upload with PHI detection

Revision ID: h6i7j8k9l0m1
Revises: g5h6i7j8k9l0
Create Date: 2025-12-30 12:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "h6i7j8k9l0m1"
down_revision: str | None = "g5h6i7j8k9l0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "preprocessing_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", sa.String(50), nullable=False, default="pending", index=True),
        # Progress tracking
        sa.Column("total_images", sa.Integer, nullable=False, default=0),
        sa.Column("processed_images", sa.Integer, nullable=False, default=0),
        sa.Column("uploaded_images", sa.Integer, nullable=False, default=0),
        sa.Column("failed_images", sa.Integer, nullable=False, default=0),
        # Configuration
        sa.Column("group_id", sa.String(100), nullable=False),
        sa.Column("redaction_method", sa.String(50), nullable=False, default="redbox"),
        sa.Column("detection_preset", sa.String(50), nullable=False, default="hipaa_compliant"),
        # File paths
        sa.Column("zip_file_path", sa.String(500), nullable=True),
        sa.Column("extracted_path", sa.String(500), nullable=True),
        # Results
        sa.Column("errors", sa.JSON, nullable=True),
        sa.Column("uploaded_screenshot_ids", sa.JSON, nullable=True),
        sa.Column("phi_stats", sa.JSON, nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Add composite index for user + status queries
    op.create_index(
        "ix_preprocessing_jobs_user_status",
        "preprocessing_jobs",
        ["user_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_preprocessing_jobs_user_status", table_name="preprocessing_jobs")
    op.drop_table("preprocessing_jobs")
