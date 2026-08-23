"""add expense categories

Revision ID: 4fa24502c6fd
Revises: ad764185fe15
Create Date: 2026-08-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '4fa24502c6fd'
down_revision: Union[str, None] = 'ad764185fe15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'expense_categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('color', sa.String(length=7), nullable=False, server_default='#8a8a8a'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'name'),
    )
    op.add_column('expenses', sa.Column('category_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'expenses', 'expense_categories', ['category_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint(None, 'expenses', type_='foreignkey')
    op.drop_column('expenses', 'category_id')
    op.drop_table('expense_categories')
