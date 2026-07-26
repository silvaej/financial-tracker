"""add channel logo

Revision ID: e3f4a5b6c7d8
Revises: bafc51ed3cb6
Create Date: 2026-07-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, None] = 'bafc51ed3cb6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('channels', sa.Column('logo_data', sa.LargeBinary(), nullable=True))
    op.add_column('channels', sa.Column('logo_mimetype', sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column('channels', 'logo_mimetype')
    op.drop_column('channels', 'logo_data')
