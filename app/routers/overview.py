from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import crud, models
from app.auth import get_current_user
from app.database import get_db
from app.templating import templates

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("")
def index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    template = (
        "partials/overview_page.html" if request.headers.get("HX-Request") else "overview.html"
    )
    return templates.TemplateResponse(
        request, template, crud.overview_page_data(db, current_user.id)
    )
