from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import crud, models, schemas


def _is_empty(db: Session, model: type[Any], user_id: int) -> bool:
    return db.scalar(select(func.count()).select_from(model).where(model.user_id == user_id)) == 0


def _seed_channels(db: Session, user_id: int) -> None:
    crud.create_channel(
        db,
        schemas.ChannelCreate(name="BPI Payroll", channel_type="Traditional Bank", color="#2f6d4f"),
        user_id,
    )
    crud.create_channel(
        db,
        schemas.ChannelCreate(name="BPI Savings", channel_type="Traditional Bank", color="#3a6ea5"),
        user_id,
    )
    crud.create_channel(
        db, schemas.ChannelCreate(name="GCash", channel_type="E-Wallet", color="#1e88e5"), user_id
    )
    crud.create_channel(
        db, schemas.ChannelCreate(name="Maya", channel_type="E-Wallet", color="#5a4fa0"), user_id
    )
    crud.create_channel(
        db,
        schemas.ChannelCreate(name="UnionBank UNO", channel_type="Digital Bank", color="#d97b29"),
        user_id,
    )
    crud.create_channel(
        db,
        schemas.ChannelCreate(
            name="CIMB Time Deposit", channel_type="Time Deposit", color="#8a8a8a"
        ),
        user_id,
    )
    crud.create_channel(
        db,
        schemas.ChannelCreate(
            name="PayMongo Payouts", channel_type="Payment Gateway", color="#0ea5a5"
        ),
        user_id,
    )
    crud.create_channel(
        db, schemas.ChannelCreate(name="Cash Wallet", channel_type="Cash", color="#7c8a63"), user_id
    )

    crud.create_channel(
        db,
        schemas.ChannelCreate(name="BPI Credit Card", channel_type="Credit Card", color="#a83f28"),
        user_id,
    )
    crud.create_channel(
        db,
        schemas.ChannelCreate(name="RCBC Credit Card", channel_type="Credit Card", color="#c2410c"),
        user_id,
    )


def _channels_by_name(db: Session, user_id: int) -> dict[str, models.Channel]:
    return {c.name: c for c in crud.list_channels(db, user_id)}


def _seed_payout_periods(db: Session, channels: dict[str, models.Channel], user_id: int) -> None:
    payroll = channels.get("BPI Payroll")
    gateway = channels.get("PayMongo Payouts")
    if payroll is None or gateway is None:
        return
    crud.create_payout_period(
        db,
        schemas.PayoutPeriodCreate(
            label="15th", income_amount=32000, receiving_channel_id=payroll.id
        ),
        user_id,
    )
    crud.create_payout_period(
        db,
        schemas.PayoutPeriodCreate(
            label="30th", income_amount=32000, receiving_channel_id=payroll.id
        ),
        user_id,
    )
    crud.create_payout_period(
        db,
        schemas.PayoutPeriodCreate(
            label="Freelance Payout", income_amount=18000, receiving_channel_id=gateway.id
        ),
        user_id,
    )


def _periods_by_label(db: Session, user_id: int) -> dict[str, models.PayoutPeriod]:
    return {p.label: p for p in crud.list_payout_periods(db, user_id)}


def _goals_by_name(db: Session, user_id: int) -> dict[str, models.Goal]:
    return {g.name: g for g in crud.list_goals(db, user_id)}


def _seed_expenses(
    db: Session,
    channels: dict[str, models.Channel],
    periods: dict[str, models.PayoutPeriod],
    user_id: int,
) -> None:
    payroll, gcash, maya, unionbank, rcbc_cc = (
        channels.get("BPI Payroll"),
        channels.get("GCash"),
        channels.get("Maya"),
        channels.get("UnionBank UNO"),
        channels.get("RCBC Credit Card"),
    )
    p15, p30, freelance = periods.get("15th"), periods.get("30th"), periods.get("Freelance Payout")
    if (
        payroll is None
        or gcash is None
        or maya is None
        or unionbank is None
        or rcbc_cc is None
        or p15 is None
        or p30 is None
        or freelance is None
    ):
        return

    def expense(
        name: str, amount: float, period: models.PayoutPeriod, channel: models.Channel
    ) -> None:
        crud.create_expense(
            db,
            schemas.ExpenseCreate(
                name=name, amount=amount, payout_period_id=period.id, channel_id=channel.id
            ),
            user_id,
        )

    expense("Rent", 12000, p15, payroll)
    expense("Electricity", 2200, p15, payroll)
    expense("Water", 450, p15, payroll)
    expense("Car Amortization", 8500, p15, payroll)
    expense("Internet", 1699, p15, gcash)
    # Deliberately larger than what gets transferred into this card this
    # period, so it goes negative and trips the "channel is short" warning.
    expense("Card Annual Fee", 600, p15, rcbc_cc)

    expense("Groceries", 6000, p30, gcash)
    expense("Phone Plan", 999, p30, gcash)
    expense("Gym Membership", 1500, p30, gcash)
    expense("Insurance Premium", 3200, p30, payroll)
    expense("Streaming Subscriptions", 799, p30, maya)

    expense("Tax Reserve", 3600, freelance, unionbank)
    expense("Software Subscriptions", 2200, freelance, unionbank)


