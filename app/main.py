import os

from fastapi import Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app import models
from app.auth import SESSION_COOKIE_MAX_AGE_SECONDS, NotAuthenticated, get_current_user
from app.config import settings
from app.csrf import csrf_protect
from app.database import get_db
from app.routers import (
    assets,
    auth,
    cashflow,
    channels,
    credit,
    expenses,
    export,
    goal_contributions,
    goals,
    oauth,
    onboarding,
    overview,
    payout_periods,
    transfers,
)
from app.templating import templates

app = FastAPI(title="Finance Tracker", dependencies=[Depends(csrf_protect)])

# Vercel sets VERCEL=1 on every deployed invocation (production and preview);
# it's unset locally (Docker/Compose), which still runs over plain http.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="ft_session",
    max_age=SESSION_COOKIE_MAX_AGE_SECONDS,
    # "strict" would drop this cookie on the redirect an OAuth provider sends
    # back to /auth/<provider>/callback (a cross-site top-level navigation),
    # breaking authlib's state/nonce check every time -- "lax" is still sent
    # on top-level GET redirects but not cross-site subresource/form
    # requests, and app/csrf.py's own token check doesn't rely on SameSite
    # anyway, so this doesn't weaken CSRF protection.
    same_site="lax",
    https_only=os.environ.get("VERCEL") == "1",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.exception_handler(NotAuthenticated)
def not_authenticated_handler(request: Request, exc: NotAuthenticated) -> Response:
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=200, headers={"HX-Redirect": "/login"})
    return RedirectResponse(url="/login", status_code=303)


@app.exception_handler(ValidationError)
def schema_validation_error_handler(request: Request, exc: ValidationError) -> Response:
    # Routers build app/schemas.py models by hand from individually-parsed
    # Form(...) fields (see CLAUDE.md's "Optional FK form fields" note) rather
    # than declaring the schema itself as a FastAPI request-body dependency,
    # so FastAPI's own automatic RequestValidationError -> 422 handling never
    # kicks in for a gt=0/min_length violation raised inside a route body --
    # without this handler it would surface as an unhandled 500 instead.
    # Mirrors FastAPI's default RequestValidationError response shape.
    return JSONResponse(status_code=422, content=jsonable_encoder({"detail": exc.errors()}))


app.include_router(auth.router)
app.include_router(oauth.router)
app.include_router(channels.router)
app.include_router(payout_periods.router)
app.include_router(expenses.router)
app.include_router(transfers.router)
app.include_router(goal_contributions.router)
app.include_router(assets.router)
app.include_router(goals.router)
app.include_router(credit.router)
app.include_router(overview.router)
app.include_router(cashflow.router)
app.include_router(export.router)
app.include_router(onboarding.router)

PLACEHOLDER_SECTIONS: dict[str, str] = {}


@app.get("/health")
def health(db: Session = Depends(get_db)) -> JSONResponse:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse({"status": "error"}, status_code=503)
    return JSONResponse({"status": "ok"})


@app.get("/")
def index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Response:
    return overview.index(request, db, current_user)


@app.get("/{section}")
def placeholder(request: Request, section: str) -> HTMLResponse:
    title = PLACEHOLDER_SECTIONS.get(section)
    if title is None:
        return templates.TemplateResponse(
            request, "placeholder.html", {"title": "Not found"}, status_code=404
        )
    return templates.TemplateResponse(request, "placeholder.html", {"title": title})
