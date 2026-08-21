import calendar
import json
import logging
import math
import secrets
import zoneinfo
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, NamedTuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import models, schemas

logger = logging.getLogger("app.oauth")

# --- Channels ---------------------------------------------------------------

CHANNEL_TYPES: tuple[str, ...] = (
    "Traditional Bank",
    "Digital Bank",
    "E-Wallet",
    "Credit Card",
    "Time Deposit",
    "Payment Gateway",
    "Investment",
    "Cash",
)

# Quick-add presets for channels common in the Philippines. These are brand
# colors + initials rendered through the existing badge component, not actual
# logo artwork -- real logos are trademarked and can't be bundled here. A
# user can still upload their own image as a channel's logo.
_BANK = "Traditional Bank"
_DBANK = "Digital Bank"
_EWALLET = "E-Wallet"


def _preset(group: str, name: str, short: str, color: str, ptype: str) -> dict[str, str]:
    return {"group": group, "name": name, "short": short, "color": color, "type": ptype}


CHANNEL_PRESETS: tuple[dict[str, str], ...] = (
    _preset("Banks", "BDO", "BDO", "#003DA5", _BANK),
    _preset("Banks", "BPI", "BPI", "#C8102E", _BANK),
    _preset("Banks", "Metrobank", "MB", "#001B5E", _BANK),
    _preset("Banks", "Landbank", "LB", "#00693E", _BANK),
    _preset("Banks", "PNB", "PNB", "#7A1E1E", _BANK),
    _preset("Banks", "China Bank", "CB", "#004990", _BANK),
    _preset("Banks", "RCBC", "RCBC", "#0033A0", _BANK),
    _preset("Banks", "Security Bank", "SB", "#F47920", _BANK),
    _preset("Banks", "EastWest", "EW", "#ED1C24", _BANK),
    _preset("Banks", "UnionBank", "UB", "#F7941E", _BANK),
    _preset("Banks", "PSBank", "PS", "#FDB913", _BANK),
    _preset("Digital banks & e-wallets", "GCash", "GC", "#007DFE", _EWALLET),
    _preset("Digital banks & e-wallets", "Maya", "M", "#00D66F", _DBANK),
    _preset("Digital banks & e-wallets", "GrabPay", "GP", "#00B14F", _EWALLET),
    _preset("Digital banks & e-wallets", "ShopeePay", "SP", "#EE4D2D", _EWALLET),
    _preset("Digital banks & e-wallets", "Coins.ph", "CO", "#1E5AA8", _EWALLET),
    _preset("Digital banks & e-wallets", "SeaBank", "SB", "#EE7A0C", _DBANK),
    _preset("Digital banks & e-wallets", "Tonik", "TN", "#7A2EBE", _DBANK),
    _preset("Digital banks & e-wallets", "CIMB Bank PH", "CIMB", "#E4002B", _DBANK),
)


class ChannelInUseError(Exception):
    """Raised when deleting a channel that is still referenced elsewhere."""


class PayoutPeriodInUseError(Exception):
    """Raised when deleting a payout period that is still referenced elsewhere."""


class OwnershipError(Exception):
    """Raised when a referenced row doesn't belong to the acting user."""


def _owned(db: Session, model: type[Any], id_: int, user_id: int | None) -> Any:
    return db.scalar(select(model).where(model.id == id_, model.user_id == user_id))


def _require_owned(
    db: Session, model: type[Any], id_: int | None, user_id: int | None, label: str
) -> None:
    if id_ is not None and _owned(db, model, id_, user_id) is None:
        raise OwnershipError(f"{label} not found.")


def _delete_owned(db: Session, model: type[Any], id_: int, user_id: int | None) -> None:
    """Delete-if-owned for entities with no extra cleanup/validation on
    delete (contrast delete_channel/delete_payout_period's in-use checks or
    delete_goal's child cleanup, which stay bespoke)."""
    row = _owned(db, model, id_, user_id)
    if row is not None:
        db.delete(row)
        db.commit()


# --- Users --------------------------------------------------------------------

# (code, label) pairs for the Account page's currency <select>.
CURRENCY_OPTIONS: tuple[tuple[str, str], ...] = (
    ("PHP", "₱ PHP — Philippine Peso"),
    ("USD", "$ USD — US Dollar"),
    ("EUR", "€ EUR — Euro"),
    ("JPY", "¥ JPY — Japanese Yen"),
    ("GBP", "£ GBP — British Pound"),
    ("SGD", "$ SGD — Singapore Dollar"),
    ("AUD", "$ AUD — Australian Dollar"),
)
CURRENCY_CODES: frozenset[str] = frozenset(code for code, _ in CURRENCY_OPTIONS)
CURRENCY_SYMBOLS: dict[str, str] = {
    "PHP": "₱",
    "USD": "$",
    "EUR": "€",
    "JPY": "¥",
    "GBP": "£",
    "SGD": "$",
    "AUD": "$",
}
DEFAULT_CURRENCY_SYMBOL = CURRENCY_SYMBOLS["PHP"]


def currency_symbol_for(user: models.User | None) -> str:
    if user is None:
        return DEFAULT_CURRENCY_SYMBOL
    return CURRENCY_SYMBOLS.get(user.currency_code, DEFAULT_CURRENCY_SYMBOL)


TIMEZONE_OPTIONS: tuple[str, ...] = tuple(sorted(zoneinfo.available_timezones()))


def get_user(db: Session, user_id: int) -> models.User | None:
    return db.get(models.User, user_id)


def get_user_by_email(db: Session, email: str) -> models.User | None:
    # Case-insensitive: an OAuth provider's verified email casing isn't
    # guaranteed to match how the user (or an operator via manage_users.py)
    # originally typed it -- see issue #71.
    return db.scalar(select(models.User).where(models.User.email == email.strip().lower()))


def create_user(db: Session, email: str) -> models.User:
    user = models.User(email=email.strip().lower())
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_oauth_identity(
    db: Session, provider: str, provider_user_id: str
) -> models.OAuthIdentity | None:
    return db.scalar(
        select(models.OAuthIdentity).where(
            models.OAuthIdentity.provider == provider,
            models.OAuthIdentity.provider_user_id == provider_user_id,
        )
    )


def create_oauth_identity(
    db: Session, user: models.User, provider: str, provider_user_id: str, email: str
) -> models.OAuthIdentity:
    identity = models.OAuthIdentity(
        user_id=user.id, provider=provider, provider_user_id=provider_user_id, email=email
    )
    db.add(identity)
    db.commit()
    db.refresh(identity)
    return identity


OAuthLoginError = Literal["already_has_account", "no_account", "invalid_key"]


class OAuthLoginResult(NamedTuple):
    user: models.User | None
    error: OAuthLoginError | None


def resolve_oauth_login(
    db: Session,
    provider: str,
    provider_user_id: str,
    email: str,
    pending_invite_key: str,
    pending_intent: str,
) -> OAuthLoginResult:
    """The account-linking decision tree for an OAuth callback: identity
    lookup -> email match -> auto-link -> invite-key validation -> account
    creation. Pulled out of app/routers/oauth.py (see issue #82) so the
    router can stay thin (parse -> call -> respond) like every other router
    in this app -- this was the one place business logic lived directly in
    a route handler."""
    identity = get_oauth_identity(db, provider, provider_user_id)
    if identity is not None:
        if pending_intent == "signup":
            return OAuthLoginResult(user=None, error="already_has_account")
        return OAuthLoginResult(user=identity.user, error=None)

    existing_user = get_user_by_email(db, email)
    if existing_user is not None:
        if pending_intent == "signup":
            return OAuthLoginResult(user=None, error="already_has_account")
        create_oauth_identity(db, existing_user, provider, provider_user_id, email)
        return OAuthLoginResult(user=existing_user, error=None)

    if not pending_invite_key:
        return OAuthLoginResult(user=None, error="no_account")

    signup_key = get_active_signup_key(db, pending_invite_key)
    if signup_key is None:
        return OAuthLoginResult(user=None, error="invalid_key")

    user = create_user(db, email)
    redeem_signup_key(db, signup_key)
    logger.info("New account created via signup key: %r", email)
    create_oauth_identity(db, user, provider, provider_user_id, email)
    return OAuthLoginResult(user=user, error=None)


def update_profile(
    db: Session,
    user: models.User,
    *,
    display_name: str | None,
    currency_code: str,
    timezone: str | None,
    notify_cash_flow_warnings: bool,
) -> None:
    user.display_name = display_name
    user.currency_code = currency_code
    user.timezone = timezone
    user.notify_cash_flow_warnings = notify_cash_flow_warnings
    db.commit()


def set_avatar(db: Session, user: models.User, data: bytes, mimetype: str) -> None:
    user.avatar_data = data
    user.avatar_mimetype = mimetype
    db.commit()


def clear_avatar(db: Session, user: models.User) -> None:
    user.avatar_data = None
    user.avatar_mimetype = None
    db.commit()


# --- Onboarding ---------------------------------------------------------------


def _has_any_expenses(db: Session, user_id: int) -> bool:
    stmt = select(models.Expense.id).where(models.Expense.user_id == user_id).limit(1)
    return db.scalar(stmt) is not None