def _seed_goals(db: Session, channels: dict[str, models.Channel], user_id: int) -> None:
    savings, maya, timedeposit = (
        channels.get("BPI Savings"),
        channels.get("Maya"),
        channels.get("CIMB Time Deposit"),
    )
    if savings is None or maya is None or timedeposit is None:
        return
    crud.create_goal(
        db,
        schemas.GoalCreate(
            name="Emergency Fund",
            target=150000,
            months=12,
            channel_id=savings.id,
            round_up_to_hundred=True,
        ),
        user_id,
    )
    crud.create_goal(
        db,
        schemas.GoalCreate(
            name="Wedding Fund",
            target=400000,
            months=24,
            channel_id=savings.id,
            round_up_to_hundred=True,
        ),
        user_id,
    )
    crud.create_goal(
        db,
        schemas.GoalCreate(
            name="Vacation Fund",
            target=60000,
            months=8,
            channel_id=maya.id,
            round_up_to_hundred=True,
        ),
        user_id,
    )
    # Not rounded up, and deliberately underfunded below -- shows the
    # "isn't fully funded this payout" warning on the canvas.
    crud.create_goal(
        db,
        schemas.GoalCreate(name="New Laptop", target=70000, months=10, channel_id=timedeposit.id),
        user_id,
    )


# Per-period transfer graph: (from channel name, to channel name, amount).
# Multi-hop chains (Payroll -> Savings -> Time Deposit, Gateway -> UnionBank
# -> Savings/Cash) and funding-source pass-throughs (GCash/Maya -> their
# credit cards) exercise the canvas's shortest-path routing and the
# balance/warning rollups the same way real usage would.
_TRANSFERS_BY_PERIOD: dict[str, list[tuple[str, str, float]]] = {
    "15th": [
        ("BPI Payroll", "GCash", 5000),
        ("BPI Payroll", "BPI Savings", 3000),
        ("BPI Savings", "CIMB Time Deposit", 1500),
        ("GCash", "BPI Credit Card", 2000),
        ("BPI Payroll", "Maya", 1000),
        ("Maya", "RCBC Credit Card", 500),
    ],
    "30th": [
        ("BPI Payroll", "GCash", 9000),
        ("BPI Payroll", "BPI Savings", 3000),
        ("BPI Savings", "CIMB Time Deposit", 1500),
        ("GCash", "BPI Credit Card", 2500),
        ("BPI Payroll", "Maya", 1200),
        ("Maya", "RCBC Credit Card", 400),
    ],
    "Freelance Payout": [
        ("PayMongo Payouts", "UnionBank UNO", 12000),
        ("UnionBank UNO", "BPI Savings", 3000),
        ("UnionBank UNO", "Cash Wallet", 1000),
    ],
}

# Per-period goal contributions: (channel name, goal name, amount). Vacation
# Fund is fed from two different channels in two different periods, and
# Emergency Fund/Wedding Fund share a channel -- both common real patterns.
_CONTRIBUTIONS_BY_PERIOD: dict[str, list[tuple[str, str, float]]] = {
    "15th": [
        ("BPI Savings", "Emergency Fund", 2000),
        ("Maya", "Vacation Fund", 800),
        ("CIMB Time Deposit", "New Laptop", 1000),
    ],
    "30th": [
        ("BPI Savings", "Emergency Fund", 2000),
        ("BPI Savings", "Wedding Fund", 500),
        ("Maya", "Vacation Fund", 800),
        ("CIMB Time Deposit", "New Laptop", 1000),
    ],
    "Freelance Payout": [
        ("UnionBank UNO", "Vacation Fund", 1500),
    ],
}


