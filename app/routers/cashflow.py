from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/cashflow", tags=["cashflow"])
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    template = (
        "partials/cashflow_page.html" if request.headers.get("HX-Request") else "cashflow.html"
    )
    return templates.TemplateResponse(
        request, template, crud.cashflow_page_data(db, current_user.id)
    )


@router.post("/{payout_period_id}/save")
def save_canvas(
    request: Request,
    payout_period_id: int,
    data: schemas.CanvasSaveIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    try:
        error = crud.save_canvas(db, payout_period_id, data, current_user.id)
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if error is not None:
        raise HTTPException(status_code=422, detail=error)
    return templates.TemplateResponse(
        request, "partials/cashflow_page.html", crud.cashflow_page_data(db, current_user.id)
    )


@router.post("/{payout_period_id}/preview")
def preview_canvas(
    payout_period_id: int,
    data: schemas.CanvasSaveIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> schemas.CanvasPreviewOut:
    try:
        return crud.preview_canvas(db, payout_period_id, data, current_user.id)
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
