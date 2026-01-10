"""Rename required_annotations to target_annotations

Revision ID: a7b8c9d0e1f2
Revises: 825cee0c9c5c
Create Date: 2025-11-28

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "825cee0c9c5c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename required_annotations to target_annotations.

    The old name was misleading - it's a configurable goal for annotation count,
    not a hard requirement that gates completion.
    """
    op.alter_column(
        "screenshots",
        "required_annotations",
        new_column_name="target_annotations",
    )
    print("[OK] Renamed required_annotations to target_annotations")


def downgrade() -> None:
    """Rename target_annotations back to required_annotations."""
    op.alter_column(
        "screenshots",
        "target_annotations",
        new_column_name="required_annotations",
    )
    print("[DOWN] Renamed target_annotations back to required_annotations")
