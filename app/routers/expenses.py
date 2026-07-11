from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/expenses", tags=["expenses"])
templates = Jinja2Templates(directory="app/templates")


def _render_page(request: Request, db: Session, user_id: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "partials/expenses_page.html", crud.expenses_page_data(db, user_id)
    )


@router.get("")
def index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    template = (
        "partials/expenses_page.html" if request.headers.get("HX-Request") else "expenses.html"
    )
    return templates.TemplateResponse(
        request, template, crud.expenses_page_data(db, current_user.id)
    )


@router.post("")
def create_expense(
    request: Request,
    name: str = Form(...),
    amount: float = Form(...),
    payout_period_id: int = Form(...),
    channel_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    try:
        crud.create_expense(
            db,
            schemas.ExpenseCreate(
                name=name, amount=amount, payout_period_id=payout_period_id, channel_id=channel_id
            ),
            current_user.id,
        )
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _render_page(request, db, current_user.id)


@router.delete("/{expense_id}")
def delete_expense(
    request: Request,
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    crud.delete_expense(db, expense_id, current_user.id)
    return _render_page(request, db, current_user.id)
