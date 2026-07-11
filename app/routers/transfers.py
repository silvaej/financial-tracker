import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/transfers", tags=["transfers"])
templates = Jinja2Templates(directory="app/templates")


def _render_page(request: Request, db: Session, user_id: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "partials/cashflow_page.html", crud.cashflow_page_data(db, user_id)
    )


@router.post("")
def create_transfer(
    request: Request,
    payout_period_id: int = Form(...),
    from_channel_id: int = Form(...),
    to_channel_id: int = Form(...),
    amount: float = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    try:
        crud.create_transfer(
            db,
            schemas.TransferCreate(
                payout_period_id=payout_period_id,
                from_channel_id=from_channel_id,
                to_channel_id=to_channel_id,
                amount=amount,
            ),
            current_user.id,
        )
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _render_page(request, db, current_user.id)


@router.patch("/{transfer_id}")
def update_transfer(
    request: Request,
    transfer_id: int,
    amount: float = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    crud.update_transfer(db, transfer_id, schemas.TransferUpdate(amount=amount), current_user.id)
    return _render_page(request, db, current_user.id)


@router.delete("/{transfer_id}")
def delete_transfer(
    request: Request,
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    crud.delete_transfer(db, transfer_id, current_user.id)
    return _render_page(request, db, current_user.id)


@router.post("/generate/{payout_period_id}")
def generate_transfers(
    request: Request,
    payout_period_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    result = crud.generate_transfers(db, payout_period_id, current_user.id)
    messages = []
    if result["unfunded"]:
        messages.append("No funding source configured for: " + ", ".join(result["unfunded"]))
    if result["circular"]:
        messages.append("Circular funding detected, skipped: " + ", ".join(result["circular"]))
    response = _render_page(request, db, current_user.id)
    if messages:
        response.headers["HX-Trigger"] = json.dumps({"showAlert": " ".join(messages)})
    return response
