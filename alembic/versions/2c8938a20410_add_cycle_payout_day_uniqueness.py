"""add cycle payout day uniqueness

Revision ID: 2c8938a20410
Revises: 611719b3f44b
Create Date: 2026-09-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = '2c8938a20410'
down_revision: Union[str, None] = '611719b3f44b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOTE: this will fail to apply if any user already has two cycles
    # sharing the same payout_day -- exactly the bug issue #212 is about.
    # If it fails on a real environment, find and resolve the duplicate(s)
    # (change one's payout_day) before retrying.
    op.create_unique_constraint('uq_cycles_user_id_payout_day', 'cycles', ['user_id', 'payout_day'])


def downgrade() -> None:
    op.drop_constraint('uq_cycles_user_id_payout_day', 'cycles', type_='unique')
