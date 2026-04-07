"""Add annotation unique constraint

Revision ID: c1d2e3f4g5h6
Revises: b8c9d0e1f2a3
Create Date: 2024-12-14

This migration adds a unique constraint on (screenshot_id, user_id) to the annotations
table to ensure data integrity at the database level. Previously, this uniqueness
was only enforced at the application level via upsert logic.
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4g5h6"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add unique constraint to prevent duplicate annotations per user per screenshot."""
    op.create_unique_constraint(
        "uq_annotation_screenshot_user",
        "annotations",
        ["screenshot_id", "user_id"],
    )


def downgrade() -> None:
    """Remove the unique constraint."""
    op.drop_constraint("uq_annotation_screenshot_user", "annotations", type_="unique")
