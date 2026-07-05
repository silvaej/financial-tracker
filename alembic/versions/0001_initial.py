"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("color", sa.String(length=7), nullable=False, server_default="#8a8a8a"),
    )

    op.create_table(
        "payout_periods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label", sa.String(length=50), nullable=False, unique=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("income_amount", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column(
            "receiving_channel_id", sa.Integer(), sa.ForeignKey("channels.id"), nullable=True
        ),
    )

    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "payout_period_id",
            sa.Integer(),
            sa.ForeignKey("payout_periods.id"),
            nullable=False,
        ),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id"), nullable=False),
    )

    op.create_table(
        "transfers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "payout_period_id",
            sa.Integer(),
            sa.ForeignKey("payout_periods.id"),
            nullable=False,
        ),
        sa.Column("from_channel_id", sa.Integer(), sa.ForeignKey("channels.id"), nullable=False),
        sa.Column("to_channel_id", sa.Integer(), sa.ForeignKey("channels.id"), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
    )

    op.create_table(
        "goals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("target", sa.Numeric(10, 2), nullable=False),
        sa.Column("allocated", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("months", sa.Integer(), nullable=False, server_default="1"),
    )

    op.create_table(
        "credit_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("limit", sa.Numeric(10, 2), nullable=False),
        sa.Column("used", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id"), nullable=True),
    )

    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("assets")
    op.drop_table("credit_lines")
    op.drop_table("goals")
    op.drop_table("transfers")
    op.drop_table("expenses")
    op.drop_table("payout_periods")
    op.drop_table("channels")
