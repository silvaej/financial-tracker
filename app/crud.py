from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import models, schemas

# --- Channels ---------------------------------------------------------------


class ChannelInUseError(Exception):
    """Raised when deleting a channel that is still referenced elsewhere."""


class InvalidFundingSourceError(Exception):
    """Raised when a channel's funding source would create a self-reference."""


def list_channels(db: Session) -> list[models.Channel]:
    return list(db.scalars(select(models.Channel).order_by(models.Channel.name)))


def create_channel(db: Session, data: schemas.ChannelCreate) -> models.Channel:
    channel = models.Channel(
        name=data.name, color=data.color, funding_source_channel_id=data.funding_source_channel_id
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def update_channel(
    db: Session, channel_id: int, data: schemas.ChannelUpdate
) -> models.Channel | None:
    if data.funding_source_channel_id == channel_id:
        raise InvalidFundingSourceError("A channel can't fund itself.")
    channel = db.get(models.Channel, channel_id)
    if channel is not None:
        channel.name = data.name
        channel.color = data.color
        channel.funding_source_channel_id = data.funding_source_channel_id
        db.commit()
        db.refresh(channel)
    return channel


def delete_channel(db: Session, channel_id: int) -> None:
    channel = db.get(models.Channel, channel_id)
    if channel is None:
        return

    in_use = (
        db.query(models.PayoutPeriod).filter_by(receiving_channel_id=channel_id).first()
        or db.query(models.Expense).filter_by(channel_id=channel_id).first()
        or db.query(models.Transfer)
        .filter(
            or_(
                models.Transfer.from_channel_id == channel_id,
                models.Transfer.to_channel_id == channel_id,
            )
        )
        .first()
        or db.query(models.Channel).filter_by(funding_source_channel_id=channel_id).first()
    )
    if in_use is not None:
        raise ChannelInUseError(
            "This channel is still used by a payout period, expense, transfer, "
            "or another channel's funding source, and can't be deleted until those "
            "are removed or reassigned."
        )

    db.delete(channel)
    db.commit()


# --- Payout periods ----------------------------------------------------------


def list_payout_periods(db: Session) -> list[models.PayoutPeriod]:
    stmt = select(models.PayoutPeriod).order_by(models.PayoutPeriod.display_order)
    return list(db.scalars(stmt))


def create_payout_period(db: Session, data: schemas.PayoutPeriodCreate) -> models.PayoutPeriod:
    max_order = db.scalar(
        select(models.PayoutPeriod.display_order).order_by(models.PayoutPeriod.display_order.desc())
    )
    period = models.PayoutPeriod(
        label=data.label,
        income_amount=data.income_amount,
        receiving_channel_id=data.receiving_channel_id,
        display_order=(max_order or 0) + 1,
    )
    db.add(period)
    db.commit()
    db.refresh(period)
    return period


def update_payout_period(
    db: Session, payout_period_id: int, data: schemas.PayoutPeriodUpdate
) -> models.PayoutPeriod | None:
    period = db.get(models.PayoutPeriod, payout_period_id)
    if period is not None:
        period.income_amount = data.income_amount
        period.receiving_channel_id = data.receiving_channel_id
        db.commit()
        db.refresh(period)
    return period


def delete_payout_period(db: Session, payout_period_id: int) -> None:
    period = db.get(models.PayoutPeriod, payout_period_id)
    if period is not None:
        db.delete(period)
        db.commit()


# --- Expenses -----------------------------------------------------------------


def list_expenses(db: Session) -> list[models.Expense]:
    stmt = select(models.Expense).order_by(models.Expense.id)
    return list(db.scalars(stmt))


def create_expense(db: Session, data: schemas.ExpenseCreate) -> models.Expense:
    expense = models.Expense(**data.model_dump())
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


def delete_expense(db: Session, expense_id: int) -> None:
    expense = db.get(models.Expense, expense_id)
    if expense is not None:
        db.delete(expense)
        db.commit()


# --- Transfers ------------------------------------------------------------------


def list_transfers(db: Session, payout_period_id: int) -> list[models.Transfer]:
    stmt = (
        select(models.Transfer)
        .where(models.Transfer.payout_period_id == payout_period_id)
        .order_by(models.Transfer.id)
    )
    return list(db.scalars(stmt))


def create_transfer(db: Session, data: schemas.TransferCreate) -> models.Transfer:
    transfer = models.Transfer(**data.model_dump())
    db.add(transfer)
    db.commit()
    db.refresh(transfer)
    return transfer


def update_transfer(
    db: Session, transfer_id: int, data: schemas.TransferUpdate
) -> models.Transfer | None:
    transfer = db.get(models.Transfer, transfer_id)
    if transfer is not None:
        transfer.amount = data.amount
        db.commit()
        db.refresh(transfer)
    return transfer


def delete_transfer(db: Session, transfer_id: int) -> None:
    transfer = db.get(models.Transfer, transfer_id)
    if transfer is not None:
        db.delete(transfer)
        db.commit()


# --- Channel balances -----------------------------------------------------------


def channel_balances(db: Session, payout_period_id: int) -> list[tuple[models.Channel, float]]:
    payout_period = db.get(models.PayoutPeriod, payout_period_id)
    channels = list_channels(db)
    expenses = [e for e in list_expenses(db) if e.payout_period_id == payout_period_id]
    transfers = list_transfers(db, payout_period_id)

    balances = []
    for channel in channels:
        net = 0.0
        if payout_period is not None and payout_period.receiving_channel_id == channel.id:
            net += float(payout_period.income_amount)
        net += sum(float(t.amount) for t in transfers if t.to_channel_id == channel.id)
        net -= sum(float(t.amount) for t in transfers if t.from_channel_id == channel.id)
        net -= sum(float(e.amount) for e in expenses if e.channel_id == channel.id)
        balances.append((channel, net))
    return balances


def generate_transfers(db: Session, payout_period_id: int) -> dict[str, list[str]]:
    """Delete all transfers for this payout period and regenerate them from each
    channel's configured funding source. Each channel's required inflow is its
    own expense shortfall plus whatever it must forward to every channel that
    names it as a funding source (a pure pass-through channel with no expenses
    of its own can still need an inbound transfer this way). Returns the names
    of channels with an unmet shortfall and no funding source ("unfunded"), and
    channels caught in a circular funding loop ("circular")."""
    for transfer in list_transfers(db, payout_period_id):
        db.delete(transfer)

    payout_period = db.get(models.PayoutPeriod, payout_period_id)
    channels = list_channels(db)
    expenses = [e for e in list_expenses(db) if e.payout_period_id == payout_period_id]

    children: dict[int, list[models.Channel]] = {}
    for c in channels:
        if c.funding_source_channel_id is not None:
            children.setdefault(c.funding_source_channel_id, []).append(c)

    def own_shortfall(channel: models.Channel) -> float:
        expense_total = sum(float(e.amount) for e in expenses if e.channel_id == channel.id)
        income = (
            float(payout_period.income_amount)
            if payout_period is not None and payout_period.receiving_channel_id == channel.id
            else 0.0
        )
        return max(expense_total - income, 0.0)

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
            )
        )
    db.commit()
    return {
        "unfunded": unfunded,
        "circular": [c.name for c in channels if c.id in circular],
    }


