"""add user profile fields

Revision ID: b7c8d9e0f1a2
Revises: f1a2b3c4d5e6
Create Date: 2026-08-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('display_name', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('avatar_data', sa.LargeBinary(), nullable=True))
    op.add_column('users', sa.Column('avatar_mimetype', sa.String(length=50), nullable=True))
    op.add_column(
        'users',
        sa.Column('currency_code', sa.String(length=3), nullable=False, server_default='PHP'),
    )
    op.add_column('users', sa.Column('timezone', sa.String(length=50), nullable=True))
    op.add_column(
        'users',
        sa.Column('notify_cash_flow_warnings', sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column('users', 'notify_cash_flow_warnings')
    op.drop_column('users', 'timezone')
    op.drop_column('users', 'currency_code')
    op.drop_column('users', 'avatar_mimetype')
    op.drop_column('users', 'avatar_data')
    op.drop_column('users', 'display_name')
