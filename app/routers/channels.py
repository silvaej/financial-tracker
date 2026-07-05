from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/channels", tags=["channels"])
templates = Jinja2Templates(directory="app/templates")


def _render_page(request: Request, db: Session) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "partials/expenses_page.html", crud.expenses_page_data(db)
    )


@router.post("")
def create_channel(
    request: Request,
    name: str = Form(...),
    color: str = Form("#8a8a8a"),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    crud.create_channel(db, schemas.ChannelCreate(name=name, color=color))
    return _render_page(request, db)


@router.patch("/{channel_id}")
def update_channel(
    request: Request,
    channel_id: int,
    name: str = Form(...),
    color: str = Form(...),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    crud.update_channel(db, channel_id, schemas.ChannelUpdate(name=name, color=color))
    return _render_page(request, db)


@router.delete("/{channel_id}")
def delete_channel(
    request: Request, channel_id: int, db: Session = Depends(get_db)
) -> HTMLResponse:
    crud.delete_channel(db, channel_id)
    return _render_page(request, db)
