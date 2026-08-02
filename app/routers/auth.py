import logging

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import crud, models
from app.auth import get_current_user
from app.database import get_db
from app.image_uploads import read_image_upload
from app.templating import templates

router = APIRouter(tags=["auth"])
logger = logging.getLogger("app.auth")

MAX_AVATAR_BYTES = 300 * 1024


@router.get("/login")
def login_form(request: Request) -> Response:
    if request.session.get("user_id") is not None:
        return RedirectResponse(url="/", status_code=303)
    error = request.query_params.get("oauth_error")
    return templates.TemplateResponse(request, "login.html", {"error": error} if error else {})


def _key_check_context(db: Session, invite_key: str) -> dict[str, object]:
    invite_key = invite_key.strip()
    key_valid = False
    key_error = None
    if invite_key:
        if crud.get_active_signup_key(db, invite_key) is not None:
            key_valid = True
        else:
            key_error = "That invite key is invalid or has expired."
    return {"invite_key": invite_key, "key_valid": key_valid, "key_error": key_error}


@router.get("/signup")
def signup_form(request: Request, invite_key: str = "", db: Session = Depends(get_db)) -> Response:
    if request.session.get("user_id") is not None:
        return RedirectResponse(url="/", status_code=303)
    error = request.query_params.get("oauth_error")
    # Lets an operator hand someone a pre-filled link (/signup?invite_key=...)
    # instead of the key itself -- pre-fills and pre-validates the field the
    # same way blurring it would.
    context = _key_check_context(db, invite_key)
    if error:
        context["error"] = error
    return templates.TemplateResponse(request, "signup.html", context)


@router.get("/signup/check-key")
def check_signup_key(
    request: Request, invite_key: str = "", db: Session = Depends(get_db)
) -> Response:
    return templates.TemplateResponse(
        request, "partials/signup_key_section.html", _key_check_context(db, invite_key)
    )


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
