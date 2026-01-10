"""add_original_filepath_to_screenshots

Revision ID: 1dc90afb6cac
Revises: h6i7j8k9l0m1
Create Date: 2025-12-31 10:47:37.086258

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1dc90afb6cac'
down_revision: Union[str, None] = 'h6i7j8k9l0m1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('screenshots', sa.Column('original_filepath', sa.String(1000), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('screenshots', 'original_filepath')
