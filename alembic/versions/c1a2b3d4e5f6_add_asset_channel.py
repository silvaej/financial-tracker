"""add asset channel

Revision ID: c1a2b3d4e5f6
Revises: 8ff13437c567
Create Date: 2026-07-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1a2b3d4e5f6'
down_revision: Union[str, None] = '8ff13437c567'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('assets', sa.Column('channel_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'assets', 'channels', ['channel_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint(None, 'assets', type_='foreignkey')
    op.drop_column('assets', 'channel_id')