# --- Assets ---------------------------------------------------------------


def list_assets(db: Session) -> list[models.Asset]:
    return list(db.scalars(select(models.Asset).order_by(models.Asset.id)))


def create_asset(db: Session, data: schemas.AssetCreate) -> models.Asset:
    asset = models.Asset(**data.model_dump())
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def update_asset(db: Session, asset_id: int, data: schemas.AssetUpdate) -> models.Asset | None:
    asset = db.get(models.Asset, asset_id)
    if asset is not None:
        asset.name = data.name
        asset.amount = data.amount
        db.commit()
        db.refresh(asset)
    return asset


def delete_asset(db: Session, asset_id: int) -> None:
    asset = db.get(models.Asset, asset_id)
    if asset is not None:
        db.delete(asset)
        db.commit()


def assets_page_data(db: Session) -> dict:
    assets = list_assets(db)
    return {"assets": assets, "total_assets": sum(float(a.amount) for a in assets)}


# --- Goals -----------------------------------------------------------------


def list_goals(db: Session) -> list[models.Goal]:
    return list(db.scalars(select(models.Goal).order_by(models.Goal.id)))


def create_goal(db: Session, data: schemas.GoalCreate) -> models.Goal:
    goal = models.Goal(**data.model_dump())
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def update_goal(db: Session, goal_id: int, data: schemas.GoalUpdate) -> models.Goal | None:
    goal = db.get(models.Goal, goal_id)
    if goal is not None:
        goal.name = data.name
        goal.target = data.target
        goal.allocated = data.allocated
        goal.months = data.months
        db.commit()
        db.refresh(goal)
    return goal


