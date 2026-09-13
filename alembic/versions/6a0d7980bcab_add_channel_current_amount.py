"""add channel current_amount

Revision ID: 6a0d7980bcab
Revises: 9c3f0e5a1b7d
Create Date: 2026-08-22 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '6a0d7980bcab'
down_revision: Union[str, None] = '9c3f0e5a1b7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'channels',
        sa.Column(
            'current_amount', sa.Numeric(10, 2), nullable=False, server_default='0'
        ),
    )


def downgrade() -> None:
    op.drop_column('channels', 'current_amount')
