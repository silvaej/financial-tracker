"""add expense active flag

Revision ID: f0f32193e46f
Revises: df0cbf88a4a2
Create Date: 2026-08-16 10:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f0f32193e46f'
down_revision: Union[str, None] = 'df0cbf88a4a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'expenses', sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true())
    )


def downgrade() -> None:
    op.drop_column('expenses', 'active')
