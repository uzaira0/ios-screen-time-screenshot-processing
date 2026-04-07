"""Add user_queue_state unique constraint

Revision ID: d2e3f4g5h6i7
Revises: c1d2e3f4g5h6
Create Date: 2024-12-18

This migration adds a unique constraint on (user_id, screenshot_id) to the user_queue_states
table to prevent duplicate queue state entries for the same user and screenshot combination.
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d2e3f4g5h6i7"
down_revision: Union[str, None] = "c1d2e3f4g5h6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add unique constraint to prevent duplicate queue states per user per screenshot."""
    # First, clean up any existing duplicates by keeping only the most recent entry
    op.execute("""
        DELETE FROM user_queue_states
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM user_queue_states
            GROUP BY user_id, screenshot_id
        )
    """)

    # Use batch mode for SQLite compatibility
    with op.batch_alter_table("user_queue_states") as batch_op:
        batch_op.create_unique_constraint(
            "uq_user_queue_state_user_screenshot",
            ["user_id", "screenshot_id"],
        )


def downgrade() -> None:
    """Remove the unique constraint."""
    with op.batch_alter_table("user_queue_states") as batch_op:
        batch_op.drop_constraint("uq_user_queue_state_user_screenshot", type_="unique")
