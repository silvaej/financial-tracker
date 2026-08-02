from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import crud, models
from app.auth import get_current_user
from app.database import get_db
from app.templating import templates

router = APIRouter(tags=["onboarding"])


@router.post("/onboarding/skip")
def skip_onboarding(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    crud.skip_onboarding(db, current_user)
    return templates.TemplateResponse(
        request, "partials/expenses_page.html", crud.expenses_page_data(db, current_user.id)
    )
