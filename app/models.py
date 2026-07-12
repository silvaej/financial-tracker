from sqlalchemy import ForeignKey, LargeBinary, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)


class Channel(Base):
    __tablename__ = "channels"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str] = mapped_column(String(7), default="#8a8a8a")
    channel_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    logo_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    logo_mimetype: Mapped[str | None] = mapped_column(String(50), nullable=True)


class PayoutPeriod(Base):
    __tablename__ = "payout_periods"
    __table_args__ = (UniqueConstraint("user_id", "label"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    display_order: Mapped[int] = mapped_column(default=0)
    income_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    receiving_channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id"), nullable=True
    )

    receiving_channel: Mapped[Channel | None] = relationship()


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    payout_period_id: Mapped[int] = mapped_column(ForeignKey("payout_periods.id"), nullable=False)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False)

    payout_period: Mapped[PayoutPeriod] = relationship()
    channel: Mapped[Channel] = relationship()


class Transfer(Base):
    __tablename__ = "transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    payout_period_id: Mapped[int] = mapped_column(ForeignKey("payout_periods.id"), nullable=False)
    from_channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False)
    to_channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    payout_period: Mapped[PayoutPeriod] = relationship()
    from_channel: Mapped[Channel] = relationship(foreign_keys=[from_channel_id])
    to_channel: Mapped[Channel] = relationship(foreign_keys=[to_channel_id])


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    target: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    allocated: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    months: Mapped[int] = mapped_column(default=1)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id"), nullable=True)
    round_up_to_hundred: Mapped[bool] = mapped_column(default=False)

    channel: Mapped[Channel | None] = relationship()


class GoalContribution(Base):
    __tablename__ = "goal_contributions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), nullable=False)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False)
    payout_period_id: Mapped[int] = mapped_column(ForeignKey("payout_periods.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    goal: Mapped[Goal] = relationship()
    channel: Mapped[Channel] = relationship()
    payout_period: Mapped[PayoutPeriod] = relationship()


class ChannelPlacement(Base):
    """A channel's presence + position on one specific payout period's canvas.

    No row for a given (payout_period_id, channel_id) means that channel isn't
    on that period's canvas -- it shows up in the toolbox instead."""

    __tablename__ = "channel_placements"
    __table_args__ = (UniqueConstraint("payout_period_id", "channel_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    payout_period_id: Mapped[int] = mapped_column(ForeignKey("payout_periods.id"), nullable=False)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False)
    x: Mapped[float] = mapped_column()
    y: Mapped[float] = mapped_column()

    channel: Mapped[Channel] = relationship()


class GoalPlacement(Base):
    """A goal's presence + position on one specific payout period's canvas."""

    __tablename__ = "goal_placements"
    __table_args__ = (UniqueConstraint("payout_period_id", "goal_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    payout_period_id: Mapped[int] = mapped_column(ForeignKey("payout_periods.id"), nullable=False)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), nullable=False)
    x: Mapped[float] = mapped_column()
    y: Mapped[float] = mapped_column()

    goal: Mapped[Goal] = relationship()


class CreditLine(Base):
    __tablename__ = "credit_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    limit: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    used: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id"), nullable=True)

    channel: Mapped[Channel | None] = relationship()


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id"), nullable=True)

    channel: Mapped[Channel | None] = relationship()
