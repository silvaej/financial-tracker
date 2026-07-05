from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas

# --- Channels ---------------------------------------------------------------


def list_channels(db: Session) -> list[models.Channel]:
    return list(db.scalars(select(models.Channel).order_by(models.Channel.name)))


def create_channel(db: Session, data: schemas.ChannelCreate) -> models.Channel:
    channel = models.Channel(name=data.name, color=data.color)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def update_channel(
    db: Session, channel_id: int, data: schemas.ChannelUpdate
) -> models.Channel | None:
    channel = db.get(models.Channel, channel_id)
    if channel is not None:
        channel.name = data.name
        channel.color = data.color
        db.commit()
        db.refresh(channel)
    return channel


def delete_channel(db: Session, channel_id: int) -> None:
    channel = db.get(models.Channel, channel_id)
    if channel is not None:
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


# --- Composed view data -----------------------------------------------------


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
