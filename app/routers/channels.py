from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/channels", tags=["channels"])
templates = Jinja2Templates(directory="app/templates")


def _render_page(request: Request, db: Session, user_id: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "partials/expenses_page.html", crud.expenses_page_data(db, user_id)
    )


def _parse_channel_id(raw: str) -> int | None:
    return int(raw) if raw else None


@router.post("")
def create_channel(
    request: Request,
    name: str = Form(...),
    color: str = Form("#8a8a8a"),
    channel_type: str = Form(""),
    funding_source_channel_id: str = Form(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    try:
        crud.create_channel(
            db,
            schemas.ChannelCreate(
                name=name,
                color=color,
                channel_type=channel_type or None,
                funding_source_channel_id=_parse_channel_id(funding_source_channel_id),
            ),
            current_user.id,
        )
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _render_page(request, db, current_user.id)


@router.patch("/{channel_id}")
def update_channel(
    request: Request,
    channel_id: int,
    name: str = Form(...),
    color: str = Form(...),
    channel_type: str = Form(""),
    funding_source_channel_id: str = Form(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    try:
        crud.update_channel(
            db,
            channel_id,
            schemas.ChannelUpdate(
                name=name,
                color=color,
                channel_type=channel_type or None,
                funding_source_channel_id=_parse_channel_id(funding_source_channel_id),
            ),
            current_user.id,
        )
    except (crud.InvalidFundingSourceError, crud.OwnershipError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _render_page(request, db, current_user.id)


@router.post("/{channel_id}/placement")
def create_channel_placement(
    request: Request,
    channel_id: int,
    payout_period_id: int = Form(...),
    x: float = Form(...),
    y: float = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    try:
        crud.place_channel(db, payout_period_id, channel_id, x, y, current_user.id)
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request, "partials/cashflow_page.html", crud.cashflow_page_data(db, current_user.id)
    )


@router.patch("/{channel_id}/placement")
def update_channel_placement(
    channel_id: int,
    data: schemas.PlacementUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Response:
    crud.place_channel(db, data.payout_period_id, channel_id, data.x, data.y, current_user.id)
    return Response(status_code=204)


@router.delete("/{channel_id}/placement")
def delete_channel_placement(
    request: Request,
    channel_id: int,
    payout_period_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    crud.remove_channel_placement(db, payout_period_id, channel_id, current_user.id)
    return templates.TemplateResponse(
        request, "partials/cashflow_page.html", crud.cashflow_page_data(db, current_user.id)
    )


@router.delete("/{channel_id}")
def delete_channel(
    request: Request,
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    try:
        crud.delete_channel(db, channel_id, current_user.id)
    except crud.ChannelInUseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _render_page(request, db, current_user.id)
