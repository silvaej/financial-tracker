from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/transfers", tags=["transfers"])
templates = Jinja2Templates(directory="app/templates")


def _render_page(request: Request, db: Session) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "partials/expenses_page.html", crud.expenses_page_data(db)
    )


@router.post("")
def create_transfer(
    request: Request,
    payout_period_id: int = Form(...),
    from_channel_id: int = Form(...),
    to_channel_id: int = Form(...),
    amount: float = Form(...),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    crud.create_transfer(
        db,
        schemas.TransferCreate(
            payout_period_id=payout_period_id,
            from_channel_id=from_channel_id,
            to_channel_id=to_channel_id,
            amount=amount,
        ),
    )
    return _render_page(request, db)


@router.patch("/{transfer_id}")
def update_transfer(
    request: Request, transfer_id: int, amount: float = Form(...), db: Session = Depends(get_db)
) -> HTMLResponse:
    crud.update_transfer(db, transfer_id, schemas.TransferUpdate(amount=amount))
    return _render_page(request, db)


@router.delete("/{transfer_id}")
def delete_transfer(
    request: Request, transfer_id: int, db: Session = Depends(get_db)
) -> HTMLResponse:
    crud.delete_transfer(db, transfer_id)
    return _render_page(request, db)
