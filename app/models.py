from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    color: Mapped[str] = mapped_column(String(7), default="#8a8a8a")
    funding_source_channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id"), nullable=True
    )

    funding_source: Mapped["Channel | None"] = relationship(remote_side="Channel.id")


class PayoutPeriod(Base):
    __tablename__ = "payout_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    display_order: Mapped[int] = mapped_column(default=0)
    income_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    receiving_channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id"), nullable=True
    )

    receiving_channel: Mapped[Channel | None] = relationship()


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    payout_period_id: Mapped[int] = mapped_column(ForeignKey("payout_periods.id"), nullable=False)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False)

    payout_period: Mapped[PayoutPeriod] = relationship()
    channel: Mapped[Channel] = relationship()


class Transfer(Base):
    __tablename__ = "transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    target: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    allocated: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    months: Mapped[int] = mapped_column(default=1)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id"), nullable=True)
    round_up_to_hundred: Mapped[bool] = mapped_column(default=False)

    channel: Mapped[Channel | None] = relationship()


class CreditLine(Base):
    __tablename__ = "credit_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    limit: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    used: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id"), nullable=True)

    channel: Mapped[Channel | None] = relationship()


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
