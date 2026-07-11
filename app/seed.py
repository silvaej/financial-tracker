from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import crud, models, schemas


def _is_empty(db: Session, model: type) -> bool:
    return db.scalar(select(func.count()).select_from(model)) == 0


def _seed_channels(db: Session) -> None:
    crud.create_channel(
        db, schemas.ChannelCreate(name="BPI Checking", channel_type="Traditional Bank")
    )
    crud.create_channel(db, schemas.ChannelCreate(name="GCash", channel_type="E-Wallet"))
    crud.create_channel(db, schemas.ChannelCreate(name="Maya", channel_type="E-Wallet"))
    crud.create_channel(
        db, schemas.ChannelCreate(name="BPI Credit Card", channel_type="Credit Card")
    )


def _channels_by_name(db: Session) -> dict[str, models.Channel]:
    return {c.name: c for c in crud.list_channels(db)}


def _seed_payout_periods(db: Session, channels: dict[str, models.Channel]) -> None:
    checking = channels.get("BPI Checking")
    if checking is None:
        return
    crud.create_payout_period(
        db,
        schemas.PayoutPeriodCreate(
            label="15th", income_amount=25000, receiving_channel_id=checking.id
        ),
    )
    crud.create_payout_period(
        db,
        schemas.PayoutPeriodCreate(
            label="30th", income_amount=25000, receiving_channel_id=checking.id
        ),
    )


def _periods_by_label(db: Session) -> dict[str, models.PayoutPeriod]:
    return {p.label: p for p in crud.list_payout_periods(db)}


def _seed_expenses(
    db: Session, channels: dict[str, models.Channel], periods: dict[str, models.PayoutPeriod]
) -> None:
    checking, gcash = channels.get("BPI Checking"), channels.get("GCash")
    period_15, period_30 = periods.get("15th"), periods.get("30th")
    if not (checking and gcash and period_15 and period_30):
        return
    crud.create_expense(
        db,
        schemas.ExpenseCreate(
            name="Rent", amount=12000, payout_period_id=period_15.id, channel_id=checking.id
        ),
    )
    crud.create_expense(
        db,
        schemas.ExpenseCreate(
            name="Electricity", amount=2500, payout_period_id=period_15.id, channel_id=checking.id
        ),
    )
    crud.create_expense(
        db,
        schemas.ExpenseCreate(
            name="Streaming subscription",
            amount=549,
            payout_period_id=period_30.id,
            channel_id=gcash.id,
        ),
    )


def _seed_transfers(
    db: Session, channels: dict[str, models.Channel], periods: dict[str, models.PayoutPeriod]
) -> None:
    checking, gcash, maya = (
        channels.get("BPI Checking"),
        channels.get("GCash"),
        channels.get("Maya"),
    )
    period_15, period_30 = periods.get("15th"), periods.get("30th")
    if not (checking and gcash and maya and period_15 and period_30):
        return
    crud.create_transfer(
        db,
        schemas.TransferCreate(
            payout_period_id=period_15.id,
            from_channel_id=checking.id,
            to_channel_id=gcash.id,
            amount=3000,
        ),
    )
    crud.create_transfer(
        db,
        schemas.TransferCreate(
            payout_period_id=period_30.id,
            from_channel_id=checking.id,
            to_channel_id=maya.id,
            amount=2000,
        ),
    )


def _seed_goals(db: Session, channels: dict[str, models.Channel]) -> None:
    maya = channels.get("Maya")
    if maya is None:
        return
    crud.create_goal(
        db,
        schemas.GoalCreate(
            name="Emergency Fund",
            target=50000,
            allocated=10000,
            months=6,
            channel_id=maya.id,
            round_up_to_hundred=True,
        ),
    )


def _seed_credit_lines(db: Session, channels: dict[str, models.Channel]) -> None:
    credit_card = channels.get("BPI Credit Card")
    if credit_card is None:
        return
    crud.create_credit_line(
        db,
        schemas.CreditLineCreate(
            name="BPI Credit Card", limit=50000, used=12000, channel_id=credit_card.id
        ),
    )


def _seed_assets(db: Session, channels: dict[str, models.Channel]) -> None:
    maya = channels.get("Maya")
    if maya is None:
        return
    crud.create_asset(
        db, schemas.AssetCreate(name="Digital Bank Savings", amount=20000, channel_id=maya.id)
    )


def seed_if_empty(db: Session) -> None:
    """Insert sample staging data into whichever of the tables below are currently empty.

    Safe to call repeatedly: already-populated tables are left untouched, so it won't
    clobber real/edited staging data, but a newly added empty table still gets seeded.
    """
    if _is_empty(db, models.Channel):
        _seed_channels(db)
    channels = _channels_by_name(db)

    if _is_empty(db, models.PayoutPeriod):
        _seed_payout_periods(db, channels)
    periods = _periods_by_label(db)

    if _is_empty(db, models.Expense):
        _seed_expenses(db, channels, periods)
    if _is_empty(db, models.Transfer):
        _seed_transfers(db, channels, periods)
    if _is_empty(db, models.Goal):
        _seed_goals(db, channels)
    if _is_empty(db, models.CreditLine):
        _seed_credit_lines(db, channels)
    if _is_empty(db, models.Asset):
        _seed_assets(db, channels)


if __name__ == "__main__":
    from app.database import SessionLocal

    session = SessionLocal()
    try:
        seed_if_empty(session)
    finally:
        session.close()
