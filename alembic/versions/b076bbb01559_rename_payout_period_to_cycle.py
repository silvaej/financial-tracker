"""rename payout period to cycle

Revision ID: b076bbb01559
Revises: a583d4a319d2
Create Date: 2026-09-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b076bbb01559'
down_revision: Union[str, None] = 'a583d4a319d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Every table with a payout_period_id FK column, renamed to cycle_id below.
_FK_TABLES = (
    'expenses',
    'transfers',
    'goal_contributions',
    'channel_placements',
    'goal_placements',
)


def upgrade() -> None:
    # Pure renames -- autogenerate does not detect a rename (it would emit a
    # destructive drop+create pair instead), so every op here is hand-written.
    # Constraint/index *names* are deliberately left as-is (e.g. still
    # "payout_periods_pkey", "channel_placements_payout_period_id_channel_id_key")
    # -- cosmetic only, not worth the extra risk of also renaming them.
    op.rename_table('payout_periods', 'cycles')
    for table in _FK_TABLES:
        op.alter_column(table, 'payout_period_id', new_column_name='cycle_id')

    op.rename_table('payout_cycles', 'closed_cycles')
    op.alter_column('closed_cycles', 'payout_period_id', new_column_name='cycle_id')
    op.rename_table('payout_cycle_balances', 'closed_cycle_balances')
    op.alter_column('closed_cycle_balances', 'payout_cycle_id', new_column_name='closed_cycle_id')

    # closed_cycles.label -> a denormalized payout_day, matching how
    # receiving_channel_name is already denormalized rather than read live
    # off the Cycle -- a later edit to the live cycle's day shouldn't
    # retroactively change what a historical snapshot displays. Existing
    # rows never recorded a day (the field didn't exist yet), so they get
    # the same day=1 placeholder used elsewhere in this rename -- a known,
    # documented limitation, same precedent as created_at's backfill in
    # 7a46ca981ef4.
    op.drop_column('closed_cycles', 'label')
    op.add_column(
        'closed_cycles',
        sa.Column('payout_day', sa.Integer(), nullable=False, server_default='1'),
    )


def downgrade() -> None:
    op.drop_column('closed_cycles', 'payout_day')
    op.add_column(
        'closed_cycles',
        sa.Column('label', sa.String(length=50), nullable=False, server_default=''),
    )
    op.alter_column('closed_cycle_balances', 'closed_cycle_id', new_column_name='payout_cycle_id')
    op.rename_table('closed_cycle_balances', 'payout_cycle_balances')
    op.alter_column('closed_cycles', 'cycle_id', new_column_name='payout_period_id')
    op.rename_table('closed_cycles', 'payout_cycles')

    for table in _FK_TABLES:
        op.alter_column(table, 'cycle_id', new_column_name='payout_period_id')
    op.rename_table('cycles', 'payout_periods')
