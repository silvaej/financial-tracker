"""add expense paid flag

Revision ID: df0cbf88a4a2
Revises: 76352e3a5eef
Create Date: 2026-08-16 10:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'df0cbf88a4a2'
down_revision: Union[str, None] = '76352e3a5eef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'expenses', sa.Column('paid', sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column('expenses', 'paid')
