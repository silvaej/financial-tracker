"""cycle schema prep

Revision ID: a583d4a319d2
Revises: fef6e4047d80
Create Date: 2026-09-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a583d4a319d2'
down_revision: Union[str, None] = 'fef6e4047d80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Backfills every existing period with no payout_day (previously
    # optional -- the seeded "Freelance Payout" period is one known
    # offender, but any period created before issue #134 added the field
    # is a NULL row too) before the column becomes NOT NULL below. Day 1 is
    # a placeholder the user can correct in the UI afterward -- see #189.
    op.execute("UPDATE payout_periods SET payout_day = 1 WHERE payout_day IS NULL")
    op.alter_column(
        'payout_periods', 'payout_day', existing_type=sa.Integer(), nullable=False
    )

    op.drop_constraint(
        'payout_periods_user_id_label_key', 'payout_periods', type_='unique'
    )
    op.drop_column('payout_periods', 'label')
    op.drop_column('payout_periods', 'display_order')

    op.add_column(
        'users',
        sa.Column('cycles_per_month', sa.Integer(), nullable=False, server_default='1'),
    )
    # Seeds each existing user's real cycle count from their current row
    # count, rather than leaving everyone at the column's default of 1 --
    # a user who already has 3 payout periods should start with a cap of 3,
    # not be immediately blocked from creating a 4th once #191 enforces
    # this. Users with zero payout periods keep the server_default of 1.
    op.execute(
        "UPDATE users SET cycles_per_month = sub.cnt "
        "FROM (SELECT user_id, COUNT(*) cnt FROM payout_periods GROUP BY user_id) sub "
        "WHERE users.id = sub.user_id"
    )


def downgrade() -> None:
    op.drop_column('users', 'cycles_per_month')

    op.add_column(
        'payout_periods',
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
    )
    # The original label text is not recoverable -- same "schema reversible,
    # data is not" precedent as bafc51ed3cb6's funding_source_channel_id
    # downgrade. Empty string satisfies the NOT NULL constraint being
    # restored; existing rows all land on it.
    op.add_column(
        'payout_periods',
        sa.Column(
            'label', sa.String(length=50), nullable=False, server_default=''
        ),
    )
    op.alter_column('payout_periods', 'payout_day', existing_type=sa.Integer(), nullable=True)
    op.create_unique_constraint(
        'payout_periods_user_id_label_key', 'payout_periods', ['user_id', 'label']
    )
