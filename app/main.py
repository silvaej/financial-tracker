from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app import models
from app.auth import NotAuthenticated, get_current_user
from app.config import settings
from app.database import get_db
from app.routers import (
    assets,
    auth,
    cashflow,
    channels,
    credit,
    expenses,
    goals,
    overview,
    payout_periods,
    transfers,
)

app = FastAPI(title="Finance Tracker")

app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, session_cookie="ft_session")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.exception_handler(NotAuthenticated)
def not_authenticated_handler(request: Request, exc: NotAuthenticated) -> Response:
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=200, headers={"HX-Redirect": "/login"})
    return RedirectResponse(url="/login", status_code=303)


app.include_router(auth.router)
app.include_router(channels.router)
app.include_router(payout_periods.router)
app.include_router(expenses.router)
app.include_router(transfers.router)
app.include_router(assets.router)
app.include_router(goals.router)
app.include_router(credit.router)
app.include_router(overview.router)
app.include_router(cashflow.router)

PLACEHOLDER_SECTIONS: dict[str, str] = {}


@app.get("/")
def index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    return overview.index(request, db, current_user)


@app.get("/{section}")
def placeholder(request: Request, section: str) -> HTMLResponse:
    title = PLACEHOLDER_SECTIONS.get(section)
    if title is None:
        return templates.TemplateResponse(
            request, "placeholder.html", {"title": "Not found"}, status_code=404
        )
    return templates.TemplateResponse(request, "placeholder.html", {"title": title})
