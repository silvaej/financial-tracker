"""add onboarding nudges

Revision ID: 9c3f0e5a1b7d
Revises: 6a478192fbe4
Create Date: 2026-08-18 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '9c3f0e5a1b7d'
down_revision: Union[str, None] = '6a478192fbe4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'onboarding_nudges',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('section', sa.String(length=20), nullable=False),
        sa.Column(
            'dismissed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'section'),
    )


def downgrade() -> None:
    op.drop_table('onboarding_nudges')
