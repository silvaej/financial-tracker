from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/channels", tags=["channels"])
templates = Jinja2Templates(directory="app/templates")

ALLOWED_LOGO_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_LOGO_BYTES = 300 * 1024


def _render_page(request: Request, db: Session, user_id: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "partials/expenses_page.html", crud.expenses_page_data(db, user_id)
    )


async def _read_logo(logo: UploadFile | None) -> tuple[bytes, str] | None:
    if logo is None or not logo.filename:
        return None
    if logo.content_type not in ALLOWED_LOGO_TYPES:
        raise HTTPException(
            status_code=400, detail="Logo must be a PNG, JPEG, WEBP, or GIF image."
        )
    data = await logo.read()
    if not data:
        return None
    if len(data) > MAX_LOGO_BYTES:
        raise HTTPException(status_code=400, detail="Logo image must be under 300KB.")
    return data, logo.content_type


@router.post("")
async def create_channel(
    request: Request,
    name: str = Form(...),
    color: str = Form("#8a8a8a"),
    channel_type: str = Form(""),
    logo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    logo_payload = await _read_logo(logo)
    try:
        channel = crud.create_channel(
            db,
            schemas.ChannelCreate(name=name, color=color, channel_type=channel_type or None),
            current_user.id,
        )
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if logo_payload is not None:
        crud.set_channel_logo(db, channel.id, logo_payload[0], logo_payload[1], current_user.id)
    return _render_page(request, db, current_user.id)


@router.patch("/{channel_id}")
async def update_channel(
    request: Request,
    channel_id: int,
    name: str = Form(...),
    color: str = Form(...),
    channel_type: str = Form(""),
    logo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    logo_payload = await _read_logo(logo)
    crud.update_channel(
        db,
        channel_id,
        schemas.ChannelUpdate(name=name, color=color, channel_type=channel_type or None),
        current_user.id,
    )
    if logo_payload is not None:
        crud.set_channel_logo(db, channel_id, logo_payload[0], logo_payload[1], current_user.id)
    return _render_page(request, db, current_user.id)


@router.delete("/{channel_id}/logo")
def delete_channel_logo(
    request: Request,
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    crud.clear_channel_logo(db, channel_id, current_user.id)
    return _render_page(request, db, current_user.id)


@router.get("/{channel_id}/logo")
def get_channel_logo(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Response:
    channel = crud.get_channel_logo(db, channel_id, current_user.id)
    if channel is None or channel.logo_data is None or channel.logo_mimetype is None:
        raise HTTPException(status_code=404, detail="No logo for this channel.")
    return Response(
        content=channel.logo_data,
        media_type=channel.logo_mimetype,
        headers={"Cache-Control": "private, max-age=300"},
    )


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
