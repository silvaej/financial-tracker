"""add user palette

Revision ID: fef6e4047d80
Revises: 4fa24502c6fd
Create Date: 2026-08-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'fef6e4047d80'
down_revision: Union[str, None] = '4fa24502c6fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'palette', sa.String(length=20), nullable=False, server_default='ledger'
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'palette')
