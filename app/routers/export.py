import csv
from io import StringIO

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app import crud, models
from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/export", tags=["export"])


def _csv_response(rows: list[list[object]], header: list[str], filename: str) -> Response:
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/channels.csv")
def export_channels(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Response:
    channels = crud.list_channels(db, current_user.id)
    rows: list[list[object]] = [[c.name, c.color, c.channel_type or ""] for c in channels]
    return _csv_response(rows, ["Name", "Color", "Type"], "channels.csv")


@router.get("/payout-periods.csv")
def export_payout_periods(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Response:
    periods = crud.list_payout_periods(db, current_user.id)
    rows = [
        [
            p.label,
            p.income_amount,
            p.receiving_channel.name if p.receiving_channel else "",
        ]
        for p in periods
    ]
    return _csv_response(
        rows, ["Label", "Income Amount", "Receiving Channel"], "payout-periods.csv"
    )


@router.get("/expenses.csv")
def export_expenses(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Response:
    expenses = crud.list_expenses(db, current_user.id)
    rows = [[e.name, e.amount, e.payout_period.label, e.channel.name] for e in expenses]
    return _csv_response(rows, ["Name", "Amount", "Payout Period", "Channel"], "expenses.csv")


@router.get("/transfers.csv")
def export_transfers(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Response:
    transfers = crud.list_all_transfers(db, current_user.id)
    rows = [
        [t.payout_period.label, t.from_channel.name, t.to_channel.name, t.amount] for t in transfers
    ]
    return _csv_response(
        rows, ["Payout Period", "From Channel", "To Channel", "Amount"], "transfers.csv"
    )
