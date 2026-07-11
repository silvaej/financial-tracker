from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud, models
from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/cashflow", tags=["cashflow"])
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    template = (
        "partials/cashflow_page.html" if request.headers.get("HX-Request") else "cashflow.html"
    )
    return templates.TemplateResponse(
        request, template, crud.cashflow_page_data(db, current_user.id)
    )
