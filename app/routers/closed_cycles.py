from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import crud, models
from app.auth import get_current_user
from app.database import get_db
from app.templating import templates

router = APIRouter(prefix="/cycles/{cycle_id}/history", tags=["closed-cycles"])


def _render_page(
    request: Request, db: Session, cycle_id: int, user_id: int, closed_cycle_id: int | None
) -> HTMLResponse:
    try:
        context = crud.closed_cycle_history_page_data(db, cycle_id, user_id, closed_cycle_id)
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    template = (
        "partials/closed_cycle_history_page.html"
        if request.headers.get("HX-Request")
        else "closed_cycle_history.html"
    )
    return templates.TemplateResponse(request, template, context)


@router.get("")
def index(
    request: Request,
    cycle_id: int,
    closed_cycle_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    return _render_page(request, db, cycle_id, current_user.id, closed_cycle_id)


@router.post("")
def close_cycle(
    request: Request,
    cycle_id: int,
    request_id: str = Form(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    try:
        crud.close_cycle(db, cycle_id, current_user.id, request_id or None)
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _render_page(request, db, cycle_id, current_user.id, closed_cycle_id=None)
