"""add_content_hash_to_screenshots

Revision ID: 8d2e3be6f7de
Revises: 3613c2977638
Create Date: 2026-03-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8d2e3be6f7de'
down_revision: Union[str, None] = '3613c2977638'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('screenshots', sa.Column('content_hash', sa.String(length=128), nullable=True))
    op.create_index(op.f('ix_screenshots_content_hash'), 'screenshots', ['content_hash'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_screenshots_content_hash'), table_name='screenshots')
    op.drop_column('screenshots', 'content_hash')
