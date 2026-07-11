import bcrypt
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app import models
from app.database import get_db


class NotAuthenticated(Exception):
    """Raised when a route requires a logged-in user but the session has none."""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def get_current_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    user_id = request.session.get("user_id")
    user = db.get(models.User, user_id) if user_id is not None else None
    if user is None:
        raise NotAuthenticated()
    return user
