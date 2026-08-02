from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
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
) -> Response:
    if crud.needs_onboarding(db, current_user):
        # htmx (rail nav's hx-boost) won't follow a normal redirect for a
        # boosted request -- it swaps the redirect target's HTML into the
        # page as-is -- so a genuine client-side redirect needs HX-Redirect
        # instead. Same pattern as main.py's NotAuthenticated handler.
        if request.headers.get("HX-Request") == "true":
            return Response(status_code=200, headers={"HX-Redirect": "/expenses"})
        return RedirectResponse(url="/expenses", status_code=303)

    template = (
        "partials/overview_page.html" if request.headers.get("HX-Request") else "overview.html"
    )
    return templates.TemplateResponse(
        request, template, crud.overview_page_data(db, current_user.id)
    )
