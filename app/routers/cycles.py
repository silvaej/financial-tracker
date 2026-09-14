from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.auth import get_current_user
from app.database import get_db
from app.templating import templates

router = APIRouter(prefix="/cycles", tags=["cycles"])


def _render_page(request: Request, db: Session, user_id: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "partials/expenses_page.html", crud.expenses_page_data(db, user_id)
    )


def _parse_channel_id(raw: str) -> int | None:
    return int(raw) if raw else None


@router.post("")
def create_cycle(
    request: Request,
    income_amount: float = Form(0),
    receiving_channel_id: str = Form(""),
    payout_day: int = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    try:
        crud.create_cycle(
            db,
            schemas.CycleCreate(
                income_amount=income_amount,
                receiving_channel_id=_parse_channel_id(receiving_channel_id),
                payout_day=payout_day,
            ),
            current_user.id,
        )
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except crud.CycleCapExceededError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except crud.CycleDuplicatePayoutDayError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _render_page(request, db, current_user.id)


@router.patch("/count")
def update_cycles_per_month(
    request: Request,
    cycles_per_month: int = Form(..., ge=1),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    crud.update_cycles_per_month(db, current_user, cycles_per_month)
    return _render_page(request, db, current_user.id)


@router.patch("/{cycle_id}")
def update_cycle(
    request: Request,
    cycle_id: int,
    income_amount: float = Form(...),
    receiving_channel_id: str = Form(""),
    payout_day: int = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    try:
        crud.update_cycle(
            db,
            cycle_id,
            schemas.CycleUpdate(
                income_amount=income_amount,
                receiving_channel_id=_parse_channel_id(receiving_channel_id),
                payout_day=payout_day,
            ),
            current_user.id,
        )
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except crud.CycleDuplicatePayoutDayError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _render_page(request, db, current_user.id)


@router.delete("/{cycle_id}")
def delete_cycle(
    request: Request,
    cycle_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    try:
        crud.delete_cycle(db, cycle_id, current_user.id)
    except crud.CycleInUseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _render_page(request, db, current_user.id)
