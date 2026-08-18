"""add payout cycles (dated cycle history)

Revision ID: 21ce9028b3e1
Revises: f0f32193e46f
Create Date: 2026-08-16 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '21ce9028b3e1'
down_revision: Union[str, None] = 'f0f32193e46f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'payout_cycles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('payout_period_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=50), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('income_amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('receiving_channel_name', sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(['payout_period_id'], ['payout_periods.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'payout_cycle_balances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payout_cycle_id', sa.Integer(), nullable=False),
        sa.Column('channel_name', sa.String(length=100), nullable=False),
        sa.Column('channel_color', sa.String(length=7), nullable=False),
        sa.Column('income', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('transfers_net', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('expenses_total', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('net', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.ForeignKeyConstraint(['payout_cycle_id'], ['payout_cycles.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('payout_cycle_balances')
    op.drop_table('payout_cycles')
