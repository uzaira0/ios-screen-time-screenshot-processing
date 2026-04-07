"""Standardize ImageType enum values

Revision ID: c211dfc3aaff
Revises: 31a3e57cdd5d
Create Date: 2025-11-22 15:57:19.231385

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c211dfc3aaff"
down_revision: Union[str, None] = "31a3e57cdd5d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Update ImageType enum values from PascalCase to lowercase_underscore.

    Changes:
    - "Battery" → "battery"
    - "Screen Time" → "screen_time"
    """
    conn = op.get_bind()

    # Update screenshots table
    conn.execute(
        sa.text("""
        UPDATE screenshots
        SET image_type = CASE image_type
            WHEN 'Battery' THEN 'battery'
            WHEN 'Screen Time' THEN 'screen_time'
            ELSE LOWER(REPLACE(image_type, ' ', '_'))
        END
        WHERE image_type IN ('Battery', 'Screen Time')
    """)
    )

    # Don't commit - Alembic handles transactions
    print("[OK] Updated ImageType enum values in screenshots table")


def downgrade() -> None:
    """Revert ImageType enum values to PascalCase.

    Changes:
    - "battery" → "Battery"
    - "screen_time" → "Screen Time"
    """
    conn = op.get_bind()

    # Revert screenshots table
    conn.execute(
        sa.text("""
        UPDATE screenshots
        SET image_type = CASE image_type
            WHEN 'battery' THEN 'Battery'
            WHEN 'screen_time' THEN 'Screen Time'
            ELSE image_type
        END
        WHERE image_type IN ('battery', 'screen_time')
    """)
    )

    # Don't commit - Alembic handles transactions
    print("[DOWN] Reverted ImageType enum values to original format")
