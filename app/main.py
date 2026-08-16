import os
from collections.abc import Awaitable, Callable

from fastapi import Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app import models
from app.auth import SESSION_COOKIE_MAX_AGE_SECONDS, NotAuthenticated, get_current_user
from app.config import settings
from app.csrf import csrf_protect
from app.database import get_db
from app.rate_limit import limiter
from app.routers import (
    admin,
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
    payout_cycles,
    payout_periods,
    transfers,
)
from app.templating import templates

app = FastAPI(title="Finance Tracker", dependencies=[Depends(csrf_protect)])
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

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

# CSP audited against this app's actual resource usage (see #73): htmx from
# unpkg, the compiled Tailwind stylesheet + Google Fonts, and same-origin
# everything else (channel logos/avatars are served through app routes, not
# data: URIs). 'unsafe-inline' on script-src/style-src is a real, deliberate
# gap, not an oversight -- the app relies throughout on inline onclick/
# onchange/oninput handlers and a few inline style="width: {{ pct }}%"
# attributes (progress bars, dynamic channel colors) that would need a
# larger template refactor (nonces don't cover inline *event handler*
# attributes at all) to remove. Still meaningfully restricts remote script/
# object/frame sources and exfiltration paths even with that gap.
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://unpkg.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


@app.middleware("http")
async def security_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = _CSP
    if os.environ.get("VERCEL") == "1":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.exception_handler(NotAuthenticated)
def not_authenticated_handler(request: Request, exc: NotAuthenticated) -> Response:
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=200, headers={"HX-Redirect": "/login"})
    return RedirectResponse(url="/login", status_code=303)


@app.exception_handler(RateLimitExceeded)
def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    # slowapi's own default handler responds with {"error": ...}, not
    # {"detail": ...} -- base.html's global htmx:responseError listener does
    # `alertMessage.textContent = data.detail` for every error path in this
    # app (see ValidationError/OwnershipError/ChannelInUseError below/
    # elsewhere), so a mismatched key would render as "undefined" instead of
    # a real message on a rate-limited htmx request (e.g. /signup/check-key,
    # triggered live as the user types an invite key).
    return JSONResponse(
        status_code=429, content={"detail": "Too many requests. Please wait and try again."}
    )


@app.exception_handler(ValidationError)
def schema_validation_error_handler(request: Request, exc: ValidationError) -> Response:
    # Routers build app/schemas.py models by hand from individually-parsed
    # Form(...) fields (see CLAUDE.md's "Optional FK form fields" note) rather
    # than declaring the schema itself as a FastAPI request-body dependency,
    # so FastAPI's own automatic RequestValidationError -> 422 handling never
    # kicks in for a gt=0/min_length violation raised inside a route body --
    # without this handler it would surface as an unhandled 500 instead.
    #
    # `detail` must be a plain string, not FastAPI's default list-of-dicts
    # shape: base.html's global `htmx:responseError` listener does
    # `alertMessage.textContent = data.detail` for every error path in this
    # app (see OwnershipError -> 404, ChannelInUseError -> 409, both plain
    # strings) -- assigning an array there would render as "[object Object]".
    message = "; ".join(f"{err['loc'][-1]}: {err['msg']}" for err in exc.errors())
    return JSONResponse(status_code=422, content=jsonable_encoder({"detail": message}))


app.include_router(auth.router)
app.include_router(oauth.router)
app.include_router(channels.router)
app.include_router(payout_periods.router)
app.include_router(payout_cycles.router)
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
app.include_router(admin.router)

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
