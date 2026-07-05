from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/payout-periods", tags=["payout-periods"])
templates = Jinja2Templates(directory="app/templates")


def _render_page(request: Request, db: Session) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "partials/expenses_page.html", crud.expenses_page_data(db)
    )


def _parse_channel_id(raw: str) -> int | None:
    return int(raw) if raw else None


@router.post("")
def create_payout_period(
    request: Request,
    label: str = Form(...),
    income_amount: float = Form(0),
    receiving_channel_id: str = Form(""),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    crud.create_payout_period(
        db,
        schemas.PayoutPeriodCreate(
            label=label,
            income_amount=income_amount,
            receiving_channel_id=_parse_channel_id(receiving_channel_id),
        ),
    )
    return _render_page(request, db)


@router.patch("/{payout_period_id}")
def update_payout_period(
    request: Request,
    payout_period_id: int,
    income_amount: float = Form(...),
    receiving_channel_id: str = Form(""),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    crud.update_payout_period(
        db,
        payout_period_id,
        schemas.PayoutPeriodUpdate(
            income_amount=income_amount,
            receiving_channel_id=_parse_channel_id(receiving_channel_id),
        ),
    )
    return _render_page(request, db)


@router.delete("/{payout_period_id}")
def delete_payout_period(
    request: Request, payout_period_id: int, db: Session = Depends(get_db)
) -> HTMLResponse:
    crud.delete_payout_period(db, payout_period_id)
    return _render_page(request, db)
