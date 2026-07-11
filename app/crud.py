import math
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import models, schemas

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


class ChannelInUseError(Exception):
    """Raised when deleting a channel that is still referenced elsewhere."""


class InvalidFundingSourceError(Exception):
    """Raised when a channel's funding source would create a self-reference."""


class OwnershipError(Exception):
    """Raised when a referenced row doesn't belong to the acting user."""


def _owned(db: Session, model: type[Any], id_: int, user_id: int) -> Any:
    return db.scalar(select(model).where(model.id == id_, model.user_id == user_id))


def _require_owned(
    db: Session, model: type[Any], id_: int | None, user_id: int, label: str
) -> None:
    if id_ is not None and _owned(db, model, id_, user_id) is None:
        raise OwnershipError(f"{label} not found.")


# --- Users --------------------------------------------------------------------


def get_user(db: Session, user_id: int) -> models.User | None:
    return db.get(models.User, user_id)


def get_user_by_email(db: Session, email: str) -> models.User | None:
    return db.scalar(select(models.User).where(models.User.email == email))


def create_user(db: Session, email: str, hashed_password: str) -> models.User:
    user = models.User(email=email, hashed_password=hashed_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# --- Channels ---------------------------------------------------------------


def list_channels(db: Session, user_id: int) -> list[models.Channel]:
    stmt = select(models.Channel).where(models.Channel.user_id == user_id)
    return list(db.scalars(stmt.order_by(models.Channel.name)))


def create_channel(db: Session, data: schemas.ChannelCreate, user_id: int) -> models.Channel:
    _require_owned(db, models.Channel, data.funding_source_channel_id, user_id, "Funding source")
    channel = models.Channel(
        name=data.name,
        color=data.color,
        channel_type=data.channel_type,
        funding_source_channel_id=data.funding_source_channel_id,
        user_id=user_id,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def update_channel(
    db: Session, channel_id: int, data: schemas.ChannelUpdate, user_id: int
) -> models.Channel | None:
    if data.funding_source_channel_id == channel_id:
        raise InvalidFundingSourceError("A channel can't fund itself.")
    _require_owned(db, models.Channel, data.funding_source_channel_id, user_id, "Funding source")
    channel = _owned(db, models.Channel, channel_id, user_id)
    if channel is not None:
        channel.name = data.name
        channel.color = data.color
        channel.channel_type = data.channel_type
        channel.funding_source_channel_id = data.funding_source_channel_id
        db.commit()
        db.refresh(channel)
    return channel


def update_channel_position(
    db: Session, channel_id: int, x: float, y: float, user_id: int
) -> models.Channel | None:
    channel = _owned(db, models.Channel, channel_id, user_id)
    if channel is not None:
        channel.canvas_x = x
        channel.canvas_y = y
        db.commit()
    return channel


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
        or db.query(models.Channel)
        .filter_by(funding_source_channel_id=channel_id, user_id=user_id)
        .first()
    )
    if in_use is not None:
        raise ChannelInUseError(
            "This channel is still used by a payout period, expense, transfer, "
            "goal contribution, or another channel's funding source, and can't be "
            "deleted until those are removed or reassigned."
        )

    db.delete(channel)
    db.commit()


# --- Payout periods ----------------------------------------------------------


def list_payout_periods(db: Session, user_id: int) -> list[models.PayoutPeriod]:
    stmt = (
        select(models.PayoutPeriod)
        .where(models.PayoutPeriod.user_id == user_id)
        .order_by(models.PayoutPeriod.display_order)
    )
    return list(db.scalars(stmt))


def create_payout_period(
    db: Session, data: schemas.PayoutPeriodCreate, user_id: int
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
        db.commit()
        db.refresh(period)
    return period


def delete_payout_period(db: Session, payout_period_id: int, user_id: int) -> None:
    period = _owned(db, models.PayoutPeriod, payout_period_id, user_id)
    if period is not None:
        db.delete(period)
        db.commit()


# --- Expenses -----------------------------------------------------------------


def list_expenses(db: Session, user_id: int) -> list[models.Expense]:
    stmt = (
        select(models.Expense).where(models.Expense.user_id == user_id).order_by(models.Expense.id)
    )
    return list(db.scalars(stmt))


def create_expense(db: Session, data: schemas.ExpenseCreate, user_id: int) -> models.Expense:
    _require_owned(db, models.PayoutPeriod, data.payout_period_id, user_id, "Payout period")
    _require_owned(db, models.Channel, data.channel_id, user_id, "Channel")
    expense = models.Expense(**data.model_dump(), user_id=user_id)
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


def delete_expense(db: Session, expense_id: int, user_id: int) -> None:
    expense = _owned(db, models.Expense, expense_id, user_id)
    if expense is not None:
        db.delete(expense)
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
    transfer = _owned(db, models.Transfer, transfer_id, user_id)
    if transfer is not None:
        db.delete(transfer)
        db.commit()


# --- Goal contributions -------------------------------------------------------


def list_goal_contributions(
    db: Session, payout_period_id: int, user_id: int
) -> list[models.GoalContribution]:
    stmt = select(models.GoalContribution).where(
        models.GoalContribution.payout_period_id == payout_period_id,
        models.GoalContribution.user_id == user_id,
    )
    return list(db.scalars(stmt))


def _recompute_goal_allocated(db: Session, goal_id: int, user_id: int) -> None:
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


# --- Channel balances -----------------------------------------------------------


def _carry_in_for_period(db: Session, payout_period_id: int, user_id: int) -> dict[int, float]:
    """Each channel's ending balance from the payout period before this one (in
    display_order), so a month's leftover cash chains forward period to period."""
    carry: dict[int, float] = {}
    for period in list_payout_periods(db, user_id):
        if period.id == payout_period_id:
            break
        carry = {c.id: net for c, net in channel_balances(db, period.id, user_id)}
    return carry


def channel_balances(
    db: Session, payout_period_id: int, user_id: int
) -> list[tuple[models.Channel, float]]:
    carry_in = _carry_in_for_period(db, payout_period_id, user_id)
    payout_period = _owned(db, models.PayoutPeriod, payout_period_id, user_id)
    channels = list_channels(db, user_id)
    expenses = [e for e in list_expenses(db, user_id) if e.payout_period_id == payout_period_id]
    transfers = list_transfers(db, payout_period_id, user_id)
    goal_contributions = list_goal_contributions(db, payout_period_id, user_id)

    balances = []
    for channel in channels:
        net = carry_in.get(channel.id, 0.0)
        if payout_period is not None and payout_period.receiving_channel_id == channel.id:
            net += float(payout_period.income_amount)
        net += sum(float(t.amount) for t in transfers if t.to_channel_id == channel.id)
        net -= sum(float(t.amount) for t in transfers if t.from_channel_id == channel.id)
        net -= sum(float(e.amount) for e in expenses if e.channel_id == channel.id)
        net -= sum(float(gc.amount) for gc in goal_contributions if gc.channel_id == channel.id)
        balances.append((channel, net))
    return balances


def generate_transfers(db: Session, payout_period_id: int, user_id: int) -> dict[str, list[str]]:
    """Delete all transfers for this payout period and regenerate them from each
    channel's configured funding source. Each channel's required inflow is its
    own expense shortfall plus whatever it must forward to every channel that
    names it as a funding source (a pure pass-through channel with no expenses
    of its own can still need an inbound transfer this way), less any balance
    carried in from the prior payout period. Also fills in a suggested
    GoalContribution (at goal_payout_amount) for any goal with a funding channel
    that doesn't already have one for this period. Returns the names of channels
    with an unmet shortfall and no funding source ("unfunded"), and channels
    caught in a circular funding loop ("circular")."""
    for transfer in list_transfers(db, payout_period_id, user_id):
        db.delete(transfer)

    payout_period = _owned(db, models.PayoutPeriod, payout_period_id, user_id)
    channels = list_channels(db, user_id)
    expenses = [e for e in list_expenses(db, user_id) if e.payout_period_id == payout_period_id]
    goals = list_goals(db, user_id)
    payout_period_count = len(list_payout_periods(db, user_id))
    carry_in = _carry_in_for_period(db, payout_period_id, user_id)

    contributions_by_goal = {
        c.goal_id: float(c.amount) for c in list_goal_contributions(db, payout_period_id, user_id)
    }
    changed_goal_ids: set[int] = set()
    for g in goals:
        if g.channel_id is not None and g.id not in contributions_by_goal:
            amount = goal_payout_amount(g, payout_period_count)
            db.add(
                models.GoalContribution(
                    goal_id=g.id,
                    channel_id=g.channel_id,
                    payout_period_id=payout_period_id,
                    amount=amount,
                    user_id=user_id,
                )
            )
            contributions_by_goal[g.id] = amount
            changed_goal_ids.add(g.id)

    children: dict[int, list[models.Channel]] = {}
    for c in channels:
        if c.funding_source_channel_id is not None:
            children.setdefault(c.funding_source_channel_id, []).append(c)

    def own_shortfall(channel: models.Channel) -> float:
        expense_total = sum(float(e.amount) for e in expenses if e.channel_id == channel.id)
        goal_total = sum(
            contributions_by_goal.get(g.id, 0.0) for g in goals if g.channel_id == channel.id
        )
        income = carry_in.get(channel.id, 0.0) + (
            float(payout_period.income_amount)
            if payout_period is not None and payout_period.receiving_channel_id == channel.id
            else 0.0
        )
        return max(expense_total + goal_total - income, 0.0)

    required: dict[int, float] = {}
    circular: set[int] = set()

    def required_inflow(channel: models.Channel, visiting: set[int]) -> float:
        if channel.id in required:
            return required[channel.id]
        if channel.id in visiting:
            circular.update(visiting)
            return 0.0
        visiting.add(channel.id)
        total = own_shortfall(channel) + sum(
            required_inflow(child, visiting) for child in children.get(channel.id, [])
        )
        visiting.discard(channel.id)
        required[channel.id] = total
        return total

    unfunded = []
    for channel in channels:
        if own_shortfall(channel) > 0 and channel.funding_source_channel_id is None:
            unfunded.append(channel.name)
        if channel.funding_source_channel_id is None:
            continue
        amount = required_inflow(channel, set())
        if amount <= 0 or channel.id in circular:
            continue
        db.add(
            models.Transfer(
                payout_period_id=payout_period_id,
                from_channel_id=channel.funding_source_channel_id,
                to_channel_id=channel.id,
                amount=amount,
                user_id=user_id,
            )
        )
    db.commit()
    for goal_id in changed_goal_ids:
        _recompute_goal_allocated(db, goal_id, user_id)
    return {
        "unfunded": unfunded,
        "circular": [c.name for c in channels if c.id in circular],
    }


def cashflow_warnings(db: Session, payout_period_id: int, user_id: int) -> dict[str, list[str]]:
    unfunded_channels = [
        c.name for c, net in channel_balances(db, payout_period_id, user_id) if net < 0
    ]

    goals = list_goals(db, user_id)
    payout_period_count = len(list_payout_periods(db, user_id))
    contributed = {
        c.goal_id: float(c.amount) for c in list_goal_contributions(db, payout_period_id, user_id)
    }
    underfunded_goals = [
        g.name
        for g in goals
        if contributed.get(g.id, 0.0) < goal_payout_amount(g, payout_period_count)
    ]
    return {"unfunded_channels": unfunded_channels, "underfunded_goals": underfunded_goals}


# --- Assets ---------------------------------------------------------------


def list_assets(db: Session, user_id: int) -> list[models.Asset]:
    stmt = select(models.Asset).where(models.Asset.user_id == user_id).order_by(models.Asset.id)
    return list(db.scalars(stmt))


def create_asset(db: Session, data: schemas.AssetCreate, user_id: int) -> models.Asset:
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
    asset = _owned(db, models.Asset, asset_id, user_id)
    if asset is not None:
        db.delete(asset)
        db.commit()


def assets_page_data(db: Session, user_id: int) -> dict:
    assets = list_assets(db, user_id)
    return {
        "assets": assets,
        "total_assets": sum(float(a.amount) for a in assets),
        "channels": list_channels(db, user_id),
    }


# --- Goals -----------------------------------------------------------------


def list_goals(db: Session, user_id: int) -> list[models.Goal]:
    stmt = select(models.Goal).where(models.Goal.user_id == user_id).order_by(models.Goal.id)
    return list(db.scalars(stmt))


def create_goal(db: Session, data: schemas.GoalCreate, user_id: int) -> models.Goal:
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


def update_goal_position(
    db: Session, goal_id: int, x: float, y: float, user_id: int
) -> models.Goal | None:
    goal = _owned(db, models.Goal, goal_id, user_id)
    if goal is not None:
        goal.canvas_x = x
        goal.canvas_y = y
        db.commit()
    return goal


def delete_goal(db: Session, goal_id: int, user_id: int) -> None:
    goal = _owned(db, models.Goal, goal_id, user_id)
    if goal is not None:
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
    db: Session, data: schemas.CreditLineCreate, user_id: int
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
    credit_line = _owned(db, models.CreditLine, credit_line_id, user_id)
    if credit_line is not None:
        db.delete(credit_line)
        db.commit()


def credit_utilization(credit_line: models.CreditLine) -> dict:
    pct = (float(credit_line.used) / float(credit_line.limit) * 100) if credit_line.limit else 0.0
    level = "red" if pct >= 100 else "amber" if pct >= 80 else "ok"
    return {"pct": pct, "level": level}


def credit_page_data(db: Session, user_id: int) -> dict:
    lines = list_credit_lines(db, user_id)
    return {
        "credit_lines": [{"line": c, **credit_utilization(c)} for c in lines],
        "channels": list_channels(db, user_id),
    }


# --- Composed view data -----------------------------------------------------


def overview_page_data(db: Session, user_id: int) -> dict:
    assets = list_assets(db, user_id)
    credit_lines = list_credit_lines(db, user_id)
    total_assets = sum(float(a.amount) for a in assets)
    total_liabilities = sum(float(c.used) for c in credit_lines)
    return {
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": total_assets - total_liabilities,
        "goals": [{"goal": g, **goal_progress(g)} for g in list_goals(db, user_id)],
        "credit_lines": [{"line": c, **credit_utilization(c)} for c in credit_lines],
    }


def expenses_page_data(db: Session, user_id: int) -> dict:
    return {
        "channels": list_channels(db, user_id),
        "channel_types": CHANNEL_TYPES,
        "payout_periods": list_payout_periods(db, user_id),
        "expenses": list_expenses(db, user_id),
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


def _peso(amount: float) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}₱{abs(amount):,.2f}"


def _transfer_note(
    to_channel_id: int,
    expenses: list[models.Expense],
    goals: list[models.Goal],
    payout_period_count: int,
) -> str:
    parts = [
        f"{e.name} ({_peso(float(e.amount))})" for e in expenses if e.channel_id == to_channel_id
    ]
    parts += [
        f"{g.name} goal ({_peso(goal_payout_amount(g, payout_period_count))})"
        for g in goals
        if g.channel_id == to_channel_id
    ]
    if not parts:
        return "No expenses or goals tagged to this channel for this payout yet."
    return "Covers: " + ", ".join(parts)


def cashflow_page_data(db: Session, user_id: int) -> dict:
    payout_periods = list_payout_periods(db, user_id)
    channels = list_channels(db, user_id)
    goals = list_goals(db, user_id)
    all_expenses = list_expenses(db, user_id)
    payout_period_count = len(payout_periods)
    payout_data = []
    for period in payout_periods:
        expenses = [e for e in all_expenses if e.payout_period_id == period.id]
        transfers = _order_transfers(channels, list_transfers(db, period.id, user_id))
        payout_data.append(
            {
                "period": period,
                "transfers": [
                    {
                        "transfer": t,
                        "note": _transfer_note(
                            t.to_channel_id, expenses, goals, payout_period_count
                        ),
                    }
                    for t in transfers
                ],
                "goal_contributions": list_goal_contributions(db, period.id, user_id),
                "balances": channel_balances(db, period.id, user_id),
                "carry_in": _carry_in_for_period(db, period.id, user_id),
                "warnings": cashflow_warnings(db, period.id, user_id),
            }
        )
    return {"channels": channels, "goals": goals, "payout_data": payout_data}
