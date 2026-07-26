import logging
import math
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud
from app.auth import start_session, verify_password
from app.database import get_db

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("app.auth")


@router.get("/login")
def login_form(request: Request) -> Response:
    if request.session.get("user_id") is not None:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
) -> Response:
    user = crud.get_user_by_email(db, email)
    locked_until = user.locked_until if user is not None else None
    if locked_until is not None and locked_until.tzinfo is None:
        # SQLite (used in tests) doesn't persist tzinfo on DateTime(timezone=True) columns.
        locked_until = locked_until.replace(tzinfo=UTC)

    if locked_until is not None and locked_until > datetime.now(UTC):
        logger.warning("Login blocked for locked-out account %r from %s", email, request.client)
        remaining_minutes = max(
            1, math.ceil((locked_until - datetime.now(UTC)).total_seconds() / 60)
        )
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": f"Too many failed attempts. Try again in {remaining_minutes} minute"
                f"{'s' if remaining_minutes != 1 else ''}."
            },
            status_code=429,
        )

    if user is None or not verify_password(password, user.hashed_password):
        if user is not None:
            crud.register_failed_login(db, user)
            logger.warning("Failed login for %r from %s", email, request.client)
        return templates.TemplateResponse(
            request, "login.html", {"error": "Invalid email or password."}, status_code=401
        )
    crud.register_successful_login(db, user)
    start_session(request, user.id)
    return RedirectResponse(url="/", status_code=303)


@router.post("/logout")
def logout(request: Request) -> Response:
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
