from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/assets", tags=["assets"])
templates = Jinja2Templates(directory="app/templates")


def _render_page(request: Request, db: Session, user_id: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "partials/assets_page.html", crud.assets_page_data(db, user_id)
    )


def _parse_channel_id(raw: str) -> int | None:
    return int(raw) if raw else None


@router.get("")
def index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    template = "partials/assets_page.html" if request.headers.get("HX-Request") else "assets.html"
    return templates.TemplateResponse(request, template, crud.assets_page_data(db, current_user.id))


@router.post("")
def create_asset(
    request: Request,
    name: str = Form(...),
    amount: float = Form(...),
    channel_id: str = Form(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    try:
        crud.create_asset(
            db,
            schemas.AssetCreate(name=name, amount=amount, channel_id=_parse_channel_id(channel_id)),
            current_user.id,
        )
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _render_page(request, db, current_user.id)


@router.patch("/{asset_id}")
def update_asset(
    request: Request,
    asset_id: int,
    name: str = Form(...),
    amount: float = Form(...),
    channel_id: str = Form(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    try:
        crud.update_asset(
            db,
            asset_id,
            schemas.AssetUpdate(name=name, amount=amount, channel_id=_parse_channel_id(channel_id)),
            current_user.id,
        )
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _render_page(request, db, current_user.id)


@router.delete("/{asset_id}")
def delete_asset(
    request: Request,
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    crud.delete_asset(db, asset_id, current_user.id)
    return _render_page(request, db, current_user.id)
