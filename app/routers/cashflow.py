from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db

router = APIRouter(prefix="/cashflow", tags=["cashflow"])
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(request, "cashflow.html", crud.cashflow_page_data(db))
