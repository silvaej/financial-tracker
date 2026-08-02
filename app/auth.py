import time

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app import models
from app.database import get_db

# Absolute cap on a session's lifetime since login, regardless of activity.
SESSION_ABSOLUTE_TIMEOUT_SECONDS = 60 * 60 * 24 * 7  # 7 days
# How long a session may sit idle before it's treated as expired. Not
# enforced at all for a "keep me signed in" session -- see start_session().
SESSION_IDLE_TIMEOUT_SECONDS = 60 * 30  # 30 minutes
# Absolute cap for a "keep me signed in" session instead of the default above.
KEEP_SIGNED_IN_ABSOLUTE_TIMEOUT_SECONDS = 60 * 60 * 24 * 30  # 30 days
# SessionMiddleware's max_age (app/main.py) needs to cover the *longest*
# possible session, since Starlette only supports one fixed cookie lifetime
# -- the shorter default/idle timeouts above are enforced ourselves, in
# get_current_user(), independently of how long the cookie itself survives.
SESSION_COOKIE_MAX_AGE_SECONDS = KEEP_SIGNED_IN_ABSOLUTE_TIMEOUT_SECONDS


class NotAuthenticated(Exception):
    """Raised when a route requires a logged-in user but the session has none."""


def start_session(request: Request, user_id: int, keep_signed_in: bool = False) -> None:
    now = time.time()
    request.session["user_id"] = user_id
    request.session["issued_at"] = now
    request.session["last_seen"] = now
    request.session["keep_signed_in"] = keep_signed_in


def get_current_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    user_id = request.session.get("user_id")
    issued_at = request.session.get("issued_at")
    last_seen = request.session.get("last_seen")
    keep_signed_in = request.session.get("keep_signed_in", False)
    now = time.time()

    absolute_timeout = (
        KEEP_SIGNED_IN_ABSOLUTE_TIMEOUT_SECONDS
        if keep_signed_in
        else SESSION_ABSOLUTE_TIMEOUT_SECONDS
    )
    expired = (
        user_id is None
        or issued_at is None
        or last_seen is None
        or now - issued_at > absolute_timeout
        or (not keep_signed_in and now - last_seen > SESSION_IDLE_TIMEOUT_SECONDS)
    )
    user = db.get(models.User, user_id) if not expired and user_id is not None else None
    if user is None:
        request.session.clear()
        raise NotAuthenticated()

    request.session["last_seen"] = now
    # Stashed for Jinja2Templates' context_processor (app/main.py) so every
    # template render gets `current_user` (e.g. the rail's avatar) without
    # threading it through each router's own render context.
    request.state.user = user
    return user
