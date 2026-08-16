"""case-insensitive email index

Revision ID: 76352e3a5eef
Revises: 675bc76494c0
Create Date: 2026-08-16 08:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '76352e3a5eef'
down_revision: Union[str, None] = '675bc76494c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Backfill any pre-existing mixed-case emails to lowercase before adding
    # the unique index below, so two accounts that only differ by casing
    # (which the app never intentionally created, but the old case-sensitive
    # constraint didn't prevent) don't make this index un-creatable. Written
    # as raw SQL rather than op.execute(users.update()...) since this
    # migration must keep working regardless of what app/models.py looks
    # like in the future -- see CLAUDE.md's "Models vs. migrations" note.
    op.execute("UPDATE users SET email = lower(email) WHERE email != lower(email)")
    op.create_index(
        "ix_users_email_lower", "users", [sa.text("lower(email)")], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_users_email_lower", table_name="users")