def compute_onboarding_step(
    user: models.User,
    channels: list[models.Channel],
    payout_periods: list[models.PayoutPeriod],
    has_expenses: bool,
) -> int | None:
    """1/2/3 for the active onboarding step, or None once onboarding is
    finished (explicitly skipped, or all three prerequisites now exist --
    see create_expense()'s auto-complete). Never re-derived from data once
    finished, so e.g. later deleting a channel doesn't resurrect the banner."""
    if user.onboarding_completed_at is not None:
        return None
    if not channels:
        return 1
    if not payout_periods:
        return 2
    if not has_expenses:
        return 3
    return None


def needs_onboarding(db: Session, user: models.User) -> bool:
    if user.onboarding_completed_at is not None:
        return False
    channels = list_channels(db, user.id)
    if not channels:
        return True
    if not list_payout_periods(db, user.id):
        return True
    return not _has_any_expenses(db, user.id)


def _has_any_transfers(db: Session, user_id: int) -> bool:
    stmt = select(models.Transfer.id).where(models.Transfer.user_id == user_id).limit(1)
    return db.scalar(stmt) is not None


def needs_nudge(db: Session, user_id: int, section: str, is_empty: bool) -> bool:
    """Whether the first-visit nudge banner for `section` (one of "cashflow",
    "goals", "credit", "assets" -- see issue #138) should show. Only while
    the section is still empty *and* hasn't been explicitly dismissed --
    auto-clears the moment either flips, same "auto-completes on real data"
    spirit as the Channels/PayoutPeriods/Expenses flow above, just
    per-section instead of a single global timestamp."""
    if not is_empty:
        return False
    stmt = (
        select(models.OnboardingNudge.id)
        .where(models.OnboardingNudge.user_id == user_id, models.OnboardingNudge.section == section)
        .limit(1)
    )
    return db.scalar(stmt) is None


def dismiss_nudge(db: Session, user_id: int, section: str) -> None:
    existing = db.scalar(
        select(models.OnboardingNudge).where(
            models.OnboardingNudge.user_id == user_id, models.OnboardingNudge.section == section
        )
    )
    if existing is None:
        db.add(models.OnboardingNudge(user_id=user_id, section=section))
        db.commit()


def skip_onboarding(db: Session, user: models.User) -> None:
    user.onboarding_completed_at = datetime.now(UTC)
    db.commit()


# --- Signup keys --------------------------------------------------------------

# Excludes 0/O and 1/I to avoid ambiguity when an operator reads a key aloud
# or a user retypes it by hand.
_SIGNUP_KEY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_signup_key_value() -> str:
    groups = ["".join(secrets.choice(_SIGNUP_KEY_ALPHABET) for _ in range(4)) for _ in range(2)]
    return "LEDGER-" + "-".join(groups)


