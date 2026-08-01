import logging
import math
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import crud, models
from app.auth import get_current_user, hash_password, start_session, verify_password
from app.database import get_db
from app.image_uploads import read_image_upload
from app.manage_users import MIN_PASSWORD_LENGTH
from app.templating import templates

router = APIRouter(tags=["auth"])
logger = logging.getLogger("app.auth")

MAX_AVATAR_BYTES = 300 * 1024


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


def _account_context(**extra: object) -> dict[str, object]:
    return {
        "currency_options": crud.CURRENCY_OPTIONS,
        "timezone_options": crud.TIMEZONE_OPTIONS,
        **extra,
    }


def _account_response(
    request: Request, context: dict[str, object], status_code: int = 200
) -> Response:
    template = "partials/account_page.html" if request.headers.get("HX-Request") else "account.html"
    return templates.TemplateResponse(request, template, context, status_code=status_code)


@router.get("/account")
def account_form(
    request: Request, current_user: models.User = Depends(get_current_user)
) -> Response:
    return _account_response(request, _account_context())


@router.post("/account/password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Response:
    if not verify_password(current_password, current_user.hashed_password):
        return _account_response(
            request,
            _account_context(password_error="Current password is incorrect."),
            status_code=401,
        )
    if new_password != confirm_password:
        return _account_response(
            request,
            _account_context(password_error="New passwords don't match."),
            status_code=400,
        )
    if len(new_password) < MIN_PASSWORD_LENGTH:
        return _account_response(
            request,
            _account_context(
                password_error=f"New password must be at least {MIN_PASSWORD_LENGTH} "
                "characters long.",
            ),
            status_code=400,
        )
    crud.update_password(db, current_user, hash_password(new_password))
    return _account_response(request, _account_context(password_success=True))


@router.post("/account/profile")
def update_profile(
    request: Request,
    display_name: str = Form(""),
    currency_code: str = Form(...),
    timezone: str = Form(""),
    notify_cash_flow_warnings: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Response:
    if currency_code not in crud.CURRENCY_CODES:
        return _account_response(
            request,
            _account_context(profile_error="Please choose a valid currency."),
            status_code=400,
        )
    timezone = timezone.strip()
    if timezone and timezone not in crud.TIMEZONE_OPTIONS:
        return _account_response(
            request,
            _account_context(profile_error="Please choose a valid timezone."),
            status_code=400,
        )
    crud.update_profile(
        db,
        current_user,
        display_name=display_name.strip()[:100] or None,
        currency_code=currency_code,
        timezone=timezone or None,
        notify_cash_flow_warnings=notify_cash_flow_warnings,
    )
    return _account_response(request, _account_context(profile_success=True))


@router.post("/account/avatar")
async def upload_avatar(
    request: Request,
    avatar: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Response:
    payload = await read_image_upload(avatar, max_bytes=MAX_AVATAR_BYTES, label="Avatar")
    if payload is None:
        return _account_response(
            request,
            _account_context(profile_error="Please choose an image to upload."),
            status_code=400,
        )
    crud.set_avatar(db, current_user, payload[0], payload[1])
    return _account_response(request, _account_context(profile_success=True))


@router.delete("/account/avatar")
def delete_avatar(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Response:
    crud.clear_avatar(db, current_user)
    return _account_response(request, _account_context(profile_success=True))


@router.get("/account/avatar")
def get_avatar(current_user: models.User = Depends(get_current_user)) -> Response:
    if current_user.avatar_data is None or current_user.avatar_mimetype is None:
        raise HTTPException(status_code=404, detail="No avatar set.")
    return Response(
        content=current_user.avatar_data,
        media_type=current_user.avatar_mimetype,
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )
