"""Add unique partial index on content_hash to prevent duplicate uploads

Revision ID: k9l0m1n2o3p4
Revises: j8k9l0m1n2o3
Create Date: 2026-03-24 01:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "k9l0m1n2o3p4"
down_revision = "j8k9l0m1n2o3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Unique partial index: prevents duplicate uploads by content hash.
    # Partial (WHERE content_hash IS NOT NULL) because not all screenshots have hashes.
    # Also drops the redundant non-unique index on content_hash.
    op.drop_index("ix_screenshots_content_hash", table_name="screenshots", if_exists=True)
    op.create_index(
        "ix_screenshots_content_hash_unique",
        "screenshots",
        ["content_hash"],
        unique=True,
        postgresql_where="content_hash IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("ix_screenshots_content_hash_unique", table_name="screenshots", if_exists=True)
    op.create_index("ix_screenshots_content_hash", "screenshots", ["content_hash"])
