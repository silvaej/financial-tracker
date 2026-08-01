import time

import bcrypt
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app import models
from app.database import get_db

# Absolute cap on a session's lifetime since login, regardless of activity.
# Also passed as SessionMiddleware's max_age in app/main.py.
SESSION_ABSOLUTE_TIMEOUT_SECONDS = 60 * 60 * 24 * 7  # 7 days
# How long a session may sit idle before it's treated as expired.
SESSION_IDLE_TIMEOUT_SECONDS = 60 * 30  # 30 minutes


class NotAuthenticated(Exception):
    """Raised when a route requires a logged-in user but the session has none."""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def start_session(request: Request, user_id: int) -> None:
    now = time.time()
    request.session["user_id"] = user_id
    request.session["issued_at"] = now
    request.session["last_seen"] = now


def get_current_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    user_id = request.session.get("user_id")
    issued_at = request.session.get("issued_at")
    last_seen = request.session.get("last_seen")
    now = time.time()

    expired = (
        user_id is None
        or issued_at is None
        or last_seen is None
        or now - issued_at > SESSION_ABSOLUTE_TIMEOUT_SECONDS
        or now - last_seen > SESSION_IDLE_TIMEOUT_SECONDS
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
