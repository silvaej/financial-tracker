"""add user created_at

Revision ID: 7a46ca981ef4
Revises: 21ce9028b3e1
Create Date: 2026-08-16 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '7a46ca981ef4'
down_revision: Union[str, None] = '21ce9028b3e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing rows get this migration's run time, not their real signup
    # date -- that was never tracked before now. See models.py's User.created_at
    # docstring.
    op.add_column(
        'users',
        sa.Column(
            'created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'created_at')
