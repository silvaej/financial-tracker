import json
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
    channel = models.Channel(
        name=data.name,
        color=data.color,
        channel_type=data.channel_type,
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
    )
    if in_use is not None:
        raise ChannelInUseError(
            "This channel is still used by a payout period, expense, transfer, "
            "or goal contribution, and can't be deleted until those are removed "
            "or reassigned."
        )

    db.query(models.ChannelPlacement).filter_by(channel_id=channel_id, user_id=user_id).delete()
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
    db: Session, payout_period_id: int, data: schemas.CanvasSaveIn, user_id: int
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


def channel_presets_by_group() -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = {}
    for preset in CHANNEL_PRESETS:
        groups.setdefault(preset["group"], []).append(preset)
    return groups


def expenses_page_data(db: Session, user_id: int) -> dict:
    return {
        "channels": list_channels(db, user_id),
        "channel_types": CHANNEL_TYPES,
        "channel_preset_groups": channel_presets_by_group(),
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
    goal_entries: list[dict[str, Any]] = [
        {"goal": g, "per_payout": goal_payout_amount(g, payout_period_count)} for g in goals
    ]
    payout_data = []
    for period in payout_periods:
        expenses = [e for e in all_expenses if e.payout_period_id == period.id]
        transfers = _order_transfers(channels, list_transfers(db, period.id, user_id))
        goal_contributions = list_goal_contributions(db, period.id, user_id)
        balances = channel_balances(db, period.id, user_id)
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
                            t.to_channel_id, expenses, goals, payout_period_count
                        ),
                    }
                    for t in transfers
                ],
                "goal_contributions": goal_contributions,
                "balances": balances,
                "balance_by_channel": {c.id: net for c, net in balances},
                "contributed_by_goal": contributed_by_goal,
                "carry_in": _carry_in_for_period(db, period.id, user_id),
                "warnings": cashflow_warnings(db, period.id, user_id),
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
    }