def _seed_canvas(
    db: Session,
    channels: dict[str, models.Channel],
    periods: dict[str, models.PayoutPeriod],
    goals: dict[str, models.Goal],
    user_id: int,
) -> None:
    for label, period in periods.items():
        transfer_specs = _TRANSFERS_BY_PERIOD.get(label, [])
        contribution_specs = _CONTRIBUTIONS_BY_PERIOD.get(label, [])
        if not (transfer_specs or contribution_specs):
            continue

        transfers = [
            schemas.CanvasTransferIn(
                from_channel_id=channels[from_name].id,
                to_channel_id=channels[to_name].id,
                amount=amount,
            )
            for from_name, to_name, amount in transfer_specs
            if from_name in channels and to_name in channels
        ]
        contributions = [
            schemas.CanvasGoalContributionIn(
                channel_id=channels[channel_name].id, goal_id=goals[goal_name].id, amount=amount
            )
            for channel_name, goal_name, amount in contribution_specs
            if channel_name in channels and goal_name in goals
        ]

        channel_ids = (
            {t.from_channel_id for t in transfers}
            | {t.to_channel_id for t in transfers}
            | {c.channel_id for c in contributions}
        )
        goal_ids = {c.goal_id for c in contributions}

        error = crud.save_canvas(
            db,
            period.id,
            schemas.CanvasSaveIn(
                channel_placements=[
                    schemas.CanvasChannelPlacementIn(channel_id=cid, x=0, y=0)
                    for cid in channel_ids
                ],
                goal_placements=[
                    schemas.CanvasGoalPlacementIn(goal_id=gid, x=0, y=0) for gid in goal_ids
                ],
                transfers=transfers,
                goal_contributions=contributions,
            ),
            user_id,
        )
        if error:
            raise RuntimeError(f"seed canvas failed for payout period {label!r}: {error}")


def _seed_credit_lines(db: Session, channels: dict[str, models.Channel], user_id: int) -> None:
    bpi_cc, rcbc_cc = channels.get("BPI Credit Card"), channels.get("RCBC Credit Card")
    if not (bpi_cc and rcbc_cc):
        return
    crud.create_credit_line(
        db,
        schemas.CreditLineCreate(
            name="BPI Credit Card", limit=100000, used=42000, channel_id=bpi_cc.id
        ),
        user_id,
    )
    # Near its limit, to show what a tight credit line looks like.
    crud.create_credit_line(
        db,
        schemas.CreditLineCreate(
            name="RCBC Credit Card", limit=60000, used=57500, channel_id=rcbc_cc.id
        ),
        user_id,
    )


def _seed_assets(db: Session, channels: dict[str, models.Channel], user_id: int) -> None:
    timedeposit = channels.get("CIMB Time Deposit")
    crud.create_asset(
        db, schemas.AssetCreate(name="Stock Portfolio (COL Financial)", amount=85000), user_id
    )
    crud.create_asset(db, schemas.AssetCreate(name="Crypto Wallet", amount=15000), user_id)
    if timedeposit is not None:
        crud.create_asset(
            db,
            schemas.AssetCreate(
                name="Time Deposit Balance", amount=120000, channel_id=timedeposit.id
            ),
            user_id,
        )


def seed_if_empty(db: Session, user_id: int) -> None:
    """Insert sample staging data into whichever of this user's tables are currently empty.

    Safe to call repeatedly: already-populated tables are left untouched, so it won't
    clobber real/edited data, but a newly added empty table still gets seeded.
    """
    if _is_empty(db, models.Channel, user_id):
        _seed_channels(db, user_id)
    channels = _channels_by_name(db, user_id)

    if _is_empty(db, models.PayoutPeriod, user_id):
        _seed_payout_periods(db, channels, user_id)
    periods = _periods_by_label(db, user_id)

    if _is_empty(db, models.Expense, user_id):
        _seed_expenses(db, channels, periods, user_id)

    if _is_empty(db, models.Goal, user_id):
        _seed_goals(db, channels, user_id)
    goals = _goals_by_name(db, user_id)

    if _is_empty(db, models.Transfer, user_id):
        _seed_canvas(db, channels, periods, goals, user_id)

    if _is_empty(db, models.CreditLine, user_id):
        _seed_credit_lines(db, channels, user_id)
    if _is_empty(db, models.Asset, user_id):
        _seed_assets(db, channels, user_id)


if __name__ == "__main__":
    from app.database import SessionLocal

    session = SessionLocal()
    try:
        first_user = session.scalar(select(models.User).order_by(models.User.id))
        if first_user is not None:
            seed_if_empty(session, first_user.id)
    finally:
        session.close()
