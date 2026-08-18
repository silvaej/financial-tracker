from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SignupKey(Base):
    """An operator-issued invite key gating /signup -- see CLAUDE.md's "No
    public registration" note. Created via `manage_users.py create-key`."""

    __tablename__ = "signup_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    max_uses: Mapped[int] = mapped_column(default=1)
    use_count: Mapped[int] = mapped_column(default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    avatar_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    avatar_mimetype: Mapped[str | None] = mapped_column(String(50), nullable=True)
    currency_code: Mapped[str] = mapped_column(
        String(3), nullable=False, default="PHP", server_default="PHP"
    )
    timezone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notify_cash_flow_warnings: Mapped[bool] = mapped_column(default=True)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Added retroactively for the admin dashboard's "signup date" column
    # (issue #65) -- existing rows get the migration's run time as their
    # value (server_default=now()), not their real signup date, since that
    # was never tracked before this. Documented as a known limitation in
    # the migration rather than trying to backfill a value this app never
    # actually recorded.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    # Plain unique=True above only rejects byte-identical duplicates -- app
    # code always normalizes email to lowercase before read/write (see
    # crud.get_user_by_email/create_user), but this functional index is a
    # DB-level backstop against any write path that forgets to (a raw SQL
    # script, a future admin tool, etc.) -- see issue #71.
    __table_args__ = (Index("ix_users_email_lower", func.lower(email), unique=True),)


class OAuthIdentity(Base):
    """A Google/GitHub identity linked to a User -- see app/routers/oauth.py.
    One User can have identities from both providers (linked automatically
    when a sign-in's verified email matches an existing account)."""

    __tablename__ = "oauth_identities"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    user: Mapped["User"] = relationship()


class Channel(Base):
    __tablename__ = "channels"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str] = mapped_column(String(7), default="#8a8a8a")
    channel_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    badge_label: Mapped[str | None] = mapped_column(String(4), nullable=True)
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
    # Optional day-of-month this period's payday falls on -- same pattern as
    # Expense.due_day. Purely a hint (crud.overdue_payout_period_ids uses it
    # to flag periods whose payday has passed with no cycle closed since),
    # not a real calendar anchor: `label` stays free text, and nothing else
    # in the app infers dates from it. See issue #134.
    payout_day: Mapped[int | None] = mapped_column(nullable=True)

    receiving_channel: Mapped[Channel | None] = relationship()


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    payout_period_id: Mapped[int] = mapped_column(ForeignKey("payout_periods.id"), nullable=False)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False)
    due_day: Mapped[int | None] = mapped_column(nullable=True)
    # A simple manually-maintained marker ("did I pay this bill"), not tied
    # to a specific cycle -- Expense rows are perpetual templates with no
    # dated-cycle concept (see issue #84), so this doesn't auto-reset at the
    # start of a new payout period; the user checks it off, then unchecks it
    # themselves next cycle. See issue #85.
    paid: Mapped[bool] = mapped_column(default=False)
    # Paused expenses are excluded from channel_balances() (see
    # _all_channel_balances in crud.py) but the row itself is kept --
    # cancelling a subscription for one cycle shouldn't mean losing its
    # channel/amount/history the way deleting it would. See issue #86.
    active: Mapped[bool] = mapped_column(default=True)

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


class PayoutCycle(Base):
    """A locked, dated snapshot of one occurrence of a PayoutPeriod -- see
    issue #84. PayoutPeriod itself stays a perpetual, always-editable
    template (per CLAUDE.md's Domain section); closing a cycle here doesn't
    touch or clear the period's live transfers/expenses, it just records
    what channel_balances() computed at that moment so a later edit to the
    live template can't silently overwrite the only record that ever
    existed. Deliberately no FK to Channel for the receiving channel (see
    PayoutCycleBalance below) -- a snapshot is a historical fact and
    shouldn't block deleting a channel used only in old history, or need
    updating if that channel is later renamed/recolored."""

    __tablename__ = "payout_cycles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    payout_period_id: Mapped[int] = mapped_column(ForeignKey("payout_periods.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    closed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    income_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    receiving_channel_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    payout_period: Mapped[PayoutPeriod] = relationship()


class PayoutCycleBalance(Base):
    """One channel's snapshotted activity within a closed PayoutCycle.
    channel_name/channel_color are denormalized (not a Channel FK) for the
    same reason as PayoutCycle.receiving_channel_name above. `net` is the
    channel's full running balance (as crud.channel_balances() computed it
    at closure time, including carry-in from prior periods); `income`/
    `transfers_net`/`expenses_total` describe only this cycle's own
    activity and generally won't sum to `net` on their own -- both are
    useful, so both are kept rather than picking one."""

    __tablename__ = "payout_cycle_balances"

    id: Mapped[int] = mapped_column(primary_key=True)
    payout_cycle_id: Mapped[int] = mapped_column(ForeignKey("payout_cycles.id"), nullable=False)
    channel_name: Mapped[str] = mapped_column(String(100), nullable=False)
    channel_color: Mapped[str] = mapped_column(String(7), nullable=False)
    income: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    transfers_net: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    expenses_total: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    net: Mapped[float] = mapped_column(Numeric(10, 2), default=0)

    payout_cycle: Mapped[PayoutCycle] = relationship()


class OnboardingNudge(Base):
    """Per-(user, section) dismissal for the first-visit nudge banners on
    Cash Flow/Goals/Credit/Assets -- see issue #138. Distinct from
    User.onboarding_completed_at (the Channels/PayoutPeriods/Expenses
    3-step flow, which this doesn't touch): those three are genuinely
    sequential, these four are independent, so each section is tracked
    separately rather than folded into the same single timestamp. A row's
    mere existence means "dismissed" -- crud.needs_nudge() also checks
    whether the section still has no data, so the banner auto-clears the
    moment either the user dismisses it or adds something, without
    needing to distinguish the two."""

    __tablename__ = "onboarding_nudges"
    __table_args__ = (UniqueConstraint("user_id", "section"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    section: Mapped[str] = mapped_column(String(20), nullable=False)
    dismissed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
