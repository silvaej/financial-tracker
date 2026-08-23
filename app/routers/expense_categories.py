from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.auth import get_current_user
from app.database import get_db
from app.templating import templates

router = APIRouter(prefix="/expense-categories", tags=["expense-categories"])


def _render_page(request: Request, db: Session, user_id: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "partials/expenses_page.html", crud.expenses_page_data(db, user_id)
    )


@router.post("")
def create_expense_category(
    request: Request,
    name: str = Form(...),
    color: str = Form("#8a8a8a"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    crud.create_expense_category(
        db, schemas.ExpenseCategoryCreate(name=name, color=color), current_user.id
    )
    return _render_page(request, db, current_user.id)


@router.patch("/{category_id}")
def update_expense_category(
    request: Request,
    category_id: int,
    name: str = Form(...),
    color: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    crud.update_expense_category(
        db, category_id, schemas.ExpenseCategoryUpdate(name=name, color=color), current_user.id
    )
    return _render_page(request, db, current_user.id)


@router.delete("/{category_id}")
def delete_expense_category(
    request: Request,
    category_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    try:
        crud.delete_expense_category(db, category_id, current_user.id)
    except crud.ExpenseCategoryInUseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _render_page(request, db, current_user.id)
