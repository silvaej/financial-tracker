import logging
from urllib.parse import urlencode

from authlib.integrations.base_client import OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import crud
from app.auth import start_session
from app.database import get_db
from app.oauth import fetch_identity, oauth
from app.rate_limit import limiter

router = APIRouter(tags=["oauth"])
logger = logging.getLogger("app.oauth")

_PROVIDERS = ("google", "github")


def _redirect_with_error(path: str, message: str) -> Response:
    query = urlencode({"oauth_error": message})
    return RedirectResponse(url=f"{path}?{query}", status_code=303)


_INTENTS = ("login", "signup")


@router.get("/auth/{provider}/start")
@limiter.limit("10/minute")
async def oauth_start(
    provider: str,
    request: Request,
    invite_key: str = "",
    keep_signed_in: bool = False,
    intent: str = "login",
) -> Response:
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=404)
    # Stashed in the session so it survives the round-trip to the provider
    # and back -- see oauth_callback() below. `intent` records which page
    # (login.html/signup.html) the button was clicked from, via a hidden
    # form field -- it's what lets the callback tell "log in" apart from
    # "sign up with an account that turns out to already exist".
    request.session["pending_invite_key"] = invite_key.strip()
    request.session["pending_keep_signed_in"] = keep_signed_in
    request.session["pending_intent"] = intent if intent in _INTENTS else "login"
    redirect_uri = str(request.url_for("oauth_callback", provider=provider))
    client = oauth.create_client(provider)
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/auth/{provider}/callback")
@limiter.limit("10/minute")
async def oauth_callback(
    provider: str, request: Request, db: Session = Depends(get_db)
) -> Response:
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=404)

    pending_invite_key = request.session.pop("pending_invite_key", "")
    pending_keep_signed_in = bool(request.session.pop("pending_keep_signed_in", False))
    pending_intent = request.session.pop("pending_intent", "login")
    fallback_path = "/signup" if pending_intent == "signup" else "/login"

    client = oauth.create_client(provider)
    try:
        token = await client.authorize_access_token(request)
    except OAuthError:
        logger.warning("OAuth error during %s callback", provider, exc_info=True)
        return _redirect_with_error(fallback_path, "Sign-in was cancelled or failed.")

    provider_user_id, email = await fetch_identity(provider, client, token)
    if email is None:
        return _redirect_with_error(
            fallback_path,
            f"Your {provider.capitalize()} account has no verified email we can use.",
        )

    already_has_account_error = _redirect_with_error(
        "/login", "You already have an account with that email — log in instead."
    )

    identity = crud.get_oauth_identity(db, provider, provider_user_id)
    if identity is not None:
        if pending_intent == "signup":
            return already_has_account_error
        user = identity.user
    else:
        existing_user = crud.get_user_by_email(db, email)
        if existing_user is not None:
            if pending_intent == "signup":
                return already_has_account_error
            user = existing_user
            crud.create_oauth_identity(db, user, provider, provider_user_id, email)
        else:
            if not pending_invite_key:
                return _redirect_with_error(
                    "/signup", "No account found for that email. Enter your invite key first."
                )
            signup_key = crud.get_active_signup_key(db, pending_invite_key)
            if signup_key is None:
                return _redirect_with_error("/signup", "That invite key is invalid or has expired.")
            user = crud.create_user(db, email)
            crud.redeem_signup_key(db, signup_key)
            logger.info("New account created via signup key: %r", email)
            crud.create_oauth_identity(db, user, provider, provider_user_id, email)

    start_session(request, user.id, keep_signed_in=pending_keep_signed_in)
    return RedirectResponse(url="/", status_code=303)
