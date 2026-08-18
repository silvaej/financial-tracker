from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import crud, models
from app.auth import get_current_user
from app.database import get_db
from app.templating import templates

router = APIRouter(prefix="/payout-periods/{payout_period_id}/cycles", tags=["payout-cycles"])


def _render_page(
    request: Request, db: Session, payout_period_id: int, user_id: int, cycle_id: int | None
) -> HTMLResponse:
    try:
        context = crud.payout_cycle_history_page_data(db, payout_period_id, user_id, cycle_id)
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    template = (
        "partials/payout_cycle_history_page.html"
        if request.headers.get("HX-Request")
        else "payout_cycle_history.html"
    )
    return templates.TemplateResponse(request, template, context)


@router.get("")
def index(
    request: Request,
    payout_period_id: int,
    cycle_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    return _render_page(request, db, payout_period_id, current_user.id, cycle_id)


@router.post("")
def close_cycle(
    request: Request,
    payout_period_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    try:
        crud.close_payout_cycle(db, payout_period_id, current_user.id)
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _render_page(request, db, payout_period_id, current_user.id, cycle_id=None)
