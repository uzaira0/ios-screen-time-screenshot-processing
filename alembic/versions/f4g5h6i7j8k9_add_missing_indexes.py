"""Add missing database indexes for query optimization

Revision ID: f4g5h6i7j8k9
Revises: e3f4g5h6i7j8
Create Date: 2024-12-19

This migration adds indexes for frequently queried columns:
- ConsensusResult.has_consensus (used in stats queries)
- User.is_active (used in stats queries)
- Annotation.created_at (used for ordering in history queries)
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f4g5h6i7j8k9"
down_revision: Union[str, None] = "e3f4g5h6i7j8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add indexes for frequently queried columns."""
    # Index for consensus stats queries
    op.create_index(
        "ix_consensus_results_has_consensus",
        "consensus_results",
        ["has_consensus"],
    )

    # Index for active user queries
    op.create_index(
        "ix_users_is_active",
        "users",
        ["is_active"],
    )

    # Index for annotation history ordering
    op.create_index(
        "ix_annotations_created_at",
        "annotations",
        ["created_at"],
    )

    # Composite index for annotation history by user (covers WHERE and ORDER BY)
    op.create_index(
        "ix_annotations_user_created",
        "annotations",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    """Remove the indexes."""
    op.drop_index("ix_annotations_user_created", table_name="annotations")
    op.drop_index("ix_annotations_created_at", table_name="annotations")
    op.drop_index("ix_users_is_active", table_name="users")
    op.drop_index("ix_consensus_results_has_consensus", table_name="consensus_results")