def delete_goal(db: Session, goal_id: int) -> None:
    goal = db.get(models.Goal, goal_id)
    if goal is not None:
        db.delete(goal)
        db.commit()


def goal_progress(goal: models.Goal) -> dict:
    remaining = max(float(goal.target) - float(goal.allocated), 0.0)
    pct = min(float(goal.allocated) / float(goal.target), 1.0) * 100 if goal.target else 0.0
    monthly_needed = float(goal.target) / goal.months if goal.months else 0.0
    return {"pct": pct, "monthly_needed": monthly_needed, "remaining": remaining}


def goals_page_data(db: Session) -> dict:
    goals = list_goals(db)
    return {"goals": [{"goal": g, **goal_progress(g)} for g in goals]}


# --- Credit lines -----------------------------------------------------------


def list_credit_lines(db: Session) -> list[models.CreditLine]:
    return list(db.scalars(select(models.CreditLine).order_by(models.CreditLine.id)))


def create_credit_line(db: Session, data: schemas.CreditLineCreate) -> models.CreditLine:
    credit_line = models.CreditLine(**data.model_dump())
    db.add(credit_line)
    db.commit()
    db.refresh(credit_line)
    return credit_line


def update_credit_line(
    db: Session, credit_line_id: int, data: schemas.CreditLineUpdate
) -> models.CreditLine | None:
    credit_line = db.get(models.CreditLine, credit_line_id)
    if credit_line is not None:
        credit_line.name = data.name
        credit_line.limit = data.limit
        credit_line.used = data.used
        credit_line.channel_id = data.channel_id
        db.commit()
        db.refresh(credit_line)
    return credit_line


def delete_credit_line(db: Session, credit_line_id: int) -> None:
    credit_line = db.get(models.CreditLine, credit_line_id)
    if credit_line is not None:
        db.delete(credit_line)
        db.commit()


def credit_utilization(credit_line: models.CreditLine) -> dict:
    pct = (
        (float(credit_line.used) / float(credit_line.limit) * 100) if credit_line.limit else 0.0
    )
    level = "red" if pct >= 100 else "amber" if pct >= 80 else "ok"
    return {"pct": pct, "level": level}


def credit_page_data(db: Session) -> dict:
    lines = list_credit_lines(db)
    return {
        "credit_lines": [{"line": c, **credit_utilization(c)} for c in lines],
        "channels": list_channels(db),
    }


# --- Composed view data -----------------------------------------------------


def overview_page_data(db: Session) -> dict:
    assets = list_assets(db)
    credit_lines = list_credit_lines(db)
    total_assets = sum(float(a.amount) for a in assets)
    total_liabilities = sum(float(c.used) for c in credit_lines)
    return {
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": total_assets - total_liabilities,
        "goals": [{"goal": g, **goal_progress(g)} for g in list_goals(db)],
        "credit_lines": [{"line": c, **credit_utilization(c)} for c in credit_lines],
    }


def expenses_page_data(db: Session) -> dict:
    payout_periods = list_payout_periods(db)
    return {
        "channels": list_channels(db),
        "payout_periods": payout_periods,
        "expenses": list_expenses(db),
        "payout_data": [
            {
                "period": period,
                "transfers": list_transfers(db, period.id),
                "balances": channel_balances(db, period.id),
            }
            for period in payout_periods
        ],
    }
