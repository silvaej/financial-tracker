"""add closed cycle idempotency key

Revision ID: 9dd2626d3d6d
Revises: 611719b3f44b
Create Date: 2026-09-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '9dd2626d3d6d'
down_revision: Union[str, None] = '611719b3f44b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'closed_cycles', sa.Column('idempotency_key', sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('closed_cycles', 'idempotency_key')