def create_signup_key(
    db: Session, max_uses: int = 1, expires_at: datetime | None = None
) -> models.SignupKey:
    key = models.SignupKey(
        key=generate_signup_key_value(), max_uses=max_uses, expires_at=expires_at
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return key


def get_active_signup_key(db: Session, key_value: str) -> models.SignupKey | None:
    key = db.scalar(select(models.SignupKey).where(models.SignupKey.key == key_value))
    if key is None or key.use_count >= key.max_uses:
        return None
    expires_at = key.expires_at
    if expires_at is not None:
        if expires_at.tzinfo is None:
            # SQLite (used in tests) doesn't persist tzinfo on DateTime(timezone=True) columns.
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            return None
    return key


def redeem_signup_key(db: Session, key: models.SignupKey) -> None:
    key.use_count += 1
    db.commit()


# --- Channels ---------------------------------------------------------------


def list_channels(db: Session, user_id: int | None) -> list[models.Channel]:
    stmt = select(models.Channel).where(models.Channel.user_id == user_id)
    return list(db.scalars(stmt.order_by(models.Channel.name)))


def create_channel(db: Session, data: schemas.ChannelCreate, user_id: int | None) -> models.Channel:
    channel = models.Channel(
        name=data.name,
        color=data.color,
        channel_type=data.channel_type,
        badge_label=data.badge_label,
        user_id=user_id,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def update_channel(
    db: Session, channel_id: int, data: schemas.ChannelUpdate, user_id: int
) -> models.Channel | None:
    channel = _owned(db, models.Channel, channel_id, user_id)
    if channel is not None:
        channel.name = data.name
        channel.color = data.color
        channel.channel_type = data.channel_type
        channel.current_amount = data.current_amount
        db.commit()
        db.refresh(channel)
    return channel


def get_channel_logo(db: Session, channel_id: int, user_id: int) -> models.Channel | None:
    return _owned(db, models.Channel, channel_id, user_id)


def set_channel_logo(
    db: Session, channel_id: int, data: bytes, mimetype: str, user_id: int
) -> models.Channel | None:
    channel = _owned(db, models.Channel, channel_id, user_id)
    if channel is not None:
        channel.logo_data = data
        channel.logo_mimetype = mimetype
        db.commit()
    return channel


def clear_channel_logo(db: Session, channel_id: int, user_id: int) -> models.Channel | None:
    channel = _owned(db, models.Channel, channel_id, user_id)
    if channel is not None:
        channel.logo_data = None
        channel.logo_mimetype = None
        db.commit()
    return channel


def list_channel_placements(
    db: Session, payout_period_id: int, user_id: int
) -> list[models.ChannelPlacement]:
    stmt = select(models.ChannelPlacement).where(
        models.ChannelPlacement.payout_period_id == payout_period_id,
        models.ChannelPlacement.user_id == user_id,
    )
    return list(db.scalars(stmt))


def place_channel(
    db: Session, payout_period_id: int, channel_id: int, x: float, y: float, user_id: int
) -> models.ChannelPlacement:
    _require_owned(db, models.PayoutPeriod, payout_period_id, user_id, "Payout period")
    _require_owned(db, models.Channel, channel_id, user_id, "Channel")
    placement = db.scalar(
        select(models.ChannelPlacement).where(
            models.ChannelPlacement.payout_period_id == payout_period_id,
            models.ChannelPlacement.channel_id == channel_id,
            models.ChannelPlacement.user_id == user_id,
        )
    )
    if placement is None:
        placement = models.ChannelPlacement(
            payout_period_id=payout_period_id, channel_id=channel_id, x=x, y=y, user_id=user_id
        )
        db.add(placement)
    else:
        placement.x = x
        placement.y = y
    db.commit()
    db.refresh(placement)
    return placement


def remove_channel_placement(
    db: Session, payout_period_id: int, channel_id: int, user_id: int
) -> None:
    placement = db.scalar(
        select(models.ChannelPlacement).where(
            models.ChannelPlacement.payout_period_id == payout_period_id,
            models.ChannelPlacement.channel_id == channel_id,
            models.ChannelPlacement.user_id == user_id,
        )
    )
    if placement is not None:
        db.delete(placement)
        db.commit()


def delete_channel(db: Session, channel_id: int, user_id: int) -> None:
    channel = _owned(db, models.Channel, channel_id, user_id)
    if channel is None:
        return

    in_use = (
        db.query(models.PayoutPeriod)
        .filter_by(receiving_channel_id=channel_id, user_id=user_id)
        .first()
        or db.query(models.Expense).filter_by(channel_id=channel_id, user_id=user_id).first()
        or db.query(models.Transfer)
        .filter(
            models.Transfer.user_id == user_id,
            or_(
                models.Transfer.from_channel_id == channel_id,
                models.Transfer.to_channel_id == channel_id,
            ),
        )
        .first()
        or db.query(models.GoalContribution)
        .filter_by(channel_id=channel_id, user_id=user_id)
        .first()
        or db.query(models.Goal).filter_by(channel_id=channel_id, user_id=user_id).first()
        or db.query(models.CreditLine).filter_by(channel_id=channel_id, user_id=user_id).first()
        or db.query(models.Asset).filter_by(channel_id=channel_id, user_id=user_id).first()
    )
    if in_use is not None:
        raise ChannelInUseError(
            "This channel is still used by a payout period, expense, transfer, "
            "goal contribution, goal, credit line, or asset, and can't be "
            "deleted until those are removed or reassigned."
        )

    db.query(models.ChannelPlacement).filter_by(channel_id=channel_id, user_id=user_id).delete()
    db.delete(channel)
    db.commit()


# --- Payout periods ----------------------------------------------------------


def list_payout_periods(db: Session, user_id: int | None) -> list[models.PayoutPeriod]:
    stmt = (
        select(models.PayoutPeriod)
        .where(models.PayoutPeriod.user_id == user_id)
        .order_by(models.PayoutPeriod.display_order)
    )
    return list(db.scalars(stmt))


def create_payout_period(
    db: Session, data: schemas.PayoutPeriodCreate, user_id: int | None
) -> models.PayoutPeriod:
    _require_owned(db, models.Channel, data.receiving_channel_id, user_id, "Receiving channel")
    max_order = db.scalar(
        select(models.PayoutPeriod.display_order)
        .where(models.PayoutPeriod.user_id == user_id)
        .order_by(models.PayoutPeriod.display_order.desc())
    )
    period = models.PayoutPeriod(
        label=data.label,
        income_amount=data.income_amount,
        receiving_channel_id=data.receiving_channel_id,
        payout_day=data.payout_day,
        display_order=(max_order or 0) + 1,
        user_id=user_id,
    )
    db.add(period)
    db.commit()
    db.refresh(period)
    return period


def update_payout_period(
    db: Session, payout_period_id: int, data: schemas.PayoutPeriodUpdate, user_id: int
) -> models.PayoutPeriod | None:
    _require_owned(db, models.Channel, data.receiving_channel_id, user_id, "Receiving channel")
    period = _owned(db, models.PayoutPeriod, payout_period_id, user_id)
    if period is not None:
        period.income_amount = data.income_amount
        period.receiving_channel_id = data.receiving_channel_id
        period.payout_day = data.payout_day
        db.commit()
        db.refresh(period)
    return period


def delete_payout_period(db: Session, payout_period_id: int, user_id: int) -> None:
    period = _owned(db, models.PayoutPeriod, payout_period_id, user_id)
    if period is None:
        return

    in_use = (
        db.query(models.Expense)
        .filter_by(payout_period_id=payout_period_id, user_id=user_id)
        .first()
        or db.query(models.Transfer)
        .filter_by(payout_period_id=payout_period_id, user_id=user_id)
        .first()
        or db.query(models.GoalContribution)
        .filter_by(payout_period_id=payout_period_id, user_id=user_id)
        .first()
        or db.query(models.ChannelPlacement)
        .filter_by(payout_period_id=payout_period_id, user_id=user_id)
        .first()
        or db.query(models.GoalPlacement)
        .filter_by(payout_period_id=payout_period_id, user_id=user_id)
        .first()
    )
    if in_use is not None:
        raise PayoutPeriodInUseError(
            "This payout period is still used by an expense, transfer, goal "
            "contribution, or canvas placement, and can't be deleted until "
            "those are removed or reassigned."
        )

    db.delete(period)
    db.commit()


# --- Expenses -----------------------------------------------------------------


def list_expenses(db: Session, user_id: int, q: str | None = None) -> list[models.Expense]:
    stmt = (
        select(models.Expense).where(models.Expense.user_id == user_id).order_by(models.Expense.id)
    )
    if q:
        stmt = stmt.where(models.Expense.name.ilike(f"%{q}%"))
    return list(db.scalars(stmt))


def create_expense(db: Session, data: schemas.ExpenseCreate, user_id: int | None) -> models.Expense:
    _require_owned(db, models.PayoutPeriod, data.payout_period_id, user_id, "Payout period")
    _require_owned(db, models.Channel, data.channel_id, user_id, "Channel")
    expense = models.Expense(**data.model_dump(), user_id=user_id)
    db.add(expense)
    # This expense is necessarily the user's first once onboarding_completed_at
    # is still unset (steps 1/2 already require a channel + payout period to
    # exist), so adding it is exactly the "all three prerequisites now exist"
    # completion condition -- see compute_onboarding_step().
    user = get_user(db, user_id) if user_id is not None else None
    if user is not None and user.onboarding_completed_at is None:
        user.onboarding_completed_at = datetime.now(UTC)
    db.commit()
    db.refresh(expense)
    return expense


def delete_expense(db: Session, expense_id: int, user_id: int) -> None:
    _delete_owned(db, models.Expense, expense_id, user_id)


def set_expense_paid(db: Session, expense_id: int, user_id: int, paid: bool) -> None:
    """A simple manual paid/unpaid marker -- see Expense.paid's docstring
    for why this doesn't auto-reset per cycle (issue #85)."""
    expense = _owned(db, models.Expense, expense_id, user_id)
    if expense is None:
        raise OwnershipError("Expense not found.")
    expense.paid = paid
    db.commit()


def set_expense_active(db: Session, expense_id: int, user_id: int, active: bool) -> None:
    """Pause/resume a recurring expense without deleting it -- see
    Expense.active's docstring (issue #86)."""
    expense = _owned(db, models.Expense, expense_id, user_id)
    if expense is None:
        raise OwnershipError("Expense not found.")
    expense.active = active
    db.commit()


# --- Transfers ------------------------------------------------------------------


def list_transfers(db: Session, payout_period_id: int, user_id: int) -> list[models.Transfer]:
    stmt = (
        select(models.Transfer)
        .where(
            models.Transfer.payout_period_id == payout_period_id,
            models.Transfer.user_id == user_id,
        )
        .order_by(models.Transfer.id)
    )
    return list(db.scalars(stmt))


def list_all_transfers(db: Session, user_id: int) -> list[models.Transfer]:
    stmt = (
        select(models.Transfer)
        .where(models.Transfer.user_id == user_id)
        .order_by(models.Transfer.payout_period_id, models.Transfer.id)
    )
    return list(db.scalars(stmt))


def create_transfer(db: Session, data: schemas.TransferCreate, user_id: int) -> models.Transfer:
    _require_owned(db, models.PayoutPeriod, data.payout_period_id, user_id, "Payout period")
    _require_owned(db, models.Channel, data.from_channel_id, user_id, "From channel")
    _require_owned(db, models.Channel, data.to_channel_id, user_id, "To channel")
    transfer = models.Transfer(**data.model_dump(), user_id=user_id)
    db.add(transfer)
    db.commit()
    db.refresh(transfer)
    return transfer


def update_transfer(
    db: Session, transfer_id: int, data: schemas.TransferUpdate, user_id: int
) -> models.Transfer | None:
    transfer = _owned(db, models.Transfer, transfer_id, user_id)
    if transfer is not None:
        transfer.amount = data.amount
        db.commit()
        db.refresh(transfer)
    return transfer


def delete_transfer(db: Session, transfer_id: int, user_id: int) -> None:
    _delete_owned(db, models.Transfer, transfer_id, user_id)


# --- Goal contributions -------------------------------------------------------


def list_goal_contributions(
    db: Session, payout_period_id: int, user_id: int | None
) -> list[models.GoalContribution]:
    stmt = select(models.GoalContribution).where(
        models.GoalContribution.payout_period_id == payout_period_id,
        models.GoalContribution.user_id == user_id,
    )
    return list(db.scalars(stmt))


def _recompute_goal_allocated(db: Session, goal_id: int, user_id: int | None) -> None:
    total = (
        db.scalar(
            select(func.sum(models.GoalContribution.amount)).where(
                models.GoalContribution.goal_id == goal_id,
                models.GoalContribution.user_id == user_id,
            )
        )
        or 0
    )
    goal = _owned(db, models.Goal, goal_id, user_id)
    if goal is not None:
        goal.allocated = total
        db.commit()


def create_goal_contribution(
    db: Session, data: schemas.GoalContributionCreate, user_id: int
) -> models.GoalContribution:
    _require_owned(db, models.Goal, data.goal_id, user_id, "Goal")
    _require_owned(db, models.Channel, data.channel_id, user_id, "Channel")
    _require_owned(db, models.PayoutPeriod, data.payout_period_id, user_id, "Payout period")
    contribution = models.GoalContribution(**data.model_dump(), user_id=user_id)
    db.add(contribution)
    db.commit()
    db.refresh(contribution)
    _recompute_goal_allocated(db, data.goal_id, user_id)
    return contribution


def update_goal_contribution(
    db: Session, contribution_id: int, data: schemas.GoalContributionUpdate, user_id: int
) -> models.GoalContribution | None:
    contribution = _owned(db, models.GoalContribution, contribution_id, user_id)
    if contribution is not None:
        contribution.amount = data.amount
        db.commit()
        db.refresh(contribution)
        _recompute_goal_allocated(db, contribution.goal_id, user_id)
    return contribution


def delete_goal_contribution(db: Session, contribution_id: int, user_id: int) -> None:
    contribution = _owned(db, models.GoalContribution, contribution_id, user_id)
    if contribution is not None:
        goal_id = contribution.goal_id
        db.delete(contribution)
        db.commit()
        _recompute_goal_allocated(db, goal_id, user_id)


_LAYOUT_COLUMN_WIDTH = 320.0
_LAYOUT_ROW_HEIGHT = 180.0
_LAYOUT_MARGIN = 36.0


def _layered_canvas_positions(
    channel_ids: list[int],
    goal_ids: list[int],
    transfers: list[schemas.CanvasTransferIn],
    goal_contributions: list[schemas.CanvasGoalContributionIn],
) -> tuple[dict[int, tuple[float, float]], dict[int, tuple[float, float]]]:
    """Arrange placed nodes into neat left-to-right columns by money-flow depth:
    channels with no incoming transfer start at column 0, and each node sits one
    column past its furthest predecessor, with goals trailing their funding
    channel. Any cycle (a transfer loop between channels) is broken by treating
    the second-visited node as depth 0 for that path, rather than recursing
    forever. Within each column, nodes are ordered by a barycenter heuristic
    (average position of their connected neighbors in the adjacent column) so
    edges routed straight across columns don't needlessly cross one another --
    exact crossing-free layout isn't always possible, but this avoids the
    avoidable cases."""
    NodeKey = tuple[str, int]
    nodes: set[NodeKey] = {("channel", c) for c in channel_ids} | {("goal", g) for g in goal_ids}

    incoming: dict[NodeKey, list[NodeKey]] = {node: [] for node in nodes}
    outgoing: dict[NodeKey, list[NodeKey]] = {node: [] for node in nodes}
    for transfer in transfers:
        src, dst = ("channel", transfer.from_channel_id), ("channel", transfer.to_channel_id)
        if src in incoming and dst in incoming:
            incoming[dst].append(src)
            outgoing[src].append(dst)
    for contribution in goal_contributions:
        src, dst = ("channel", contribution.channel_id), ("goal", contribution.goal_id)
        if src in incoming and dst in incoming:
            incoming[dst].append(src)
            outgoing[src].append(dst)

    depth: dict[NodeKey, int] = {}

    def resolve(node: NodeKey, path: frozenset[NodeKey]) -> int:
        if node in depth:
            return depth[node]
        if node in path:
            return 0
        preds = incoming[node]
        result = 0 if not preds else 1 + max(resolve(p, path | {node}) for p in preds)
        depth[node] = result
        return result

    for node in sorted(nodes):
        resolve(node, frozenset())

    columns: dict[int, list[NodeKey]] = {}
    for node, col in depth.items():
        columns.setdefault(col, []).append(node)
    for col in columns:
        columns[col].sort()

    def barycenter(
        node: NodeKey,
        linked_nodes: list[NodeKey],
        ref_index: dict[NodeKey, int],
        fallback: dict[NodeKey, int],
    ) -> float:
        linked = [n for n in linked_nodes if n in ref_index]
        if not linked:
            return float(fallback[node])
        return sum(ref_index[n] for n in linked) / len(linked)

    def reorder_pass(
        col_order: list[int], neighbors: dict[NodeKey, list[NodeKey]], reference_offset: int
    ) -> None:
        for col in col_order:
            ref_col = col + reference_offset
            if ref_col not in columns:
                continue
            ref_index = {node: i for i, node in enumerate(columns[ref_col])}
            fallback = {node: i for i, node in enumerate(columns[col])}
            columns[col] = sorted(
                columns[col],
                key=lambda n: (barycenter(n, neighbors[n], ref_index, fallback), n),
            )

    ascending = sorted(columns)
    for _ in range(2):
        reorder_pass(ascending, incoming, -1)
        reorder_pass(list(reversed(ascending)), outgoing, 1)

    channel_positions: dict[int, tuple[float, float]] = {}
    goal_positions: dict[int, tuple[float, float]] = {}
    for col in sorted(columns):
        x = _LAYOUT_MARGIN + col * _LAYOUT_COLUMN_WIDTH
        for row, (kind, node_id) in enumerate(columns[col]):
            y = _LAYOUT_MARGIN + row * _LAYOUT_ROW_HEIGHT
            if kind == "channel":
                channel_positions[node_id] = (x, y)
            else:
                goal_positions[node_id] = (x, y)
    return channel_positions, goal_positions


def save_canvas(
    db: Session, payout_period_id: int, data: schemas.CanvasSaveIn, user_id: int | None
) -> str | None:
    """Replace a payout period's placements/transfers/goal contributions to match
    a client's staged canvas edits, in one transaction. Returns an error message
    (making no changes) if any placed node has no connection, else None."""
    _require_owned(db, models.PayoutPeriod, payout_period_id, user_id, "Payout period")
    for channel_placement in data.channel_placements:
        _require_owned(db, models.Channel, channel_placement.channel_id, user_id, "Channel")
    for goal_placement in data.goal_placements:
        _require_owned(db, models.Goal, goal_placement.goal_id, user_id, "Goal")
    for transfer in data.transfers:
        _require_owned(db, models.Channel, transfer.from_channel_id, user_id, "From channel")
        _require_owned(db, models.Channel, transfer.to_channel_id, user_id, "To channel")
    for contribution in data.goal_contributions:
        _require_owned(db, models.Channel, contribution.channel_id, user_id, "Channel")
        _require_owned(db, models.Goal, contribution.goal_id, user_id, "Goal")

    placed_channel_ids = {p.channel_id for p in data.channel_placements}
    placed_goal_ids = {p.goal_id for p in data.goal_placements}
    connected_channel_ids = (
        {t.from_channel_id for t in data.transfers}
        | {t.to_channel_id for t in data.transfers}
        | {c.channel_id for c in data.goal_contributions}
    )
    connected_goal_ids = {c.goal_id for c in data.goal_contributions}

    if (placed_channel_ids - connected_channel_ids) or (placed_goal_ids - connected_goal_ids):
        return "Every node on the canvas needs at least one connection before saving."

    affected_goal_ids = {
        c.goal_id for c in list_goal_contributions(db, payout_period_id, user_id)
    } | connected_goal_ids

    channel_positions, goal_positions = _layered_canvas_positions(
        sorted(placed_channel_ids), sorted(placed_goal_ids), data.transfers, data.goal_contributions
    )

    db.query(models.ChannelPlacement).filter_by(
        payout_period_id=payout_period_id, user_id=user_id
    ).delete()
    db.query(models.GoalPlacement).filter_by(
        payout_period_id=payout_period_id, user_id=user_id
    ).delete()
    db.query(models.Transfer).filter_by(payout_period_id=payout_period_id, user_id=user_id).delete()
    db.query(models.GoalContribution).filter_by(
        payout_period_id=payout_period_id, user_id=user_id
    ).delete()

    for channel_placement in data.channel_placements:
        x, y = channel_positions[channel_placement.channel_id]
        db.add(
            models.ChannelPlacement(
                payout_period_id=payout_period_id,
                channel_id=channel_placement.channel_id,
                x=x,
                y=y,
                user_id=user_id,
            )
        )
    for goal_placement in data.goal_placements:
        x, y = goal_positions[goal_placement.goal_id]
        db.add(
            models.GoalPlacement(
                payout_period_id=payout_period_id,
                goal_id=goal_placement.goal_id,
                x=x,
                y=y,
                user_id=user_id,
            )
        )
    for transfer in data.transfers:
        db.add(
            models.Transfer(
                payout_period_id=payout_period_id,
                from_channel_id=transfer.from_channel_id,
                to_channel_id=transfer.to_channel_id,
                amount=transfer.amount,
                user_id=user_id,
            )
        )
    for contribution in data.goal_contributions:
        db.add(
            models.GoalContribution(
                payout_period_id=payout_period_id,
                channel_id=contribution.channel_id,
                goal_id=contribution.goal_id,
                amount=contribution.amount,
                user_id=user_id,
            )
        )
    db.commit()

    for goal_id in affected_goal_ids:
        _recompute_goal_allocated(db, goal_id, user_id)

    return None


def preview_canvas(
    db: Session, payout_period_id: int, data: schemas.CanvasSaveIn, user_id: int
) -> schemas.CanvasPreviewOut:
    """Compute channel balances and goal-contribution totals as if `data`'s
    transfers/goal contributions were this period's saved state, without
    writing anything to the database. Everything else that feeds a balance --
    expenses, this period's income, and carry-in from prior (already saved)
    periods -- is real, persisted data, since none of that is affected by
    edits still staged on this period's canvas."""
    _require_owned(db, models.PayoutPeriod, payout_period_id, user_id, "Payout period")
    for transfer in data.transfers:
        _require_owned(db, models.Channel, transfer.from_channel_id, user_id, "From channel")
        _require_owned(db, models.Channel, transfer.to_channel_id, user_id, "To channel")
    for contribution in data.goal_contributions:
        _require_owned(db, models.Channel, contribution.channel_id, user_id, "Channel")
        _require_owned(db, models.Goal, contribution.goal_id, user_id, "Goal")

    carry_in = _carry_in_for_period(db, payout_period_id, user_id)
    payout_period = _owned(db, models.PayoutPeriod, payout_period_id, user_id)
    channels = list_channels(db, user_id)
    expenses = [e for e in list_expenses(db, user_id) if e.payout_period_id == payout_period_id]

    channel_balances_out: dict[int, float] = {}
    for channel in channels:
        net = carry_in.get(channel.id, 0.0)
        if payout_period is not None and payout_period.receiving_channel_id == channel.id:
            net += float(payout_period.income_amount)
        net += sum(t.amount for t in data.transfers if t.to_channel_id == channel.id)
        net -= sum(t.amount for t in data.transfers if t.from_channel_id == channel.id)
        net -= sum(float(e.amount) for e in expenses if e.channel_id == channel.id)
        net -= sum(c.amount for c in data.goal_contributions if c.channel_id == channel.id)
        channel_balances_out[channel.id] = net

    goal_contributed: dict[int, float] = {}
    for contribution in data.goal_contributions:
        goal_contributed[contribution.goal_id] = (
            goal_contributed.get(contribution.goal_id, 0.0) + contribution.amount
        )

    payout_period_count = len(list_payout_periods(db, user_id))
    underfunded_goal_ids = [
        goal.id
        for goal in list_goals(db, user_id)
        if goal_contributed.get(goal.id, 0.0) < goal_payout_amount(goal, payout_period_count)
    ]
    unfunded_channel_ids = [
        channel_id for channel_id, net in channel_balances_out.items() if net < 0
    ]

    return schemas.CanvasPreviewOut(
        channel_balances=channel_balances_out,
        goal_contributed=goal_contributed,
        unfunded_channel_ids=unfunded_channel_ids,
        underfunded_goal_ids=underfunded_goal_ids,
    )


# --- Channel balances -----------------------------------------------------------


def _all_channel_balances(
    db: Session, user_id: int
) -> tuple[dict[int, dict[int, float]], dict[int, list[tuple[models.Channel, float]]]]:
    """Every payout period's carry-in and channel balances, computed once per
    request in a single display_order pass -- each period's ending balances
    become the next period's carry-in, fed forward directly, rather than each
    period independently re-deriving every prior period's full balance
    calculation (which was exponential: computing period k re-triggered a
    fresh computation of periods 0..k-1, each of which re-triggered periods
    0..k-2, and so on). This is the O(n) replacement; callers that need one
    period's data should index into the returned dicts rather than calling
    this per period in a loop."""
    channels = list_channels(db, user_id)
    periods = list_payout_periods(db, user_id)
    # Paused expenses (Expense.active=False) are excluded here -- see #86 --
    # so they don't count toward the period's balance without needing to
    # touch the row's identity (still shown, unfiltered, on the Expenses
    # page itself via list_expenses()).
    all_expenses = [e for e in list_expenses(db, user_id) if e.active]

    carry_in_by_period: dict[int, dict[int, float]] = {}
    balances_by_period: dict[int, list[tuple[models.Channel, float]]] = {}
    # Seeded from each channel's persistent "Actual" balance (see issue #162)
    # rather than an implicit 0 -- this is the single choke point every caller
    # (channel_balances, cashflow_page_data, preview_canvas, _live_cycle_balances)
    # inherits the baseline through.
    carry: dict[int, float] = {c.id: float(c.current_amount) for c in channels}
    for period in periods:
        carry_in_by_period[period.id] = carry
        expenses = [e for e in all_expenses if e.payout_period_id == period.id]
        transfers = list_transfers(db, period.id, user_id)
        goal_contributions = list_goal_contributions(db, period.id, user_id)

        balances: list[tuple[models.Channel, float]] = []
        for channel in channels:
            net = carry.get(channel.id, 0.0)
            if period.receiving_channel_id == channel.id:
                net += float(period.income_amount)
            net += sum(float(t.amount) for t in transfers if t.to_channel_id == channel.id)
            net -= sum(float(t.amount) for t in transfers if t.from_channel_id == channel.id)
            net -= sum(float(e.amount) for e in expenses if e.channel_id == channel.id)
            net -= sum(float(gc.amount) for gc in goal_contributions if gc.channel_id == channel.id)
            balances.append((channel, net))
        balances_by_period[period.id] = balances
        carry = {c.id: net for c, net in balances}

    return carry_in_by_period, balances_by_period


def _carry_in_for_period(db: Session, payout_period_id: int, user_id: int) -> dict[int, float]:
    """Each channel's ending balance from the payout period before this one (in
    display_order), so a month's leftover cash chains forward period to period.
    Single-period convenience wrapper around `_all_channel_balances` -- don't
    call this in a per-period loop, call `_all_channel_balances` once instead."""
    carry_in_by_period, _ = _all_channel_balances(db, user_id)
    return carry_in_by_period.get(payout_period_id, {})


def channel_balances(
    db: Session, payout_period_id: int, user_id: int
) -> list[tuple[models.Channel, float]]:
    """Single-period convenience wrapper around `_all_channel_balances` -- don't
    call this in a per-period loop (each call recomputes every period), call
    `_all_channel_balances` once instead and index into its result."""
    _, balances_by_period = _all_channel_balances(db, user_id)
    return balances_by_period.get(payout_period_id, [])


def _cashflow_warnings_from_balances(
    balances: list[tuple[models.Channel, float]],
    goals: list[models.Goal],
    payout_period_count: int,
    contributed: dict[int, float],
) -> dict[str, list[str]]:
    unfunded_channels = [c.name for c, net in balances if net < 0]
    underfunded_goals = [
        g.name
        for g in goals
        if contributed.get(g.id, 0.0) < goal_payout_amount(g, payout_period_count)
    ]
    return {"unfunded_channels": unfunded_channels, "underfunded_goals": underfunded_goals}


def cashflow_warnings(db: Session, payout_period_id: int, user_id: int) -> dict[str, list[str]]:
    balances = channel_balances(db, payout_period_id, user_id)
    goals = list_goals(db, user_id)
    payout_period_count = len(list_payout_periods(db, user_id))
    contributed = {
        c.goal_id: float(c.amount) for c in list_goal_contributions(db, payout_period_id, user_id)
    }
    return _cashflow_warnings_from_balances(balances, goals, payout_period_count, contributed)


def overview_warnings(db: Session, user_id: int) -> list[dict]:
    periods = list_payout_periods(db, user_id)
    _, balances_by_period = _all_channel_balances(db, user_id)
    goals = list_goals(db, user_id)
    payout_period_count = len(periods)

    entries = []
    for period in periods:
        contributed = {
            c.goal_id: float(c.amount) for c in list_goal_contributions(db, period.id, user_id)
        }
        warnings = _cashflow_warnings_from_balances(
            balances_by_period.get(period.id, []), goals, payout_period_count, contributed
        )
        if warnings["unfunded_channels"] or warnings["underfunded_goals"]:
            entries.append({"period": period, "warnings": warnings})
    return entries


# --- Payout cycles ----------------------------------------------------------


def list_payout_cycles(
    db: Session, payout_period_id: int, user_id: int
) -> list[models.PayoutCycle]:
    stmt = (
        select(models.PayoutCycle)
        .where(
            models.PayoutCycle.payout_period_id == payout_period_id,
            models.PayoutCycle.user_id == user_id,
        )
        .order_by(models.PayoutCycle.closed_at.desc())
    )
    return list(db.scalars(stmt))


def list_payout_cycle_balances(
    db: Session, payout_cycle_id: int
) -> list[models.PayoutCycleBalance]:
    stmt = (
        select(models.PayoutCycleBalance)
        .where(models.PayoutCycleBalance.payout_cycle_id == payout_cycle_id)
        .order_by(models.PayoutCycleBalance.id)
    )
    return list(db.scalars(stmt))


def _live_cycle_balances(
    db: Session, period: models.PayoutPeriod, user_id: int
) -> list[models.PayoutCycleBalance]:
    """The live template's current per-channel breakdown, in the exact shape
    a closed PayoutCycle's balances would be -- shared by close_payout_cycle
    (persisted) and the "viewing the live template" case in
    payout_cycle_history_page_data (transient, never db.add()ed, just reused
    for the template to render both cases identically). `net` includes
    carry-in from prior periods (the real running balance, same as
    channel_balances() everywhere else in the app); income/transfers_net/
    expenses_total describe only this period's own activity, and generally
    won't sum to `net` on their own -- see PayoutCycleBalance's docstring."""
    channels = list_channels(db, user_id)
    transfers = list_transfers(db, period.id, user_id)
    expenses = [
        e for e in list_expenses(db, user_id) if e.payout_period_id == period.id and e.active
    ]
    net_by_channel_id = {c.id: net for c, net in channel_balances(db, period.id, user_id)}

    balances = []
    for channel in channels:
        income = float(period.income_amount) if period.receiving_channel_id == channel.id else 0.0
        transfers_net = sum(
            float(t.amount) for t in transfers if t.to_channel_id == channel.id
        ) - sum(float(t.amount) for t in transfers if t.from_channel_id == channel.id)
        expenses_total = sum(float(e.amount) for e in expenses if e.channel_id == channel.id)
        net = net_by_channel_id.get(channel.id, 0.0)
        if income == 0 and transfers_net == 0 and expenses_total == 0 and net == 0:
            continue  # skip channels with no activity this cycle
        balances.append(
            models.PayoutCycleBalance(
                channel_name=channel.name,
                channel_color=channel.color,
                income=income,
                transfers_net=transfers_net,
                expenses_total=expenses_total,
                net=net,
            )
        )
    return balances


def close_payout_cycle(db: Session, payout_period_id: int, user_id: int) -> models.PayoutCycle:
    """Snapshot the given payout period's current channel balances into a
    new dated PayoutCycle -- explicit, user-triggered only (no auto-snapshot
    on some inferred date, since PayoutPeriod has no real calendar anchor).
    The live template (period, its transfers, its expenses) is left
    completely untouched -- closing a cycle is purely additive, so there's
    no data-loss risk and no "did I already close this month" bookkeeping
    to get wrong. See issue #84.

    Also increments each channel's persistent Channel.current_amount ("Actual"
    balance, see issue #162) by this period's own delta (net - carry_in), not
    the full carried net -- PayoutPeriod is a reused recurring template, not a
    dated one-off, so crediting the full net would double-count a channel's
    already-counted carry-in on every subsequent close."""
    period = _owned(db, models.PayoutPeriod, payout_period_id, user_id)
    if period is None:
        raise OwnershipError("Payout period not found.")

    live_balances = _live_cycle_balances(db, period, user_id)

    channels = list_channels(db, user_id)
    carry_in_by_period, balances_by_period = _all_channel_balances(db, user_id)
    carry_in = carry_in_by_period.get(payout_period_id, {})
    net_by_channel_id = {c.id: net for c, net in balances_by_period.get(payout_period_id, [])}

    cycle = models.PayoutCycle(
        user_id=user_id,
        payout_period_id=payout_period_id,
        label=period.label,
        income_amount=period.income_amount,
        receiving_channel_name=(
            period.receiving_channel.name if period.receiving_channel else None
        ),
    )
    db.add(cycle)
    db.flush()  # assigns cycle.id, needed for the balance rows below

    for balance in live_balances:
        balance.payout_cycle_id = cycle.id
        db.add(balance)

    for channel in channels:
        delta = net_by_channel_id.get(channel.id, 0.0) - carry_in.get(channel.id, 0.0)
        channel.current_amount = float(channel.current_amount) + delta

    db.commit()
    db.refresh(cycle)
    return cycle


def payout_cycle_history_page_data(
    db: Session, payout_period_id: int, user_id: int, cycle_id: int | None
) -> dict:
    period = _owned(db, models.PayoutPeriod, payout_period_id, user_id)
    if period is None:
        raise OwnershipError("Payout period not found.")

    cycles = list_payout_cycles(db, payout_period_id, user_id)
    selected_cycle = None
    if cycle_id is not None:
        selected_cycle = next((c for c in cycles if c.id == cycle_id), None)
        if selected_cycle is None:
            raise OwnershipError("Cycle not found.")

    balances = (
        list_payout_cycle_balances(db, selected_cycle.id)
        if selected_cycle is not None
        else _live_cycle_balances(db, period, user_id)
    )

    return {
        "period": period,
        "cycles": cycles,
        "selected_cycle": selected_cycle,
        "balances": balances,
    }


# --- Assets ---------------------------------------------------------------


def list_assets(db: Session, user_id: int) -> list[models.Asset]:
    stmt = select(models.Asset).where(models.Asset.user_id == user_id).order_by(models.Asset.id)
    return list(db.scalars(stmt))


def create_asset(db: Session, data: schemas.AssetCreate, user_id: int | None) -> models.Asset:
    _require_owned(db, models.Channel, data.channel_id, user_id, "Channel")
    asset = models.Asset(**data.model_dump(), user_id=user_id)
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def update_asset(
    db: Session, asset_id: int, data: schemas.AssetUpdate, user_id: int
) -> models.Asset | None:
    _require_owned(db, models.Channel, data.channel_id, user_id, "Channel")
    asset = _owned(db, models.Asset, asset_id, user_id)
    if asset is not None:
        asset.name = data.name
        asset.amount = data.amount
        asset.channel_id = data.channel_id
        db.commit()
        db.refresh(asset)
    return asset


def delete_asset(db: Session, asset_id: int, user_id: int) -> None:
    _delete_owned(db, models.Asset, asset_id, user_id)


def assets_page_data(db: Session, user_id: int) -> dict:
    assets = list_assets(db, user_id)
    return {
        "assets": assets,
        "total_assets": sum(float(a.amount) for a in assets),
        "channels": list_channels(db, user_id),
        "show_nudge": needs_nudge(db, user_id, "assets", is_empty=not assets),
    }


# --- Goals -----------------------------------------------------------------


def list_goals(db: Session, user_id: int | None) -> list[models.Goal]:
    stmt = select(models.Goal).where(models.Goal.user_id == user_id).order_by(models.Goal.id)
    return list(db.scalars(stmt))


def create_goal(db: Session, data: schemas.GoalCreate, user_id: int | None) -> models.Goal:
    _require_owned(db, models.Channel, data.channel_id, user_id, "Channel")
    goal = models.Goal(**data.model_dump(), user_id=user_id)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def update_goal(
    db: Session, goal_id: int, data: schemas.GoalUpdate, user_id: int
) -> models.Goal | None:
    _require_owned(db, models.Channel, data.channel_id, user_id, "Channel")
    goal = _owned(db, models.Goal, goal_id, user_id)
    if goal is not None:
        goal.name = data.name
        goal.target = data.target
        goal.months = data.months
        goal.channel_id = data.channel_id
        goal.round_up_to_hundred = data.round_up_to_hundred
        db.commit()
        db.refresh(goal)
    return goal


def list_goal_placements(
    db: Session, payout_period_id: int, user_id: int
) -> list[models.GoalPlacement]:
    stmt = select(models.GoalPlacement).where(
        models.GoalPlacement.payout_period_id == payout_period_id,
        models.GoalPlacement.user_id == user_id,
    )
    return list(db.scalars(stmt))


def place_goal(
    db: Session, payout_period_id: int, goal_id: int, x: float, y: float, user_id: int
) -> models.GoalPlacement:
    _require_owned(db, models.PayoutPeriod, payout_period_id, user_id, "Payout period")
    _require_owned(db, models.Goal, goal_id, user_id, "Goal")
    placement = db.scalar(
        select(models.GoalPlacement).where(
            models.GoalPlacement.payout_period_id == payout_period_id,
            models.GoalPlacement.goal_id == goal_id,
            models.GoalPlacement.user_id == user_id,
        )
    )
    if placement is None:
        placement = models.GoalPlacement(
            payout_period_id=payout_period_id, goal_id=goal_id, x=x, y=y, user_id=user_id
        )
        db.add(placement)
    else:
        placement.x = x
        placement.y = y
    db.commit()
    db.refresh(placement)
    return placement


def remove_goal_placement(db: Session, payout_period_id: int, goal_id: int, user_id: int) -> None:
    placement = db.scalar(
        select(models.GoalPlacement).where(
            models.GoalPlacement.payout_period_id == payout_period_id,
            models.GoalPlacement.goal_id == goal_id,
            models.GoalPlacement.user_id == user_id,
        )
    )
    if placement is not None:
        db.delete(placement)
        db.commit()


def delete_goal(db: Session, goal_id: int, user_id: int) -> None:
    goal = _owned(db, models.Goal, goal_id, user_id)
    if goal is not None:
        db.query(models.GoalPlacement).filter_by(goal_id=goal_id, user_id=user_id).delete()
        db.query(models.GoalContribution).filter_by(goal_id=goal_id, user_id=user_id).delete()
        db.delete(goal)
        db.commit()


def goal_progress(goal: models.Goal) -> dict:
    remaining = max(float(goal.target) - float(goal.allocated), 0.0)
    pct = min(float(goal.allocated) / float(goal.target), 1.0) * 100 if goal.target else 0.0
    monthly_needed = float(goal.target) / goal.months if goal.months else 0.0
    return {"pct": pct, "monthly_needed": monthly_needed, "remaining": remaining}


def goal_payout_amount(goal: models.Goal, payout_period_count: int) -> float:
    monthly_needed = float(goal.target) / goal.months if goal.months else 0.0
    per_payout = monthly_needed / payout_period_count if payout_period_count else monthly_needed
    if goal.round_up_to_hundred:
        per_payout = math.ceil(per_payout / 100) * 100
    return per_payout


def goals_page_data(db: Session, user_id: int) -> dict:
    payout_period_count = len(list_payout_periods(db, user_id))
    goals = list_goals(db, user_id)
    return {
        "goals": [
            {
                "goal": g,
                **goal_progress(g),
                "per_payout": goal_payout_amount(g, payout_period_count),
            }
            for g in goals
        ],
        "channels": list_channels(db, user_id),
        "show_nudge": needs_nudge(db, user_id, "goals", is_empty=not goals),
    }


# --- Credit lines -----------------------------------------------------------


def list_credit_lines(db: Session, user_id: int) -> list[models.CreditLine]:
    stmt = (
        select(models.CreditLine)
        .where(models.CreditLine.user_id == user_id)
        .order_by(models.CreditLine.id)
    )
    return list(db.scalars(stmt))


def create_credit_line(
    db: Session, data: schemas.CreditLineCreate, user_id: int | None
) -> models.CreditLine:
    _require_owned(db, models.Channel, data.channel_id, user_id, "Channel")
    credit_line = models.CreditLine(**data.model_dump(), user_id=user_id)
    db.add(credit_line)
    db.commit()
    db.refresh(credit_line)
    return credit_line


def update_credit_line(
    db: Session, credit_line_id: int, data: schemas.CreditLineUpdate, user_id: int
) -> models.CreditLine | None:
    _require_owned(db, models.Channel, data.channel_id, user_id, "Channel")
    credit_line = _owned(db, models.CreditLine, credit_line_id, user_id)
    if credit_line is not None:
        credit_line.name = data.name
        credit_line.limit = data.limit
        credit_line.used = data.used
        credit_line.channel_id = data.channel_id
        db.commit()
        db.refresh(credit_line)
    return credit_line


def delete_credit_line(db: Session, credit_line_id: int, user_id: int) -> None:
    _delete_owned(db, models.CreditLine, credit_line_id, user_id)


def credit_utilization(credit_line: models.CreditLine) -> dict:
    pct = (float(credit_line.used) / float(credit_line.limit) * 100) if credit_line.limit else 0.0
    level = "red" if pct >= 100 else "amber" if pct >= 80 else "ok"
    return {"pct": pct, "level": level}


def credit_page_data(db: Session, user_id: int) -> dict:
    lines = list_credit_lines(db, user_id)
    return {
        "credit_lines": [{"line": c, **credit_utilization(c)} for c in lines],
        "channels": list_channels(db, user_id),
        "show_nudge": needs_nudge(db, user_id, "credit", is_empty=not lines),
    }


# --- Composed view data -----------------------------------------------------


def next_payout_period(db: Session, user_id: int) -> models.PayoutPeriod | None:
    """The soonest-upcoming payout period. Periods have no calendar date (just a
    user-facing label like "15th" and a display_order for cycling through them),
    so "next" is the first one by display_order — the same ordering used
    everywhere else periods are listed."""
    periods = list_payout_periods(db, user_id)
    return periods[0] if periods else None


def overview_page_data(db: Session, user_id: int) -> dict:
    assets = list_assets(db, user_id)
    credit_lines = list_credit_lines(db, user_id)
    total_assets = sum(float(a.amount) for a in assets)
    total_liabilities = sum(float(c.used) for c in credit_lines)
    period = next_payout_period(db, user_id)
    upcoming_expenses = (
        sorted(
            (
                e
                for e in list_expenses(db, user_id)
                if e.payout_period_id == period.id and e.active and not e.paid
            ),
            key=lambda e: (e.due_day is None, e.due_day),
        )
        if period is not None
        else []
    )
    return {
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": total_assets - total_liabilities,
        "goals": [{"goal": g, **goal_progress(g)} for g in list_goals(db, user_id)],
        "credit_lines": [{"line": c, **credit_utilization(c)} for c in credit_lines],
        "next_payout_period": period,
        "upcoming_expenses": upcoming_expenses,
        "upcoming_expenses_total": sum(float(e.amount) for e in upcoming_expenses),
        "period_warnings": overview_warnings(db, user_id),
    }


def channel_presets_by_group() -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = {}
    for preset in CHANNEL_PRESETS:
        groups.setdefault(preset["group"], []).append(preset)
    return groups


def _most_recent_monthly_occurrence(day: int, today: date) -> date:
    """The most recent calendar date <= today whose day-of-month is `day`,
    clamped to the last day of a shorter month (e.g. day=31 in April -> 30)."""
    year, month = today.year, today.month
    clamped = min(day, calendar.monthrange(year, month)[1])
    candidate = date(year, month, clamped)
    if candidate <= today:
        return candidate
    month -= 1
    if month == 0:
        month, year = 12, year - 1
    clamped = min(day, calendar.monthrange(year, month)[1])
    return date(year, month, clamped)


def overdue_payout_period_ids(
    db: Session, user_id: int, payout_periods: list[models.PayoutPeriod]
) -> set[int]:
    """Periods whose payout_day has passed this month with no PayoutCycle
    closed since -- a UI hint only (see #134), not enforcement. Closing a
    cycle clears the hint until next month's payday passes again. Periods
    with no payout_day set never show it -- that field is optional."""
    candidates = [p for p in payout_periods if p.payout_day is not None]
    if not candidates:
        return set()

    today = datetime.now(UTC).date()
    # dict(Result.tuples()) is ambiguous -- Result exposes .keys(), which
    # makes dict() try mapping-style construction (subscripting the Result
    # itself) instead of treating it as an iterable of pairs. .all() first
    # materializes a plain list of tuples, sidestepping that.
    latest_closed_by_period: dict[int, datetime] = dict(
        db.execute(
            select(models.PayoutCycle.payout_period_id, func.max(models.PayoutCycle.closed_at))
            .where(models.PayoutCycle.user_id == user_id)
            .group_by(models.PayoutCycle.payout_period_id)
        )
        .tuples()
        .all()
    )

    overdue = set()
    for period in candidates:
        assert period.payout_day is not None  # narrowed by the `candidates` filter above
        occurrence = _most_recent_monthly_occurrence(period.payout_day, today)
        latest_closed = latest_closed_by_period.get(period.id)
        if latest_closed is not None and latest_closed.date() >= occurrence:
            continue
        overdue.add(period.id)
    return overdue


def expenses_page_data(db: Session, user_id: int, q: str | None = None) -> dict:
    channels = list_channels(db, user_id)
    payout_periods = list_payout_periods(db, user_id)
    user = get_user(db, user_id)
    onboarding_step = (
        compute_onboarding_step(user, channels, payout_periods, _has_any_expenses(db, user_id))
        if user is not None
        else None
    )
    # Sensible defaults for the onboarding steps' pre-opened add-rows --
    # channels/periods have no created_at, so "latest" is just highest id.
    onboarding_latest_channel = max(channels, key=lambda c: c.id) if channels else None
    onboarding_latest_payout_period = (
        max(payout_periods, key=lambda p: p.id) if payout_periods else None
    )
    # Step 3's default expense channel: whichever channel the latest payout
    # period actually deposits into (it already "has the money"), falling
    # back to the latest channel if that period has no receiving channel set.
    onboarding_default_expense_channel_id = None
    if onboarding_latest_payout_period is not None:
        onboarding_default_expense_channel_id = (
            onboarding_latest_payout_period.receiving_channel_id
            or (onboarding_latest_channel.id if onboarding_latest_channel else None)
        )
    return {
        "channels": channels,
        "channel_types": CHANNEL_TYPES,
        "channel_preset_groups": channel_presets_by_group(),
        "payout_periods": payout_periods,
        "overdue_payout_period_ids": overdue_payout_period_ids(db, user_id, payout_periods),
        "expenses": list_expenses(db, user_id, q),
        "q": q or "",
        "onboarding_step": onboarding_step,
        "onboarding_latest_channel": onboarding_latest_channel,
        "onboarding_latest_payout_period": onboarding_latest_payout_period,
        "onboarding_default_expense_channel_id": onboarding_default_expense_channel_id,
    }


def _order_transfers(
    channels: list[models.Channel], transfers: list[models.Transfer]
) -> list[models.Transfer]:
    """Order transfers by which should be done first: a transfer out of a
    channel can't happen (in a real sense) until any transfer funding that
    channel has already landed, so sort by each transfer's from_channel's
    topological depth in the transfer graph (Kahn's algorithm), tie-broken
    by id for stability."""
    graph: dict[int, set[int]] = {c.id: set() for c in channels}
    indegree: dict[int, int] = dict.fromkeys(graph, 0)
    for t in transfers:
        if t.to_channel_id not in graph[t.from_channel_id]:
            graph[t.from_channel_id].add(t.to_channel_id)
            indegree[t.to_channel_id] += 1

    depth: dict[int, int] = {}
    ready = sorted(cid for cid, d in indegree.items() if d == 0)
    while ready:
        cid = ready.pop(0)
        depth[cid] = len(depth)
        for nxt in sorted(graph[cid]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
        ready.sort()
    for cid in graph:
        if cid not in depth:
            depth[cid] = len(depth)

    return sorted(transfers, key=lambda t: (depth[t.from_channel_id], t.id))


def _format_amount(amount: float, symbol: str) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}{symbol}{abs(amount):,.2f}"


def _transfer_note(
    to_channel_id: int,
    expenses: list[models.Expense],
    goals: list[models.Goal],
    payout_period_count: int,
    symbol: str,
) -> str:
    parts = [
        f"{e.name} ({_format_amount(float(e.amount), symbol)})"
        for e in expenses
        if e.channel_id == to_channel_id
    ]
    parts += [
        f"{g.name} goal ({_format_amount(goal_payout_amount(g, payout_period_count), symbol)})"
        for g in goals
        if g.channel_id == to_channel_id
    ]
    if not parts:
        return "No expenses or goals tagged to this channel for this payout yet."
    return "Covers: " + ", ".join(parts)


def cashflow_page_data(db: Session, user_id: int) -> dict:
    currency_symbol = currency_symbol_for(get_user(db, user_id))
    payout_periods = list_payout_periods(db, user_id)
    channels = list_channels(db, user_id)
    goals = list_goals(db, user_id)
    # Same exclusion as _all_channel_balances -- keeps the canvas's per-
    # channel expense breakdown consistent with the balances it's shown
    # alongside (a paused expense doesn't visually deduct here either).
    all_expenses = [e for e in list_expenses(db, user_id) if e.active]
    payout_period_count = len(payout_periods)
    goal_entries: list[dict[str, Any]] = [
        {"goal": g, "per_payout": goal_payout_amount(g, payout_period_count)} for g in goals
    ]
    # Computed once for the whole request (O(n) in the number of payout
    # periods) rather than once per period -- see `_all_channel_balances`.
    carry_in_by_period, balances_by_period = _all_channel_balances(db, user_id)
    payout_data = []
    for period in payout_periods:
        expenses = [e for e in all_expenses if e.payout_period_id == period.id]
        transfers = _order_transfers(channels, list_transfers(db, period.id, user_id))
        goal_contributions = list_goal_contributions(db, period.id, user_id)
        balances = balances_by_period.get(period.id, [])
        # Matches `cashflow_warnings`'s own (non-summing, last-write-wins)
        # dict construction so the embedded "warnings" below stay identical
        # to a direct `cashflow_warnings(db, period.id, user_id)` call.
        contributed_for_warnings = {c.goal_id: float(c.amount) for c in goal_contributions}
        contributed_by_goal: dict[int, float] = {}
        for gc in goal_contributions:
            contributed_by_goal[gc.goal_id] = contributed_by_goal.get(gc.goal_id, 0.0) + float(
                gc.amount
            )

        channel_placements = list_channel_placements(db, period.id, user_id)
        goal_placements = list_goal_placements(db, period.id, user_id)
        position_by_channel = {p.channel_id: (p.x, p.y) for p in channel_placements}
        position_by_goal = {p.goal_id: (p.x, p.y) for p in goal_placements}
        placed_channel_ids = set(position_by_channel)
        placed_goal_ids = set(position_by_goal)

        # One read-only "Expenses" node per channel, aggregating that
        # channel's expenses this period. Positioned client-side, directly
        # below whatever the channel's actual rendered height turns out to
        # be (see redrawCanvas) rather than a fixed server-guessed offset --
        # channel node height varies with content (carry-in note, etc.), so
        # a fixed offset can't guarantee no overlap. items_json also lets a
        # freshly toolbox-placed channel (not yet saved, so not in
        # expenses_by_channel's server-rendered form) get its own expense
        # node synthesized client-side in placeNode().
        expenses_by_channel: dict[int, dict[str, Any]] = {}
        for expense in expenses:
            entry = expenses_by_channel.setdefault(expense.channel_id, {"total": 0.0, "items": []})
            entry["total"] += float(expense.amount)
            entry["items"].append(expense)
        for entry in expenses_by_channel.values():
            entry["items_json"] = json.dumps(
                [{"name": item.name, "amount": float(item.amount)} for item in entry["items"]]
            )

        payout_data.append(
            {
                "period": period,
                "transfers": [
                    {
                        "transfer": t,
                        "note": _transfer_note(
                            t.to_channel_id,
                            expenses,
                            goals,
                            payout_period_count,
                            currency_symbol,
                        ),
                    }
                    for t in transfers
                ],
                "goal_contributions": goal_contributions,
                "balances": balances,
                "balance_by_channel": {c.id: net for c, net in balances},
                "contributed_by_goal": contributed_by_goal,
                "carry_in": carry_in_by_period.get(period.id, {}),
                "warnings": _cashflow_warnings_from_balances(
                    balances, goals, payout_period_count, contributed_for_warnings
                ),
                "expenses_by_channel": expenses_by_channel,
                "position_by_channel": position_by_channel,
                "position_by_goal": position_by_goal,
                "placed_channels": [c for c in channels if c.id in placed_channel_ids],
                "placed_goals": [e for e in goal_entries if e["goal"].id in placed_goal_ids],
                "available_channels": [c for c in channels if c.id not in placed_channel_ids],
                "available_goals": [e for e in goal_entries if e["goal"].id not in placed_goal_ids],
            }
        )
    return {
        "channels": channels,
        "goals": goal_entries,
        "payout_data": payout_data,
        # Page-level, not per-period -- Cash Flow shows one section per
        # payout period, but the nudge is about the section/feature itself
        # (Transfers), so "empty" means no transfers anywhere yet, not
        # "this one period has none".
        "show_nudge": needs_nudge(
            db, user_id, "cashflow", is_empty=not _has_any_transfers(db, user_id)
        ),
    }


# --- Admin --------------------------------------------------------------------
# See issue #65. Gated by require_admin (app/auth.py), not a per-crud-call
# check -- these functions operate across *all* users deliberately (an
# admin's whole job here is cross-user visibility/hygiene), unlike every
# other crud.py function which scopes to one user_id.

# Same table set app/manage_users.py's assign-orphans CLI command handles --
# it now imports this constant rather than keeping its own separate copy,
# so the two can't drift apart.
ORPHANABLE_MODELS: tuple[type[Any], ...] = (
    models.Channel,
    models.PayoutPeriod,
    models.Expense,
    models.Transfer,
    models.Goal,
    models.CreditLine,
    models.Asset,
    models.PayoutCycle,
)


def mask_email(email: str) -> str:
    """Partially obscure an email for display in the admin dashboard --
    keeps the first couple of local-part characters and the full domain
    (still useful for an admin to recognize/distinguish accounts) but
    replaces the rest of the local part with asterisks."""
    local, _, domain = email.partition("@")
    if not domain:
        return "*" * len(email)
    visible = local[:2]
    return f"{visible}{'*' * max(1, len(local) - len(visible))}@{domain}"


def list_users_for_admin(db: Session) -> list[dict[str, Any]]:
    users = list(db.scalars(select(models.User).order_by(models.User.created_at.desc())))
    rows = []
    for user in users:
        providers = sorted(
            {
                identity.provider
                for identity in db.scalars(
                    select(models.OAuthIdentity).where(models.OAuthIdentity.user_id == user.id)
                )
            }
        )
        channel_count = (
            db.scalar(
                select(func.count())
                .select_from(models.Channel)
                .where(models.Channel.user_id == user.id)
            )
            or 0
        )
        expense_count = (
            db.scalar(
                select(func.count())
                .select_from(models.Expense)
                .where(models.Expense.user_id == user.id)
            )
            or 0
        )
        rows.append(
            {
                "user": user,
                "masked_email": mask_email(user.email),
                "providers": providers,
                "channel_count": channel_count,
                "expense_count": expense_count,
            }
        )
    return rows


def delete_user_and_data(db: Session, user_id: int) -> None:
    """Delete a user and every row they own, in FK-dependency order (children
    before parents -- there's no ON DELETE CASCADE at the DB level, FKs
    default to RESTRICT, so deleting parents first would fail). There was
    previously no way to do this at all, CLI or otherwise -- see issue #65."""
    cycle_ids = list(
        db.scalars(select(models.PayoutCycle.id).where(models.PayoutCycle.user_id == user_id))
    )
    if cycle_ids:
        db.query(models.PayoutCycleBalance).filter(
            models.PayoutCycleBalance.payout_cycle_id.in_(cycle_ids)
        ).delete(synchronize_session=False)
    for model in (
        models.GoalContribution,
        models.ChannelPlacement,
        models.GoalPlacement,
        models.Transfer,
        models.Expense,
        models.PayoutCycle,
        models.Goal,
        models.CreditLine,
        models.Asset,
        models.PayoutPeriod,
        models.Channel,
        models.OAuthIdentity,
    ):
        db.query(model).filter_by(user_id=user_id).delete()
    db.query(models.User).filter_by(id=user_id).delete()
    db.commit()


def list_signup_keys(db: Session) -> list[models.SignupKey]:
    return list(db.scalars(select(models.SignupKey).order_by(models.SignupKey.created_at.desc())))


def signup_key_status(key: models.SignupKey) -> Literal["active", "exhausted", "expired"]:
    if key.use_count >= key.max_uses:
        return "exhausted"
    expires_at = key.expires_at
    if expires_at is not None:
        if expires_at.tzinfo is None:
            # SQLite (used in tests) doesn't persist tzinfo on DateTime(timezone=True) columns.
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            return "expired"
    return "active"


def revoke_signup_key(db: Session, key_id: int) -> None:
    db.query(models.SignupKey).filter_by(id=key_id).delete()
    db.commit()


def orphan_counts(db: Session) -> list[tuple[str, int]]:
    return [
        (
            model.__tablename__,
            db.scalar(select(func.count()).select_from(model).where(model.user_id.is_(None))) or 0,
        )
        for model in ORPHANABLE_MODELS
    ]


def assign_orphans_for_table(db: Session, table_name: str, target_user_id: int) -> int:
    model = next((m for m in ORPHANABLE_MODELS if m.__tablename__ == table_name), None)
    if model is None:
        raise ValueError(f"Unknown orphanable table: {table_name!r}")
    rows = db.scalars(select(model).where(model.user_id.is_(None))).all()
    for row in rows:
        row.user_id = target_user_id
    db.commit()
    return len(rows)


def admin_page_data(db: Session) -> dict[str, Any]:
    total_users = db.scalar(select(func.count()).select_from(models.User)) or 0
    week_ago = datetime.now(UTC) - timedelta(days=7)
    recent_signups = (
        db.scalar(
            select(func.count()).select_from(models.User).where(models.User.created_at >= week_ago)
        )
        or 0
    )
    signup_keys = list_signup_keys(db)
    counts = orphan_counts(db)
    return {
        "users": list_users_for_admin(db),
        "signup_keys": [(key, signup_key_status(key)) for key in signup_keys],
        "orphan_counts": counts,
        "stats": {
            "total_users": total_users,
            "recent_signups": recent_signups,
            "active_keys": sum(1 for k in signup_keys if signup_key_status(k) == "active"),
            "orphan_total": sum(count for _, count in counts),
        },
    }
