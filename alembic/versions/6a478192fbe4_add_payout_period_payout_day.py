"""add payout period payout_day

Revision ID: 6a478192fbe4
Revises: 7a46ca981ef4
Create Date: 2026-08-16 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '6a478192fbe4'
down_revision: Union[str, None] = '7a46ca981ef4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Optional -- existing periods get NULL (no overdue hint until the user
    # sets one). See models.py's PayoutPeriod.payout_day docstring.
    op.add_column('payout_periods', sa.Column('payout_day', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('payout_periods', 'payout_day')
