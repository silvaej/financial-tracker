from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/expenses", tags=["expenses"])
templates = Jinja2Templates(directory="app/templates")


def _render_page(request: Request, db: Session) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "partials/expenses_page.html", crud.expenses_page_data(db)
    )


@router.post("")
def create_expense(
    request: Request,
    name: str = Form(...),
    amount: float = Form(...),
    payout_period_id: int = Form(...),
    channel_id: int = Form(...),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    crud.create_expense(
        db,
        schemas.ExpenseCreate(
            name=name, amount=amount, payout_period_id=payout_period_id, channel_id=channel_id
        ),
    )
    return _render_page(request, db)


@router.delete("/{expense_id}")
def delete_expense(
    request: Request, expense_id: int, db: Session = Depends(get_db)
) -> HTMLResponse:
    crud.delete_expense(db, expense_id)
    return _render_page(request, db)
