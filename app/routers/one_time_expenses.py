from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.auth import get_current_user
from app.database import get_db
from app.templating import templates

router = APIRouter(prefix="/one-time-expenses", tags=["one-time-expenses"])


def _render_page(request: Request, db: Session, user_id: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "partials/expenses_page.html", crud.expenses_page_data(db, user_id)
    )


def _parse_category_id(raw: str) -> int | None:
    return int(raw) if raw else None


@router.get("")
def index(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "partials/expenses_page.html",
        crud.expenses_page_data(db, current_user.id, one_time_expense_q=q),
    )


@router.post("")
def create_one_time_expense(
    request: Request,
    name: str = Form(...),
    amount: float = Form(...),
    cycle_id: int = Form(...),
    channel_id: int = Form(...),
    category_id: str = Form(""),
    date: date = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    try:
        crud.create_one_time_expense(
            db,
            schemas.OneTimeExpenseCreate(
                name=name,
                amount=amount,
                cycle_id=cycle_id,
                channel_id=channel_id,
                category_id=_parse_category_id(category_id),
                date=date,
            ),
            current_user.id,
        )
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _render_page(request, db, current_user.id)


@router.patch("/{expense_id}")
def update_one_time_expense(
    request: Request,
    expense_id: int,
    name: str = Form(...),
    amount: float = Form(...),
    cycle_id: int = Form(...),
    channel_id: int = Form(...),
    category_id: str = Form(""),
    date: date = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    try:
        crud.update_one_time_expense(
            db,
            expense_id,
            schemas.OneTimeExpenseUpdate(
                name=name,
                amount=amount,
                cycle_id=cycle_id,
                channel_id=channel_id,
                category_id=_parse_category_id(category_id),
                date=date,
            ),
            current_user.id,
        )
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _render_page(request, db, current_user.id)


@router.delete("/{expense_id}")
def delete_one_time_expense(
    request: Request,
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    crud.delete_one_time_expense(db, expense_id, current_user.id)
    return _render_page(request, db, current_user.id)


@router.post("/clear")
def clear_one_time_expenses(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    crud.clear_one_time_expenses(db, current_user.id)
    return _render_page(request, db, current_user.id)
