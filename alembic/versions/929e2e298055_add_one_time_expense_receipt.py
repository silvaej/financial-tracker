"""add one time expense receipt

Revision ID: 929e2e298055
Revises: 611719b3f44b
Create Date: 2026-09-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '929e2e298055'
down_revision: Union[str, None] = '611719b3f44b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('one_time_expenses', sa.Column('receipt_data', sa.LargeBinary(), nullable=True))
    op.add_column(
        'one_time_expenses', sa.Column('receipt_mimetype', sa.String(length=50), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('one_time_expenses', 'receipt_mimetype')
    op.drop_column('one_time_expenses', 'receipt_data')
